"""結帳整張訂單只鎖一次庫存點，品項多寡不影響鎖定查詢數；鎖的順序維持 庫存點(id 順序) → 門市 → 庫存列。"""

import re
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from src.db.session import engine
from src.services.inventory_service import RETURNED_LOCATION_ID
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select, _stock_qty
from tests.test_inventory import _product

postgres_only = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="FOR UPDATE is only emitted on PostgreSQL; set TEST_DATABASE_URI",
)


@contextmanager
def _recorded_sql():
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def _location_queries(statements: list[str]) -> list[str]:
    return [s for s in statements if re.search(r"\bFROM inventory_location\b", s)]


def _ready(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    products = [_product(client, login["token"], f"SKU-LOCK-{n}") for n in range(4)]
    return headers, shelf, products


def _order(client, headers, items, amount):
    with _recorded_sql() as statements:
        response = client.post(
            "/api/v1/checkout/orders",
            json={
                "items": items,
                "shippingFee": 0,
                "payments": [{"type": "cash", "name": "現金", "amount": amount}],
            },
            headers=headers,
        )
    assert response.status_code == 201, response.text
    return response.json()["order"], statements


def test_location_locking_does_not_grow_with_the_number_of_lines(client, google_jwks):
    headers, shelf, products = _ready(client, google_jwks)
    _one, one_line = _order(client, headers, [{"productId": products[0], "quantity": 1}], 100)
    order, four_lines = _order(
        client,
        headers,
        [{"productId": product_id, "quantity": 1} for product_id in products],
        400,
    )
    location_count = len(client.get("/api/v1/inventory/locations", headers=headers).json())
    # 一次列出庫存點 id + 每個庫存點鎖一次；每個品項不再重鎖或重查庫存點。
    assert len(_location_queries(one_line)) == 1 + location_count
    assert len(_location_queries(four_lines)) == 1 + location_count
    assert [item["inventoryLocationId"] for item in order["items"]] == [shelf] * 4
    assert _stock_qty(products[0], shelf) == -2
    assert all(_stock_qty(product_id, shelf) == -1 for product_id in products[1:])


def test_mixed_sale_and_returns_still_use_the_right_locations(client, google_jwks):
    headers, shelf, products = _ready(client, google_jwks)
    sale, _ = _order(client, headers, [{"productId": products[0], "quantity": 2}, {"productId": products[1], "quantity": 1}], 300)
    items = sale["items"]
    mixed, _ = _order(
        client,
        headers,
        [
            {"productId": products[2], "quantity": 1},
            {
                "productId": products[0],
                "quantity": -1,
                "originalOrderId": sale["id"],
                "originalOrderItemId": items[0]["id"],
                "restock": False,
            },
            {
                "productId": products[1],
                "quantity": -1,
                "originalOrderId": sale["id"],
                "originalOrderItemId": items[1]["id"],
            },
        ],
        -100,
    )
    assert [item["inventoryLocationId"] for item in mixed["items"]] == [shelf, RETURNED_LOCATION_ID, shelf]
    assert _stock_qty(products[0], shelf) == -2
    assert _stock_qty(products[0], RETURNED_LOCATION_ID) == 1
    assert _stock_qty(products[1], shelf) == 0
    assert _stock_qty(products[2], shelf) == -1


@postgres_only
def test_locks_are_taken_once_in_location_store_stock_order(client, google_jwks):
    headers, _shelf, products = _ready(client, google_jwks)
    _order_body, statements = _order(
        client,
        headers,
        [{"productId": product_id, "quantity": 1} for product_id in products],
        400,
    )
    locks = [s for s in statements if re.search(r"\bFOR UPDATE\b", s)]
    location_locks = [i for i, s in enumerate(locks) if "FROM inventory_location" in s]
    store_locks = [i for i, s in enumerate(locks) if "FROM store_branch" in s]
    stock_locks = [i for i, s in enumerate(locks) if "FROM product_inventory" in s]
    location_count = len(client.get("/api/v1/inventory/locations", headers=headers).json())
    assert len(location_locks) == location_count
    assert len(store_locks) == 1
    assert len(stock_locks) == len(products)
    assert max(location_locks) < min(store_locks) < min(stock_locks)
