from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.deps import get_db, require_session_user
from src.schemas.auth import (
    AuthLoginDto,
    AuthStateDto,
    AuthUserDto,
    GoogleLoginRequest,
    LogoutDto,
    SelectStoreRequest,
)
from src.schemas.system import StoreDto
from src.services.auth_service import AuthService, Principal
from src.services.system_service import SystemService

router = APIRouter()


def _state(principal: Principal, *, token: str | None = None) -> AuthLoginDto | AuthStateDto:
    body = {
        "expiresAt": principal.expires_at,
        "storeSelected": principal.store_name is not None,
        "storeName": principal.store_name,
        "user": AuthUserDto(
            id=principal.account_id,
            email=principal.email,
            name=principal.name,
            role=principal.role,
        ),
    }
    if token is None:
        return AuthStateDto(**body)
    return AuthLoginDto(token=token, tokenType="Bearer", **body)


@router.post("/google", response_model=AuthLoginDto, response_model_by_alias=True)
def login_with_google(body: GoogleLoginRequest, db: Session = Depends(get_db)) -> AuthLoginDto:
    """用 Google ID token 換本系統 session。未在白名單的帳號不會被建立。"""
    token, principal = AuthService(db).login_with_google(body.credential)
    return _state(principal, token=token)  # type: ignore[return-value]


@router.get("/stores", response_model=List[StoreDto], response_model_by_alias=True)
def list_stores_for_login(
    db: Session = Depends(get_db),
    _user: Principal = Depends(require_session_user),
) -> List[StoreDto]:
    """選門市之前就能讀門市清單。不開放其他業務 API。"""
    return SystemService(db).stores()


@router.post("/store", response_model=AuthStateDto, response_model_by_alias=True)
def select_store(
    body: SelectStoreRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_session_user),
) -> AuthStateDto:
    """登入後選門市，之後換門市也走這裡，不必重新跟 Google 驗證。"""
    principal = AuthService(db).select_store(user, body.store_name)
    return _state(principal)  # type: ignore[return-value]


@router.post("/logout", response_model=LogoutDto, response_model_by_alias=True)
def logout(
    db: Session = Depends(get_db),
    user: Principal = Depends(require_session_user),
) -> LogoutDto:
    """只作廢這一個 session。其他裝置的 session 保持有效。"""
    AuthService(db).logout(user)
    return LogoutDto(loggedOut=True)


@router.get("/me", response_model=AuthStateDto, response_model_by_alias=True)
def current_session(user: Principal = Depends(require_session_user)) -> AuthStateDto:
    return _state(user)  # type: ignore[return-value]
