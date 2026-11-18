"""GET /products 的數量篩選（庫存頁低庫存／缺貨／有現貨），在 SQL 篩完再分頁。"""

from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select, _set_location_qty
from tests.test_product_pagination import _create, _get


def _catalog(client, google_jwks, *, select_store: bool = True):
    _add_account(ADMIN_EMAIL)
    shelf = _add_store("奇可門市")
    login = _login(client, google_jwks)
    if select_store:
        _select(client, login["token"], "奇可門市")
    headers = _auth(login["token"])
    locations = client.get("/api/v1/inventory/locations", headers=headers).json()
    warehouse = next(row["id"] for row in locations if row["name"] == "後方倉庫")
    ids = {sku: _create(client, headers, sku) for sku in ["A-NONE", "B-TWO", "C-THREE", "D-NEG", "E-WH", "F-GONE"]}
    _set_location_qty(ids["B-TWO"], shelf, 2)
    _set_location_qty(ids["C-THREE"], shelf, 3)
    _set_location_qty(ids["C-THREE"], warehouse, 1)
    _set_location_qty(ids["D-NEG"], shelf, -1)
    _set_location_qty(ids["E-WH"], shelf, 0)
    _set_location_qty(ids["E-WH"], warehouse, 5)
    assert client.put(f"/api/v1/products/{ids['F-GONE']}", json={"deleted": True}, headers=headers).status_code == 200
    return headers, warehouse


def _skus(body) -> list[str]:
    rows = body["items"] if isinstance(body, dict) else body
    return [row["sku"] for row in rows]


def test_login_store_low_stock_matches_login_store_quantity(client, google_jwks):
    headers, _warehouse = _catalog(client, google_jwks)
    low = _get(client, headers, loginStoreQuantityMax=2, page=1, pageSize=2)
    assert low["total"] == 4
    assert _skus(low) == ["A-NONE", "B-TWO"]
    assert _skus(_get(client, headers, loginStoreQuantityMax=2, page=2, pageSize=2)) == ["D-NEG", "E-WH"]
    # 每一筆都符合 loginStoreQuantity <= 2（沒有庫存列算 0，負數也算）。
    everything = _get(client, headers)
    expected = [row["sku"] for row in everything if row["loginStoreQuantity"] <= 2]
    assert _skus(_get(client, headers, loginStoreQuantityMax=2)) == expected


def test_login_store_out_of_stock_is_exactly_zero(client, google_jwks):
    headers, _warehouse = _catalog(client, google_jwks)
    assert _skus(_get(client, headers, loginStoreQuantityMin=0, loginStoreQuantityMax=0, page=1, pageSize=50)) == [
        "A-NONE",
        "E-WH",
    ]


def test_location_low_stock_and_total_filters(client, google_jwks):
    headers, warehouse = _catalog(client, google_jwks)
    low_wh = _get(client, headers, locationId=warehouse, locationQuantityMax=2, page=1, pageSize=50)
    assert _skus(low_wh) == ["A-NONE", "B-TWO", "C-THREE", "D-NEG"]
    assert low_wh["total"] == 4
    assert _skus(_get(client, headers, totalInventoryMin=0, totalInventoryMax=0, page=1, pageSize=50)) == ["A-NONE"]
    in_stock = _get(client, headers, inInventoryOnly=True, page=1, pageSize=50)
    assert _skus(in_stock) == ["B-TWO", "C-THREE", "E-WH"]
    assert in_stock["total"] == 3
    # 跟關鍵字一起用。
    assert _skus(_get(client, headers, keyword="E-WH", loginStoreQuantityMax=2, page=1, pageSize=50)) == ["E-WH"]


def test_login_store_filter_matches_nothing_without_a_selected_store(client, google_jwks):
    headers, warehouse = _catalog(client, google_jwks, select_store=False)
    body = _get(client, headers, loginStoreQuantityMax=2, page=1, pageSize=50)
    assert body == {"items": [], "page": 1, "pageSize": 50, "total": 0}
    # 沒有門市時其他數量條件照常。
    assert _skus(_get(client, headers, locationId=warehouse, locationQuantityMin=5, page=1, pageSize=50)) == ["E-WH"]


def test_location_filter_needs_an_existing_location(client, google_jwks):
    headers, _warehouse = _catalog(client, google_jwks)
    for params in ({"locationId": "nope", "locationQuantityMax": 2}, {"locationQuantityMax": 2}):
        response = client.get("/api/v1/products", params=params, headers=headers)
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "LOCATION_NOT_FOUND"
