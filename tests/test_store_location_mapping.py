import uuid

from sqlalchemy import select

from src.db.session import SessionFactory
from src.models.location import StockLocation
from src.models.product import ProductStock
from src.services.checkout_service import STORE_LOCATION
from src.services.inventory_service import DEFAULT_STORE_LOCATION_ID
from tests.test_auth import (
    ADMIN_EMAIL,
    STAFF_EMAIL,
    _add_account,
    _add_store,
    _auth,
    _login,
    _select,
)


def _qty(product_id: str, location_id: str) -> int:
    db = SessionFactory()
    try:
        row = db.scalar(
            select(ProductStock).where(
                ProductStock.product_id == product_id,
                ProductStock.location == location_id,
            )
        )
        return 0 if row is None else row.quantity
    finally:
        db.close()


def _set_qty(product_id: str, location_id: str, quantity: int) -> None:
    db = SessionFactory()
    try:
        row = db.scalar(
            select(ProductStock).where(
                ProductStock.product_id == product_id,
                ProductStock.location == location_id,
            )
        )
        if row is None:
            db.add(
                ProductStock(
                    product_id=product_id,
                    location=location_id,
                    location_name=location_id,
                    quantity=quantity,
                )
            )
        else:
            row.quantity = quantity
        db.commit()
    finally:
        db.close()


def _add_location(name: str) -> str:
    location_id = f"loc-{uuid.uuid4().hex}"
    db = SessionFactory()
    try:
        db.add(
            StockLocation(
                id=location_id,
                name=name,
                icon="📍",
                is_default=False,
                display_order=9,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()
    return location_id


def _sale(client, token: str, product_id: str, amount: int = 100, key: str | None = None):
    headers = _auth(token)
    if key:
        headers["X-Idempotency-Key"] = key
    return client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{"productId": product_id, "quantity": 1}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": amount}],
        },
        headers=headers,
    )


def test_shared_default_two_stores_and_idempotent_replay(client, google_jwks):
    assert DEFAULT_STORE_LOCATION_ID == STORE_LOCATION == "e1a10001-0000-4000-8000-000000000001"
    _add_account(ADMIN_EMAIL)
    _add_store("甲店")
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    created = client.post(
        "/api/v1/system/stores",
        json={"name": "乙店"},
        headers=_auth(login["token"]),
    )
    assert created.status_code == 201, created.text
    assert created.json()["stockLocationId"] == DEFAULT_STORE_LOCATION_ID
    assert created.json()["stockLocationName"] == "門市現貨"
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-MAP", "barcode": "444", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)

    first = _sale(client, login["token"], product_id, key="map-replay")
    assert first.status_code == 201, first.text
    assert first.json()["order"]["branchName"] == "甲店"
    assert first.json()["order"]["totalAmount"] == 100
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0

    replay = _sale(client, login["token"], product_id, key="map-replay")
    assert replay.status_code == 201, replay.text
    assert replay.json()["order"]["id"] == first.json()["order"]["id"]
    assert replay.json()["order"]["totalAmount"] == 100
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0

    _select(client, login["token"], "乙店")
    blocked = _sale(client, login["token"], product_id)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "INSUFFICIENT_STORE_STOCK"
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0


def test_separate_locations_mapping_update_and_return_to_current_store(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_account(STAFF_EMAIL, "staff", "店員")
    warehouse = _add_location("後方倉二")
    _add_store("甲店")
    _add_store("乙店", warehouse)
    admin = _login(client, google_jwks, ADMIN_EMAIL)
    staff = _login(client, google_jwks, STAFF_EMAIL)
    _select(client, admin["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-ISO", "barcode": "555", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(admin["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)
    _set_qty(product_id, warehouse, 3)

    sale = _sale(client, admin["token"], product_id)
    assert sale.status_code == 201, sale.text
    order = sale.json()["order"]
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0
    assert _qty(product_id, warehouse) == 3

    forbidden = client.put(
        "/api/v1/system/stores/乙店/stock-location",
        json={"stockLocationId": DEFAULT_STORE_LOCATION_ID},
        headers=_auth(staff["token"]),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"
    switched = _select(client, staff["token"], "乙店")
    assert switched["storeName"] == "乙店"

    missing = client.put(
        "/api/v1/system/stores/甲店/stock-location",
        json={"stockLocationId": "does-not-exist"},
        headers=_auth(admin["token"]),
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "LOCATION_NOT_FOUND"

    remapped = client.put(
        "/api/v1/system/stores/甲店/stock-location",
        json={"stockLocationId": warehouse},
        headers=_auth(admin["token"]),
    )
    assert remapped.status_code == 200, remapped.text
    assert remapped.json()["stockLocationId"] == warehouse
    original = client.get(f"/api/v1/checkout/orders/{order['id']}", headers=_auth(admin["token"]))
    assert original.json()["branchName"] == "甲店"
    assert original.json()["totalAmount"] == 100
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0
    assert _qty(product_id, warehouse) == 3

    _select(client, admin["token"], "乙店")
    returned = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": product_id,
                "quantity": -1,
                "originalOrderId": order["id"],
                "originalOrderItemId": order["items"][0]["id"],
                "restock": True,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金退款", "amount": -100}],
        },
        headers=_auth(admin["token"]),
    )
    assert returned.status_code == 201, returned.text
    assert returned.json()["order"]["branchName"] == "乙店"
    assert returned.json()["order"]["totalAmount"] == -100
    assert _qty(product_id, warehouse) == 4
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0

    blocked_delete = client.request(
        "DELETE",
        f"/api/v1/inventory/locations/{warehouse}",
        json={"transferToLocation": DEFAULT_STORE_LOCATION_ID, "reason": "停用"},
        headers=_auth(admin["token"]),
    )
    assert blocked_delete.status_code == 409
    assert blocked_delete.json()["code"] == "STOCK_LOCATION_IN_USE"
    assert _qty(product_id, warehouse) == 4


def test_restock_false_does_not_change_current_location(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    other = _add_location("退貨倉")
    _add_store("甲店")
    _add_store("乙店", other)
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    product = client.post(
        "/api/v1/products",
        json={"sku": "SKU-NO", "barcode": "666", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    product_id = product.json()["id"]
    _set_qty(product_id, DEFAULT_STORE_LOCATION_ID, 1)
    sale = _sale(client, login["token"], product_id)
    order = sale.json()["order"]
    _select(client, login["token"], "乙店")
    returned = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": product_id,
                "quantity": -1,
                "originalOrderId": order["id"],
                "originalOrderItemId": order["items"][0]["id"],
                "restock": False,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金退款", "amount": -100}],
        },
        headers=_auth(login["token"]),
    )
    assert returned.status_code == 201, returned.text
    assert _qty(product_id, other) == 0
    assert _qty(product_id, DEFAULT_STORE_LOCATION_ID) == 0


def test_store_without_location_requires_explicit_id_when_shared_row_is_gone(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    other = _add_location("只剩這倉")
    _add_store("甲店", other)
    login = _login(client, google_jwks)
    _select(client, login["token"], "甲店")
    db = SessionFactory()
    try:
        shared = db.get(StockLocation, DEFAULT_STORE_LOCATION_ID)
        if shared is not None:
            db.delete(shared)
            db.commit()
    finally:
        db.close()
    created = client.post("/api/v1/system/stores", json={"name": "丙店"}, headers=_auth(login["token"]))
    assert created.status_code == 409
    assert created.json()["code"] == "STOCK_LOCATION_REQUIRED"
    explicit = client.post(
        "/api/v1/system/stores",
        json={"name": "丙店", "stockLocationId": other},
        headers=_auth(login["token"]),
    )
    assert explicit.status_code == 201, explicit.text
    assert explicit.json()["stockLocationId"] == other
