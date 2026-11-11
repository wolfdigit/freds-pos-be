"""SKIP_LOGIN lets a non-production deployment call protected APIs with no session."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.core.config import Settings, settings
from src.services.checkout_service import STORE_LOCATION
from src.core.exceptions import BusinessException
from src.db.session import SessionFactory
from src.models.auth import AuthSession
from src.models.system import OAuthAccount
from src.schemas.common import BusinessErrorCode
from src.services.auth_service import (
    SKIP_LOGIN_ACCOUNT_ID,
    SKIP_LOGIN_EMAIL,
    SKIP_LOGIN_NAME,
    SKIP_LOGIN_SESSION_ID,
    AuthService,
)
from src.services.bootstrap import DEMO_EMAILS
from tests.test_auth import (
    ADMIN_EMAIL,
    STAFF_EMAIL,
    _add_account,
    _add_store,
    _auth,
    _expire,
    _login,
    _set_store_stock,
    _stock_locations,
    _stock_qty,
    _token,
)


def _enable(monkeypatch, *, environment="test", vercel_env="", store=""):
    monkeypatch.setattr(settings, "SKIP_LOGIN", True)
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "VERCEL_ENV", vercel_env)
    monkeypatch.setattr(settings, "SKIP_LOGIN_STORE", store)


def _emails_and_sessions():
    db = SessionFactory()
    try:
        emails = list(db.scalars(select(OAuthAccount.email)).all())
        sessions = list(db.scalars(select(AuthSession.id)).all())
        return emails, sessions
    finally:
        db.close()


def test_skip_login_defaults_to_false_and_unauthenticated_business_api_stays_401(client, monkeypatch):
    assert Settings.model_fields["SKIP_LOGIN"].default is False
    assert SKIP_LOGIN_EMAIL not in DEMO_EMAILS
    monkeypatch.setattr(settings, "SKIP_LOGIN", False)
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "VERCEL_ENV", "preview")
    monkeypatch.setattr(settings, "SKIP_LOGIN_STORE", "alpha")
    _add_store("alpha")

    blocked = client.get("/api/v1/products")
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH_REQUIRED"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/system/stores").status_code == 401


def test_skip_login_acts_as_admin_and_binds_the_first_or_named_store(client, monkeypatch):
    _enable(monkeypatch)
    _add_store("zeta")
    _add_store("alpha")

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["user"] == {
        "id": SKIP_LOGIN_ACCOUNT_ID,
        "email": SKIP_LOGIN_EMAIL,
        "name": SKIP_LOGIN_NAME,
        "role": "admin",
    }
    assert body["storeSelected"] is True
    assert body["storeName"] == "alpha"
    assert client.get("/api/v1/products").status_code == 200
    assert client.get("/api/v1/system/stores").status_code == 200
    assert client.get("/api/v1/system/oauth/accounts").status_code == 200

    monkeypatch.setattr(settings, "SKIP_LOGIN_STORE", "   ")
    assert client.get("/api/v1/auth/me").json()["storeName"] == "alpha"

    monkeypatch.setattr(settings, "SKIP_LOGIN_STORE", "zeta")
    assert client.get("/api/v1/auth/me").json()["storeName"] == "zeta"
    selected = client.post("/api/v1/auth/store", json={"storeName": "alpha"})
    assert selected.status_code == 200, selected.text
    assert selected.json()["storeName"] == "zeta"
    missing = client.post("/api/v1/auth/store", json={"storeName": "不存在"})
    assert missing.status_code == 400
    assert missing.json()["code"] == "AUTH_STORE_INVALID"

    monkeypatch.setattr(settings, "SKIP_LOGIN_STORE", "missing")
    unbound = client.get("/api/v1/auth/me")
    assert unbound.json()["storeSelected"] is False
    assert unbound.json()["storeName"] is None
    denied = client.get("/api/v1/products")
    assert denied.status_code == 403
    assert denied.json()["code"] == "AUTH_STORE_REQUIRED"
    assert client.get("/api/v1/system/stores").status_code == 200

    emails, sessions = _emails_and_sessions()
    assert emails == []
    assert sessions == []


def test_skip_login_without_stores_keeps_admin_routes_and_blocks_business(client, monkeypatch):
    _enable(monkeypatch)

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["storeSelected"] is False
    assert me.json()["storeName"] is None
    assert me.json()["user"]["role"] == "admin"
    stores = client.get("/api/v1/system/stores")
    assert stores.status_code == 200
    assert stores.json() == []
    blocked = client.get("/api/v1/products")
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "AUTH_STORE_REQUIRED"
    accounts = client.get("/api/v1/system/oauth/accounts")
    assert accounts.status_code == 403
    assert accounts.json()["code"] == "AUTH_STORE_REQUIRED"


@pytest.mark.parametrize(
    ("environment", "vercel_env"),
    [
        ("production", "preview"),
        ("Production", ""),
        ("preview", "production"),
        ("test", "Production"),
    ],
)
def test_production_ignores_skip_login(client, monkeypatch, environment, vercel_env):
    _enable(monkeypatch, environment=environment, vercel_env=vercel_env)
    _add_store("alpha")

    blocked = client.get("/api/v1/products")
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH_REQUIRED"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/system/stores").status_code == 401


def test_valid_session_is_not_replaced_by_the_synthetic_admin(client, google_jwks, monkeypatch):
    _add_account(STAFF_EMAIL, "staff", "店員")
    _add_store("alpha")
    login = _login(client, google_jwks, STAFF_EMAIL)
    _enable(monkeypatch)

    me = client.get("/api/v1/auth/me", headers=_auth(login["token"]))
    assert me.status_code == 200, me.text
    assert me.json()["user"]["email"] == STAFF_EMAIL
    assert me.json()["user"]["role"] == "staff"
    forbidden = client.get("/api/v1/system/stores", headers=_auth(login["token"]))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"
    pending = client.get("/api/v1/products", headers=_auth(login["token"]))
    assert pending.status_code == 403
    assert pending.json()["code"] == "AUTH_STORE_REQUIRED"


def test_invalid_or_expired_token_uses_the_synthetic_admin(client, google_jwks, monkeypatch):
    _add_account(ADMIN_EMAIL)
    _add_store("alpha")
    login = _login(client, google_jwks)
    _expire(login["token"])
    _enable(monkeypatch)

    expired = client.get("/api/v1/auth/me", headers=_auth(login["token"]))
    assert expired.status_code == 200, expired.text
    assert expired.json()["user"]["email"] == SKIP_LOGIN_EMAIL
    garbage = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-session"})
    assert garbage.status_code == 200
    assert garbage.json()["user"]["id"] == SKIP_LOGIN_ACCOUNT_ID
    assert garbage.json()["storeName"] == "alpha"


def test_google_login_stays_closed_when_skip_login_is_on(client, google_jwks, monkeypatch):
    _enable(monkeypatch)
    bad = client.post("/api/v1/auth/google", json={"credential": "not-a-google-token"})
    assert bad.status_code == 401
    assert bad.json()["code"] == "AUTH_INVALID_CREDENTIAL"
    stranger = client.post(
        "/api/v1/auth/google",
        json={"credential": _token(google_jwks, email="stranger@example.com")},
    )
    assert stranger.status_code == 403
    assert stranger.json()["code"] == "AUTH_ACCOUNT_NOT_ALLOWED"
    emails, _sessions = _emails_and_sessions()
    assert emails == []
    assert SKIP_LOGIN_EMAIL not in emails


def test_checkout_without_a_token_uses_the_synthetic_admin(client, monkeypatch):
    _enable(monkeypatch, store="alpha")
    _add_store("zeta")
    _add_store("alpha")
    created = client.post(
        "/api/v1/products",
        json={"sku": "SKU-1", "barcode": "111", "brand": "Brand", "name": "車", "listPrice": 100},
    )
    assert created.status_code == 201, created.text
    assert created.json()["createdBy"] == SKIP_LOGIN_NAME
    product_id = created.json()["id"]
    _set_store_stock(product_id, 1)

    checked_out = client.post(
        "/api/v1/checkout/orders",
        json={
            "branchId": "branch-online",
            "items": [{"productId": product_id, "quantity": 1}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": 100}],
        },
    )
    assert checked_out.status_code == 201, checked_out.text
    order = checked_out.json()["order"]
    assert order["branchId"] == "alpha"
    assert order["branchName"] == "alpha"
    assert order["cashierId"] == SKIP_LOGIN_ACCOUNT_ID
    assert order["cashierName"] == SKIP_LOGIN_NAME
    assert order["createdBy"] == SKIP_LOGIN_NAME
    assert _stock_qty(product_id, STORE_LOCATION) == 0
    assert "alpha" not in _stock_locations(product_id)
    created_at = datetime.fromisoformat(order["createdAt"])
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    assert abs((datetime.now(timezone.utc) - created_at).total_seconds()) < 120

    emails, sessions = _emails_and_sessions()
    assert SKIP_LOGIN_EMAIL not in emails
    assert sessions == []


def test_skip_login_admin_can_edit_the_whitelist_without_joining_it(client, monkeypatch):
    _enable(monkeypatch)
    _add_store("alpha")
    _add_account(ADMIN_EMAIL, "admin", "管理員")
    _add_account(STAFF_EMAIL, "staff", "店員")

    deleted = client.delete(f"/api/v1/system/oauth/accounts/{STAFF_EMAIL}")
    assert deleted.status_code == 200, deleted.text
    emails, sessions = _emails_and_sessions()
    assert STAFF_EMAIL not in emails
    assert ADMIN_EMAIL in emails
    assert SKIP_LOGIN_EMAIL not in emails
    assert sessions == []

    last = client.delete(f"/api/v1/system/oauth/accounts/{ADMIN_EMAIL}")
    assert last.status_code == 409
    assert last.json()["code"] == "ACCOUNT_LAST_ADMIN"
    emails, _sessions = _emails_and_sessions()
    assert SKIP_LOGIN_EMAIL not in emails
    assert ADMIN_EMAIL in emails


def test_logout_does_not_create_or_revoke_a_session(client, monkeypatch):
    _enable(monkeypatch)
    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    assert logged_out.json()["loggedOut"] is True
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == SKIP_LOGIN_EMAIL
    _emails, sessions = _emails_and_sessions()
    assert sessions == []


def test_synthetic_session_id_is_rejected_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(settings, "SKIP_LOGIN", False)
    db = SessionFactory()
    try:
        with pytest.raises(BusinessException) as caught:
            AuthService(db).lock_for_checkout(SKIP_LOGIN_SESSION_ID)
        assert caught.value.code == BusinessErrorCode.AUTH_SESSION_REVOKED
    finally:
        db.close()


def test_checkout_lock_without_a_store_still_requires_one(client, monkeypatch):
    _enable(monkeypatch)
    db = SessionFactory()
    try:
        with pytest.raises(BusinessException) as caught:
            AuthService(db).lock_for_checkout(SKIP_LOGIN_SESSION_ID)
        assert caught.value.code == BusinessErrorCode.AUTH_STORE_REQUIRED
    finally:
        db.close()
