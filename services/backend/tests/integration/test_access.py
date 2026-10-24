"""Access boundaries: guest sessions, instructor login, CSRF and same-origin checks, and secret handling."""

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from pydantic import SecretStr

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.seed import seed_database
from helpers import Browser, OpenClient, run_sql, start_guest

# TEST-ONLY instructor password.
ADMIN_PASSWORD = "access-test-instructor-password"
INSTRUCTOR_USERNAME = "instructor"
GUEST_COOKIE = "cloudcart_guest"
INSTRUCTOR_COOKIE = "cloudcart_instructor"
GUEST_LIFETIME = timedelta(days=7)
INSTRUCTOR_LIFETIME = timedelta(hours=8)
SAME_ORIGIN = "https://testserver"
CROSS_SITE_HEADERS = [
    {"Origin": "https://attacker.example"},
    {"Origin": "https://testserver.attacker.example"},
    {"Origin": "https://testserver:8443"},
    {"Origin": "null"},
    {"Sec-Fetch-Site": "cross-site"},
    {"Origin": SAME_ORIGIN, "Sec-Fetch-Site": "cross-site"},
]
CROSS_SITE_IDS = ["other-host", "suffix-host", "other-port", "opaque-origin", "fetch-metadata", "both"]


@dataclass(frozen=True)
class Change:
    """A state-changing route and the kind of session allowed to call it."""

    name: str
    actor: str  # "guest" or "instructor"
    method: str
    path: str
    body: object
    headers: tuple[tuple[str, str], ...] = ()  # sent with every attempt, e.g. Idempotency-Key
    success: int = 200

    def send(self, actor: Browser, product_id: UUID, csrf_token: str | None, **headers: str) -> Response:
        url = self.path.format(product_id=product_id)
        return actor.send(self.method, url, self.body, csrf_token, **dict(self.headers), **headers)


GUEST_CHANGES = [
    Change("set-cart-item", "guest", "PUT", "/api/v1/cart/items/{product_id}", {"quantity": 2}),
    Change("remove-cart-item", "guest", "DELETE", "/api/v1/cart/items/{product_id}", None),
    # The `guest` fixture's cart is at version 1.
    Change(
        "checkout",
        "guest",
        "POST",
        "/api/v1/orders",
        {"cart_version": 1, "payment_outcome": "approved"},
        headers=(("Idempotency-Key", "access-test-checkout-key"),),
        success=201,
    ),
]
INSTRUCTOR_CHANGES = [
    Change("update-stock", "instructor", "PUT", "/api/v1/admin/products/{product_id}/stock", {"stock": 42}),
]
ALL_CHANGES = GUEST_CHANGES + INSTRUCTOR_CHANGES


def item_url(product_id: UUID) -> str:
    return f"/api/v1/cart/items/{product_id}"


def stock_url(product_id: UUID) -> str:
    return f"/api/v1/admin/products/{product_id}/stock"


def check_out(browser: Browser, product_id: UUID, key: str) -> Response:
    """Put one unit of `product_id` in the cart and check it out."""
    cart = browser.send("PUT", item_url(product_id), {"quantity": 1}, browser.csrf_token)
    assert cart.status_code == 200, cart.text
    body = {"cart_version": cart.json()["version"], "payment_outcome": "approved"}
    return browser.send("POST", "/api/v1/orders", body, browser.csrf_token, **{"Idempotency-Key": key})


def credentials(password: str = ADMIN_PASSWORD, username: str = INSTRUCTOR_USERNAME) -> dict[str, str]:
    return {"username": username, "password": password}


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def expected_csrf_token(session_token: str) -> str:
    digest = hmac.new(session_token.encode(), b"cloudcart-csrf-v1", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def cookie_attributes(response: Response, name: str) -> dict[str, str]:
    """Attributes of the one Set-Cookie header for `name`, keyed in lower case; the value is under ''."""
    headers = [header for header in response.headers.get_list("set-cookie") if header.startswith(f"{name}=")]
    assert len(headers) == 1, response.headers.get_list("set-cookie")
    value, *attributes = (part.strip() for part in headers[0].split(";"))
    parsed = {"": value.split("=", 1)[1]}
    for attribute in attributes:
        key, _, attribute_value = attribute.partition("=")
        parsed[key.lower()] = attribute_value
    return parsed


def log_in(client: TestClient, password: str = ADMIN_PASSWORD) -> Browser:
    response = client.post("/api/v1/admin/login", json=credentials(password))
    assert response.status_code == 200, response.text
    return Browser(client, response.json()["csrf_token"])


@pytest.fixture
def product_id(database: Database) -> UUID:
    with database.session_scope() as session:
        seed_database(session, ADMIN_PASSWORD)
    return run_sql(database, "SELECT id FROM products ORDER BY sku LIMIT 1")[0][0]


@pytest.fixture
def guest(open_client: OpenClient, product_id: UUID) -> Browser:
    """A guest whose cart already holds one of `product_id`, so removing it can succeed."""
    browser = start_guest(open_client())
    assert browser.send("PUT", item_url(product_id), {"quantity": 1}, browser.csrf_token).status_code == 200
    return browser


@pytest.fixture
def instructor(open_client: OpenClient, product_id: UUID) -> Browser:
    return log_in(open_client())


@pytest.fixture
def actors(guest: Browser, instructor: Browser) -> dict[str, Browser]:
    return {"guest": guest, "instructor": instructor}


def observed_state(database: Database, product_id: UUID) -> tuple:
    """Everything a forged change could alter: cart versions and lines, product stock, orders, and outbox events."""
    return (
        run_sql(database, "SELECT id, version FROM carts ORDER BY id"),
        run_sql(database, "SELECT cart_id, product_id, quantity FROM cart_items ORDER BY cart_id, product_id"),
        run_sql(database, "SELECT stock FROM products WHERE id = :id", id=product_id),
        run_sql(database, "SELECT id, guest_id, status FROM orders ORDER BY id"),
        run_sql(database, "SELECT id, order_id FROM outbox_events ORDER BY id"),
    )


# --- Guest sessions -------------------------------------------------------------------------


def test_guest_session_cookie_is_http_only_secure_and_strict(open_client: OpenClient, database: Database) -> None:
    client = open_client()

    started = client.get("/api/v1/session")

    assert started.status_code == 200
    cookie = cookie_attributes(started, GUEST_COOKIE)
    assert "httponly" in cookie and "secure" in cookie
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/"
    assert int(cookie["max-age"]) == GUEST_LIFETIME.total_seconds()
    assert started.headers["cache-control"] == "no-store"
    body = started.json()
    assert set(body) == {"csrf_token", "expires_at"}
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert expires_at.utcoffset() == timedelta(0)
    assert abs(expires_at - (datetime.now(UTC) + GUEST_LIFETIME)) < timedelta(minutes=1)
    # Only the SHA-256 of the token is stored, and the CSRF token is derived from the token (R1).
    token = cookie[""]
    assert body["csrf_token"] == expected_csrf_token(token)
    assert run_sql(database, "SELECT count(*) FROM guests WHERE token_hash = :hash", hash=token_hash(token)) == [(1,)]

    resumed = client.get("/api/v1/session")

    assert resumed.status_code == 200
    assert "set-cookie" not in resumed.headers
    assert resumed.json() == body
    assert run_sql(database, "SELECT count(*) FROM guests") == [(1,)]


def test_cookies_omit_secure_only_when_https_is_disabled(
    open_client: OpenClient, integration_settings: Settings, product_id: UUID
) -> None:
    plain_http = Settings(
        database_url=SecretStr(integration_settings.database_url.get_secret_value()), cookie_secure=False
    )
    client = open_client(plain_http)

    guest_cookie = cookie_attributes(client.get("/api/v1/session"), GUEST_COOKIE)
    login = client.post("/api/v1/admin/login", json=credentials())
    instructor_cookie = cookie_attributes(login, INSTRUCTOR_COOKIE)

    for cookie in (guest_cookie, instructor_cookie):
        assert "secure" not in cookie
        assert "httponly" in cookie and cookie["samesite"].lower() == "strict"


def test_cart_requires_a_live_guest_session(open_client: OpenClient, product_id: UUID) -> None:
    anonymous = Browser(open_client(), csrf_token="")
    forged_token = "x" * 43
    stranger = Browser(open_client(cookies={GUEST_COOKIE: forged_token}), expected_csrf_token(forged_token))

    for browser in (anonymous, stranger):
        assert browser.send("GET", "/api/v1/cart").status_code == 401
        assert browser.send("PUT", item_url(product_id), {"quantity": 1}, browser.csrf_token).status_code == 401
        assert browser.send("DELETE", item_url(product_id), None, browser.csrf_token).status_code == 401


def test_orders_require_a_live_guest_session(open_client: OpenClient, database: Database, product_id: UUID) -> None:
    owner = start_guest(open_client())
    order_id = check_out(owner, product_id, "access-test-owner-key").json()["id"]
    forged_token = "x" * 43
    anonymous = Browser(open_client(), csrf_token="")
    stranger = Browser(open_client(cookies={GUEST_COOKIE: forged_token}), expected_csrf_token(forged_token))
    instructor = log_in(open_client())  # an instructor session is not a guest session
    checkout_body = {"cart_version": 1, "payment_outcome": "approved"}

    for browser in (anonymous, stranger, instructor):
        assert browser.send("GET", "/api/v1/orders").status_code == 401
        assert browser.send("GET", f"/api/v1/orders/{order_id}").status_code == 401
        assert browser.send("GET", f"/api/v1/orders/{order_id}/receipt").status_code == 401
        placed = browser.send(
            "POST", "/api/v1/orders", checkout_body, browser.csrf_token, **{"Idempotency-Key": "access-test-key"}
        )
        assert placed.status_code == 401
    assert run_sql(database, "SELECT count(*) FROM orders") == [(1,)]


def test_guests_cannot_see_or_change_each_others_carts(
    open_client: OpenClient, database: Database, product_id: UUID
) -> None:
    alice = start_guest(open_client())
    assert alice.send("PUT", item_url(product_id), {"quantity": 2}, alice.csrf_token).status_code == 200
    alice_cart = alice.send("GET", "/api/v1/cart").json()
    bob = start_guest(open_client())

    bob_cart = bob.send("GET", "/api/v1/cart").json()
    assert bob_cart["id"] != alice_cart["id"]
    assert bob_cart["items"] == []
    # Bob's changes only ever reach Bob's own cart.
    assert bob.send("DELETE", item_url(product_id), None, bob.csrf_token).status_code == 404
    assert bob.send("PUT", item_url(product_id), {"quantity": 5}, bob.csrf_token).status_code == 200
    # Alice's CSRF token is bound to Alice's session; Bob cannot use it.
    assert bob.send("PUT", item_url(product_id), {"quantity": 1}, alice.csrf_token).status_code == 403

    assert alice.send("GET", "/api/v1/cart").json() == alice_cart
    assert alice_cart["items"][0]["quantity"] == 2
    assert bob.send("GET", "/api/v1/cart").json()["items"][0]["quantity"] == 5


def test_expired_guest_session_is_rejected_and_never_revived(
    open_client: OpenClient, database: Database, product_id: UUID
) -> None:
    client = open_client()
    guest = start_guest(client)
    assert guest.send("PUT", item_url(product_id), {"quantity": 2}, guest.csrf_token).status_code == 200
    old_cart = guest.send("GET", "/api/v1/cart").json()
    old_token = client.cookies[GUEST_COOKIE]
    [(old_guest_id,)] = run_sql(
        database,
        "UPDATE guests SET expires_at = now() - interval '1 second' WHERE token_hash = :hash RETURNING id",
        hash=token_hash(old_token),
    )

    assert guest.send("GET", "/api/v1/cart").status_code == 401
    assert guest.send("PUT", item_url(product_id), {"quantity": 3}, guest.csrf_token).status_code == 401

    restarted = client.get("/api/v1/session")

    assert restarted.status_code == 200
    new_token = cookie_attributes(restarted, GUEST_COOKIE)[""]
    assert new_token != old_token
    assert restarted.json()["csrf_token"] != guest.csrf_token
    [(new_guest_id,)] = run_sql(database, "SELECT id FROM guests WHERE token_hash = :hash", hash=token_hash(new_token))
    assert new_guest_id != old_guest_id
    new_cart = client.get("/api/v1/cart").json()
    assert new_cart["id"] != old_cart["id"]
    assert (new_cart["version"], new_cart["items"], new_cart["total_cents"]) == (0, [], 0)
    # The old session stays expired; presenting its token again still fails.
    assert run_sql(database, "SELECT expires_at < now() FROM guests WHERE id = :id", id=old_guest_id) == [(True,)]
    stale = open_client(cookies={GUEST_COOKIE: old_token})
    assert stale.get("/api/v1/cart").status_code == 401


def test_guests_cannot_read_each_others_orders_or_receipts(
    open_client: OpenClient, database: Database, product_id: UUID
) -> None:
    alice = start_guest(open_client())
    alice_order = check_out(alice, product_id, "access-test-alice-key").json()
    run_sql(database, "INSERT INTO receipts (id, order_id) VALUES (:id, :order_id)", id=uuid4(), order_id=alice_order["id"])
    bob = start_guest(open_client())
    unknown_id = uuid4()

    # Alice's own reads succeed.
    assert alice.send("GET", f"/api/v1/orders/{alice_order['id']}").status_code == 200
    assert alice.send("GET", f"/api/v1/orders/{alice_order['id']}/receipt").status_code == 200
    # To Bob, Alice's guessed order id is indistinguishable from an id that does not exist.
    for suffix in ("", "/receipt"):
        guessed = bob.send("GET", f"/api/v1/orders/{alice_order['id']}{suffix}")
        unknown = bob.send("GET", f"/api/v1/orders/{unknown_id}{suffix}")
        assert guessed.status_code == unknown.status_code == 404
        assert guessed.json() == unknown.json()
    assert bob.send("GET", "/api/v1/orders").json() == []
    # Bob checking out with Alice's key creates Bob's own order and leaves Alice's alone.
    bob_order = check_out(bob, product_id, "access-test-alice-key")
    assert bob_order.status_code == 201
    assert bob_order.json()["id"] != alice_order["id"]
    assert [order["id"] for order in alice.send("GET", "/api/v1/orders").json()] == [alice_order["id"]]


# --- Instructor authentication ----------------------------------------------------------------


def test_instructor_login_sets_a_strict_http_only_cookie(
    open_client: OpenClient, database: Database, product_id: UUID
) -> None:
    response = open_client().post("/api/v1/admin/login", json=credentials())

    assert response.status_code == 200
    cookie = cookie_attributes(response, INSTRUCTOR_COOKIE)
    assert "httponly" in cookie and "secure" in cookie
    assert cookie["samesite"].lower() == "strict"
    assert cookie["path"] == "/"
    assert int(cookie["max-age"]) == INSTRUCTOR_LIFETIME.total_seconds()
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"csrf_token", "expires_at"}
    assert body["csrf_token"] == expected_csrf_token(cookie[""])
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert abs(expires_at - (datetime.now(UTC) + INSTRUCTOR_LIFETIME)) < timedelta(minutes=1)
    assert run_sql(
        database, "SELECT count(*) FROM instructor_sessions WHERE token_hash = :hash", hash=token_hash(cookie[""])
    ) == [(1,)]


def test_failed_logins_are_indistinguishable(open_client: OpenClient, product_id: UUID) -> None:
    client = open_client()

    wrong_password = client.post("/api/v1/admin/login", json=credentials("not-the-password"))
    unknown_user = client.post("/api/v1/admin/login", json=credentials(username="nobody"))

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert "set-cookie" not in wrong_password.headers and "set-cookie" not in unknown_user.headers


@pytest.mark.parametrize(
    "body",
    [
        credentials(username="i" * 65),
        credentials("p" * 257),
        credentials(username=""),
        credentials(""),
        {"username": INSTRUCTOR_USERNAME},
        {**credentials(), "role": "admin"},
    ],
    ids=["long-username", "long-password", "empty-username", "empty-password", "missing-password", "unknown-field"],
)
def test_login_fields_are_bounded_and_never_echoed(open_client: OpenClient, product_id: UUID, body: dict) -> None:
    response = open_client().post("/api/v1/admin/login", json=body)

    assert response.status_code == 422
    assert "set-cookie" not in response.headers
    if body.get("password"):
        assert body["password"] not in response.text


def test_seed_rerun_rotates_the_instructor_password(open_client: OpenClient, database: Database) -> None:
    with database.session_scope() as session:
        seed_database(session, "first-instructor-password")
    with database.session_scope() as session:
        seed_database(session, ADMIN_PASSWORD)
    client = open_client()

    old = client.post("/api/v1/admin/login", json=credentials("first-instructor-password"))
    new = client.post("/api/v1/admin/login", json=credentials())

    assert old.status_code == 401
    assert new.status_code == 200
    [(password_hash,)] = run_sql(database, "SELECT password_hash FROM instructors WHERE username = 'instructor'")
    assert password_hash.startswith("$argon2id$")


def test_stock_changes_require_a_live_instructor_session(
    open_client: OpenClient, database: Database, product_id: UUID
) -> None:
    url = stock_url(product_id)
    anonymous = Browser(open_client(), csrf_token="anything")
    guest = start_guest(open_client())

    assert anonymous.send("PUT", url, {"stock": 7}, anonymous.csrf_token).status_code == 401
    # A guest session, even with its own valid CSRF token, is not an instructor session.
    assert guest.send("PUT", url, {"stock": 7}, guest.csrf_token).status_code == 401

    instructor = log_in(open_client())
    updated = instructor.send("PUT", url, {"stock": 7}, instructor.csrf_token)

    assert updated.status_code == 200
    assert updated.json()["id"] == str(product_id)
    assert updated.json()["stock"] == 7
    catalog = {product["id"]: product for product in guest.send("GET", "/api/v1/products").json()}
    assert catalog[str(product_id)]["stock"] == 7
    # An instructor session is not a guest session either.
    assert instructor.send("GET", "/api/v1/cart").status_code == 401


def test_session_tokens_only_authorize_their_own_kind(open_client: OpenClient, product_id: UUID) -> None:
    client = open_client()
    guest = start_guest(client)
    instructor = log_in(client)  # the same browser now holds both cookies

    assert instructor.send("PUT", stock_url(product_id), {"stock": 9}, guest.csrf_token).status_code == 403
    assert guest.send("PUT", item_url(product_id), {"quantity": 1}, instructor.csrf_token).status_code == 403
    assert instructor.send("PUT", stock_url(product_id), {"stock": 9}, instructor.csrf_token).status_code == 200
    assert guest.send("PUT", item_url(product_id), {"quantity": 1}, guest.csrf_token).status_code == 200


def test_expired_instructor_session_is_rejected(open_client: OpenClient, database: Database, product_id: UUID) -> None:
    instructor = log_in(open_client())
    run_sql(database, "UPDATE instructor_sessions SET expires_at = now() - interval '1 second'")

    response = instructor.send("PUT", stock_url(product_id), {"stock": 3}, instructor.csrf_token)

    assert response.status_code == 401
    assert run_sql(database, "SELECT stock FROM products WHERE id = :id", id=product_id) != [(3,)]


@pytest.mark.parametrize(
    "body",
    [{"stock": -1}, {"stock": 100_001}, {"stock": "5"}, {"stock": 1.5}, {"stock": None}, {"stock": 5, "sku": "x"}, {}],
    ids=["negative", "too-large", "string", "fraction", "null", "unknown-field", "missing"],
)
def test_stock_values_are_validated(instructor: Browser, product_id: UUID, body: dict) -> None:
    response = instructor.send("PUT", stock_url(product_id), body, instructor.csrf_token)

    assert response.status_code == 422


def test_stock_bounds_are_accepted_and_unknown_products_are_not_found(instructor: Browser, product_id: UUID) -> None:
    for stock in (0, 100_000):
        response = instructor.send("PUT", stock_url(product_id), {"stock": stock}, instructor.csrf_token)
        assert response.status_code == 200
        assert response.json()["stock"] == stock

    unknown = instructor.send("PUT", stock_url(uuid4()), {"stock": 1}, instructor.csrf_token)
    assert unknown.status_code == 404


# --- CSRF and same-origin protection on every state-changing route ---------------------------


@pytest.mark.parametrize("change", ALL_CHANGES, ids=[change.name for change in ALL_CHANGES])
@pytest.mark.parametrize("presented", ["missing", "wrong", "empty"])
def test_state_changing_routes_require_the_session_csrf_token(
    actors: dict[str, Browser], database: Database, product_id: UUID, change: Change, presented: str
) -> None:
    actor = actors[change.actor]
    csrf_token = {"missing": None, "wrong": expected_csrf_token("not-this-session"), "empty": ""}[presented]
    before = observed_state(database, product_id)

    response = change.send(actor, product_id, csrf_token)

    assert response.status_code == 403
    assert observed_state(database, product_id) == before


@pytest.mark.parametrize("change", ALL_CHANGES, ids=[change.name for change in ALL_CHANGES])
@pytest.mark.parametrize("forged", CROSS_SITE_HEADERS, ids=CROSS_SITE_IDS)
def test_cross_site_requests_are_rejected_even_with_a_valid_csrf_token(
    actors: dict[str, Browser], database: Database, product_id: UUID, change: Change, forged: dict[str, str]
) -> None:
    actor = actors[change.actor]
    before = observed_state(database, product_id)

    response = change.send(actor, product_id, actor.csrf_token, **forged)

    assert response.status_code == 403
    assert observed_state(database, product_id) == before


@pytest.mark.parametrize("change", ALL_CHANGES, ids=[change.name for change in ALL_CHANGES])
def test_same_origin_requests_with_the_csrf_token_succeed(
    actors: dict[str, Browser], product_id: UUID, change: Change
) -> None:
    actor = actors[change.actor]
    headers = {"Origin": SAME_ORIGIN, "Sec-Fetch-Site": "same-origin"}

    response = change.send(actor, product_id, actor.csrf_token, **headers)

    assert response.status_code == change.success, response.text


@pytest.mark.parametrize("change", ALL_CHANGES, ids=[change.name for change in ALL_CHANGES])
def test_checks_run_in_order_origin_then_session_then_csrf(
    open_client: OpenClient, actors: dict[str, Browser], product_id: UUID, change: Change
) -> None:
    no_session = Browser(open_client(), csrf_token="")
    forged = {"Origin": "https://attacker.example"}

    assert change.send(no_session, product_id, None, **forged).status_code == 403
    assert change.send(no_session, product_id, None).status_code == 401
    assert change.send(actors[change.actor], product_id, None).status_code == 403


@pytest.mark.parametrize("forged", CROSS_SITE_HEADERS, ids=CROSS_SITE_IDS)
def test_cross_site_login_is_rejected(open_client: OpenClient, product_id: UUID, forged: dict[str, str]) -> None:
    response = open_client().post("/api/v1/admin/login", json=credentials(), headers=forged)

    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_same_origin_login_succeeds(open_client: OpenClient, product_id: UUID) -> None:
    response = open_client().post(
        "/api/v1/admin/login",
        json=credentials(),
        headers={"Origin": SAME_ORIGIN, "Sec-Fetch-Site": "same-origin"},
    )

    assert response.status_code == 200


# --- Secrets stay out of responses -------------------------------------------------------------


def test_responses_never_contain_session_tokens_or_password_hashes(
    open_client: OpenClient, database: Database, product_id: UUID
) -> None:
    guest_client, instructor_client = open_client(), open_client()
    responses = [guest_client.get("/api/v1/session")]
    guest = Browser(guest_client, responses[0].json()["csrf_token"])
    responses += [
        guest.send("GET", "/api/v1/session"),
        guest.send("PUT", item_url(product_id), {"quantity": 1}, guest.csrf_token),
        guest.send("GET", "/api/v1/cart"),
        guest.send("DELETE", item_url(product_id), None, guest.csrf_token),
        guest.send("PUT", item_url(product_id), {"quantity": 99}, guest.csrf_token),
        guest.send("GET", "/api/v1/products"),
        instructor_client.post("/api/v1/admin/login", json=credentials("wrong-password")),
        instructor_client.post("/api/v1/admin/login", json=credentials()),
    ]
    instructor = Browser(instructor_client, responses[-1].json()["csrf_token"])
    responses += [
        instructor.send("PUT", stock_url(product_id), {"stock": 5}, instructor.csrf_token),
        instructor.send("PUT", stock_url(product_id), {"stock": -5}, instructor.csrf_token),
    ]
    order = check_out(guest, product_id, "access-test-secrets-key")
    responses += [
        order,
        check_out(guest, product_id, "access-test-secrets-key"),
        guest.send("GET", "/api/v1/orders"),
        guest.send("GET", f"/api/v1/orders/{order.json()['id']}"),
        guest.send("GET", f"/api/v1/orders/{order.json()['id']}/receipt"),
    ]

    guest_token = guest_client.cookies[GUEST_COOKIE]
    instructor_token = instructor_client.cookies[INSTRUCTOR_COOKIE]
    [(password_hash,)] = run_sql(database, "SELECT password_hash FROM instructors")
    secrets = [
        guest_token,
        token_hash(guest_token),
        instructor_token,
        token_hash(instructor_token),
        password_hash,
        ADMIN_PASSWORD,
    ]
    for response in responses:
        for secret in secrets:
            assert secret not in response.text, f"{response.request.method} {response.request.url} leaked a secret"
    # Raw tokens and passwords are never stored either.
    stored = "".join(
        row
        for (row,) in run_sql(
            database,
            "SELECT row_to_json(g)::text FROM guests g UNION ALL "
            "SELECT row_to_json(s)::text FROM instructor_sessions s UNION ALL "
            "SELECT row_to_json(i)::text FROM instructors i",
        )
    )
    assert token_hash(guest_token) in stored and token_hash(instructor_token) in stored
    for secret in (guest_token, instructor_token, ADMIN_PASSWORD):
        assert secret not in stored
