from datetime import date, datetime, timezone

from src.db.session import SessionFactory
from src.models.checkout import CheckoutOrder, CheckoutPayment
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select
from tests.test_inventory import _product

PAYMENT_METHODS = [
    ("cash", "現金"),
    ("bank_transfer_ctbc", "轉帳(中信)"),
    ("bank_transfer_ubot", "轉帳(聯邦)"),
    ("credit_card_physical", "信用卡(實體)"),
    ("credit_card_online", "信用卡(網路)"),
    ("line_pay", "LINE Pay"),
    ("cod", "貨到付款"),
]


def _ready(client, google_jwks, sku: str = "SKU-PAY") -> tuple[dict, str]:
    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    product_id = _product(client, login["token"], sku)
    return _auth(login["token"]), product_id


def _sale_body(product_id: str, payment_type: str, payment_name: str, amount: int = 100) -> dict:
    return {
        "items": [{"productId": product_id, "quantity": 1}],
        "shippingFee": 0,
        "payments": [{"type": payment_type, "name": payment_name, "amount": amount}],
    }


def test_each_frontend_payment_type_creates_an_order(client, google_jwks):
    headers, product_id = _ready(client, google_jwks)
    created_types = []
    for payment_type, payment_name in PAYMENT_METHODS:
        response = client.post(
            "/api/v1/checkout/orders",
            json=_sale_body(product_id, payment_type, payment_name),
            headers=headers,
        )
        assert response.status_code == 201, (payment_type, response.text)
        payments = response.json()["order"]["payments"]
        assert len(payments) == 1
        assert payments[0]["type"] == payment_type
        assert payments[0]["name"] == payment_name
        created_types.append(payment_type)

    listed = client.get("/api/v1/checkout/orders", params={"pageSize": 20}, headers=headers)
    assert listed.status_code == 200, listed.text
    listed_types = [order["payments"][0]["type"] for order in listed.json()["items"]]
    assert set(listed_types) == {payment_type for payment_type, _ in PAYMENT_METHODS}
    assert created_types == [payment_type for payment_type, _ in PAYMENT_METHODS]


def test_invalid_and_legacy_payment_types_are_rejected_on_create(client, google_jwks):
    headers, product_id = _ready(client, google_jwks, "SKU-PAY-BAD")
    for payment_type in ("credit_card", "bank_transfer", "paypal", "CREDIT_CARD_PHYSICAL"):
        response = client.post(
            "/api/v1/checkout/orders",
            json=_sale_body(product_id, payment_type, payment_type),
            headers=headers,
        )
        assert response.status_code == 422, (payment_type, response.text)


def test_legacy_stored_payment_types_are_returned_on_list_and_get(client, google_jwks):
    headers, _product_id = _ready(client, google_jwks, "SKU-PAY-LEGACY")
    now = datetime.now(timezone.utc)
    db = SessionFactory()
    try:
        for index, (payment_type, payment_name) in enumerate(
            (("credit_card", "信用卡"), ("bank_transfer", "銀行轉帳")),
            start=1,
        ):
            order_id = f"ord-legacy-{index}"
            db.add(
                CheckoutOrder(
                    id=order_id,
                    order_number=f"SO-20260101-000000-{index:04d}",
                    branch_id="奇可門市",
                    branch_name="奇可門市",
                    cashier_id="acct-legacy",
                    cashier_name="收銀員",
                    status="completed",
                    items_subtotal=100,
                    discount_amount=0,
                    shipping_fee=0,
                    total_amount=100,
                    business_date=date(2026, 1, 1),
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                CheckoutPayment(
                    id=f"pay-legacy-{index}",
                    order_id=order_id,
                    line_no=1,
                    type=payment_type,
                    name=payment_name,
                    amount=100,
                )
            )
        db.commit()
    finally:
        db.close()

    listed = client.get("/api/v1/checkout/orders", params={"pageSize": 20}, headers=headers)
    assert listed.status_code == 200, listed.text
    by_id = {order["id"]: order for order in listed.json()["items"]}
    assert by_id["ord-legacy-1"]["payments"][0]["type"] == "credit_card"
    assert by_id["ord-legacy-2"]["payments"][0]["type"] == "bank_transfer"

    for order_id, payment_type, payment_name in (
        ("ord-legacy-1", "credit_card", "信用卡"),
        ("ord-legacy-2", "bank_transfer", "銀行轉帳"),
    ):
        fetched = client.get(f"/api/v1/checkout/orders/{order_id}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        payment = fetched.json()["payments"][0]
        assert payment["type"] == payment_type
        assert payment["name"] == payment_name


def test_refund_accepts_a_frontend_payment_type(client, google_jwks):
    headers, product_id = _ready(client, google_jwks, "SKU-PAY-REFUND")
    sale = client.post(
        "/api/v1/checkout/orders",
        json=_sale_body(product_id, "credit_card_physical", "信用卡(實體)"),
        headers=headers,
    )
    assert sale.status_code == 201, sale.text
    order = sale.json()["order"]
    refund = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{
                "productId": product_id,
                "quantity": -1,
                "originalOrderId": order["id"],
                "originalOrderItemId": order["items"][0]["id"],
            }],
            "shippingFee": 0,
            "payments": [{"type": "bank_transfer_ctbc", "name": "轉帳(中信)退款", "amount": -100}],
        },
        headers=headers,
    )
    assert refund.status_code == 201, refund.text
    payments = refund.json()["order"]["payments"]
    assert payments[0]["type"] == "bank_transfer_ctbc"
    assert payments[0]["amount"] == -100
    original = client.get(f"/api/v1/checkout/orders/{order['id']}", headers=headers)
    assert original.status_code == 200, original.text
    assert original.json()["status"] == "refunded"
