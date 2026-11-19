from datetime import date, datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from src.db.session import SessionFactory, engine
from src.models.checkout import CheckoutOrder, CheckoutOrderItem
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/2026_11_20_0500-b3d9f2a6c481_points_discount_flag_only.py"
)


def _ready(client, google_jwks) -> dict:
    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    return _auth(login["token"])


def _product(client, headers, sku: str, list_price: int) -> str:
    response = client.post(
        "/api/v1/products",
        json={"sku": sku, "barcode": sku, "brand": "Brand", "name": f"車 {sku}", "listPrice": list_price},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _member(client, headers) -> str:
    response = client.post("/api/v1/customers", json={"name": "王小明", "phone": "0911222333"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _cash(amount: int) -> list:
    return [{"type": "cash", "name": "現金", "amount": amount}]


def _checkout(client, headers, body: dict):
    return client.post("/api/v1/checkout/orders", json={"shippingFee": 0, **body}, headers=headers)


def test_points_line_stores_only_the_flag_and_splits_discount_from_points(client, google_jwks):
    headers = _ready(client, google_jwks)
    customer_id = _member(client, headers)
    car = _product(client, headers, "SKU-PTS-A", 500)
    other = _product(client, headers, "SKU-PTS-B", 500)

    response = _checkout(client, headers, {
        "customerId": customer_id,
        "items": [
            {"productId": car, "quantity": 2},
            {"productId": car, "quantity": 1, "unitPrice": 140, "pointsDiscountApplied": True},
            {"productId": other, "quantity": 1, "unitPrice": 450, "isManualPrice": True, "priceDiffReason": "熟客"},
        ],
        "payments": _cash(1590),
    })
    assert response.status_code == 201, response.text
    order = response.json()["order"]
    flagged = order["items"][1]
    assert flagged["pointsDiscountApplied"] is True
    assert flagged["unitPrice"] == 140 and flagged["subtotal"] == 140
    assert "pointsDiscountAmount" not in flagged
    assert [item["pointsDiscountApplied"] for item in order["items"]] == [False, True, False]
    assert order["discountAmount"] == 50
    assert order["pointsDiscountAmount"] == 360
    assert order["itemsSubtotal"] == 1590
    assert order["totalAmount"] == 1590
    # 商品原價 − 折讓 − 點數折抵 = 成交金額
    original = sum(item["originalPrice"] * item["quantity"] for item in order["items"])
    assert original - order["discountAmount"] - order["pointsDiscountAmount"] == order["itemsSubtotal"]

    fetched = client.get(f"/api/v1/checkout/orders/{order['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["pointsDiscountAmount"] == 360
    assert fetched.json()["discountAmount"] == 50


def test_whole_difference_counts_as_points_on_a_manually_priced_points_line(client, google_jwks):
    headers = _ready(client, google_jwks)
    customer_id = _member(client, headers)
    cheap = _product(client, headers, "SKU-PTS-CHEAP", 80)
    car = _product(client, headers, "SKU-PTS-MAN", 500)

    response = _checkout(client, headers, {
        "customerId": customer_id,
        "items": [
            # 80 元商品折到 0：點數折抵記實際差額 80，不是 360。
            {"productId": cheap, "quantity": 1, "unitPrice": 0, "pointsDiscountApplied": True},
            # 先手動改成 450 再勾點數 → 90：整個差額 410 都算點數。
            {"productId": car, "quantity": 1, "unitPrice": 90, "isManualPrice": True, "pointsDiscountApplied": True},
        ],
        "payments": _cash(90),
    })
    assert response.status_code == 201, response.text
    order = response.json()["order"]
    assert order["pointsDiscountAmount"] == 80 + 410
    assert order["discountAmount"] == 0
    assert order["totalAmount"] == 90


def test_points_validations(client, google_jwks):
    headers = _ready(client, google_jwks)
    customer_id = _member(client, headers)
    car = _product(client, headers, "SKU-PTS-V", 500)

    cases = [
        ({"items": [{"productId": car, "quantity": 1, "unitPrice": 140, "pointsDiscountApplied": True}]}, "散客不能使用點數折抵"),
        ({"customerId": customer_id, "items": [{"productId": car, "quantity": 1, "pointsDiscountApplied": True}]}, "點數折抵必須提供單價"),
        ({"customerId": customer_id, "items": [{"productId": car, "quantity": 1, "unitPrice": -1, "pointsDiscountApplied": True}]}, "點數折抵後單價不能為負數"),
        ({"customerId": customer_id, "items": [{"productId": car, "quantity": 2, "unitPrice": 140, "pointsDiscountApplied": True}]}, "點數折抵的品項數量必須為 1"),
        (
            {
                "customerId": customer_id,
                "items": [
                    {"productId": car, "quantity": 1, "unitPrice": 140, "pointsDiscountApplied": True},
                    {"productId": car, "quantity": 1, "unitPrice": 140, "pointsDiscountApplied": True},
                ],
            },
            "同一商品只能折抵一次",
        ),
    ]
    for body, message in cases:
        response = _checkout(client, headers, {**body, "payments": _cash(1000)})
        assert response.status_code == 422, (message, response.text)
        assert message in response.text, response.text


def test_return_of_a_points_line_keeps_the_flag_and_reverses_points(client, google_jwks):
    headers = _ready(client, google_jwks)
    customer_id = _member(client, headers)
    car = _product(client, headers, "SKU-PTS-R", 500)
    sale = _checkout(client, headers, {
        "customerId": customer_id,
        "items": [{"productId": car, "quantity": 1, "unitPrice": 140, "pointsDiscountApplied": True}],
        "payments": _cash(140),
    })
    assert sale.status_code == 201, sale.text
    original = sale.json()["order"]
    line_id = original["items"][0]["id"]

    flagged_return = _checkout(client, headers, {
        "customerId": customer_id,
        "items": [{
            "productId": car, "quantity": -1, "originalOrderId": original["id"],
            "originalOrderItemId": line_id, "pointsDiscountApplied": True,
        }],
        "payments": _cash(-140),
    })
    assert flagged_return.status_code == 422
    assert "退貨品項不能使用點數折抵" in flagged_return.text

    refund = _checkout(client, headers, {
        "customerId": customer_id,
        "items": [{"productId": car, "quantity": -1, "originalOrderId": original["id"], "originalOrderItemId": line_id}],
        "payments": _cash(-140),
    })
    assert refund.status_code == 201, refund.text
    order = refund.json()["order"]
    assert order["items"][0]["pointsDiscountApplied"] is True
    assert order["items"][0]["unitPrice"] == 140
    assert order["totalAmount"] == -140
    assert order["pointsDiscountAmount"] == -360
    assert order["discountAmount"] == 0


def _load_migration():
    spec = spec_from_file_location("points_flag_only_migration", MIGRATION_PATH)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_backfills_return_flags_and_recomputes_discount(client, google_jwks):
    _ready(client, google_jwks)
    car = _product(client, _auth(_login(client, google_jwks)["token"]), "SKU-PTS-MIG", 500)
    now = datetime.now(timezone.utc)

    def order(order_id: str, number: int, discount: int, subtotal: int) -> CheckoutOrder:
        return CheckoutOrder(
            id=order_id, order_number=f"SO-20260101-000000-{number:04d}", branch_id="b", branch_name="b",
            cashier_id="c", cashier_name="c", status="completed", items_subtotal=subtotal,
            discount_amount=discount, shipping_fee=0, total_amount=subtotal,
            business_date=date(2026, 1, 1), created_at=now, updated_at=now,
        )

    def item(item_id: str, order_id: str, line_no: int, unit: int, qty: int, manual: bool, points: bool, original=None):
        return CheckoutOrderItem(
            id=item_id, order_id=order_id, line_no=line_no, product_id=car, sku="SKU-PTS-MIG", name="車",
            scale="", brand="Brand", original_price=500, unit_price=unit, is_manual_price=manual,
            quantity=qty, subtotal=unit * qty, points_discount_applied=points, returned_quantity=0,
            original_order_id="ord-mig-1" if original else None, original_order_item_id=original,
        )

    db = SessionFactory()
    try:
        # 舊資料：折讓含手動改價的點數列 (500-90) + 一般手動改價 (500-450)。
        db.add(order("ord-mig-1", 1, 410 + 50, 90 + 450))
        db.flush()
        db.add(item("itm-mig-1", "ord-mig-1", 1, 90, 1, True, True))
        db.add(item("itm-mig-2", "ord-mig-1", 2, 450, 1, True, False))
        db.add(order("ord-mig-2", 2, -410, -90))
        db.flush()
        db.add(item("itm-mig-3", "ord-mig-2", 1, 90, -1, True, False, original="itm-mig-1"))
        db.commit()
    finally:
        db.close()

    with engine.begin() as connection:
        _load_migration().apply_upgrade_backfill(connection.execute)

    db = SessionFactory()
    try:
        assert db.get(CheckoutOrder, "ord-mig-1").discount_amount == 50
        assert db.get(CheckoutOrder, "ord-mig-2").discount_amount == 0
        assert db.get(CheckoutOrderItem, "itm-mig-3").points_discount_applied is True
        assert db.get(CheckoutOrderItem, "itm-mig-2").points_discount_applied is False
    finally:
        db.close()
