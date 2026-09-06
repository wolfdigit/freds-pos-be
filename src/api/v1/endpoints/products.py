from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.product import CreateProductRequest, Product, UpdateProductRequest
from src.services.product_service import ProductService

router = APIRouter()


@router.get(
    "",
    response_model=List[Product],
    response_model_by_alias=True,
    summary="Search products",
)
def search_products(
    keyword: Optional[str] = Query(None, description="SKU / barcode / name / brand"),
    scale: Optional[str] = Query(None, description="ModelScale or ALL"),
    brand: Optional[str] = Query(None, description="Brand filter, or ALL"),
    inStockOnly: bool = Query(False, description="Only products with totalStock > 0"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> List[Product]:
    """Default sort: sku ASC."""
    return ProductService(db).search(
        keyword=keyword,
        scale=scale,
        brand=brand,
        in_stock_only=inStockOnly,
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
    _user=Depends(get_current_user_optional),
) -> Product:
    return ProductService(db).create(body)


@router.get(
    "/{productId}",
    response_model=Product,
    response_model_by_alias=True,
    summary="Get product by ID",
)
def get_product(
    productId: str = Path(..., description="Product id"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> Product:
    return ProductService(db).get_by_id(productId)


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
    _user=Depends(get_current_user_optional),
) -> Product:
    return ProductService(db).update(productId, body)
