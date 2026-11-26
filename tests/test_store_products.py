"""門市商品清單：product_scope 'all' / 'list'、store_product 編輯 API、商品列表與結帳的門市限制。"""

from sqlalchemy import func, select

from src.db.session import SessionFactory
from src.models.checkout import CheckoutOrder
from src.models.system import StoreProduct
from tests.test_auth import (
    ADMIN_EMAIL,
    STAFF_EMAIL,
    _add_account,
    _add_store,
    _auth,
    _login,
    _select,
    _set_location_qty,
)
from tests.test_product_pagination import _create

POPUP = "台南快閃店"
MAIN = "奇可門市"


def _setup(client, google_jwks):
    """管理員與店員都登入；先在 'all' 門市建 A–E 五個商品，再把快閃店切成 'list' 並放 A、B、D。"""
    _add_account(ADMIN_EMAIL, "admin", "管理員甲")
    _add_account(STAFF_EMAIL, "staff", "店員乙")
    main_shelf = _add_store(MAIN)
    popup_shelf = _add_store(POPUP)
    admin = _auth(_login(client, google_jwks, ADMIN_EMAIL)["token"])
    staff_login = _login(client, google_jwks, STAFF_EMAIL)
    staff = _auth(staff_login["token"])
    _select(client, staff_login["token"], MAIN)
    ids = {sku: _create(client, staff, sku, brand=f"牌{sku}") for sku in ["A", "B", "C", "D", "E"]}
    # 一般店員也可以切換販售範圍。
    scope = client.put(
        f"/api/v1/system/stores/{POPUP}/product-scope", json={"productScope": "list"}, headers=staff
    )
    assert scope.status_code == 200, scope.text
    assert scope.json()["productScope"] == "list"
    added = client.post(
        f"/api/v1/system/stores/{POPUP}/products/batch",
        json={"add": [ids["A"], ids["B"], ids["D"], ids["A"]]},
        headers=staff,
    )
    assert added.status_code == 200, added.text
    assert added.json()["changed"] == 3
    assert added.json()["added"] == 3
    assert added.json()["removed"] == 0
    assert added.json()["listedTotal"] == 3
    _select(client, staff_login["token"], POPUP)
    return admin, staff, staff_login["token"], ids, main_shelf, popup_shelf


def _skus(body) -> list[str]:
    rows = body["items"] if isinstance(body, dict) else body
    return [row["sku"] for row in rows]


def test_existing_stores_default_to_all_and_sell_everything(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_store(MAIN)
    login = _login(client, google_jwks)
    headers = _auth(login["token"])
    _create(client, headers, "X")
    stores = client.get("/api/v1/auth/stores", headers=headers).json()
    assert [row["productScope"] for row in stores] == ["all"]
    # 管理員沒選門市：看全部商品，soldInLoginStore 為 null。
    rows = client.get("/api/v1/products", headers=headers).json()["items"]
    assert [row["soldInLoginStore"] for row in rows] == [None]
    _select(client, login["token"], MAIN)
    rows = client.get("/api/v1/products", headers=headers).json()["items"]
    assert [row["soldInLoginStore"] for row in rows] == [True]


def test_list_store_only_lists_its_products_everywhere(client, google_jwks):
    admin, staff, _token, ids, _main, _popup = _setup(client, google_jwks)
    assert _skus(client.get("/api/v1/products", headers=staff).json()) == ["A", "B", "D"]
    page = client.get("/api/v1/products", params={"page": 1, "pageSize": 2}, headers=staff).json()
    assert page["total"] == 3
    assert _skus(page) == ["A", "B"]
    # 條碼掃描與關鍵字一樣套清單。
    assert _skus(client.get("/api/v1/products", params={"barcode": "C"}, headers=staff).json()) == []
    assert _skus(client.get("/api/v1/products", params={"barcode": "D"}, headers=staff).json()) == ["D"]
    # 條碼 + allProducts + 分頁：可找到清單外商品，且是分頁物件。
    skipped = client.get(
        "/api/v1/products",
        params={"barcode": "C", "allProducts": "true", "page": 1, "pageSize": 50},
        headers=staff,
    ).json()
    assert skipped["total"] == 1
    assert _skus(skipped) == ["C"]
    assert skipped["items"][0]["soldInLoginStore"] is False
    assert all(row["soldInLoginStore"] for row in client.get("/api/v1/products", headers=staff).json()["items"])

    # 單一商品不受清單影響，但會標示 soldInLoginStore。
    single = client.get(f"/api/v1/products/{ids['C']}", headers=staff)
    assert single.status_code == 200
    assert single.json()["soldInLoginStore"] is False
    assert client.get(f"/api/v1/products/{ids['A']}", headers=staff).json()["soldInLoginStore"] is True

    # 一般店員也可以用 allProducts 看全部商品。
    staff_all = client.get("/api/v1/products", params={"allProducts": "true"}, headers=staff)
    assert staff_all.status_code == 200, staff_all.text
    assert _skus(staff_all.json()) == ["A", "B", "C", "D", "E"]
    paged_all = client.get(
        "/api/v1/products", params={"allProducts": "true", "page": 1, "pageSize": 50}, headers=staff
    ).json()
    assert paged_all["total"] == 5
    # 管理員沒選門市時看全部；選了快閃店也一樣套清單，加 allProducts 才看全部。
    assert _skus(client.get("/api/v1/products", headers=admin).json()) == ["A", "B", "C", "D", "E"]
    admin_token = admin["Authorization"].split()[1]
    _select(client, admin_token, POPUP)
    assert _skus(client.get("/api/v1/products", headers=admin).json()) == ["A", "B", "D"]
    everything = client.get("/api/v1/products", params={"allProducts": "true"}, headers=admin).json()["items"]
    assert {row["sku"]: row["soldInLoginStore"] for row in everything} == {
        "A": True,
        "B": True,
        "C": False,
        "D": True,
        "E": False,
    }


def test_inventory_columns_still_cover_every_location(client, google_jwks):
    _admin, staff, _token, ids, main_shelf, popup_shelf = _setup(client, google_jwks)
    _set_location_qty(ids["A"], main_shelf, 5)
    _set_location_qty(ids["A"], popup_shelf, 2)
    row = next(r for r in client.get("/api/v1/products", headers=staff).json()["items"] if r["sku"] == "A")
    assert row["totalInventory"] == 7
    assert row["loginStoreQuantity"] == 2
    by_location = {item["location"]: item["quantity"] for item in row["inventories"]}
    assert by_location[main_shelf] == 5 and by_location[popup_shelf] == 2


def test_store_product_editor_search_paging_and_audit(client, google_jwks):
    _admin, staff, _token, ids, _main, _popup = _setup(client, google_jwks)
    url = f"/api/v1/system/stores/{POPUP}/products"
    body = client.get(url, params={"page": 1, "pageSize": 2}, headers=staff).json()
    assert body["productScope"] == "list"
    assert body["listedTotal"] == 3
    assert body["total"] == 5
    assert [(row["sku"], row["inList"]) for row in body["items"]] == [("A", True), ("B", True)]
    assert body["items"][0]["addedBy"] == "店員乙"
    assert body["items"][0]["addedAt"]
    unlisted = client.get(url, params={"inList": "false"}, headers=staff).json()
    assert [row["sku"] for row in unlisted["items"]] == ["C", "E"]
    assert unlisted["listedTotal"] == 3
    found = client.get(url, params={"keyword": "牌d", "inList": "true"}, headers=staff).json()
    assert [row["sku"] for row in found["items"]] == ["D"]

    # 存檔：加入與移出一次送出。B 移出、C 本來就不在（不算），E 加入、A 已在（不算）。
    saved = client.post(
        f"{url}/batch",
        json={"add": [ids["E"], ids["A"]], "remove": [ids["B"], ids["C"]]},
        headers=staff,
    )
    assert saved.status_code == 200, saved.text
    assert (saved.json()["added"], saved.json()["removed"], saved.json()["changed"]) == (1, 1, 2)
    assert saved.json()["listedTotal"] == 3
    listed = client.get(url, params={"inList": "true"}, headers=staff).json()
    assert [row["sku"] for row in listed["items"]] == ["A", "D", "E"]

    # 任何一筆失敗整批不寫入。
    missing = client.post(
        f"{url}/batch", json={"add": ["prod-missing"], "remove": [ids["A"]]}, headers=staff
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "PRODUCT_NOT_FOUND"
    assert client.get(url, params={"inList": "true"}, headers=staff).json()["listedTotal"] == 3
    assert client.get("/api/v1/system/stores/沒有這間/products", headers=staff).status_code == 404
    assert client.post(
        "/api/v1/system/stores/沒有這間/products/batch", json={"add": [ids["A"]]}, headers=staff
    ).status_code == 404
    assert client.post(f"{url}/batch", json={"add": [], "remove": []}, headers=staff).status_code == 422
    assert client.post(f"{url}/batch", json={"add": [ids["A"]], "remove": [ids["A"]]}, headers=staff).status_code == 422
    # 舊的逐筆端點已移除。
    assert client.post(f"{url}/remove", json={"productIds": [ids["A"]]}, headers=staff).status_code in (404, 405)


def test_deleted_products_stay_in_the_list_but_are_hidden(client, google_jwks):
    _admin, staff, _token, ids, _main, _popup = _setup(client, google_jwks)
    assert client.put(f"/api/v1/products/{ids['D']}", json={"deleted": True}, headers=staff).status_code == 200
    url = f"/api/v1/system/stores/{POPUP}/products"
    body = client.get(url, params={"inList": "true"}, headers=staff).json()
    assert [row["sku"] for row in body["items"]] == ["A", "B"]
    assert body["listedTotal"] == 2
    assert _skus(client.get("/api/v1/products", headers=staff).json()) == ["A", "B"]
    # 列還在；恢復商品後自動回到清單。
    db = SessionFactory()
    try:
        assert db.get(StoreProduct, (POPUP, ids["D"])) is not None
    finally:
        db.close()
    rejected = client.post(f"{url}/batch", json={"add": [ids["D"]]}, headers=staff)
    assert rejected.status_code == 404
    assert client.put(f"/api/v1/products/{ids['D']}", json={"deleted": False}, headers=staff).status_code == 200
    assert _skus(client.get("/api/v1/products", headers=staff).json()) == ["A", "B", "D"]


def test_new_products_join_only_the_list_store_they_were_created_in(client, google_jwks):
    _admin, staff, token, _ids, _main, _popup = _setup(client, google_jwks)
    created_here = _create(client, staff, "NEW-POPUP")
    assert client.get(f"/api/v1/products/{created_here}", headers=staff).json()["soldInLoginStore"] is True
    _select(client, token, MAIN)
    created_main = _create(client, staff, "NEW-MAIN")
    _select(client, token, POPUP)
    skus = _skus(client.get("/api/v1/products", headers=staff).json())
    assert "NEW-POPUP" in skus
    assert "NEW-MAIN" not in skus
    assert client.get(f"/api/v1/products/{created_main}", headers=staff).json()["soldInLoginStore"] is False
    row = next(
        r
        for r in client.get(f"/api/v1/system/stores/{POPUP}/products", params={"keyword": "NEW-POPUP"}, headers=staff)
        .json()["items"]
    )
    assert row["addedBy"] == "店員乙"


def test_copy_list_from_another_store(client, google_jwks):
    admin, staff, _token, ids, _main, _popup = _setup(client, google_jwks)
    created = client.post(
        "/api/v1/system/stores",
        json={
            "name": "高雄快閃店",
            "inventoryLocationId": client.get("/api/v1/auth/stores", headers=admin).json()[0]["inventoryLocationId"],
            "returnedInventoryLocationId": client.get("/api/v1/auth/stores", headers=admin).json()[0][
                "returnedInventoryLocationId"
            ],
            "productScope": "list",
        },
        headers=admin,
    )
    assert created.status_code == 201, created.text
    assert created.json()["productScope"] == "list"
    url = "/api/v1/system/stores/高雄快閃店/products"
    assert client.post(f"{url}/batch", json={"add": [ids["E"]]}, headers=staff).json()["listedTotal"] == 1
    merged = client.post(f"{url}/copy", json={"sourceStoreName": POPUP}, headers=staff)
    assert merged.status_code == 200, merged.text
    assert merged.json()["changed"] == 3
    assert merged.json()["listedTotal"] == 4
    client.post(f"/api/v1/system/stores/{POPUP}/products/batch", json={"remove": [ids["A"]]}, headers=staff)
    replaced = client.post(f"{url}/copy", json={"sourceStoreName": POPUP, "replace": True}, headers=staff)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["changed"] == 2  # 移除 A、E
    assert (replaced.json()["added"], replaced.json()["removed"]) == (0, 2)
    listed = client.get(url, params={"inList": "true"}, headers=staff).json()
    assert [row["sku"] for row in listed["items"]] == ["B", "D"]
    missing = client.post(f"{url}/copy", json={"sourceStoreName": "沒有這間"}, headers=staff)
    assert missing.status_code == 404

    # 刪除門市連同清單一起刪除。
    assert client.delete("/api/v1/system/stores/高雄快閃店", headers=admin).status_code == 200
    db = SessionFactory()
    try:
        left = db.scalar(
            select(func.count()).select_from(StoreProduct).where(StoreProduct.store_name == "高雄快閃店")
        )
    finally:
        db.close()
    assert left == 0


def test_staff_switches_scope_and_all_restores_everything(client, google_jwks):
    admin, staff, _token, _ids, _main, _popup = _setup(client, google_jwks)
    url = f"/api/v1/system/stores/{POPUP}/product-scope"
    assert client.put(url, json={"productScope": "bogus"}, headers=staff).status_code == 422
    assert client.put("/api/v1/system/stores/沒有這間/product-scope", json={"productScope": "all"}, headers=staff).status_code == 404
    switched = client.put(url, json={"productScope": "all"}, headers=staff)
    assert switched.status_code == 200, switched.text
    assert switched.json()["productScope"] == "all"
    assert switched.json()["preorderInventoryLocationId"]
    assert _skus(client.get("/api/v1/products", headers=staff).json()) == ["A", "B", "C", "D", "E"]
    # 清單保留，切回 list 立刻沿用；管理員也可以切。
    assert client.put(url, json={"productScope": "list"}, headers=admin).status_code == 200
    assert _skus(client.get("/api/v1/products", headers=staff).json()) == ["A", "B", "D"]


def _order_count() -> int:
    db = SessionFactory()
    try:
        return db.scalar(select(func.count()).select_from(CheckoutOrder)) or 0
    finally:
        db.close()


def _sale(product_id: str, quantity: int = 1) -> dict:
    return {
        "items": [{"productId": product_id, "quantity": quantity}],
        "shippingFee": 0,
        "payments": [{"type": "cash", "name": "現金", "amount": 100 * quantity}],
    }


def test_checkout_rejects_unlisted_sales_but_allows_returns(client, google_jwks):
    _admin, staff, _token, ids, _main, _popup = _setup(client, google_jwks)
    before = _order_count()
    rejected = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{"productId": ids["A"], "quantity": 1}, {"productId": ids["C"], "quantity": 1}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": 200}],
        },
        headers=staff,
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["code"] == "PRODUCT_NOT_IN_STORE"
    assert ids["C"] in rejected.json()["message"]
    assert _order_count() == before

    sale = client.post("/api/v1/checkout/orders", json=_sale(ids["B"]), headers=staff)
    assert sale.status_code == 201, sale.text
    order = sale.json()["order"]
    # 賣出後移出清單：不能再賣，但可以退。
    client.post(f"/api/v1/system/stores/{POPUP}/products/batch", json={"remove": [ids["B"]]}, headers=staff)
    assert client.post("/api/v1/checkout/orders", json=_sale(ids["B"]), headers=staff).status_code == 409
    refund = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": ids["B"],
                "quantity": -1,
                "originalOrderId": order["id"],
                "originalOrderItemId": order["items"][0]["id"],
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金退款", "amount": -100}],
        },
        headers=staff,
    )
    assert refund.status_code == 201, refund.text


def test_all_scope_store_checkout_is_unchanged(client, google_jwks):
    _admin, staff, token, ids, _main, _popup = _setup(client, google_jwks)
    _select(client, token, MAIN)
    assert client.post("/api/v1/checkout/orders", json=_sale(ids["C"]), headers=staff).status_code == 201
