from typing import List, Optional, Union

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_db, require_business_user
from src.schemas.product import CreateProductRequest, Product, ProductPage, UpdateProductRequest
from src.services.product_service import ProductService, StockFilters

router = APIRouter()


DEFAULT_PRODUCT_PAGE_SIZE = 50
MAX_PRODUCT_PAGE_SIZE = 200


@router.get(
    "",
    response_model=Union[ProductPage, List[Product]],
    response_model_by_alias=True,
    summary="Search products",
)
def search_products(
    keyword: Optional[str] = Query(None, description="SKU / barcode / name / brand"),
    scale: Optional[str] = Query(None, description="ModelScale or ALL"),
    brand: Optional[str] = Query(None, description="Brand filter, or ALL"),
    barcode: Optional[str] = Query(None, description="Exact barcode match"),
    inInventoryOnly: bool = Query(False, description="Only products with totalInventory > 0"),
    loginStoreQuantityMin: Optional[int] = Query(
        None, description="loginStoreQuantity >= N (login store's sellable location; no store = no match)"
    ),
    loginStoreQuantityMax: Optional[int] = Query(
        None, description="loginStoreQuantity <= N (login store's sellable location; no store = no match)"
    ),
    locationId: Optional[str] = Query(None, description="Location for locationQuantityMin/Max"),
    locationQuantityMin: Optional[int] = Query(None, description="Quantity at locationId >= N"),
    locationQuantityMax: Optional[int] = Query(None, description="Quantity at locationId <= N"),
    totalInventoryMin: Optional[int] = Query(None, description="totalInventory >= N"),
    totalInventoryMax: Optional[int] = Query(None, description="totalInventory <= N"),
    page: Optional[int] = Query(None, ge=1, description="1-based page; enables the paged response"),
    pageSize: Optional[int] = Query(
        None,
        ge=1,
        le=MAX_PRODUCT_PAGE_SIZE,
        description=f"Page size (default {DEFAULT_PRODUCT_PAGE_SIZE}); enables the paged response",
    ),
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
) -> Union[ProductPage, List[Product]]:
    """Default sort: sku ASC.

    Without page/pageSize the response is the full array (unchanged, for the
    already deployed frontend). With either one it is
    `{items, page, pageSize, total}`.
    """
    service = ProductService(db)
    stock = StockFilters(
        login_store_min=loginStoreQuantityMin,
        login_store_max=loginStoreQuantityMax,
        location_id=(locationId or "").strip() or None,
        location_min=locationQuantityMin,
        location_max=locationQuantityMax,
        total_min=totalInventoryMin,
        total_max=totalInventoryMax,
    )
    filters = dict(
        keyword=keyword,
        scale=scale,
        brand=brand,
        barcode=barcode,
        in_inventory_only=inInventoryOnly,
        stock=stock if stock != StockFilters() else None,
        store_name=user.store_name,
    )
    if page is None and pageSize is None:
        return service.search(**filters)
    return service.search_page(
        page=page or 1,
        page_size=pageSize or DEFAULT_PRODUCT_PAGE_SIZE,
        **filters,
    )


@router.post(
    "",
    response_model=Product,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
)
def create_product(
    body: CreateProductRequest,
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
) -> Product:
    return ProductService(db).create(body, actor_name=user.name, store_name=user.store_name)


@router.get(
    "/{productId}",
    response_model=Product,
    response_model_by_alias=True,
    summary="Get product by ID",
)
def get_product(
    productId: str = Path(..., description="Product id"),
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
) -> Product:
    return ProductService(db).get_by_id(productId, store_name=user.store_name)


@router.put(
    "/{productId}",
    response_model=Product,
    response_model_by_alias=True,
    summary="Update product metadata",
)
def update_product(
    body: UpdateProductRequest,
    productId: str = Path(..., description="Product id"),
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
) -> Product:
    return ProductService(db).update(
        productId, body, actor_name=user.name, store_name=user.store_name
    )
