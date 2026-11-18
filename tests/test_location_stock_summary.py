"""GET /inventory/locations/summary：各庫存點合計在 SQL 算好，設定頁不用再抓全部商品。"""

from src.services.inventory_service import RETURNED_LOCATION_ID
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select, _set_location_qty
from tests.test_product_pagination import _create


def test_summary_lists_every_location_with_signed_totals(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    locations = client.get("/api/v1/inventory/locations", headers=headers).json()
    warehouse = next(row["id"] for row in locations if row["name"] == "後方倉庫")
    company = next(row["id"] for row in locations if row["name"] == "公司總倉")

    a = _create(client, headers, "SUM-A")
    b = _create(client, headers, "SUM-B")
    zero = _create(client, headers, "SUM-ZERO")
    gone = _create(client, headers, "SUM-GONE")
    _set_location_qty(a, shelf, 5)
    _set_location_qty(b, shelf, -2)
    _set_location_qty(zero, shelf, 0)
    _set_location_qty(a, warehouse, 3)
    _set_location_qty(b, RETURNED_LOCATION_ID, 1)
    _set_location_qty(gone, company, 7)
    assert client.put(f"/api/v1/products/{gone}", json={"deleted": True}, headers=headers).status_code == 200

    response = client.get("/api/v1/inventory/locations/summary", headers=headers)
    assert response.status_code == 200, response.text
    body = {row["locationId"]: row for row in response.json()}
    assert set(body) == {row["id"] for row in locations}
    assert body[shelf] == {
        "locationId": shelf,
        "locationName": "奇可門市",
        "totalQuantity": 3,
        "productCount": 2,
        "hasNonZeroStock": True,
    }
    assert body[warehouse]["totalQuantity"] == 3
    assert body[warehouse]["productCount"] == 1
    assert body[RETURNED_LOCATION_ID]["totalQuantity"] == 1
    # 下架商品不算進合計（跟 GET /products 一致），但刪除庫存點時仍會擋，所以 hasNonZeroStock 是 true。
    assert body[company]["totalQuantity"] == 0
    assert body[company]["productCount"] == 0
    assert body[company]["hasNonZeroStock"] is True
    empty = next(row for row in locations if row["name"] == "調度暫存")["id"]
    assert body[empty] == {
        "locationId": empty,
        "locationName": "調度暫存",
        "totalQuantity": 0,
        "productCount": 0,
        "hasNonZeroStock": False,
    }

    # 跟前端原本用整份商品清單加總的結果一致。
    products = client.get("/api/v1/products", headers=headers).json()
    for location_id, row in body.items():
        rows = [inv for p in products for inv in p["inventories"] if inv["location"] == location_id]
        assert row["totalQuantity"] == sum(inv["quantity"] for inv in rows)
        assert row["productCount"] == sum(1 for inv in rows if inv["quantity"] != 0)


def test_summary_requires_login(client):
    assert client.get("/api/v1/inventory/locations/summary").status_code == 401
