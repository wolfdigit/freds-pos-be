from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_db, require_admin_session, require_admin_user, require_business_user
from src.schemas.system import (
    CreateOAuthAccountRequest,
    CreateStoreRequest,
    OAuthAccountDto,
    StoreDto,
    UpdateOAuthAccountRequest,
    UpdateStoreBindingRequest,
    UpdateStoreProductScopeRequest,
)
from src.schemas.store_product import (
    CopyStoreProductsRequest,
    StoreProductChangeResult,
    StoreProductBatchRequest,
    StoreProductPage,
)
from src.services.store_product_service import StoreProductService
from src.services.system_service import SystemService

router = APIRouter()


@router.get("/stores", response_model=List[StoreDto], response_model_by_alias=True)
def get_stores(db: Session = Depends(get_db), _user=Depends(require_admin_session)):
    return SystemService(db).stores()


@router.post("/stores", response_model=StoreDto, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_store(body: CreateStoreRequest, db: Session = Depends(get_db), user=Depends(require_admin_session)):
    return SystemService(db).create_store(body, actor_role=user.role)


@router.put("/stores/{storeName}", response_model=StoreDto, response_model_by_alias=True)
def rebind_store(
    body: UpdateStoreBindingRequest,
    storeName: str = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin_session),
):
    return SystemService(db).rebind_store(storeName, body, actor_role=user.role)


@router.delete("/stores/{storeName}")
def delete_store(storeName: str = Path(...), db: Session = Depends(get_db), user=Depends(require_admin_session)):
    return SystemService(db).delete_store(storeName, actor_role=user.role)


@router.put("/stores/{storeName}/product-scope", response_model=StoreDto, response_model_by_alias=True)
def set_store_product_scope(
    body: UpdateStoreProductScopeRequest,
    storeName: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(require_business_user),
):
    """切換門市販售範圍 all / list。一般店員也可以切換。"""
    return SystemService(db).set_product_scope(storeName, body)


DEFAULT_STORE_PRODUCT_PAGE_SIZE = 50
MAX_STORE_PRODUCT_PAGE_SIZE = 200


@router.get("/stores/{storeName}/products", response_model=StoreProductPage, response_model_by_alias=True)
def list_store_products(
    storeName: str = Path(...),
    keyword: Optional[str] = Query(None, description="SKU / barcode / name / brand"),
    inList: Optional[bool] = Query(None, description="true: only listed; false: only unlisted; omit: all"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(DEFAULT_STORE_PRODUCT_PAGE_SIZE, ge=1, le=MAX_STORE_PRODUCT_PAGE_SIZE),
    db: Session = Depends(get_db),
    _user=Depends(require_business_user),
):
    """門市商品清單的勾選畫面：搜尋整個商品目錄並標示 inList。一般店員也可以使用。"""
    return StoreProductService(db).page(
        storeName, keyword=keyword, in_list=inList, page=page, page_size=pageSize
    )


@router.post(
    "/stores/{storeName}/products/batch",
    response_model=StoreProductChangeResult,
    response_model_by_alias=True,
)
def batch_store_products(
    body: StoreProductBatchRequest,
    storeName: str = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
):
    """勾選畫面按「存檔」：add / remove 一次送出，同一個交易套用。一般店員也可以使用。"""
    return StoreProductService(db).batch(storeName, body, actor_name=user.name)


@router.post(
    "/stores/{storeName}/products/copy",
    response_model=StoreProductChangeResult,
    response_model_by_alias=True,
)
def copy_store_products(
    body: CopyStoreProductsRequest,
    storeName: str = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
):
    return StoreProductService(db).copy_from(storeName, body, actor_name=user.name)


@router.get("/oauth/accounts", response_model=List[OAuthAccountDto], response_model_by_alias=True)
def get_accounts(db: Session = Depends(get_db), _user=Depends(require_admin_user)):
    return SystemService(db).accounts()


@router.post("/oauth/accounts", response_model=OAuthAccountDto, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_account(body: CreateOAuthAccountRequest, db: Session = Depends(get_db), user=Depends(require_admin_user)):
    return SystemService(db).create_account(body, actor_role=user.role)


@router.put("/oauth/accounts/{email}", response_model=OAuthAccountDto, response_model_by_alias=True)
def update_account(
    body: UpdateOAuthAccountRequest,
    email: str = Path(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin_user),
):
    return SystemService(db).update_account(email, body, actor_email=user.email, actor_role=user.role)


@router.delete("/oauth/accounts/{email}")
def delete_account(email: str = Path(...), db: Session = Depends(get_db), user=Depends(require_admin_user)):
    return SystemService(db).delete_account(email, actor_email=user.email, actor_role=user.role)
