from typing import List

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.system import (
    CreateOAuthAccountRequest,
    CreateStoreRequest,
    OAuthAccountDto,
    StoreDto,
    UpdateOAuthAccountRequest,
)
from src.services.system_service import SystemService

router = APIRouter()


@router.get("/stores", response_model=List[StoreDto], response_model_by_alias=True)
def get_stores(db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return SystemService(db).stores()


@router.post("/stores", response_model=StoreDto, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_store(body: CreateStoreRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return SystemService(db).create_store(body)


@router.delete("/stores/{storeName}")
def delete_store(storeName: str = Path(...), db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return SystemService(db).delete_store(storeName)


@router.get("/oauth/accounts", response_model=List[OAuthAccountDto], response_model_by_alias=True)
def get_accounts(db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return SystemService(db).accounts()


@router.post("/oauth/accounts", response_model=OAuthAccountDto, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_account(body: CreateOAuthAccountRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return SystemService(db).create_account(body)


@router.put("/oauth/accounts/{email}", response_model=OAuthAccountDto, response_model_by_alias=True)
def update_account(
    body: UpdateOAuthAccountRequest,
    email: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
):
    return SystemService(db).update_account(email, body)


@router.delete("/oauth/accounts/{email}")
def delete_account(email: str = Path(...), db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return SystemService(db).delete_account(email)
