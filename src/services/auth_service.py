from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import BusinessException
from src.models.auth import AuthSession
from src.models.system import OAuthAccount, StoreBranch
from src.schemas.common import BusinessErrorCode
from src.services.bootstrap import bootstrap_admin_if_empty
from src.services.google_identity import GoogleTokenError, verify_google_id_token

SESSION_TTL = timedelta(hours=12)
ALLOWED_ROLES = frozenset({"admin", "staff"})
# 跳過登入時的固定身份。不寫入白名單，也不能當成 Google 登入帳號。
SKIP_LOGIN_SESSION_ID = "skip-login"
SKIP_LOGIN_ACCOUNT_ID = "acct-skip-login"
SKIP_LOGIN_EMAIL = "skip-login@invalid.test"
SKIP_LOGIN_NAME = "免登入測試"
_INVALID_SESSION = frozenset(
    {
        BusinessErrorCode.AUTH_REQUIRED,
        BusinessErrorCode.AUTH_SESSION_REVOKED,
        BusinessErrorCode.AUTH_SESSION_EXPIRED,
        BusinessErrorCode.AUTH_ACCOUNT_NOT_ALLOWED,
    }
)


@dataclass
class Principal:
    session_id: str
    account_id: str
    email: str
    name: str
    role: str
    store_name: Optional[str]
    expires_at: datetime

    def __getitem__(self, key: str) -> str:
        if key == "id":
            return self.account_id
        if key == "name":
            return self.name
        if key == "role":
            return self.role
        if key == "email":
            return self.email
        raise KeyError(key)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


def display_name(account: OAuthAccount) -> str:
    name = (account.name or "").strip()
    resolved = name or account.email
    if not resolved or len(resolved) > 128:
        _raise(403, BusinessErrorCode.ACCOUNT_NAME_REQUIRED, "請由管理員設定 128 字以內的顯示名稱")
    return resolved


def _normalize_role(role: Optional[str]) -> str:
    value = (role or "").strip().lower()
    if value not in ALLOWED_ROLES:
        _raise(403, BusinessErrorCode.AUTH_FORBIDDEN, "角色無法使用系統")
    return value


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def login_with_google(self, credential: str) -> tuple[str, Principal]:
        if not settings.google_client_ids():
            _raise(503, BusinessErrorCode.AUTH_NOT_CONFIGURED, "Google 登入尚未設定")
        bootstrap_admin_if_empty(self.db)
        try:
            email = verify_google_id_token(credential, audiences=settings.google_client_ids())
        except GoogleTokenError as exc:
            if exc.reason == "jwks":
                _raise(503, BusinessErrorCode.AUTH_PROVIDER_UNAVAILABLE, "暫時無法驗證 Google 登入")
            _raise(401, BusinessErrorCode.AUTH_INVALID_CREDENTIAL, "Google 登入憑證無效或已過期")
        account = self.db.get(OAuthAccount, email)
        if account is None:
            _raise(403, BusinessErrorCode.AUTH_ACCOUNT_NOT_ALLOWED, "此 Google 帳號未獲授權")
        role = _normalize_role(account.role)
        name = display_name(account)
        raw_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        session = AuthSession(
            id=_token_hash(raw_token),
            account_id=account.id,
            email=account.email,
            store_name=None,
            created_at=now,
            expires_at=now + SESSION_TTL,
            revoked_at=None,
        )
        self.db.add(session)
        self.db.commit()
        return raw_token, _principal(session, account_id=account.id, email=account.email, name=name, role=role, store_name=None)

    def authenticate(self, raw_token: Optional[str], *, require_store: bool) -> Principal:
        if raw_token:
            try:
                return self._authenticate_session(raw_token, require_store=require_store)
            except BusinessException as exc:
                if exc.code not in _INVALID_SESSION or not settings.skip_login_active():
                    raise
        elif not settings.skip_login_active():
            _raise(401, BusinessErrorCode.AUTH_REQUIRED, "需要登入")
        return self._synthetic_admin(require_store=require_store)

    def _authenticate_session(self, raw_token: str, *, require_store: bool) -> Principal:
        session = self._load_session(raw_token)
        account = self._load_account(session)
        role = _normalize_role(account.role)
        name = display_name(account)
        store_name = self._clear_missing_store(session)
        if require_store and not store_name:
            _raise(403, BusinessErrorCode.AUTH_STORE_REQUIRED, "請先選擇門市")
        return _principal(
            session,
            account_id=account.id,
            email=account.email,
            name=name,
            role=role,
            store_name=store_name,
        )

    def lock_for_checkout(self, session_id: str) -> Principal:
        """鎖住這筆 session，讓換門市與結帳不會各寫各的。"""
        if session_id == SKIP_LOGIN_SESSION_ID:
            if not settings.skip_login_active():
                _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
            # 與正式 session 相同，先結束登入檢查的讀取快照，再重讀門市。
            self.db.rollback()
            return self._synthetic_admin(require_store=True)
        # 結束登入檢查時已開啟的讀取快照，避免沿用換門市之前的門市。
        self.db.rollback()
        self.db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id)
            .values(expires_at=AuthSession.expires_at)
        )
        self.db.flush()
        session = self.db.get(AuthSession, session_id)
        if session is None:
            _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
        self.db.refresh(session)
        self._ensure_session_active(session)
        account = self.db.scalar(
            select(OAuthAccount)
            .where(OAuthAccount.email == session.email)
            .execution_options(populate_existing=True)
        )
        if account is None or account.id != session.account_id:
            _raise(401, BusinessErrorCode.AUTH_ACCOUNT_NOT_ALLOWED, "帳號已不在授權名單")
        role = _normalize_role(account.role)
        name = display_name(account)
        store_name = (session.store_name or "").strip() or None
        if store_name is None or self.db.get(StoreBranch, store_name) is None:
            session.store_name = None
            _raise(403, BusinessErrorCode.AUTH_STORE_REQUIRED, "請先選擇門市")
        return _principal(
            session,
            account_id=account.id,
            email=account.email,
            name=name,
            role=role,
            store_name=store_name,
        )

    def select_store(self, principal: Principal, store_name: str) -> Principal:
        name = store_name.strip()
        if not name or self.db.get(StoreBranch, name) is None:
            _raise(400, BusinessErrorCode.AUTH_STORE_INVALID, "門市不存在")
        if principal.session_id == SKIP_LOGIN_SESSION_ID:
            if not settings.skip_login_active():
                _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
            # 沒有 session 列可寫。門市仍以 SKIP_LOGIN_STORE 或第一間門市為準。
            return self._synthetic_admin(require_store=False)
        self.db.execute(
            update(AuthSession).where(AuthSession.id == principal.session_id).values(store_name=name)
        )
        self.db.commit()
        principal.store_name = name
        return principal

    def logout(self, principal: Principal) -> None:
        if principal.session_id == SKIP_LOGIN_SESSION_ID:
            if not settings.skip_login_active():
                _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
            return
        session = self.db.get(AuthSession, principal.session_id)
        if session is None or session.revoked_at is not None:
            _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
        session.revoked_at = datetime.now(timezone.utc)
        self.db.commit()

    def _synthetic_admin(self, *, require_store: bool) -> Principal:
        """測試用管理員。不建立 oauth_account 或 auth_session。"""
        store_name = self._skip_login_store()
        if require_store and not store_name:
            _raise(403, BusinessErrorCode.AUTH_STORE_REQUIRED, "請先選擇門市")
        now = datetime.now(timezone.utc)
        return Principal(
            session_id=SKIP_LOGIN_SESSION_ID,
            account_id=SKIP_LOGIN_ACCOUNT_ID,
            email=SKIP_LOGIN_EMAIL,
            name=SKIP_LOGIN_NAME,
            role="admin",
            store_name=store_name,
            expires_at=now + SESSION_TTL,
        )

    def _skip_login_store(self) -> Optional[str]:
        named = (settings.SKIP_LOGIN_STORE or "").strip()
        if named:
            if self.db.get(StoreBranch, named) is None:
                return None
            return named
        row = self.db.scalar(select(StoreBranch).order_by(StoreBranch.name).limit(1))
        if row is None:
            return None
        return row.name

    def _load_session(self, raw_token: Optional[str]) -> AuthSession:
        if not raw_token:
            _raise(401, BusinessErrorCode.AUTH_REQUIRED, "需要登入")
        session = self.db.get(AuthSession, _token_hash(raw_token))
        if session is None or session.revoked_at is not None:
            _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
        self._ensure_session_active(session)
        return session

    def _ensure_session_active(self, session: AuthSession) -> None:
        if session.revoked_at is not None:
            _raise(401, BusinessErrorCode.AUTH_SESSION_REVOKED, "登入已失效")
        if _aware(session.expires_at) <= datetime.now(timezone.utc):
            _raise(401, BusinessErrorCode.AUTH_SESSION_EXPIRED, "登入已過期")

    def _load_account(self, session: AuthSession) -> OAuthAccount:
        account = self.db.scalar(
            select(OAuthAccount)
            .where(OAuthAccount.email == session.email)
            .execution_options(populate_existing=True)
        )
        if account is None or account.id != session.account_id:
            _raise(401, BusinessErrorCode.AUTH_ACCOUNT_NOT_ALLOWED, "帳號已不在授權名單")
        return account

    def _clear_missing_store(self, session: AuthSession) -> Optional[str]:
        name = (session.store_name or "").strip() or None
        if name is None:
            return None
        if self.db.get(StoreBranch, name) is not None:
            return name
        session.store_name = None
        self.db.commit()
        return None


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _principal(
    session: AuthSession,
    *,
    account_id: str,
    email: str,
    name: str,
    role: str,
    store_name: Optional[str],
) -> Principal:
    return Principal(
        session_id=session.id,
        account_id=account_id,
        email=email,
        name=name,
        role=role,
        store_name=store_name,
        expires_at=_aware(session.expires_at),
    )
