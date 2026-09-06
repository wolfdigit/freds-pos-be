from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.core.exceptions import BusinessException
from src.models.product import Product, ProductStock
from src.schemas.common import BusinessErrorCode
from src.schemas.product import (
    CreateProductRequest,
    LocationStock,
    Product as ProductSchema,
    StockLocation,
    UpdateProductRequest,
)

LOCATION_NAME_MAP = {
    StockLocation.STORE: "門市現貨",
    StockLocation.WAREHOUSE: "後方倉庫",
    StockLocation.COMPANY: "公司總倉",
    StockLocation.OTHER: "調度暫存",
}

STOCK_LOCATION_ORDER: Sequence[StockLocation] = (
    StockLocation.STORE,
    StockLocation.WAREHOUSE,
    StockLocation.COMPANY,
    StockLocation.OTHER,
)


def normalize_sku(value: str) -> str:
    """Uppercase and strip every character not in [A-Z0-9] (same as FE)."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _new_product_id() -> str:
    return f"prod-{uuid.uuid4().hex}"


def _to_product_schema(product: Product) -> ProductSchema:
    stocks_by_location = {s.location: s for s in product.stocks}
    stocks: List[LocationStock] = []
    for loc in STOCK_LOCATION_ORDER:
        row = stocks_by_location.get(loc.value)
        if row is not None:
            stocks.append(
                LocationStock(
                    location=StockLocation(row.location),
                    locationName=row.location_name,
                    quantity=row.quantity,
                )
            )
        else:
            stocks.append(
                LocationStock(
                    location=loc,
                    locationName=LOCATION_NAME_MAP[loc],
                    quantity=0,
                )
            )

    total_stock = sum(s.quantity for s in stocks)
    pending = (
        product.pre_order_pending.quantity
        if product.pre_order_pending is not None
        else 0
    )

    return ProductSchema(
        id=product.id,
        sku=product.sku,
        normalizedSku=product.normalized_sku,
        barcode=product.barcode,
        brand=product.brand,
        name=product.name,
        scale=product.scale,
        material=product.material,
        color=product.color,
        imageUrl=product.image_url,
        listPrice=product.list_price,
        costPrice=product.cost_price,
        vipPrice=product.vip_price,
        stocks=stocks,
        totalStock=total_stock,
        preOrderPendingCount=pending,
        note=product.note,
        status=product.status,
    )


def _keyword_matches(product: Product, keyword: str) -> bool:
    """Mirror FE mock: matchesSku || matchesName || matchesBrand."""
    trimmed = keyword.strip()
    if not trimmed:
        return True

    normalized_query = normalize_sku(trimmed)
    # isSkuMatch: empty normalized query → True; else SKU contains or barcode includes
    if not normalized_query:
        matches_sku = True
    else:
        matches_sku = normalized_query in product.normalized_sku or (
            trimmed in product.barcode
        )

    lower = trimmed.lower()
    matches_name = lower in product.name.lower()
    matches_brand = lower in product.brand.lower()
    return matches_sku or matches_name or matches_brand


class ProductService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_by_id_or_raise(self, product_id: str) -> Product:
        product = self.db.get(
            Product,
            product_id,
            options=[
                selectinload(Product.stocks),
                selectinload(Product.pre_order_pending),
            ],
        )
        if product is None:
            raise BusinessException(
                status_code=404,
                code=BusinessErrorCode.PRODUCT_NOT_FOUND,
                message="找不到指定商品",
            )
        return product

    def _ensure_sku_unique(self, sku: str, exclude_id: Optional[str] = None) -> None:
        stmt = select(Product.id).where(Product.sku == sku)
        if exclude_id is not None:
            stmt = stmt.where(Product.id != exclude_id)
        existing = self.db.scalar(stmt)
        if existing is not None:
            raise BusinessException(
                status_code=409,
                code=BusinessErrorCode.PRODUCT_SKU_DUPLICATE,
                message="貨號已存在",
            )

    def create(self, data: CreateProductRequest) -> ProductSchema:
        self._ensure_sku_unique(data.sku)

        now = datetime.now(timezone.utc)
        product = Product(
            id=_new_product_id(),
            sku=data.sku,
            normalized_sku=normalize_sku(data.sku),
            barcode=data.barcode,
            brand=data.brand,
            name=data.name,
            scale=data.scale.value,
            material=data.material,
            color=data.color,
            image_url=data.image_url,
            list_price=data.list_price,
            cost_price=data.cost_price,
            vip_price=data.vip_price,
            status=data.status.value,
            note=data.note,
            created_at=now,
            updated_at=now,
        )
        for loc in STOCK_LOCATION_ORDER:
            product.stocks.append(
                ProductStock(
                    location=loc.value,
                    location_name=LOCATION_NAME_MAP[loc],
                    quantity=0,
                )
            )

        self.db.add(product)
        self.db.commit()
        return _to_product_schema(self._get_by_id_or_raise(product.id))

    def get_by_id(self, product_id: str) -> ProductSchema:
        return _to_product_schema(self._get_by_id_or_raise(product_id))

    def update(self, product_id: str, data: UpdateProductRequest) -> ProductSchema:
        product = self._get_by_id_or_raise(product_id)
        updates = data.model_dump(exclude_unset=True)

        if "sku" in updates and updates["sku"] is not None:
            new_sku = updates["sku"]
            if new_sku != product.sku:
                self._ensure_sku_unique(new_sku, exclude_id=product.id)
                product.sku = new_sku
                product.normalized_sku = normalize_sku(new_sku)

        field_map = {
            "barcode": "barcode",
            "brand": "brand",
            "name": "name",
            "material": "material",
            "color": "color",
            "image_url": "image_url",
            "list_price": "list_price",
            "cost_price": "cost_price",
            "vip_price": "vip_price",
            "note": "note",
        }
        for src, dest in field_map.items():
            if src in updates:
                setattr(product, dest, updates[src])

        if "scale" in updates and updates["scale"] is not None:
            scale = updates["scale"]
            product.scale = scale.value if hasattr(scale, "value") else scale
        if "status" in updates and updates["status"] is not None:
            status = updates["status"]
            product.status = status.value if hasattr(status, "value") else status

        product.updated_at = datetime.now(timezone.utc)
        self.db.add(product)
        self.db.commit()
        return _to_product_schema(self._get_by_id_or_raise(product_id))

    def search(
        self,
        *,
        keyword: Optional[str] = None,
        scale: Optional[str] = None,
        brand: Optional[str] = None,
        in_stock_only: bool = False,
    ) -> List[ProductSchema]:
        stmt = select(Product).options(
            selectinload(Product.stocks),
            selectinload(Product.pre_order_pending),
        )

        if scale and scale != "ALL":
            stmt = stmt.where(Product.scale == scale)
        if brand and brand != "ALL":
            stmt = stmt.where(Product.brand == brand)

        if in_stock_only:
            stock_sum = (
                select(func.coalesce(func.sum(ProductStock.quantity), 0))
                .where(ProductStock.product_id == Product.id)
                .correlate(Product)
                .scalar_subquery()
            )
            stmt = stmt.where(stock_sum > 0)

        stmt = stmt.order_by(Product.sku.asc())
        products = list(self.db.scalars(stmt).unique().all())

        trimmed_keyword = (keyword or "").strip()
        if trimmed_keyword:
            products = [p for p in products if _keyword_matches(p, trimmed_keyword)]

        return [_to_product_schema(p) for p in products]
