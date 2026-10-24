"""Catalog, seed data, and persistent carts against PostgreSQL through the HTTP API."""

import os
import subprocess
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import text

from cloudcart.config import Settings
from cloudcart.db import Database
from cloudcart.main import create_app
from cloudcart.seed import seed_database
from helpers import run_sql
from support import without_ambient_settings

SEED_TIMEOUT_SECONDS = 60
# TEST-ONLY instructor password; exactly 12 characters, the shortest the seed command accepts.
ADMIN_PASSWORD = "twelve-chars"
ADMIN_PASSWORD_VARIABLE = "CLOUDCART_SEED_ADMIN_PASSWORD"
GUEST_COOKIE = "cloudcart_guest"
MAX_BODY_BYTES = 16 * 1024


class Shopper:
    """One browser with a live guest session and its CSRF token."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        response = client.get("/api/v1/session")
        assert response.status_code == 200
        self.csrf_token: str = response.json()["csrf_token"]

    def cart(self) -> dict:
        response = self.client.get("/api/v1/cart")
        assert response.status_code == 200
        return response.json()

    def set_quantity(self, product_id: UUID, quantity: object) -> Response:
        return self.client.put(
            f"/api/v1/cart/items/{product_id}",
            json={"quantity": quantity},
            headers={"X-CSRF-Token": self.csrf_token},
        )

    def remove(self, product_id: UUID) -> Response:
        return self.client.delete(f"/api/v1/cart/items/{product_id}", headers={"X-CSRF-Token": self.csrf_token})


@pytest.fixture
def product_ids(database: Database) -> dict[str, UUID]:
    """Seed the catalog the way the seed Job does; return product ids by SKU."""
    with database.session_scope() as session:
        seed_database(session, ADMIN_PASSWORD)
    return products_by_sku(database)


@pytest.fixture
def shopper(open_client: Callable[..., TestClient], product_ids: dict[str, UUID]) -> Shopper:
    return Shopper(open_client())


def products_by_sku(database: Database) -> dict[str, UUID]:
    with database.engine.connect() as connection:
        return dict(connection.execute(text("SELECT sku, id FROM products")).all())


def product_rows(database: Database) -> dict[str, tuple[UUID, int, int]]:
    with database.engine.connect() as connection:
        rows = connection.execute(text("SELECT sku, id, price_cents, stock FROM products")).all()
    return {sku: (product_id, price, stock) for sku, product_id, price, stock in rows}


def run_seed_command(database_url: str, admin_password: str | None) -> subprocess.CompletedProcess[str]:
    """Run `python -m cloudcart.seed` exactly as the seed Job does, without ambient CLOUDCART_* settings."""
    environment = {**without_ambient_settings(os.environ), "CLOUDCART_DATABASE_URL": database_url}
    if admin_password is not None:
        environment[ADMIN_PASSWORD_VARIABLE] = admin_password
    return subprocess.run(
        [sys.executable, "-m", "cloudcart.seed"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=SEED_TIMEOUT_SECONDS,
        check=False,
    )


def test_seed_command_reruns_without_duplicating_or_overwriting_products(
    database: Database, test_database_url: str
) -> None:
    first = run_seed_command(test_database_url, ADMIN_PASSWORD)
    assert first.returncode == 0, first.stderr
    seeded = product_rows(database)
    assert len(seeded) == 8
    assert all(price > 0 and stock > 0 for _, price, stock in seeded.values())

    # Operators may change price and stock between seed runs; a rerun must keep their values.
    changed_sku = sorted(seeded)[0]
    run_sql(database, "UPDATE products SET stock = 3, price_cents = 111 WHERE sku = :sku", sku=changed_sku)

    second = run_seed_command(test_database_url, ADMIN_PASSWORD)
    assert second.returncode == 0, second.stderr

    reseeded = product_rows(database)
    assert reseeded.keys() == seeded.keys()
    assert reseeded[changed_sku] == (seeded[changed_sku][0], 111, 3)
    assert {sku: row for sku, row in reseeded.items() if sku != changed_sku} == {
        sku: row for sku, row in seeded.items() if sku != changed_sku
    }
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM instructors")).scalar_one() == 1


@pytest.mark.parametrize("admin_password", [None, "", "eleven-char"], ids=["missing", "empty", "eleven-chars"])
def test_seed_command_requires_an_admin_password_of_at_least_twelve_characters(
    database: Database, test_database_url: str, admin_password: str | None
) -> None:
    result = run_seed_command(test_database_url, admin_password)

    assert result.returncode != 0
    assert ADMIN_PASSWORD_VARIABLE in result.stderr
    if admin_password:
        assert admin_password not in result.stderr + result.stdout
    assert products_by_sku(database) == {}


def test_catalog_is_public_and_lists_prices_stock_and_images(
    open_client: Callable[..., TestClient], product_ids: dict[str, UUID]
) -> None:
    response = open_client().get("/api/v1/products")

    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    products = response.json()
    assert {UUID(product["id"]) for product in products} == set(product_ids.values())
    for product in products:
        assert set(product) == {"id", "sku", "name", "description", "price_cents", "currency", "stock", "image_path"}
        assert product["currency"] == "USD"
        assert isinstance(product["price_cents"], int) and product["price_cents"] > 0
        assert isinstance(product["stock"], int) and product["stock"] > 0
        assert product["image_path"] == f"/products/{product['sku']}.svg"
        assert product["name"] and product["description"]


def test_new_guest_starts_with_an_empty_cart_at_version_zero(shopper: Shopper) -> None:
    cart = shopper.cart()

    assert UUID(cart["id"])
    assert cart == {"id": cart["id"], "version": 0, "items": [], "total_cents": 0}
    assert shopper.cart() == cart  # reading never changes the cart


def test_cart_changes_survive_a_new_api_instance(
    integration_settings: Settings, product_ids: dict[str, UUID]
) -> None:
    first, second = sorted(product_ids.values())[:2]
    with TestClient(create_app(integration_settings), base_url="https://testserver") as first_api:
        shopper = Shopper(first_api)
        assert shopper.set_quantity(first, 2).status_code == 200
        assert shopper.set_quantity(second, 1).status_code == 200
        before = shopper.cart()
        guest_token = first_api.cookies[GUEST_COOKIE]

    with TestClient(
        create_app(integration_settings), base_url="https://testserver", cookies={GUEST_COOKIE: guest_token}
    ) as second_api:
        after = second_api.get("/api/v1/cart")

    assert after.status_code == 200
    assert after.json() == before
    assert before["version"] == 2
    assert {(item["product_id"], item["quantity"]) for item in before["items"]} == {(str(first), 2), (str(second), 1)}


def test_put_sets_quantity_and_every_change_increments_version_by_one(
    shopper: Shopper, database: Database, product_ids: dict[str, UUID]
) -> None:
    rows = product_rows(database)
    first_sku, second_sku = sorted(product_ids)[:2]
    first, first_price = rows[first_sku][0], rows[first_sku][1]
    second, second_price = rows[second_sku][0], rows[second_sku][1]
    cart_id = shopper.cart()["id"]

    added = shopper.set_quantity(first, 2)
    assert added.status_code == 200
    assert added.json() == {
        "id": cart_id,
        "version": 1,
        "items": [{"product_id": str(first), "quantity": 2, "unit_price_cents": first_price}],
        "total_cents": 2 * first_price,
    }

    replaced = shopper.set_quantity(first, 5).json()  # sets the line quantity; does not add to it
    assert replaced["version"] == 2
    assert replaced["items"] == [{"product_id": str(first), "quantity": 5, "unit_price_cents": first_price}]

    unchanged_quantity = shopper.set_quantity(first, 5).json()
    assert unchanged_quantity["version"] == 3

    both = shopper.set_quantity(second, 1).json()
    assert both["version"] == 4
    assert both["total_cents"] == 5 * first_price + second_price

    removed = shopper.remove(first)
    assert removed.status_code == 200
    assert removed.json() == {
        "id": cart_id,
        "version": 5,
        "items": [{"product_id": str(second), "quantity": 1, "unit_price_cents": second_price}],
        "total_cents": second_price,
    }
    assert shopper.cart() == removed.json()


def test_cart_shows_current_product_prices(shopper: Shopper, database: Database, product_ids: dict[str, UUID]) -> None:
    sku = sorted(product_ids)[0]
    assert shopper.set_quantity(product_ids[sku], 3).status_code == 200

    run_sql(database, "UPDATE products SET price_cents = 250 WHERE sku = :sku", sku=sku)

    cart = shopper.cart()
    assert cart["items"][0]["unit_price_cents"] == 250
    assert cart["total_cents"] == 750
    assert cart["version"] == 1


@pytest.mark.parametrize("quantity", [0, -1, 11, 1000, 2.5, "3", True, None])
def test_quantity_outside_one_to_ten_is_rejected(
    shopper: Shopper, product_ids: dict[str, UUID], quantity: object
) -> None:
    product_id = next(iter(product_ids.values()))

    response = shopper.set_quantity(product_id, quantity)

    assert response.status_code == 422
    assert shopper.cart()["version"] == 0
    assert shopper.cart()["items"] == []


@pytest.mark.parametrize(
    "body", [{}, {"quantity": 1, "price_cents": 1}, [1]], ids=["missing", "unknown-field", "array"]
)
def test_cart_item_body_must_match_the_schema_exactly(
    shopper: Shopper, product_ids: dict[str, UUID], body: object
) -> None:
    product_id = next(iter(product_ids.values()))

    response = shopper.client.put(
        f"/api/v1/cart/items/{product_id}", json=body, headers={"X-CSRF-Token": shopper.csrf_token}
    )

    assert response.status_code == 422
    assert shopper.cart()["version"] == 0


def test_quantity_limits_one_and_ten_are_accepted(shopper: Shopper, product_ids: dict[str, UUID]) -> None:
    first, second = sorted(product_ids.values())[:2]

    assert shopper.set_quantity(first, 1).status_code == 200
    assert shopper.set_quantity(second, 10).status_code == 200


def test_quantity_above_current_stock_conflicts(
    shopper: Shopper, database: Database, product_ids: dict[str, UUID]
) -> None:
    sku = sorted(product_ids)[0]
    run_sql(database, "UPDATE products SET stock = 3 WHERE sku = :sku", sku=sku)

    too_many = shopper.set_quantity(product_ids[sku], 4)
    assert too_many.status_code == 409
    assert shopper.cart()["version"] == 0

    assert shopper.set_quantity(product_ids[sku], 3).status_code == 200

    run_sql(database, "UPDATE products SET stock = 0 WHERE sku = :sku", sku=sku)
    assert shopper.set_quantity(product_ids[sku], 1).status_code == 409
    assert shopper.cart()["items"][0]["quantity"] == 3


def test_cart_holds_at_most_twenty_distinct_products(
    shopper: Shopper, database: Database, product_ids: dict[str, UUID]
) -> None:
    for number in range(21 - len(product_ids)):
        run_sql(
            database,
            "INSERT INTO products (id, sku, name, description, price_cents, currency, stock) "
            "VALUES (:id, :sku, :name, 'Extra product for the line limit.', 100, 'USD', 5)",
            id=uuid4(),
            sku=f"extra-{number}",
            name=f"Extra {number}",
        )
    all_products = sorted(products_by_sku(database).values())
    assert len(all_products) == 21

    for product_id in all_products[:20]:
        assert shopper.set_quantity(product_id, 1).status_code == 200

    twenty_first = shopper.set_quantity(all_products[20], 1)
    assert twenty_first.status_code == 409

    cart = shopper.cart()
    assert len(cart["items"]) == 20
    assert cart["version"] == 20
    # Changing an existing line is still allowed at the limit.
    assert shopper.set_quantity(all_products[0], 2).status_code == 200


def test_unknown_products_and_missing_lines_are_not_found(shopper: Shopper, product_ids: dict[str, UUID]) -> None:
    in_cart, not_in_cart = sorted(product_ids.values())[:2]
    assert shopper.set_quantity(in_cart, 1).status_code == 200

    assert shopper.set_quantity(uuid4(), 1).status_code == 404
    assert shopper.remove(uuid4()).status_code == 404
    assert shopper.remove(not_in_cart).status_code == 404
    assert shopper.cart()["version"] == 1


def test_concurrent_changes_each_increment_version_exactly_once(
    shopper: Shopper, product_ids: dict[str, UUID]
) -> None:
    products = sorted(product_ids.values())

    # The guest has no cart row yet, so the first requests also race to create it.
    with ThreadPoolExecutor(max_workers=len(products)) as pool:
        responses = list(pool.map(lambda product_id: shopper.set_quantity(product_id, 1), products))

    assert [response.status_code for response in responses] == [200] * len(products)
    assert sorted(response.json()["version"] for response in responses) == list(range(1, len(products) + 1))
    cart = shopper.cart()
    assert cart["version"] == len(products)
    assert len(cart["items"]) == len(products)


def test_request_bodies_over_16_kib_are_rejected_before_parsing(
    shopper: Shopper, product_ids: dict[str, UUID]
) -> None:
    url = f"/api/v1/cart/items/{next(iter(product_ids.values()))}"
    headers = {"X-CSRF-Token": shopper.csrf_token, "Content-Type": "application/json"}
    # Invalid JSON: a 413 rather than a 422 proves the size check runs before parsing.
    oversized = b"{" + b" " * MAX_BODY_BYTES

    declared = shopper.client.put(url, content=oversized, headers=headers)
    assert declared.status_code == 413

    chunked = shopper.client.put(url, content=iter([oversized[:8000], oversized[8000:]]), headers=headers)
    assert chunked.status_code == 413

    at_limit = shopper.client.put(url, content=b'{"quantity": 1}'.ljust(MAX_BODY_BYTES), headers=headers)
    assert at_limit.status_code == 200
    assert shopper.cart()["version"] == 1


def test_openapi_documents_closed_bounded_request_schemas(open_client: Callable[..., TestClient]) -> None:
    document = open_client().get("/openapi.json").json()
    paths = document["paths"]
    assert {
        (path, method)
        for path, operations in paths.items()
        for method in operations
        if path.startswith("/api/v1/")
    } == {
        ("/api/v1/products", "get"),
        ("/api/v1/session", "get"),
        ("/api/v1/cart", "get"),
        ("/api/v1/cart/items/{product_id}", "put"),
        ("/api/v1/cart/items/{product_id}", "delete"),
        ("/api/v1/admin/login", "post"),
        ("/api/v1/admin/products/{product_id}/stock", "put"),
        ("/api/v1/orders", "get"),
        ("/api/v1/orders", "post"),
        ("/api/v1/orders/{order_id}", "get"),
        ("/api/v1/orders/{order_id}/receipt", "get"),
    }

    def request_schema(path: str, method: str) -> dict:
        reference = paths[path][method]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        return document["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    quantity = request_schema("/api/v1/cart/items/{product_id}", "put")
    login = request_schema("/api/v1/admin/login", "post")
    stock = request_schema("/api/v1/admin/products/{product_id}/stock", "put")
    for schema in (quantity, login, stock):
        assert schema["additionalProperties"] is False
    assert (quantity["properties"]["quantity"]["minimum"], quantity["properties"]["quantity"]["maximum"]) == (1, 10)
    assert (stock["properties"]["stock"]["minimum"], stock["properties"]["stock"]["maximum"]) == (0, 100_000)
    assert all("maxLength" in login["properties"][field] for field in ("username", "password"))
    cart = document["components"]["schemas"]["CartView"]
    assert set(cart["required"]) == {"id", "version", "items", "total_cents"}
