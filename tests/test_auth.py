import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from src.core.config import settings
from src.db.session import SessionFactory
from src.models.auth import AuthSession
from src.models.product import ProductStock
from src.models.system import OAuthAccount, StoreBranch
from src.schemas.common import BusinessErrorCode
from src.schemas.system import UpdateOAuthAccountRequest
from src.services.bootstrap import bootstrap_admin_if_empty
from src.services.checkout_service import STORE_LOCATION
from src.services.google_identity import GoogleTokenError, verify_google_id_token
from src.services.system_service import SystemService
from tests.conftest import pragma_columns

CLIENT_ID = "test-client.apps.googleusercontent.com"
ADMIN_EMAIL = "cashier@example.com"
STAFF_EMAIL = "clerk@example.com"


def _token(private_key, **overrides) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "exp": now + 600,
        "iat": now,
        "sub": "google-sub-should-not-be-stored",
        "email": ADMIN_EMAIL,
        "email_verified": True,
    }
    payload.update(overrides)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "test-key"})


def _add_account(email: str, role: str = "admin", name: str = "收銀員", account_id: str | None = None) -> str:
    account_id = account_id or f"acct-{uuid.uuid4().hex}"
    db = SessionFactory()
    try:
        db.add(OAuthAccount(id=account_id, email=email, role=role, name=name))
        db.commit()
    finally:
        db.close()
    return account_id


def _add_store(name: str) -> None:
    db = SessionFactory()
    try:
        db.add(StoreBranch(name=name, is_default=False))
        db.commit()
    finally:
        db.close()


def _login(client, google_jwks, email=ADMIN_EMAIL, **overrides) -> dict:
    credential = _token(google_jwks, email=email, **overrides)
    response = client.post("/api/v1/auth/google", json={"credential": credential})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _select(client, token: str, store_name: str):
    response = client.post("/api/v1/auth/store", json={"storeName": store_name}, headers=_auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_google_token_rejects_bad_signature_audience_issuer_expiry_and_unverified_email(signing_key, google_jwks):
    from cryptography.hazmat.primitives.asymmetric import rsa

    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(GoogleTokenError) as bad_sig:
        verify_google_id_token(_token(wrong_key), audiences=[CLIENT_ID])
    assert bad_sig.value.reason == "signature"

    with pytest.raises(GoogleTokenError) as bad_aud:
        verify_google_id_token(_token(signing_key, aud="other-client"), audiences=[CLIENT_ID])
    assert bad_aud.value.reason == "audience"

    with pytest.raises(GoogleTokenError) as bad_iss:
        verify_google_id_token(_token(signing_key, iss="https://evil.example"), audiences=[CLIENT_ID])
    assert bad_iss.value.reason == "issuer"

    with pytest.raises(GoogleTokenError) as expired:
        verify_google_id_token(_token(signing_key, exp=int(time.time()) - 120), audiences=[CLIENT_ID])
    assert expired.value.reason == "expired"

    with pytest.raises(GoogleTokenError) as unverified:
        verify_google_id_token(_token(signing_key, email_verified=False), audiences=[CLIENT_ID])
    assert unverified.value.reason == "email_verified"

    with pytest.raises(GoogleTokenError) as string_flag:
        verify_google_id_token(_token(signing_key, email_verified="true"), audiences=[CLIENT_ID])
    assert string_flag.value.reason == "email_verified"

    assert verify_google_id_token(_token(signing_key, email="Cashier@Example.com"), audiences=[CLIENT_ID]) == ADMIN_EMAIL


def test_unapproved_google_account_is_rejected_and_not_created(client, google_jwks):
    before = _account_count()
    response = client.post("/api/v1/auth/google", json={"credential": _token(google_jwks, email="stranger@example.com")})
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_ACCOUNT_NOT_ALLOWED"
    assert _account_count() == before
    assert "sub" not in pragma_columns("oauth_account")
    assert "google_sub" not in pragma_columns("auth_session")


def test_login_failure_does_not_echo_the_credential(client, caplog):
    credential = "unique-bad-credential-token-value"
    with caplog.at_level("ERROR"):
        response = client.post("/api/v1/auth/google", json={"credential": credential})
    assert response.status_code == 401
    assert credential not in response.text
    assert credential not in caplog.text


def test_missing_google_client_id_fails_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")

    def explode(force=False):
        raise AssertionError("jwks should not be fetched")

    monkeypatch.setattr("src.services.google_identity.load_jwks", explode)
    response = client.post("/api/v1/auth/google", json={"credential": "still-not-checked"})
    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_NOT_CONFIGURED"


def test_business_api_requires_login_and_store(client, google_jwks):
    open_health = client.get("/api/v1/health")
    assert open_health.status_code == 200

    blocked = client.get("/api/v1/products")
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "AUTH_REQUIRED"

    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    login = _login(client, google_jwks)
    assert login["tokenType"] == "Bearer"
    assert login["storeSelected"] is False
    assert login["user"]["id"].startswith("acct-")
    pending = client.get("/api/v1/products", headers=_auth(login["token"]))
    assert pending.status_code == 403
    assert pending.json()["code"] == "AUTH_STORE_REQUIRED"

    stores = client.get("/api/v1/auth/stores", headers=_auth(login["token"]))
    assert stores.status_code == 200
    assert [row["name"] for row in stores.json()] == ["奇可門市"]
    created_store = client.post("/api/v1/system/stores", json={"name": "新門市"}, headers=_auth(login["token"]))
    assert created_store.status_code == 201

    selected = _select(client, login["token"], "奇可門市")
    assert selected["storeSelected"] is True
    assert selected["storeName"] == "奇可門市"
    assert "token" not in selected
    assert client.get("/api/v1/products", headers=_auth(login["token"])).status_code == 200

    missing = client.post("/api/v1/auth/store", json={"storeName": "不存在"}, headers=_auth(login["token"]))
    assert missing.status_code == 400
    assert missing.json()["code"] == "AUTH_STORE_INVALID"


def test_staff_cannot_manage_whitelist_and_admin_guards_hold(client, google_jwks):
    admin_id = _add_account(ADMIN_EMAIL, "admin", "管理員甲")
    staff_id = _add_account(STAFF_EMAIL, "staff", "店員乙")
    _add_store("奇可門市")
    admin = _login(client, google_jwks, ADMIN_EMAIL)
    staff = _login(client, google_jwks, STAFF_EMAIL, sub="another-sub")
    _select(client, admin["token"], "奇可門市")
    _select(client, staff["token"], "奇可門市")

    forbidden = client.get("/api/v1/system/oauth/accounts", headers=_auth(staff["token"]))
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"
    assert client.get("/api/v1/products", headers=_auth(staff["token"])).status_code == 200

    created = client.post(
        "/api/v1/system/oauth/accounts",
        json={"email": "new-clerk@example.com", "role": "staff", "name": "新店員"},
        headers=_auth(admin["token"]),
    )
    assert created.status_code == 201
    assert created.json()["id"].startswith("acct-")
    assert created.json()["role"] == "staff"

    bad_role = client.post(
        "/api/v1/system/oauth/accounts",
        json={"email": "x@example.com", "role": "manager", "name": "不允許"},
        headers=_auth(admin["token"]),
    )
    assert bad_role.status_code == 400
    assert bad_role.json()["code"] == "ACCOUNT_ROLE_INVALID"

    promoted = client.put(
        f"/api/v1/system/oauth/accounts/{STAFF_EMAIL}",
        json={"role": "admin"},
        headers=_auth(admin["token"]),
    )
    assert promoted.status_code == 200

    self_demote = client.put(
        f"/api/v1/system/oauth/accounts/{ADMIN_EMAIL}",
        json={"role": "staff"},
        headers=_auth(admin["token"]),
    )
    assert self_demote.status_code == 409
    assert self_demote.json()["code"] == "ACCOUNT_SELF_PROTECTED"

    self_delete = client.delete(f"/api/v1/system/oauth/accounts/{ADMIN_EMAIL}", headers=_auth(admin["token"]))
    assert self_delete.status_code == 409
    assert self_delete.json()["code"] == "ACCOUNT_SELF_PROTECTED"

    demoted = client.put(
        f"/api/v1/system/oauth/accounts/{STAFF_EMAIL}",
        json={"role": "staff"},
        headers=_auth(admin["token"]),
    )
    assert demoted.status_code == 200

    last = client.put(
        f"/api/v1/system/oauth/accounts/{ADMIN_EMAIL}",
        json={"role": "staff"},
        headers=_auth(admin["token"]),
    )
    assert last.status_code == 409
    assert last.json()["code"] == "ACCOUNT_LAST_ADMIN"
    assert admin_id != staff_id


def test_concurrent_demotion_cannot_remove_every_admin(client):
    _add_account("a@example.com", "admin", "甲")
    _add_account("b@example.com", "admin", "乙")
    results: list[str] = []

    def demote(actor_email: str, target_email: str) -> None:
        db = SessionFactory()
        try:
            SystemService(db).update_account(
                target_email,
                UpdateOAuthAccountRequest(role="staff"),
                actor_email=actor_email,
                actor_role="admin",
            )
            results.append("ok")
        except Exception as exc:
            results.append(getattr(getattr(exc, "code", None), "value", str(exc)))
        finally:
            db.close()

    first = threading.Thread(target=demote, args=("a@example.com", "b@example.com"))
    second = threading.Thread(target=demote, args=("b@example.com", "a@example.com"))
    first.start()
    second.start()
    first.join()
    second.join()

    db = SessionFactory()
    try:
        admins = list(db.scalars(select(OAuthAccount).where(OAuthAccount.role == "admin")).all())
    finally:
        db.close()
    assert len(admins) == 1
    assert results.count("ok") == 1


def test_logout_expiry_and_revocation_are_per_session(client, google_jwks):
    _add_account(ADMIN_EMAIL)
    _add_store("奇可門市")
    first = _login(client, google_jwks, sub="device-1")
    second = _login(client, google_jwks, sub="device-2")
    _select(client, first["token"], "奇可門市")
    _select(client, second["token"], "奇可門市")

    logged_out = client.post("/api/v1/auth/logout", headers=_auth(first["token"]))
    assert logged_out.status_code == 200
    assert logged_out.json()["loggedOut"] is True
    assert client.get("/api/v1/auth/me", headers=_auth(first["token"])).status_code == 401
    assert client.get("/api/v1/products", headers=_auth(second["token"])).status_code == 200

    _expire(second["token"])
    expired = client.get("/api/v1/products", headers=_auth(second["token"]))
    assert expired.status_code == 401
    assert expired.json()["code"] == "AUTH_SESSION_EXPIRED"


def test_deleted_account_and_role_change_apply_on_the_next_request(client, google_jwks):
    _add_account(ADMIN_EMAIL, "admin", "管理員甲")
    _add_account(STAFF_EMAIL, "admin", "管理員乙")
    _add_store("奇可門市")
    target = _login(client, google_jwks, STAFF_EMAIL)
    actor = _login(client, google_jwks, ADMIN_EMAIL)
    _select(client, target["token"], "奇可門市")
    _select(client, actor["token"], "奇可門市")

    changed = client.put(
        f"/api/v1/system/oauth/accounts/{STAFF_EMAIL}",
        json={"role": "staff"},
        headers=_auth(actor["token"]),
    )
    assert changed.status_code == 200
    me = client.get("/api/v1/auth/me", headers=_auth(target["token"]))
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "staff"
    assert client.get("/api/v1/system/oauth/accounts", headers=_auth(target["token"])).status_code == 403
    assert client.get("/api/v1/products", headers=_auth(target["token"])).status_code == 200

    deleted = client.delete(f"/api/v1/system/oauth/accounts/{STAFF_EMAIL}", headers=_auth(actor["token"]))
    assert deleted.status_code == 200
    denied = client.get("/api/v1/products", headers=_auth(target["token"]))
    assert denied.status_code == 401
    assert denied.json()["code"] == "AUTH_ACCOUNT_NOT_ALLOWED"


def test_checkout_uses_session_store_and_shared_shelf(client, google_jwks):
    account_id = _add_account(ADMIN_EMAIL, "admin", "櫃台小王")
    _add_store("奇可門市")
    _add_store("線上網購")
    login = _login(client, google_jwks)
    _select(client, login["token"], "奇可門市")
    created = client.post(
        "/api/v1/products",
        json={"sku": "SKU-1", "barcode": "111", "brand": "Brand", "name": "車", "listPrice": 100},
        headers=_auth(login["token"]),
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    _set_store_stock(product_id, 1)

    first = client.post(
        "/api/v1/checkout/orders",
        json={
            "branchId": "branch-online",
            "items": [{"productId": product_id, "quantity": 1}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": 100}],
        },
        headers=_auth(login["token"]),
    )
    assert first.status_code == 201, first.text
    order = first.json()["order"]
    assert order["branchId"] == "奇可門市"
    assert order["branchName"] == "奇可門市"
    assert order["cashierId"] == account_id
    assert order["cashierName"] == "櫃台小王"

    _select(client, login["token"], "線上網購")
    second = client.post(
        "/api/v1/checkout/orders",
        json={
            "items": [{"productId": product_id, "quantity": 1}],
            "shippingFee": 0,
            "payments": [{"type": "cash", "name": "現金", "amount": 100}],
        },
        headers=_auth(login["token"]),
    )
    assert second.status_code == 409
    assert second.json()["code"] == "INSUFFICIENT_STORE_STOCK"


def test_bootstrap_runs_once_and_refuses_demo_addresses(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_BOOTSTRAP_ADMIN_EMAIL", "fred@gmail.com")
    monkeypatch.setattr(settings, "AUTH_BOOTSTRAP_ADMIN_NAME", "不該寫入")
    db = SessionFactory()
    try:
        bootstrap_admin_if_empty(db)
        assert db.scalar(select(OAuthAccount)) is None
    finally:
        db.close()

    monkeypatch.setattr(settings, "AUTH_BOOTSTRAP_ADMIN_EMAIL", "owner@example.com")
    monkeypatch.setattr(settings, "AUTH_BOOTSTRAP_ADMIN_NAME", "初始管理員")
    db = SessionFactory()
    try:
        bootstrap_admin_if_empty(db)
        row = db.scalar(select(OAuthAccount))
        assert row is not None
        assert row.email == "owner@example.com"
        assert row.role == "admin"
        assert row.name == "初始管理員"
        row.role = "staff"
        db.commit()
        bootstrap_admin_if_empty(db)
        db.refresh(row)
        assert row.role == "staff"
    finally:
        db.close()


def test_blank_whitelist_name_uses_email_not_google_profile(client, google_jwks):
    _add_account(ADMIN_EMAIL, name=None)  # type: ignore[arg-type]
    db = SessionFactory()
    try:
        row = db.get(OAuthAccount, ADMIN_EMAIL)
        row.name = None
        db.commit()
    finally:
        db.close()
    login = _login(client, google_jwks, name="Google 顯示名")
    assert login["user"]["name"] == ADMIN_EMAIL
    assert login["user"]["id"].startswith("acct-")


def _account_count() -> int:
    db = SessionFactory()
    try:
        return len(db.scalars(select(OAuthAccount)).all())
    finally:
        db.close()


def _expire(raw_token: str) -> None:
    import hashlib

    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db = SessionFactory()
    try:
        session = db.get(AuthSession, digest)
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()
    finally:
        db.close()


def _set_store_stock(product_id: str, quantity: int) -> None:
    db = SessionFactory()
    try:
        stock = db.scalar(
            select(ProductStock).where(
                ProductStock.product_id == product_id,
                ProductStock.location == STORE_LOCATION,
            )
        )
        stock.quantity = quantity
        db.commit()
    finally:
        db.close()


def test_error_code_constant_is_used():
    assert BusinessErrorCode.AUTH_REQUIRED.value == "AUTH_REQUIRED"
