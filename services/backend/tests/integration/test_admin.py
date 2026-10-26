"""Instructor view: resuming and ending an instructor session, and the recent-orders overview."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from cloudcart.db import Database
from cloudcart.seed import seed_database
from helpers import Browser, OpenClient, run_sql, start_guest

# TEST-ONLY instructor password.
ADMIN_PASSWORD = "admin-test-instructor-password"
INSTRUCTOR_COOKIE = "cloudcart_instructor"
GUEST_COOKIE = "cloudcart_guest"
ADMIN_SESSION_URL = "/api/v1/admin/session"
LOGOUT_URL = "/api/v1/admin/logout"
ADMIN_ORDERS_URL = "/api/v1/admin/orders"
LISTED_ORDERS = 50
ADMIN_ORDER_FIELDS = {
    "id",
    "status",
    "publication_pending",
    "fulfillment_attempts",
    "item_count",
    "total_cents",
    "created_at",
    "receipt_available",
}


def log_in(client: TestClient) -> Browser:
    response = client.post("/api/v1/admin/login", json={"username": "instructor", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return Browser(client, response.json()["csrf_token"])


def check_out(guest: Browser, product_id: UUID, quantity: int, key: str) -> dict:
    cart = guest.send("PUT", f"/api/v1/cart/items/{product_id}", {"quantity": quantity}, guest.csrf_token)
    assert cart.status_code == 200, cart.text
    body = {"cart_version": cart.json()["version"], "payment_outcome": "approved"}
    order = guest.send("POST", "/api/v1/orders", body, guest.csrf_token, **{"Idempotency-Key": key})
    assert order.status_code == 201, order.text
    return order.json()


def max_age(response: Response, name: str) -> int:
    [header] = [value for value in response.headers.get_list("set-cookie") if value.startswith(f"{name}=")]
    [age] = [part.split("=", 1)[1] for part in header.split(";") if part.strip().lower().startswith("max-age=")]
    return int(age)


@pytest.fixture
def product_ids(database: Database) -> list[UUID]:
    with database.session_scope() as session:
        seed_database(session, ADMIN_PASSWORD)
    run_sql(database, "UPDATE products SET stock = 1000")
    return [product_id for (product_id,) in run_sql(database, "SELECT id FROM products ORDER BY sku")]


@pytest.fixture
def instructor(open_client: OpenClient, product_ids: list[UUID]) -> Browser:
    return log_in(open_client())


# --- Resuming an instructor session after a page reload --------------------------------------


def test_admin_session_returns_the_live_session_csrf_token(open_client: OpenClient, product_ids: list[UUID]) -> None:
    client = open_client()
    login = client.post("/api/v1/admin/login", json={"username": "instructor", "password": ADMIN_PASSWORD})

    resumed = client.get(ADMIN_SESSION_URL)

    assert resumed.status_code == 200
    assert resumed.json() == login.json()
    assert "set-cookie" not in resumed.headers
    assert resumed.headers["cache-control"] == "no-store"


def test_admin_session_requires_a_live_instructor_session(
    open_client: OpenClient, database: Database, product_ids: list[UUID]
) -> None:
    anonymous = open_client()
    guest = start_guest(open_client()).client
    expired = log_in(open_client()).client
    run_sql(database, "UPDATE instructor_sessions SET expires_at = now() - interval '1 second'")

    for client in (anonymous, guest, expired):
        response = client.get(ADMIN_SESSION_URL)
        assert response.status_code == 401
        assert "csrf_token" not in response.text


@pytest.mark.parametrize(
    "forged", [{"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://attacker.example"}], ids=["fetch-metadata", "origin"]
)
def test_admin_session_refuses_cross_site_requests(instructor: Browser, forged: dict[str, str]) -> None:
    response = instructor.client.get(ADMIN_SESSION_URL, headers=forged)

    assert response.status_code == 403
    assert "csrf_token" not in response.text


# --- Logging out -------------------------------------------------------------------------------


def test_logout_ends_the_session_and_clears_the_cookie(
    open_client: OpenClient, database: Database, instructor: Browser, product_ids: list[UUID]
) -> None:
    token = instructor.client.cookies[INSTRUCTOR_COOKIE]

    response = instructor.send("POST", LOGOUT_URL, None, instructor.csrf_token)

    assert response.status_code == 204
    assert max_age(response, INSTRUCTOR_COOKIE) == 0
    assert run_sql(database, "SELECT count(*) FROM instructor_sessions") == [(0,)]
    # A copy of the old cookie no longer works anywhere.
    replayed = Browser(open_client(cookies={INSTRUCTOR_COOKIE: token}), instructor.csrf_token)
    stock_url = f"/api/v1/admin/products/{product_ids[0]}/stock"
    assert replayed.send("PUT", stock_url, {"stock": 7}, replayed.csrf_token).status_code == 401
    assert replayed.send("GET", ADMIN_SESSION_URL).status_code == 401
    assert replayed.send("GET", ADMIN_ORDERS_URL).status_code == 401


def test_logout_ends_only_its_own_session(open_client: OpenClient, instructor: Browser) -> None:
    other = log_in(open_client())

    assert instructor.send("POST", LOGOUT_URL, None, instructor.csrf_token).status_code == 204

    assert other.send("GET", ADMIN_SESSION_URL).status_code == 200


# --- Recent orders across all guests -----------------------------------------------------------


def test_admin_orders_require_a_live_instructor_session(
    open_client: OpenClient, database: Database, product_ids: list[UUID]
) -> None:
    anonymous = open_client()
    guest = start_guest(open_client()).client
    expired = log_in(open_client()).client
    run_sql(database, "UPDATE instructor_sessions SET expires_at = now() - interval '1 second'")

    for client in (anonymous, guest, expired):
        assert client.get(ADMIN_ORDERS_URL).status_code == 401


def test_admin_orders_list_every_guests_orders_newest_first(
    open_client: OpenClient, instructor: Browser, product_ids: list[UUID]
) -> None:
    first_guest, second_guest = start_guest(open_client()), start_guest(open_client())
    first = check_out(first_guest, product_ids[0], 2, "admin-first-order")
    second = check_out(second_guest, product_ids[1], 3, "admin-second-order")

    response = instructor.send("GET", ADMIN_ORDERS_URL)

    assert response.status_code == 200
    orders = response.json()["orders"]
    assert [order["id"] for order in orders] == [second["id"], first["id"]]
    for order in orders:
        assert set(order) == ADMIN_ORDER_FIELDS
    assert orders[0] == {
        "id": second["id"],
        "status": "accepted",
        "publication_pending": True,
        "fulfillment_attempts": 0,
        "item_count": 3,
        "total_cents": second["total_cents"],
        "created_at": second["created_at"],
        "receipt_available": False,
    }
    created_at = datetime.fromisoformat(orders[0]["created_at"])
    assert created_at.utcoffset() == timedelta(0)
    assert abs(created_at - datetime.now(UTC)) < timedelta(minutes=1)


def test_admin_orders_count_statuses_and_pending_publication(
    open_client: OpenClient, database: Database, instructor: Browser, product_ids: list[UUID]
) -> None:
    guest = start_guest(open_client())
    ids = [check_out(guest, product_ids[0], 1, f"admin-count-{n}")["id"] for n in range(6)]
    # Orders 0-1 stay accepted and unpublished; 2 is accepted and queued; 3 processing; 4 fulfilled; 5 failed.
    run_sql(database, "UPDATE outbox_events SET published_at = now() WHERE order_id = ANY(:ids)", ids=ids[2:])
    run_sql(database, "UPDATE orders SET status = 'processing', fulfillment_attempts = 1 WHERE id = :id", id=ids[3])
    run_sql(database, "UPDATE orders SET status = 'fulfilled', fulfillment_attempts = 1 WHERE id = :id", id=ids[4])
    run_sql(database, "INSERT INTO receipts (id, order_id) VALUES (gen_random_uuid(), :id)", id=ids[4])
    run_sql(
        database,
        "UPDATE orders SET status = 'failed', fulfillment_attempts = 4, failure_reason = 'test failure' WHERE id = :id",
        id=ids[5],
    )

    body = instructor.send("GET", ADMIN_ORDERS_URL).json()

    assert body["status_counts"] == {"accepted": 3, "processing": 1, "fulfilled": 1, "failed": 1}
    assert body["publication_pending"] == 2
    by_id = {order["id"]: order for order in body["orders"]}
    assert by_id[ids[4]]["receipt_available"] is True
    assert by_id[ids[5]]["fulfillment_attempts"] == 4
    assert [by_id[order_id]["publication_pending"] for order_id in ids] == [True, True, False, False, False, False]
    # The internal failure reason is never part of the overview.
    assert "test failure" not in instructor.send("GET", ADMIN_ORDERS_URL).text


def test_pending_publication_counts_only_accepted_orders(
    open_client: OpenClient, database: Database, instructor: Browser, product_ids: list[UUID]
) -> None:
    """A worker can start an order before the publisher records the broker's confirm, so a processing
    (or finished) order can still have an unpublished event; it is no longer waiting to be queued."""
    guest = start_guest(open_client())
    waiting, started = (check_out(guest, product_ids[0], 1, f"admin-pending-{n}")["id"] for n in range(2))
    run_sql(database, "UPDATE orders SET status = 'processing', fulfillment_attempts = 1 WHERE id = :id", id=started)

    body = instructor.send("GET", ADMIN_ORDERS_URL).json()

    assert body["status_counts"] == {"accepted": 1, "processing": 1, "fulfilled": 0, "failed": 0}
    assert body["publication_pending"] == 1
    assert {order["id"]: order["publication_pending"] for order in body["orders"]} == {waiting: True, started: False}


def test_admin_orders_list_is_bounded_but_counts_are_complete(
    open_client: OpenClient, instructor: Browser, product_ids: list[UUID]
) -> None:
    guest = start_guest(open_client())
    ids = [check_out(guest, product_ids[2], 1, f"admin-bounded-{n:02}")["id"] for n in range(LISTED_ORDERS + 2)]

    body = instructor.send("GET", ADMIN_ORDERS_URL).json()

    assert [order["id"] for order in body["orders"]] == list(reversed(ids))[:LISTED_ORDERS]
    assert body["status_counts"]["accepted"] == LISTED_ORDERS + 2
    assert body["publication_pending"] == LISTED_ORDERS + 2


def test_admin_orders_never_expose_guest_identity(
    open_client: OpenClient, database: Database, instructor: Browser, product_ids: list[UUID]
) -> None:
    guest = start_guest(open_client())
    check_out(guest, product_ids[0], 1, "admin-private-key")
    [(guest_id, fingerprint)] = run_sql(database, "SELECT guest_id, request_fingerprint FROM orders")

    response = instructor.send("GET", ADMIN_ORDERS_URL)

    assert response.status_code == 200
    assert len(response.json()["orders"]) == 1
    for private in (str(guest_id), fingerprint, "admin-private-key", guest.client.cookies[GUEST_COOKIE]):
        assert private not in response.text
