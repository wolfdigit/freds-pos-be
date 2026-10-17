from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.models.location import StockLocation

from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session, selectinload

from src.core.exceptions import BusinessException
from src.models.product import Product, ProductStock
from src.schemas.common import BusinessErrorCode
from src.schemas.product import (
    CreateProductRequest,
    LocationStock,
    Product as ProductSchema,
    UpdateProductRequest,
)
from src.services.inventory_service import ensure_locations


# 將 SKU 轉成大寫並移除非 A-Z/0-9 字元（與前端相同）。
# value: 原始貨號字串。
def normalize_sku(value: str) -> str:
    """Uppercase and strip every character not in [A-Z0-9] (same as FE)."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


# 產生新商品主鍵，格式為 prod-{32 位 hex uuid}。
def _new_product_id() -> str:
    return f"prod-{uuid.uuid4().hex}"


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _actor_name(actor_name: Optional[str]) -> Optional[str]:
    return _blank_to_none(actor_name)


# 將 ORM Product 轉成 API 的 ProductSchema（含庫存與預購待出）。
# product: 已載入關聯的商品
def _to_product_schema(product: Product, locations: Sequence[StockLocation]) -> ProductSchema:
    stocks_by_location = {s.location: s for s in product.stocks}
    stocks: List[LocationStock] = []
    seen = set()
    for loc in locations:
        seen.add(loc.id)
        row = stocks_by_location.get(loc.id)
        stocks.append(
            LocationStock(
                location=loc.id,
                locationName=row.location_name if row is not None else loc.name,
                quantity=row.quantity if row is not None else 0,
            )
        )
    for row in product.stocks:
        if row.location not in seen:
            stocks.append(
                LocationStock(
                    location=row.location,
                    locationName=row.location_name,
                    quantity=row.quantity,
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
        scale=product.scale or None,
        spec=product.spec,
        material=product.material,
        color=product.color,
        imageUrl=product.image_url,
        listPrice=product.list_price,
        vipPrice=product.vip_price,
        stocks=stocks,
        totalStock=total_stock,
        preOrderPendingCount=pending,
        note=product.note,
        deleted=product.deleted,
        createdAt=product.created_at,
        createdBy=product.created_by,
        updatedAt=product.updated_at,
        updatedBy=product.updated_by,
    )


# LIKE 子字串比對：跳脫 % / _ / \，行為對齊 Python `in`。
def _contains_like(column: ColumnElement, value: str) -> ColumnElement:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.like(f"%{escaped}%", escape="\\")


class ProductService:
    # 綁定此 service 使用的資料庫 session。
    # db: 被綁定的 SQLAlchemy Session。
    def __init__(self, db: Session) -> None:
        self.db = db

    # 依 product_id (商品主鍵) 查商品並預載庫存與預購；找不到則拋 404。
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

    # 確認 SKU 未被其他商品使用，重複則拋 409。
    # sku: 欲檢查的貨號
    # exclude_id: 更新時排除自身的商品 id
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

    # 新增商品並建立各地點庫存列（數量 0）。
    # data: 建立商品的請求內容。
    def create(self, data: CreateProductRequest, *, actor_name: Optional[str] = None) -> ProductSchema:
        self._ensure_sku_unique(data.sku)

        now = datetime.now(timezone.utc)
        actor = _actor_name(actor_name)
        product = Product(
            id=_new_product_id(),
            sku=data.sku,
            normalized_sku=normalize_sku(data.sku),
            barcode=data.barcode,
            brand=data.brand,
            name=data.name,
            scale=data.scale.value if data.scale is not None else "",
            spec=_blank_to_none(data.spec),
            material=data.material,
            color=data.color,
            image_url=data.image_url,
            list_price=data.list_price,
            vip_price=data.vip_price,
            deleted=False,
            note=data.note,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        for loc in ensure_locations(self.db):
            if not loc.is_active:
                continue
            product.stocks.append(
                ProductStock(
                    location=loc.id,
                    location_name=loc.name,
                    quantity=0,
                )
            )

        self.db.add(product)
        self.db.commit()
        return _to_product_schema(self._get_by_id_or_raise(product.id), ensure_locations(self.db))

    # 依 product_id (商品主鍵) 取得單一商品的 API 資料。
    def get_by_id(self, product_id: str) -> ProductSchema:
        return _to_product_schema(self._get_by_id_or_raise(product_id), ensure_locations(self.db))

    # 更新指定商品已提供的欄位。
    # product_id: 商品主鍵
    # data: 部分更新請求
    def update(
        self,
        product_id: str,
        data: UpdateProductRequest,
        *,
        actor_name: Optional[str] = None,
    ) -> ProductSchema:
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
            "vip_price": "vip_price",
            "note": "note",
        }
        for src, dest in field_map.items():
            if src in updates:
                setattr(product, dest, updates[src])

        if "spec" in updates:
            product.spec = _blank_to_none(updates["spec"])
        if "scale" in updates and updates["scale"] is not None:
            scale = updates["scale"]
            product.scale = scale.value if hasattr(scale, "value") else scale
        if "deleted" in updates and updates["deleted"] is not None:
            product.deleted = bool(updates["deleted"])

        product.updated_at = datetime.now(timezone.utc)
        product.updated_by = _actor_name(actor_name)
        self.db.add(product)
        self.db.commit()
        return _to_product_schema(self._get_by_id_or_raise(product_id), ensure_locations(self.db))

    # 依條件搜尋商品。關鍵字／比例／品牌／庫存篩選都在 SQL 執行。
    # keyword: 關鍵字
    # scale/brand: 比例與品牌
    # in_stock_only: 是否僅回傳有庫存者
    def search(
        self,
        *,
        keyword: Optional[str] = None,
        scale: Optional[str] = None,
        brand: Optional[str] = None,
        in_stock_only: bool = False,
    ) -> List[ProductSchema]:
        stmt = (
            select(Product)
            .where(Product.deleted.is_(False))
            .options(
                selectinload(Product.stocks),
                selectinload(Product.pre_order_pending),
            )
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

        trimmed_keyword = (keyword or "").strip()
        if trimmed_keyword:
            name_match = _contains_like(
                func.lower(Product.name), trimmed_keyword.lower()
            )
            brand_match = _contains_like(
                func.lower(Product.brand), trimmed_keyword.lower()
            )
            barcode_match = _contains_like(Product.barcode, trimmed_keyword)
            keyword_preds = [name_match, brand_match, barcode_match]
            normalized_query = normalize_sku(trimmed_keyword)
            if normalized_query:
                keyword_preds.append(
                    _contains_like(Product.normalized_sku, normalized_query)
                )
            stmt = stmt.where(or_(*keyword_preds))

        stmt = stmt.order_by(Product.sku.asc())
        products = list(self.db.scalars(stmt).unique().all())
        locations = ensure_locations(self.db)
        return [_to_product_schema(p, locations) for p in products]
