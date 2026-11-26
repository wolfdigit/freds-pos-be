"""退貨查原單：GET /checkout/orders 在伺服器端篩選與分頁，不用把全部歷史訂單抓回前端。"""

from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select

URL = "/api/v1/checkout/orders"


def _ready(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    return _auth(login["token"])


def _product(client, headers, sku, barcode, name, price):
    response = client.post(
        "/api/v1/products",
        json={"sku": sku, "barcode": barcode, "brand": "Brand", "name": name, "listPrice": price},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _sell(client, headers, product_id, quantity, amount):
    response = client.post(
        URL,
        json={
            "items": [{"productId": product_id, "quantity": quantity}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": amount}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["order"]


def _search(client, headers, **params):
    response = client.get(URL, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _numbers(body):
    return [order["orderNumber"] for order in body["items"]]


def test_order_number_matches_partial_case_insensitive_and_trimmed(client, google_jwks):
    headers = _ready(client, google_jwks)
    car = _product(client, headers, "SKU-CAR", "4710000000017", "紅色跑車", 100)
    first = _sell(client, headers, car, 1, 100)
    second = _sell(client, headers, car, 2, 200)

    full = first["orderNumber"]
    assert _numbers(_search(client, headers, orderNumber=full)) == [full]
    assert _numbers(_search(client, headers, orderNumber=f"  {full.lower()}  ")) == [full]
    suffix = full.removeprefix("SO-")
    assert _numbers(_search(client, headers, orderNumber=suffix)) == [full]
    # 共同的前綴會同時找到兩張，依時間新到舊。
    both = _search(client, headers, orderNumber="so-")
    assert _numbers(both) == [second["orderNumber"], full]
    assert both["total"] == 2
    assert _search(client, headers, orderNumber="NO-SUCH")["items"] == []
    # % 和 _ 當一般字元，不是萬用字元。
    assert _search(client, headers, orderNumber="%")["items"] == []


def test_product_keyword_matches_name_sku_and_barcode(client, google_jwks):
    headers = _ready(client, google_jwks)
    car = _product(client, headers, "SKU-CAR", "4710000000017", "紅色跑車", 100)
    bus = _product(client, headers, "SKU-BUS", "4710000000024", "藍色巴士", 300)
    car_order = _sell(client, headers, car, 1, 100)
    bus_order = _sell(client, headers, bus, 1, 300)

    assert _numbers(_search(client, headers, productKeyword="跑車")) == [car_order["orderNumber"]]
    assert _numbers(_search(client, headers, productKeyword="sku-bus")) == [bus_order["orderNumber"]]
    assert _numbers(_search(client, headers, productKeyword="4710000000024")) == [bus_order["orderNumber"]]
    assert _numbers(_search(client, headers, productKeyword="0000017")) == [car_order["orderNumber"]]
    assert _search(client, headers, productKeyword="4719999")["items"] == []


def test_amount_paging_and_returnable_quantity(client, google_jwks):
    headers = _ready(client, google_jwks)
    car = _product(client, headers, "SKU-CAR", "4710000000017", "紅色跑車", 100)
    orders = [_sell(client, headers, car, n, 100 * n) for n in (1, 2, 3, 2)]

    exact = _search(client, headers, minAmount=200, maxAmount=200)
    assert _numbers(exact) == [orders[3]["orderNumber"], orders[1]["orderNumber"]]
    assert exact["total"] == 2

    page1 = _search(client, headers, page=1, pageSize=3)
    page2 = _search(client, headers, page=2, pageSize=3)
    assert page1["total"] == page2["total"] == 4
    assert (page1["page"], page1["pageSize"]) == (1, 3)
    newest_first = [order["orderNumber"] for order in reversed(orders)]
    assert _numbers(page1) + _numbers(page2) == newest_first

    # 可退數量直接來自訂單品項的 returnedQuantity，不需要掃描其他訂單。
    sale = orders[2]
    refund = client.post(
        URL,
        json={
            "items": [{
                "productId": car,
                "quantity": -1,
                "originalOrderId": sale["id"],
                "originalOrderItemId": sale["items"][0]["id"],
            }],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金退款", "amount": -100}],
        },
        headers=headers,
    )
    assert refund.status_code == 201, refund.text
    found = _search(client, headers, orderNumber=sale["orderNumber"])["items"]
    assert len(found) == 1
    assert found[0]["items"][0]["quantity"] == 3
    assert found[0]["items"][0]["returnedQuantity"] == 1
    assert found[0]["status"] == "partially_refunded"


def test_store_name_filters_orders_by_checkout_store(client, google_jwks):
    """storeName：只列在該門市結帳的訂單（branchId）。退貨單算處理退貨的門市；不帶 = 全部門市。"""
    from src.db.session import SessionFactory
    from src.models.checkout import CheckoutOrder

    headers = _ready(client, google_jwks)
    _add_store("台南快閃店")
    token = headers["Authorization"].split()[1]
    car = _product(client, headers, "SKU-CAR", "4710000000017", "紅色跑車", 100)
    main_sale = _sell(client, headers, car, 1, 100)
    _select(client, token, "台南快閃店")
    popup_sale = _sell(client, headers, car, 2, 200)
    item = main_sale["items"][0]
    refund = client.post(
        URL,
        json={
            "items": [
                {
                    "productId": car,
                    "quantity": -1,
                    "originalOrderId": main_sale["id"],
                    "originalOrderItemId": item["id"],
                    "returnReason": "QA-退貨",
                }
            ],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": -100}],
        },
        headers=headers,
    )
    assert refund.status_code == 201, refund.text
    popup_return = refund.json()["order"]
    assert popup_return["branchId"] == "台南快閃店"

    # 舊版訂單的 branch_id 不是門市名稱（branch-store），只在全部門市出現。
    legacy = _sell(client, headers, car, 1, 100)
    db = SessionFactory()
    try:
        row = db.get(CheckoutOrder, legacy["id"])
        row.branch_id = "branch-store"
        row.branch_name = "台北旗艦店"
        db.commit()
    finally:
        db.close()

    everything = _search(client, headers, pageSize=100)
    assert everything["total"] == 4
    main = _search(client, headers, storeName="奇可門市", pageSize=100)
    assert _numbers(main) == [main_sale["orderNumber"]]
    assert main["items"][0]["branchName"] == "奇可門市"
    popup = _search(client, headers, storeName=" 台南快閃店 ", pageSize=100)
    assert set(_numbers(popup)) == {popup_sale["orderNumber"], popup_return["orderNumber"]}
    # 跟其他條件一起用，也跟分頁一起用。
    assert _numbers(_search(client, headers, storeName="台南快閃店", maxAmount=0)) == [popup_return["orderNumber"]]
    paged = _search(client, headers, storeName="台南快閃店", page=1, pageSize=1)
    assert paged["total"] == 2
    assert len(paged["items"]) == 1
    # 空白 = 沒帶。
    assert _search(client, headers, storeName="  ", pageSize=100)["total"] == 4

    missing = client.get(URL, params={"storeName": "不存在的門市"}, headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "STORE_NOT_FOUND"
