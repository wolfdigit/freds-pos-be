"""結帳遇到不存在或剛被刪掉的商品時，一律回 4xx，不寫任何資料，錯誤回應也帶 CORS 標頭。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from src.db.session import SessionFactory, engine
from src.main import app
from src.models.checkout import CheckoutOrder
from src.models.location import InventoryMovement
from src.models.product import ProductInventory
from src.services import checkout_service
from src.services.checkout_service import CheckoutService
from tests.test_checkout_payments import _ready

MISSING_ID = "prod-4224495c6a4c40888f1b24cfba77cfa4"
FE_ORIGIN = "https://freds-pos.vercel.app"
postgres_only = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="foreign keys and row locks are enforced by PostgreSQL; set TEST_DATABASE_URI",
)


def _body(*product_ids: str) -> dict:
    return {
        "items": [{"productId": product_id, "quantity": 1} for product_id in product_ids],
        "shippingFee": 0,
        "payments": [{"type": "cash", "name": "現金", "amount": 100 * len(product_ids)}],
    }


def _counts() -> tuple[int, int, int]:
    db = SessionFactory()
    try:
        return (
            db.scalar(select(func.count()).select_from(CheckoutOrder)) or 0,
            db.scalar(select(func.count()).select_from(ProductInventory)) or 0,
            db.scalar(select(func.count()).select_from(InventoryMovement)) or 0,
        )
    finally:
        db.close()


def test_missing_product_is_404_before_any_write(client, google_jwks):
    headers, product_id = _ready(client, google_jwks, "SKU-MISSING")
    before = _counts()
    response = client.post(
        "/api/v1/checkout/orders",
        json=_body(product_id, MISSING_ID),
        headers={**headers, "X-Idempotency-Key": "idem-missing"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"
    assert MISSING_ID in response.json()["message"]
    assert _counts() == before


def _remove_product_after_validation(monkeypatch, product_id: str, *, same_transaction: bool):
    """商品在檢查之後、寫庫存之前消失（正式站事故的情況）。"""

    original = CheckoutService._build_lines
    outcome: dict = {}

    def build_then_remove(self, data, customer):
        drafts = original(self, data, customer)
        if same_transaction:
            self.db.execute(text("delete from product where id = :id"), {"id": product_id})
            return drafts
        other = create_engine(engine.url)
        try:
            with other.begin() as conn:
                conn.execute(text("set local lock_timeout = '300ms'"))
                conn.execute(text("delete from product where id = :id"), {"id": product_id})
            outcome["deleted"] = True
        except OperationalError as exc:
            outcome["blocked"] = "lock timeout" in str(exc).lower()
        finally:
            other.dispose()
        return drafts

    monkeypatch.setattr(CheckoutService, "_build_lines", build_then_remove)
    return outcome


@postgres_only
def test_concurrent_delete_cannot_slip_between_check_and_stock_write(client, google_jwks, monkeypatch):
    headers, product_id = _ready(client, google_jwks, "SKU-RACE")
    outcome = _remove_product_after_validation(monkeypatch, product_id, same_transaction=False)
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = safe_client.post(
            "/api/v1/checkout/orders", json=_body(product_id), headers=headers
        )
    # 結帳鎖住商品列，另一個交易刪不掉，結帳照常完成。
    assert outcome == {"blocked": True}, outcome
    assert response.status_code == 201, response.text


@postgres_only
def test_product_fk_violation_during_checkout_is_404_not_500(client, google_jwks, monkeypatch):
    headers, product_id = _ready(client, google_jwks, "SKU-FK")
    before = _counts()
    _remove_product_after_validation(monkeypatch, product_id, same_transaction=True)
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = safe_client.post(
            "/api/v1/checkout/orders",
            json=_body(product_id),
            headers={**headers, "Origin": FE_ORIGIN},
        )
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"
    assert response.headers.get("access-control-allow-origin") == FE_ORIGIN
    assert _counts() == before


class _FakeDiag:
    constraint_name = "product_inventory_product_id_fkey"


class _FakeForeignKeyViolation(Exception):
    pgcode = "23503"
    diag = _FakeDiag()


def test_product_fk_integrity_error_is_mapped_on_any_database(client, google_jwks, monkeypatch):
    headers, product_id = _ready(client, google_jwks, "SKU-FK-ANY")

    def explode(*_args, **_kwargs):
        raise IntegrityError(
            "INSERT INTO product_inventory ...",
            {},
            _FakeForeignKeyViolation(
                'insert or update on table "product_inventory" violates foreign key '
                'constraint "product_inventory_product_id_fkey"'
            ),
        )

    monkeypatch.setattr(checkout_service, "apply_checkout_stock", explode)
    response = client.post("/api/v1/checkout/orders", json=_body(product_id), headers=headers)
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


def test_unhandled_500_still_carries_cors_headers(client, google_jwks, monkeypatch):
    headers, product_id = _ready(client, google_jwks, "SKU-500")

    def boom(*_args, **_kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(CheckoutService, "create", boom)
    with TestClient(app, raise_server_exceptions=False) as safe_client:
        response = safe_client.post(
            "/api/v1/checkout/orders",
            json=_body(product_id),
            headers={**headers, "Origin": FE_ORIGIN},
        )
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    assert "error_log" not in response.json()
    assert response.headers.get("access-control-allow-origin") == FE_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_business_error_carries_cors_headers(client, google_jwks):
    headers, _product_id = _ready(client, google_jwks, "SKU-404-CORS")
    response = client.post(
        "/api/v1/checkout/orders",
        json=_body(MISSING_ID),
        headers={**headers, "Origin": FE_ORIGIN},
    )
    assert response.status_code == 404
    assert response.headers.get("access-control-allow-origin") == FE_ORIGIN
