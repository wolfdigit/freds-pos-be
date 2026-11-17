from datetime import date, datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import select

from src.db.session import SessionFactory, engine
from src.models.checkout import CheckoutOrder, CheckoutPayment
from tests.test_auth import ADMIN_EMAIL, _add_account, _add_store, _auth, _login, _select
from tests.test_inventory import _product

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/2026_11_17_1040-8be3027059d9_migrate_legacy_payment_types.py"
)


def _load_legacy_payment_migration():
    spec = spec_from_file_location("legacy_payment_types_migration", MIGRATION_PATH)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

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


def test_migration_converts_legacy_payment_types(client, google_jwks):
    headers, _product_id = _ready(client, google_jwks, "SKU-PAY-LEGACY")
    now = datetime.now(timezone.utc)
    rows = (
        ("ord-legacy-1", "pay-legacy-1", "credit_card", "信用卡"),
        ("ord-legacy-2", "pay-legacy-2", "bank_transfer", "銀行轉帳"),
        ("ord-legacy-3", "pay-legacy-3", "credit_card", "自訂信用卡名"),
        ("ord-legacy-4", "pay-legacy-4", "bank_transfer", "自訂轉帳名"),
        ("ord-legacy-5", "pay-legacy-5", "cash", "現金"),
        ("ord-legacy-6", "pay-legacy-6", "credit_card_online", "信用卡(網路)"),
    )
    db = SessionFactory()
    try:
        for index, (order_id, payment_id, payment_type, payment_name) in enumerate(rows, start=1):
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
                    id=payment_id,
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

    migration = _load_legacy_payment_migration()
    with engine.begin() as connection:
        migration.apply_upgrade(connection.execute)

    db = SessionFactory()
    try:
        payments = {payment.id: payment for payment in db.scalars(select(CheckoutPayment)).all()}
        assert payments["pay-legacy-1"].type == "credit_card_physical"
        assert payments["pay-legacy-1"].name == "信用卡(實體)"
        assert payments["pay-legacy-2"].type == "bank_transfer_ctbc"
        assert payments["pay-legacy-2"].name == "轉帳(中信)"
        assert payments["pay-legacy-3"].type == "credit_card_physical"
        assert payments["pay-legacy-3"].name == "自訂信用卡名"
        assert payments["pay-legacy-4"].type == "bank_transfer_ctbc"
        assert payments["pay-legacy-4"].name == "自訂轉帳名"
        assert payments["pay-legacy-5"].type == "cash"
        assert payments["pay-legacy-5"].name == "現金"
        assert payments["pay-legacy-6"].type == "credit_card_online"
        assert payments["pay-legacy-6"].name == "信用卡(網路)"
    finally:
        db.close()

    expected = {
        "ord-legacy-1": ("credit_card_physical", "信用卡(實體)"),
        "ord-legacy-2": ("bank_transfer_ctbc", "轉帳(中信)"),
        "ord-legacy-3": ("credit_card_physical", "自訂信用卡名"),
        "ord-legacy-4": ("bank_transfer_ctbc", "自訂轉帳名"),
        "ord-legacy-5": ("cash", "現金"),
        "ord-legacy-6": ("credit_card_online", "信用卡(網路)"),
    }
    listed = client.get("/api/v1/checkout/orders", params={"pageSize": 20}, headers=headers)
    assert listed.status_code == 200, listed.text
    by_id = {order["id"]: order for order in listed.json()["items"]}
    for order_id, (payment_type, payment_name) in expected.items():
        assert by_id[order_id]["payments"][0]["type"] == payment_type
        assert by_id[order_id]["payments"][0]["name"] == payment_name
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
