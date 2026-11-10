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
    """業務 API。staff 必須已選存在的門市。admin 是最高權限，尚未選門市也可以。"""
    user = AuthService(db).authenticate(_bearer_token(request), require_store=False)
    if user.role != "admin" and not user.store_name:
        raise BusinessException(
            status_code=403,
            code=BusinessErrorCode.AUTH_STORE_REQUIRED,
            message="請先選擇門市",
        )
    return user


def require_admin_user(user: Principal = Depends(require_business_user)) -> Principal:
    """管理員。沿用業務守衛，所以尚未選門市的管理員也可以維護白名單。"""
    if user.role != "admin":
        raise BusinessException(
            status_code=403,
            code=BusinessErrorCode.AUTH_FORBIDDEN,
            message="需要管理員權限",
        )
    return user


def require_admin_session(request: Request, db: Session = Depends(get_db)) -> Principal:
    """管理員。尚未選門市也可以，供建立第一間門市與門市清單維護。"""
    user = AuthService(db).authenticate(_bearer_token(request), require_store=False)
    if user.role != "admin":
        raise BusinessException(
            status_code=403,
            code=BusinessErrorCode.AUTH_FORBIDDEN,
            message="需要管理員權限",
        )
    return user
