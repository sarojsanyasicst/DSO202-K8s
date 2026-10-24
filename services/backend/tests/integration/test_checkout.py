"""Checkout, idempotent retries, and order reads against PostgreSQL through the HTTP API.

A successful checkout charges stock, creates the order, writes one outbox event,
and empties the cart in one transaction. Anything that fails leaves all of them
unchanged.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx2 import Response
from sqlalchemy.exc import DBAPIError, IntegrityError

from cloudcart.db import Database
from cloudcart.orders.service import checkout
from cloudcart.seed import seed_database
from helpers import Browser, OpenClient, run_sql, start_guest

# TEST-ONLY instructor password.
ADMIN_PASSWORD = "checkout-test-instructor-password"
ORDERS_URL = "/api/v1/orders"
ORDER_FIELDS = {"id", "status", "publication_pending", "total_cents", "created_at", "receipt_available", "items"}


def new_key() -> str:
    return f"checkout-{uuid4()}"


def add(browser: Browser, product_id: UUID, quantity: int) -> dict:
    """Set a cart line and return the updated cart."""
    response = browser.send("PUT", f"/api/v1/cart/items/{product_id}", {"quantity": quantity}, browser.csrf_token)
    assert response.status_code == 200, response.text
    return response.json()


def check_out(browser: Browser, cart_version: object, outcome: object = "approved", key: str | None = None) -> Response:
    headers = {} if key is None else {"Idempotency-Key": key}
    body = {"cart_version": cart_version, "payment_outcome": outcome}
    return browser.send("POST", ORDERS_URL, body, browser.csrf_token, **headers)


def stock_of(database: Database, product_id: UUID) -> int:
    [(stock,)] = run_sql(database, "SELECT stock FROM products WHERE id = :id", id=product_id)
    return stock


def durable_state(database: Database) -> dict[str, list]:
    """Every row checkout may create or change."""
    return {
        "orders": run_sql(database, "SELECT id, guest_id, status, total_cents FROM orders ORDER BY id"),
        "order_items": run_sql(
            database, "SELECT order_id, product_id, quantity, unit_price_cents FROM order_items ORDER BY 1, 2"
        ),
        "outbox_events": run_sql(database, "SELECT id, order_id, published_at FROM outbox_events ORDER BY id"),
        "stock": run_sql(database, "SELECT id, stock FROM products ORDER BY id"),
        "carts": run_sql(database, "SELECT id, version FROM carts ORDER BY id"),
        "cart_items": run_sql(database, "SELECT cart_id, product_id, quantity FROM cart_items ORDER BY 1, 2"),
    }


@pytest.fixture
def products(database: Database) -> dict[str, tuple[UUID, int, int]]:
    """Seed the catalog; return (id, price_cents, stock) by SKU."""
    with database.session_scope() as session:
        seed_database(session, ADMIN_PASSWORD)
    rows = run_sql(database, "SELECT sku, id, price_cents, stock FROM products")
    return {sku: (product_id, price, stock) for sku, product_id, price, stock in rows}


@pytest.fixture
def shopper(open_client: OpenClient, products: dict) -> Browser:
    return start_guest(open_client())


@pytest.fixture
def mug(products: dict) -> UUID:
    return products["kube-mug"][0]


@pytest.fixture
def hoodie(products: dict) -> UUID:
    return products["pod-hoodie"][0]


# --- Successful checkout -----------------------------------------------------------------------


def test_checkout_creates_one_order_and_outbox_event_and_charges_stock_once(
    shopper: Browser, database: Database, products: dict, mug: UUID, hoodie: UUID
) -> None:
    _, mug_price, mug_stock = products["kube-mug"]
    _, hoodie_price, hoodie_stock = products["pod-hoodie"]
    add(shopper, mug, 2)
    cart = add(shopper, hoodie, 1)
    key = new_key()

    response = check_out(shopper, cart["version"], key=key)

    assert response.status_code == 201, response.text
    order = response.json()
    assert set(order) == ORDER_FIELDS
    assert response.headers["location"] == f"{ORDERS_URL}/{order['id']}"
    assert (order["status"], order["publication_pending"], order["receipt_available"]) == ("accepted", True, False)
    assert order["total_cents"] == 2 * mug_price + hoodie_price
    created_at = datetime.fromisoformat(order["created_at"])
    assert created_at.utcoffset() == timedelta(0)
    assert abs(created_at - datetime.now(UTC)) < timedelta(minutes=1)
    assert sorted((item["product_id"], item["quantity"], item["unit_price_cents"]) for item in order["items"]) == sorted(
        [(str(mug), 2, mug_price), (str(hoodie), 1, hoodie_price)]
    )
    assert {item["name"] for item in order["items"]} == {"Kubernetes Mug", "Pod Hoodie"}

    order_id = UUID(order["id"])
    assert run_sql(database, "SELECT id, status, total_cents, idempotency_key FROM orders") == [
        (order_id, "accepted", order["total_cents"], key)
    ]
    assert run_sql(database, "SELECT order_id, published_at FROM outbox_events") == [(order_id, None)]
    assert stock_of(database, mug) == mug_stock - 2
    assert stock_of(database, hoodie) == hoodie_stock - 1
    # Emptying the cart is a change, so its version moves on.
    emptied = shopper.send("GET", "/api/v1/cart").json()
    assert (emptied["id"], emptied["items"], emptied["total_cents"]) == (cart["id"], [], 0)
    assert emptied["version"] == cart["version"] + 1


def test_checkout_charges_current_server_side_prices_and_keeps_them_on_the_order(
    shopper: Browser, database: Database, mug: UUID
) -> None:
    cart = add(shopper, mug, 3)
    run_sql(database, "UPDATE products SET price_cents = 1000 WHERE id = :id", id=mug)

    response = check_out(shopper, cart["version"], key=new_key())

    assert response.status_code == 201, response.text
    order = response.json()
    assert order["total_cents"] == 3000
    assert [(item["quantity"], item["unit_price_cents"]) for item in order["items"]] == [(3, 1000)]
    # Later price changes do not touch an accepted order.
    run_sql(database, "UPDATE products SET price_cents = 5000 WHERE id = :id", id=mug)
    assert shopper.send("GET", f"{ORDERS_URL}/{order['id']}").json()["total_cents"] == 3000


# --- Idempotency --------------------------------------------------------------------------------


def test_retry_with_the_same_key_and_body_returns_the_same_order_without_charging_again(
    shopper: Browser, database: Database, mug: UUID, hoodie: UUID
) -> None:
    cart = add(shopper, mug, 2)
    key = new_key()
    first = check_out(shopper, cart["version"], key=key)
    assert first.status_code == 201, first.text
    after_first = durable_state(database)

    replay = check_out(shopper, cart["version"], key=key)

    assert replay.status_code == 200, replay.text
    assert replay.json() == first.json()
    assert durable_state(database) == after_first
    # The key keeps naming that order even after the guest fills the cart again.
    add(shopper, hoodie, 1)
    again = check_out(shopper, cart["version"], key=key)
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert run_sql(database, "SELECT count(*) FROM orders") == [(1,)]


@pytest.mark.parametrize(
    "change", [{"outcome": "declined"}, {"version_offset": 1}], ids=["other-payment-outcome", "other-cart-version"]
)
def test_reusing_a_key_with_a_different_body_conflicts(
    shopper: Browser, database: Database, mug: UUID, change: dict
) -> None:
    cart = add(shopper, mug, 1)
    key = new_key()
    assert check_out(shopper, cart["version"], key=key).status_code == 201
    before = durable_state(database)

    response = check_out(
        shopper, cart["version"] + change.get("version_offset", 0), change.get("outcome", "approved"), key=key
    )

    assert response.status_code == 409
    assert "idempotency-key" in response.json()["detail"].lower()
    assert durable_state(database) == before


def test_idempotency_keys_belong_to_one_guest(open_client: OpenClient, database: Database, mug: UUID) -> None:
    alice, bob = start_guest(open_client()), start_guest(open_client())
    key = new_key()
    alice_order = check_out(alice, add(alice, mug, 1)["version"], key=key)

    bob_order = check_out(bob, add(bob, mug, 2)["version"], key=key)

    assert (alice_order.status_code, bob_order.status_code) == (201, 201)
    assert alice_order.json()["id"] != bob_order.json()["id"]
    assert run_sql(database, "SELECT count(*) FROM orders WHERE idempotency_key = :key", key=key) == [(2,)]


# --- Rejected checkouts change nothing ----------------------------------------------------------


def test_stale_cart_version_conflicts(shopper: Browser, database: Database, mug: UUID) -> None:
    first_view = add(shopper, mug, 1)
    current = add(shopper, mug, 2)
    before = durable_state(database)

    for version in (first_view["version"], current["version"] + 1, 0):
        response = check_out(shopper, version, key=new_key())
        assert response.status_code == 409, version
        assert "cart" in response.json()["detail"].lower()

    assert durable_state(database) == before
    assert check_out(shopper, current["version"], key=new_key()).status_code == 201


def test_empty_cart_cannot_be_checked_out(shopper: Browser, database: Database, mug: UUID) -> None:
    untouched = shopper.send("GET", "/api/v1/cart").json()

    response = check_out(shopper, untouched["version"], key=new_key())

    assert response.status_code == 409
    assert "empty" in response.json()["detail"].lower()
    # A cart emptied by an earlier checkout is empty too.
    assert check_out(shopper, add(shopper, mug, 1)["version"], key=new_key()).status_code == 201
    emptied = shopper.send("GET", "/api/v1/cart").json()
    before = durable_state(database)
    assert check_out(shopper, emptied["version"], key=new_key()).status_code == 409
    assert durable_state(database) == before


def test_declined_payment_returns_402_and_changes_nothing(shopper: Browser, database: Database, mug: UUID) -> None:
    cart = add(shopper, mug, 2)
    key = new_key()
    before = durable_state(database)

    declined = check_out(shopper, cart["version"], "declined", key=key)

    assert declined.status_code == 402
    assert "declined" in declined.json()["detail"].lower()
    assert durable_state(database) == before
    # Only accepted orders record their key, so the shopper may retry the same attempt.
    assert check_out(shopper, cart["version"], "approved", key=key).status_code == 201


def test_checkout_conflicts_when_stock_fell_below_the_cart(shopper: Browser, database: Database, mug: UUID) -> None:
    cart = add(shopper, mug, 3)
    run_sql(database, "UPDATE products SET stock = 2 WHERE id = :id", id=mug)
    before = durable_state(database)

    response = check_out(shopper, cart["version"], key=new_key())

    assert response.status_code == 409
    assert "stock" in response.json()["detail"].lower()
    assert durable_state(database) == before


def test_a_failure_after_the_order_insert_rolls_back_the_whole_checkout(
    shopper: Browser, database: Database, mug: UUID
) -> None:
    cart = add(shopper, mug, 2)
    [(guest_id,)] = run_sql(database, "SELECT guest_id FROM carts WHERE id = :id", id=cart["id"])
    before = durable_state(database)
    # The outbox insert comes after stock, order, and order lines are written; make it fail.
    run_sql(
        database,
        "CREATE FUNCTION test_reject_outbox() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'test rejected the outbox insert'; END $$",
    )
    run_sql(
        database,
        "CREATE TRIGGER test_reject_outbox BEFORE INSERT ON outbox_events "
        "FOR EACH ROW EXECUTE FUNCTION test_reject_outbox()",
    )
    try:
        with pytest.raises(DBAPIError, match="test rejected the outbox insert"):
            with database.session_scope() as session:
                checkout(session, guest_id, cart["version"], "approved", new_key())
    finally:
        run_sql(database, "DROP TRIGGER IF EXISTS test_reject_outbox ON outbox_events")
        run_sql(database, "DROP FUNCTION IF EXISTS test_reject_outbox()")

    assert durable_state(database) == before


@pytest.mark.parametrize(
    "key",
    [None, "", "short-7", "k" * 129, "has space-in-it", "comma,separated", "slash/separated"],
    ids=["missing", "empty", "seven-chars", "129-chars", "space", "comma", "slash"],
)
def test_checkout_requires_a_bounded_idempotency_key(
    shopper: Browser, database: Database, mug: UUID, key: str | None
) -> None:
    cart = add(shopper, mug, 1)
    before = durable_state(database)

    response = check_out(shopper, cart["version"], key=key)

    assert response.status_code == 422
    assert durable_state(database) == before


def test_idempotency_key_bounds_are_accepted(open_client: OpenClient, mug: UUID) -> None:
    for key in ("k" * 8, "K-_9" * 32):
        shopper = start_guest(open_client())
        assert check_out(shopper, add(shopper, mug, 1)["version"], key=key).status_code == 201


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"cart_version": 1},
        {"payment_outcome": "approved"},
        {"cart_version": "1", "payment_outcome": "approved"},
        {"cart_version": 1.0, "payment_outcome": "approved"},
        {"cart_version": True, "payment_outcome": "approved"},
        {"cart_version": -1, "payment_outcome": "approved"},
        {"cart_version": 1, "payment_outcome": "maybe"},
        {"cart_version": 1, "payment_outcome": "APPROVED"},
        {"cart_version": 1, "payment_outcome": "approved", "total_cents": 1},
        [1, "approved"],
    ],
    ids=[
        "empty",
        "missing-outcome",
        "missing-version",
        "string-version",
        "float-version",
        "bool-version",
        "negative-version",
        "unknown-outcome",
        "uppercase-outcome",
        "unknown-field",
        "array",
    ],
)
def test_checkout_body_must_match_the_schema_exactly(
    shopper: Browser, database: Database, mug: UUID, body: object
) -> None:
    add(shopper, mug, 1)
    before = durable_state(database)

    response = shopper.send("POST", ORDERS_URL, body, shopper.csrf_token, **{"Idempotency-Key": new_key()})

    assert response.status_code == 422
    assert durable_state(database) == before


# --- Order reads ---------------------------------------------------------------------------------


def test_guest_lists_and_reads_own_orders_newest_first(shopper: Browser, mug: UUID, hoodie: UUID) -> None:
    first = check_out(shopper, add(shopper, mug, 1)["version"], key=new_key()).json()
    second = check_out(shopper, add(shopper, hoodie, 2)["version"], key=new_key()).json()

    listing = shopper.send("GET", ORDERS_URL)
    detail = shopper.send("GET", f"{ORDERS_URL}/{first['id']}")

    assert listing.status_code == 200
    assert listing.json() == [second, first]
    assert detail.status_code == 200
    assert detail.json() == first


def test_unknown_orders_are_not_found(shopper: Browser) -> None:
    assert shopper.send("GET", ORDERS_URL).json() == []
    assert shopper.send("GET", f"{ORDERS_URL}/{uuid4()}").status_code == 404
    assert shopper.send("GET", f"{ORDERS_URL}/{uuid4()}/receipt").status_code == 404


def test_receipt_is_available_once_issued(shopper: Browser, database: Database, products: dict, mug: UUID) -> None:
    order = check_out(shopper, add(shopper, mug, 2)["version"], key=new_key()).json()
    receipt_url = f"{ORDERS_URL}/{order['id']}/receipt"

    pending = shopper.send("GET", receipt_url)

    assert pending.status_code == 404
    assert "not available" in pending.json()["detail"].lower()

    # The fulfillment worker (Task 4) issues receipts; insert one the same way.
    receipt_id = uuid4()
    run_sql(database, "INSERT INTO receipts (id, order_id) VALUES (:id, :order_id)", id=receipt_id, order_id=order["id"])

    issued = shopper.send("GET", receipt_url)

    assert issued.status_code == 200, issued.text
    receipt = issued.json()
    assert set(receipt) == {"id", "order_id", "issued_at", "items", "total_cents", "currency"}
    assert (receipt["id"], receipt["order_id"]) == (str(receipt_id), order["id"])
    assert receipt["items"] == order["items"]
    assert (receipt["total_cents"], receipt["currency"]) == (order["total_cents"], "USD")
    assert datetime.fromisoformat(receipt["issued_at"]).utcoffset() == timedelta(0)
    assert shopper.send("GET", f"{ORDERS_URL}/{order['id']}").json()["receipt_available"] is True


def test_database_allows_one_receipt_and_one_outbox_event_per_order_and_one_order_per_key(
    shopper: Browser, database: Database, mug: UUID
) -> None:
    key = new_key()
    order = check_out(shopper, add(shopper, mug, 1)["version"], key=key).json()
    run_sql(database, "INSERT INTO receipts (id, order_id) VALUES (:id, :order_id)", id=uuid4(), order_id=order["id"])

    duplicates = [
        "INSERT INTO receipts (id, order_id) VALUES (:id, :order_id)",
        "INSERT INTO outbox_events (id, order_id) VALUES (:id, :order_id)",
        "INSERT INTO orders (id, guest_id, idempotency_key, request_fingerprint, status, total_cents, currency) "
        "SELECT :id, guest_id, idempotency_key, request_fingerprint, status, total_cents, currency "
        "FROM orders WHERE id = :order_id",
    ]
    for statement in duplicates:
        with pytest.raises(IntegrityError, match="unique"):
            run_sql(database, statement, id=uuid4(), order_id=order["id"])


def test_openapi_documents_the_checkout_contract(open_client: OpenClient) -> None:
    document = open_client().get("/openapi.json").json()
    operation = document["paths"][ORDERS_URL]["post"]
    reference = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema = document["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"cart_version", "payment_outcome"}
    assert schema["properties"]["cart_version"]["minimum"] == 0
    assert schema["properties"]["payment_outcome"]["enum"] == ["approved", "declined"]
    [key_header] = [parameter for parameter in operation["parameters"] if parameter["name"] == "Idempotency-Key"]
    assert key_header["in"] == "header" and key_header["required"] is True
    assert {"200", "201", "402", "409"} <= set(operation["responses"])
    order = document["components"]["schemas"]["OrderView"]
    assert set(order["required"]) == ORDER_FIELDS
