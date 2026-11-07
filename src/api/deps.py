from typing import Generator, Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.db.session import SessionFactory
from src.schemas.common import BusinessErrorCode
from src.services.auth_service import AuthService, Principal


def get_db() -> Generator[Session, None, None]:
    """每個請求一個 Session，結束時關閉。"""
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    return token or None


def require_session_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    """已驗證身份，尚未選門市也可以。"""
    return AuthService(db).authenticate(_bearer_token(request), require_store=False)


def require_business_user(request: Request, db: Session = Depends(get_db)) -> Principal:
    """業務 API：必須已登入且已選存在的門市。"""
    return AuthService(db).authenticate(_bearer_token(request), require_store=True)


def require_admin_user(user: Principal = Depends(require_business_user)) -> Principal:
    if user.role != "admin":
        raise BusinessException(
            status_code=403,
            code=BusinessErrorCode.AUTH_FORBIDDEN,
            message="需要管理員權限",
        )
    return user


def require_store_creator(request: Request, db: Session = Depends(get_db)) -> Principal:
    """已選門市者皆可新增門市。還沒有門市時，只有管理員可建立第一間。"""
    user = AuthService(db).authenticate(_bearer_token(request), require_store=False)
    if user.store_name:
        return user
    if user.role != "admin":
        raise BusinessException(
            status_code=403,
            code=BusinessErrorCode.AUTH_STORE_REQUIRED,
            message="請先選擇門市",
        )
    return user
