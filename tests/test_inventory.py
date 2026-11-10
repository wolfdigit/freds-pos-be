import pytest

from src.core.exceptions import BusinessException
from src.db.session import SessionFactory
from src.schemas.common import BusinessErrorCode
from src.schemas.inventory import DeleteInventoryLocationRequest
from src.services.inventory_service import RETURNED_LOCATION_ID, InventoryService, ensure_locations
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select, _stock_qty


def _product(client, token: str, sku: str = "SKU-INV") -> str:
    response = client.post(
        "/api/v1/products",
        json={"sku": sku, "barcode": sku, "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_receipt_transfer_adjust_and_store_quantity(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    product_id = _product(client, login["token"])

    locations = client.get("/api/v1/inventory/locations", headers=headers)
    assert locations.status_code == 200
    warehouse = next(row for row in locations.json() if row["name"] == "後方倉庫")
    assert shelf in [row["id"] for row in locations.json()]

    receipt = client.post(
        "/api/v1/inventory/receipts",
        json={"locationId": shelf, "supplier": "甲商", "items": [{"productId": product_id, "quantity": 4}]},
        headers=headers,
    )
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["totalQuantity"] == 4
    assert _stock_qty(product_id, shelf) == 4

    listed = client.get(f"/api/v1/products/{product_id}", headers=headers)
    body = listed.json()
    assert body["loginStoreQuantity"] == 4
    assert body["totalInventory"] == 4
    shelf_row = next(row for row in body["inventories"] if row["location"] == shelf)
    assert shelf_row["quantity"] == 4
    assert body["loginStoreReturnedQuantity"] == 0

    short = client.post(
        "/api/v1/inventory/transfers",
        json={"productId": product_id, "fromLocation": shelf, "toLocation": warehouse["id"], "quantity": 9},
        headers=headers,
    )
    assert short.status_code == 409
    assert short.json()["code"] == "INSUFFICIENT_INVENTORY"

    moved = client.post(
        "/api/v1/inventory/transfers",
        json={
            "productId": product_id,
            "fromLocation": shelf,
            "toLocation": warehouse["id"],
            "quantity": 1,
        },
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert _stock_qty(product_id, shelf) == 3
    assert _stock_qty(product_id, warehouse["id"]) == 1

    adjusted = client.post(
        "/api/v1/inventory/adjustments",
        json={"productId": product_id, "location": shelf, "newQuantity": -2, "reason": "盤點"},
        headers=headers,
    )
    assert adjusted.status_code == 200, adjusted.text
    assert _stock_qty(product_id, shelf) == -2

    duplicate = client.post("/api/v1/inventory/locations", json={"name": "後方倉庫"}, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "LOCATION_NAME_TAKEN"


def test_move_all_then_delete_rebinds_the_store(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    product_id = _product(client, login["token"], "SKU-MOVE")
    client.post(
        "/api/v1/inventory/adjustments",
        json={"productId": product_id, "location": shelf, "newQuantity": -3, "reason": "退貨盤點"},
        headers=headers,
    )
    blocked = client.request("DELETE", f"/api/v1/inventory/locations/{shelf}", json={}, headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "LOCATION_NOT_EMPTY"

    locations = client.get("/api/v1/inventory/locations", headers=headers).json()
    warehouse = next(row for row in locations if row["name"] == "後方倉庫")
    moved = client.post(
        "/api/v1/inventory/transfers/all",
        json={"fromLocation": shelf, "toLocation": warehouse["id"]},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert _stock_qty(product_id, shelf) == 0
    assert _stock_qty(product_id, warehouse["id"]) == -3

    missing_target = client.request("DELETE", f"/api/v1/inventory/locations/{shelf}", json={}, headers=headers)
    assert missing_target.status_code == 400
    assert missing_target.json()["code"] == "INVALID_LOCATION_TRANSFER"

    deleted = client.request(
        "DELETE",
        f"/api/v1/inventory/locations/{shelf}",
        json={"rebindToLocation": warehouse["id"]},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    rebound = deleted.json()["reboundStoreNames"]
    assert rebound[0]["name"] == "奇可門市"
    assert rebound[0]["binding"] == "normal"
    assert rebound[0]["inventoryLocationId"] == warehouse["id"]


def test_cannot_delete_the_last_location(client):
    db = SessionFactory()
    try:
        rows = ensure_locations(db)
        db.commit()
        service = InventoryService(db)
        for row in rows[:-1]:
            service.delete_location(row.id, DeleteInventoryLocationRequest())
        with pytest.raises(BusinessException) as caught:
            service.delete_location(rows[-1].id, DeleteInventoryLocationRequest())
        assert caught.value.code == BusinessErrorCode.LAST_LOCATION
    finally:
        db.close()


def test_condition_change_releases_returned_stock(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    product_id = _product(client, login["token"], "SKU-RET")
    sale = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{"productId": product_id, "quantity": 2}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": 200}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    item_id = sale.json()["order"]["items"][0]["id"]
    order_id = sale.json()["order"]["id"]
    returned = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": product_id,
                "quantity": -1,
                "originalOrderId": order_id,
                "originalOrderItemId": item_id,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": -100}],
        },
        headers=headers,
    )
    assert returned.status_code == 201, returned.text
    assert returned.json()["order"]["items"][0]["inventoryLocationId"] == RETURNED_LOCATION_ID
    assert _stock_qty(product_id, shelf) == -2
    assert _stock_qty(product_id, RETURNED_LOCATION_ID) == 1

    released = client.post(
        "/api/v1/inventory/transfers",
        json={
            "productId": product_id,
            "fromLocation": RETURNED_LOCATION_ID,
            "toLocation": shelf,
            "quantity": 1,
        },
        headers=headers,
    )
    assert released.status_code == 200, released.text
    assert _stock_qty(product_id, RETURNED_LOCATION_ID) == 0
    assert _stock_qty(product_id, shelf) == -1


def test_store_may_use_one_location_for_normal_and_returned(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    login = _login(client, google_jwks)
    created = client.post(
        "/api/v1/system/stores",
        json={
            "name": "共用點門市",
            "inventoryLocationId": RETURNED_LOCATION_ID,
            "returnedInventoryLocationId": RETURNED_LOCATION_ID,
        },
        headers=_auth(login["token"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["inventoryLocationId"] == RETURNED_LOCATION_ID
    assert body["returnedInventoryLocationId"] == RETURNED_LOCATION_ID


def test_total_inventory_includes_warehouse_returns_and_negatives(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    product_id = _product(client, login["token"], "SKU-SUM")
    locations = client.get("/api/v1/inventory/locations", headers=headers).json()
    warehouse = next(row for row in locations if row["name"] == "後方倉庫")
    client.post(
        "/api/v1/inventory/receipts",
        json={"locationId": shelf, "items": [{"productId": product_id, "quantity": 4}]},
        headers=headers,
    )
    client.post(
        "/api/v1/inventory/adjustments",
        json={"productId": product_id, "location": warehouse["id"], "newQuantity": 1, "reason": "入倉"},
        headers=headers,
    )
    adjusted = client.post(
        "/api/v1/inventory/adjustments",
        json={"productId": product_id, "location": RETURNED_LOCATION_ID, "newQuantity": -3, "reason": "退貨盤點"},
        headers=headers,
    )
    assert adjusted.status_code == 200, adjusted.text
    body = client.get(f"/api/v1/products/{product_id}", headers=headers).json()
    assert body["loginStoreQuantity"] == 4
    assert body["loginStoreReturnedQuantity"] == -3
    assert body["totalInventory"] == 2
    listed = client.get("/api/v1/products", params={"inInventoryOnly": True}, headers=headers)
    assert product_id in [row["id"] for row in listed.json()]

    hidden_id = _product(client, login["token"], "SKU-NEG")
    client.post(
        "/api/v1/inventory/adjustments",
        json={"productId": hidden_id, "location": shelf, "newQuantity": -5, "reason": "盤虧"},
        headers=headers,
    )
    only_negative = client.get("/api/v1/products", params={"inInventoryOnly": True}, headers=headers)
    assert hidden_id not in [row["id"] for row in only_negative.json()]


def test_batch_adjust_requires_a_reason_and_can_set_returned_location_negative(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    product_id = _product(client, login["token"], "SKU-BATCH")
    blank = client.post(
        "/api/v1/inventory/batch-adjustments",
        json={
            "note": "   ",
            "adjustments": [{
                "productId": product_id,
                "sku": "SKU-BATCH",
                "name": "車",
                "brand": "Brand",
                "summaryText": "退貨",
                "changes": [{
                    "location": RETURNED_LOCATION_ID,
                    "locationName": "退貨品",
                    "oldQty": 0,
                    "newQty": -4,
                    "diff": -4,
                }],
            }],
        },
        headers=headers,
    )
    assert blank.status_code == 422
    applied = client.post(
        "/api/v1/inventory/batch-adjustments",
        json={
            "note": "退貨盤點",
            "adjustments": [{
                "productId": product_id,
                "sku": "SKU-BATCH",
                "name": "車",
                "brand": "Brand",
                "summaryText": "退貨",
                "changes": [{
                    "location": RETURNED_LOCATION_ID,
                    "locationName": "退貨品",
                    "oldQty": 0,
                    "newQty": -4,
                    "diff": -4,
                }],
            }],
        },
        headers=headers,
    )
    assert applied.status_code == 200, applied.text
    assert _stock_qty(product_id, RETURNED_LOCATION_ID) == -4
