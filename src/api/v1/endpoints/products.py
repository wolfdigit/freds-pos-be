from typing import Optional

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
    response_model=ProductPage,
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
    allProducts: bool = Query(
        False, description="Ignore the store's product list (list-scope stores); any business user. Wins over storeName's list"
    ),
    storeName: Optional[str] = Query(
        None,
        description=(
            "Look at this store instead of the login store: its product list (list scope), "
            "loginStore* fields, soldInLoginStore and loginStoreQuantityMin/Max. Unknown store = 404 STORE_NOT_FOUND"
        ),
    ),
    page: int = Query(1, ge=1, description="1-based page"),
    pageSize: int = Query(
        DEFAULT_PRODUCT_PAGE_SIZE,
        ge=1,
        le=MAX_PRODUCT_PAGE_SIZE,
        description=f"Page size (default {DEFAULT_PRODUCT_PAGE_SIZE}, max {MAX_PRODUCT_PAGE_SIZE})",
    ),
    db: Session = Depends(get_db),
    user=Depends(require_business_user),
) -> ProductPage:
    """Default sort: sku ASC.

    When the login store's productScope is 'list', only products in that
    store's list are returned (any business user may pass allProducts=true). Admin without
    a store sees every product.

    `storeName` swaps the login store for another store for this request only: the list
    filter, `loginStore*` quantities, `soldInLoginStore` and the `loginStoreQuantity*`
    filters all describe that store. `allProducts=true` still skips the list.

    Always returns `{items, page, pageSize, total}`. Defaults: page=1, pageSize=50.
    """
    service = ProductService(db)
    context_store = service.context_store_name(user.store_name, storeName)
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
        store_name=context_store,
        all_products=allProducts,
    )
    return service.search_page(
        page=page,
        page_size=pageSize,
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
