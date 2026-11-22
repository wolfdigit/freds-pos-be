from src.services.inventory_service import (
    DEFAULT_STORE_LOCATION_ID,
    PREORDER_LOCATION_ID,
    RETURNED_LOCATION_ID,
)
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select, _stock_qty
from tests.test_inventory import _product


def _admin(client, google_jwks) -> dict:
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    return {"headers": _auth(login["token"]), "token": login["token"], "shelf": shelf}


def test_new_store_defaults_preorder_binding_and_rebind_keeps_or_changes_it(client, google_jwks):
    ctx = _admin(client, google_jwks)
    headers = ctx["headers"]
    created = client.post(
        "/api/v1/system/stores",
        json={
            "name": "新門市",
            "inventoryLocationId": DEFAULT_STORE_LOCATION_ID,
            "returnedInventoryLocationId": RETURNED_LOCATION_ID,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["preorderInventoryLocationId"] == PREORDER_LOCATION_ID
    assert body["preorderInventoryLocationName"] == "預購保留"
    assert body["returnedInventoryLocationId"] == RETURNED_LOCATION_ID

    kept = client.put(
        "/api/v1/system/stores/新門市",
        json={"inventoryLocationId": DEFAULT_STORE_LOCATION_ID, "returnedInventoryLocationId": ctx["shelf"]},
        headers=headers,
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["preorderInventoryLocationId"] == PREORDER_LOCATION_ID
    assert kept.json()["returnedInventoryLocationId"] == ctx["shelf"]

    changed = client.put(
        "/api/v1/system/stores/新門市",
        json={
            "inventoryLocationId": DEFAULT_STORE_LOCATION_ID,
            "returnedInventoryLocationId": RETURNED_LOCATION_ID,
            "preorderInventoryLocationId": ctx["shelf"],
        },
        headers=headers,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["preorderInventoryLocationId"] == ctx["shelf"]

    listed = client.get("/api/v1/system/stores", headers=headers)
    assert listed.status_code == 200
    row = next(store for store in listed.json() if store["name"] == "新門市")
    assert row["preorderInventoryLocationName"] == "奇可門市"


def test_locations_report_system_role_and_preorder_bindings(client, google_jwks):
    ctx = _admin(client, google_jwks)
    response = client.get("/api/v1/inventory/locations", headers=ctx["headers"])
    assert response.status_code == 200, response.text
    by_id = {row["id"]: row for row in response.json()}
    assert by_id[PREORDER_LOCATION_ID]["systemRole"] == "preorder"
    assert by_id[PREORDER_LOCATION_ID]["preorderStoreNames"] == ["奇可門市"]
    assert by_id[RETURNED_LOCATION_ID]["systemRole"] == "defective"
    assert by_id[RETURNED_LOCATION_ID]["name"] == "退貨品"
    assert by_id[ctx["shelf"]]["systemRole"] is None

    blocked = client.request("DELETE", f"/api/v1/inventory/locations/{PREORDER_LOCATION_ID}", json={}, headers=ctx["headers"])
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "SYSTEM_LOCATION"


def test_deleting_a_location_rebinds_the_preorder_binding_too(client, google_jwks):
    ctx = _admin(client, google_jwks)
    headers = ctx["headers"]
    extra = client.post("/api/v1/inventory/locations", json={"name": "臨時預購區"}, headers=headers)
    assert extra.status_code == 201, extra.text
    extra_id = extra.json()["id"]
    rebind = client.put(
        "/api/v1/system/stores/奇可門市",
        json={
            "inventoryLocationId": ctx["shelf"],
            "returnedInventoryLocationId": RETURNED_LOCATION_ID,
            "preorderInventoryLocationId": extra_id,
        },
        headers=headers,
    )
    assert rebind.status_code == 200, rebind.text

    without_target = client.request("DELETE", f"/api/v1/inventory/locations/{extra_id}", json={}, headers=headers)
    assert without_target.status_code == 400

    deleted = client.request(
        "DELETE",
        f"/api/v1/inventory/locations/{extra_id}",
        json={"rebindToLocation": PREORDER_LOCATION_ID},
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["reboundStoreNames"] == [
        {"name": "奇可門市", "binding": "preorder", "inventoryLocationId": PREORDER_LOCATION_ID}
    ]


def test_preorder_pickup_deducts_from_the_preorder_location(client, google_jwks):
    ctx = _admin(client, google_jwks)
    headers = ctx["headers"]
    product_id = _product(client, ctx["token"], "SKU-PRE")
    member = client.post("/api/v1/customers", json={"name": "王小明", "phone": "0911222333"}, headers=headers)
    assert member.status_code == 201, member.text

    sale = client.post(
        "/api/v1/checkout/orders",
        json={
            "customerId": member.json()["id"],
            "items": [
                {"productId": product_id, "quantity": 2},
                {"productId": product_id, "quantity": 1, "preorderPickup": True},
                # 預購取貨也可以同時點數折抵。
                {"productId": product_id, "quantity": 1, "unitPrice": 0, "pointsDiscountApplied": True, "preorderPickup": True},
            ],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": 300}],
        },
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    order = sale.json()["order"]
    assert [item["preorderPickup"] for item in order["items"]] == [False, True, True]
    assert order["items"][1]["inventoryLocationId"] == PREORDER_LOCATION_ID
    assert order["items"][0]["inventoryLocationId"] == ctx["shelf"]
    assert order["pointsDiscountAmount"] == 100
    assert _stock_qty(product_id, ctx["shelf"]) == -2
    assert _stock_qty(product_id, PREORDER_LOCATION_ID) == -2

    product = client.get(f"/api/v1/products/{product_id}", headers=headers)
    assert product.status_code == 200
    assert product.json()["loginStorePreorderQuantity"] == -2
    assert product.json()["loginStoreQuantity"] == -2

    # 退貨照原本的回庫勾選，不能標預購取貨；沒標時回到門市庫存。
    line_id = order["items"][1]["id"]
    flagged = client.post(
        "/api/v1/checkout/orders",
        json={
            "customerId": member.json()["id"],
            "items": [{
                "productId": product_id, "quantity": -1, "originalOrderId": order["id"],
                "originalOrderItemId": line_id, "preorderPickup": True,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": -100}],
        },
        headers=headers,
    )
    assert flagged.status_code == 422
    assert "退貨品項不能標記預購取貨" in flagged.text
    refund = client.post(
        "/api/v1/checkout/orders",
        json={
            "customerId": member.json()["id"],
            "items": [{
                "productId": product_id, "quantity": -1, "originalOrderId": order["id"], "originalOrderItemId": line_id,
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": -100}],
        },
        headers=headers,
    )
    assert refund.status_code == 201, refund.text
    assert refund.json()["order"]["items"][0]["preorderPickup"] is False
    assert _stock_qty(product_id, ctx["shelf"]) == -1
    assert _stock_qty(product_id, PREORDER_LOCATION_ID) == -2
