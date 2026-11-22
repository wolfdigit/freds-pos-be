from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from src.models.location import InventoryLocation

from sqlalchemy import exists, false, func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session, selectinload

from src.core.exceptions import BusinessException
from src.models.product import Product, ProductInventory
from src.models.system import StoreBranch, StoreProduct
from src.schemas.common import BusinessErrorCode
from src.schemas.product import (
    CreateProductRequest,
    LocationInventory,
    Product as ProductSchema,
    ProductPage,
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


# 將 ORM Product 轉成 API 的 ProductSchema（含庫存）。
# product: 已載入關聯的商品
def _qty_at(stocks: Sequence[LocationInventory], location_id: Optional[str]) -> int:
    if location_id is None:
        return 0
    row = next((item for item in stocks if item.location == location_id), None)
    return row.quantity if row is not None else 0


def _to_product_schema(
    product: Product,
    locations: Sequence[InventoryLocation],
    *,
    login_location_id: Optional[str] = None,
    login_returned_location_id: Optional[str] = None,
    login_preorder_location_id: Optional[str] = None,
    has_login_store: bool = False,
    sold_in_login_store: Optional[bool] = None,
) -> ProductSchema:
    inventories: List[LocationInventory] = []
    seen = set()
    by_location = {row.location: row for row in product.inventories}
    for loc in locations:
        seen.add(loc.id)
        row = by_location.get(loc.id)
        inventories.append(
            LocationInventory(
                location=loc.id,
                locationName=row.location_name if row is not None else loc.name,
                quantity=row.quantity if row is not None else 0,
            )
        )
    for row in product.inventories:
        if row.location in seen:
            continue
        seen.add(row.location)
        inventories.append(
            LocationInventory(location=row.location, locationName=row.location_name, quantity=row.quantity)
        )

    total_inventory = sum(item.quantity for item in inventories)
    if has_login_store:
        login_store_quantity = _qty_at(inventories, login_location_id)
        login_store_returned_quantity = _qty_at(inventories, login_returned_location_id)
        login_store_preorder_quantity = _qty_at(inventories, login_preorder_location_id)
    else:
        login_store_quantity = None
        login_store_returned_quantity = None
        login_store_preorder_quantity = None

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
        inventories=inventories,
        totalInventory=total_inventory,
        loginStoreQuantity=login_store_quantity,
        loginStoreReturnedQuantity=login_store_returned_quantity,
        loginStorePreorderQuantity=login_store_preorder_quantity,
        soldInLoginStore=sold_in_login_store if has_login_store else None,
        note=product.note,
        status=product.status,
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


@dataclass(frozen=True)
class StockFilters:
    """庫存數量篩選（GET /products 的 loginStoreQuantity*/locationQuantity*/totalInventory* 參數）。

    上下限都含等號；None 代表不限。沒有庫存列的地點視為 0。
    """

    login_store_min: Optional[int] = None
    login_store_max: Optional[int] = None
    location_id: Optional[str] = None
    location_min: Optional[int] = None
    location_max: Optional[int] = None
    total_min: Optional[int] = None
    total_max: Optional[int] = None

    @property
    def uses_login_store(self) -> bool:
        return self.login_store_min is not None or self.login_store_max is not None

    @property
    def uses_location(self) -> bool:
        return self.location_min is not None or self.location_max is not None


def _quantity_at(location_id: str):
    return (
        select(func.coalesce(func.sum(ProductInventory.quantity), 0))
        .where(ProductInventory.product_id == Product.id, ProductInventory.location == location_id)
        .correlate(Product)
        .scalar_subquery()
    )


def _total_quantity():
    return (
        select(func.coalesce(func.sum(ProductInventory.quantity), 0))
        .where(ProductInventory.product_id == Product.id)
        .correlate(Product)
        .scalar_subquery()
    )


# 商品關鍵字：名稱／品牌（不分大小寫）、條碼、正規化貨號的子字串。空白關鍵字回 None。
def keyword_predicate(keyword: Optional[str]) -> Optional[ColumnElement]:
    trimmed_keyword = (keyword or "").strip()
    if not trimmed_keyword:
        return None
    keyword_preds = [
        _contains_like(func.lower(Product.name), trimmed_keyword.lower()),
        _contains_like(func.lower(Product.brand), trimmed_keyword.lower()),
        _contains_like(Product.barcode, trimmed_keyword),
    ]
    normalized_query = normalize_sku(trimmed_keyword)
    if normalized_query:
        keyword_preds.append(_contains_like(Product.normalized_sku, normalized_query))
    return or_(*keyword_preds)


# 商品在 store_name 的門市商品清單裡（EXISTS，走 store_product 主鍵）。
def sold_in_store(store_name: str) -> ColumnElement:
    return exists(
        select(StoreProduct.product_id)
        .where(StoreProduct.store_name == store_name, StoreProduct.product_id == Product.id)
        .correlate(Product)
    )


def _between(stmt, column, low: Optional[int], high: Optional[int]):
    if low is not None:
        stmt = stmt.where(column >= low)
    if high is not None:
        stmt = stmt.where(column <= high)
    return stmt


class ProductService:
    # 綁定此 service 使用的資料庫 session。
    # db: 被綁定的 SQLAlchemy Session。
    def __init__(self, db: Session) -> None:
        self.db = db

    # 依 product_id (商品主鍵) 查商品並預載庫存；找不到則拋 404。
    def _get_by_id_or_raise(self, product_id: str) -> Product:
        product = self.db.get(
            Product,
            product_id,
            options=[
                selectinload(Product.inventories),
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
    def _login_store(self, store_name: Optional[str]) -> Optional[StoreBranch]:
        if not store_name:
            return None
        return self.db.get(StoreBranch, store_name)

    # 登入門市是 'list' 模式時回門市名稱（要套商品清單），否則 None。
    def _list_scope_store(self, store_name: Optional[str]) -> Optional[str]:
        store = self._login_store(store_name)
        if store is None or store.product_scope != "list":
            return None
        return store.name

    # 每個商品在登入門市是否販售。沒有登入門市時回空 dict（API 欄位為 null）。
    def _sold_flags(self, store_name: Optional[str], product_ids: Sequence[str]) -> dict[str, bool]:
        store = self._login_store(store_name)
        if store is None:
            return {}
        if store.product_scope != "list":
            return {pid: True for pid in product_ids}
        if not product_ids:
            return {}
        listed = set(
            self.db.scalars(
                select(StoreProduct.product_id).where(
                    StoreProduct.store_name == store.name,
                    StoreProduct.product_id.in_(list(product_ids)),
                )
            ).all()
        )
        return {pid: pid in listed for pid in product_ids}

    def _login_bindings(
        self, store_name: Optional[str]
    ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """(有登入門市, 門市庫存, 退貨, 預購保留) 三個綁定的地點 id。"""
        if not store_name:
            return False, None, None, None
        store = self.db.get(StoreBranch, store_name)
        if store is None:
            return False, None, None, None
        return (
            True,
            store.inventory_location_id,
            store.returned_inventory_location_id,
            store.preorder_inventory_location_id,
        )

    def create(
        self,
        data: CreateProductRequest,
        *,
        actor_name: Optional[str] = None,
        store_name: Optional[str] = None,
    ) -> ProductSchema:
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
            status=(data.status.value if data.status is not None else "active"),
            deleted=(data.status is not None and data.status.value == "deleted"),
            note=data.note,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
        self.db.add(product)
        # 新商品不會自動加入其他 'list' 門市；只有在 'list' 門市登入時建立的，加入該門市清單。
        scope_store = self._list_scope_store(store_name)
        if scope_store is not None:
            self.db.flush()
            self.db.add(
                StoreProduct(
                    store_name=scope_store,
                    product_id=product.id,
                    created_at=now,
                    created_by=actor or "",
                )
            )
        self.db.commit()
        return self.get_by_id(product.id, store_name=store_name)

    # 依 product_id (商品主鍵) 取得單一商品的 API 資料。
    def get_by_id(self, product_id: str, *, store_name: Optional[str] = None) -> ProductSchema:
        has_login_store, normal_id, returned_id, preorder_id = self._login_bindings(store_name)
        return _to_product_schema(
            self._get_by_id_or_raise(product_id),
            ensure_locations(self.db),
            login_location_id=normal_id,
            login_returned_location_id=returned_id,
            login_preorder_location_id=preorder_id,
            has_login_store=has_login_store,
            sold_in_login_store=self._sold_flags(store_name, [product_id]).get(product_id),
        )

    # 更新指定商品已提供的欄位。
    # product_id: 商品主鍵
    # data: 部分更新請求
    def update(
        self,
        product_id: str,
        data: UpdateProductRequest,
        *,
        actor_name: Optional[str] = None,
        store_name: Optional[str] = None,
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
            product.status = "deleted" if product.deleted else "active"
        if "status" in updates and updates["status"] is not None:
            status = updates["status"]
            product.status = status.value if hasattr(status, "value") else status
            product.deleted = product.status == "deleted"

        product.updated_at = datetime.now(timezone.utc)
        product.updated_by = _actor_name(actor_name)
        self.db.add(product)
        self.db.commit()
        return self.get_by_id(product_id, store_name=store_name)

    # 依條件組出商品篩選查詢（不含排序、分頁與預載）。
    # keyword: 關鍵字；scale/brand: 比例與品牌；barcode: 條碼完全相符
    # in_inventory_only: 只留各庫存點合計 (totalInventory) > 0 的商品
    def _filtered(
        self,
        *,
        keyword: Optional[str],
        scale: Optional[str],
        brand: Optional[str],
        barcode: Optional[str],
        in_inventory_only: bool,
        stock: Optional[StockFilters] = None,
        store_name: Optional[str] = None,
        scope_store: Optional[str] = None,
    ):
        stmt = select(Product).where(Product.status != "deleted")
        if stock is not None:
            stmt = self._apply_stock_filters(stmt, stock, store_name)

        if scale and scale != "ALL":
            stmt = stmt.where(Product.scale == scale)
        if brand and brand != "ALL":
            stmt = stmt.where(Product.brand == brand)
        exact_barcode = (barcode or "").strip()
        if exact_barcode:
            stmt = stmt.where(Product.barcode == exact_barcode)

        if in_inventory_only:
            stmt = stmt.where(_total_quantity() > 0)

        predicate = keyword_predicate(keyword)
        if predicate is not None:
            stmt = stmt.where(predicate)
        if scope_store is not None:
            stmt = stmt.where(sold_in_store(scope_store))
        return stmt

    # 依數量篩選。登入門市條件跟 loginStoreQuantity 同一個定義：目前門市的正常庫存點；
    # 沒有選定門市時 loginStoreQuantity 是 null，所以任何登入門市條件都不會符合。
    def _apply_stock_filters(self, stmt, stock: StockFilters, store_name: Optional[str]):
        if stock.uses_login_store:
            has_store, normal_id, _returned, _preorder = self._login_bindings(store_name)
            if not has_store or not normal_id:
                return stmt.where(false())
            stmt = _between(stmt, _quantity_at(normal_id), stock.login_store_min, stock.login_store_max)
        if stock.uses_location:
            if not stock.location_id or self.db.get(InventoryLocation, stock.location_id) is None:
                raise BusinessException(
                    status_code=404,
                    code=BusinessErrorCode.LOCATION_NOT_FOUND,
                    message="找不到庫存地點",
                )
            stmt = _between(stmt, _quantity_at(stock.location_id), stock.location_min, stock.location_max)
        if stock.total_min is not None or stock.total_max is not None:
            stmt = _between(stmt, _total_quantity(), stock.total_min, stock.total_max)
        return stmt

    def _to_schemas(self, products: Sequence[Product], store_name: Optional[str]) -> List[ProductSchema]:
        locations = ensure_locations(self.db)
        has_login_store, normal_id, returned_id, preorder_id = self._login_bindings(store_name)
        sold = self._sold_flags(store_name, [p.id for p in products])
        return [
            _to_product_schema(
                p,
                locations,
                login_location_id=normal_id,
                login_returned_location_id=returned_id,
                login_preorder_location_id=preorder_id,
                has_login_store=has_login_store,
                sold_in_login_store=sold.get(p.id),
            )
            for p in products
        ]

    # 依條件搜尋商品，回傳全部符合者（舊版前端使用的形狀）。排序 sku ASC。
    # all_products: 看全部商品，不套登入門市的商品清單（任何業務帳號都可以）。
    def search(
        self,
        *,
        keyword: Optional[str] = None,
        scale: Optional[str] = None,
        brand: Optional[str] = None,
        barcode: Optional[str] = None,
        in_inventory_only: bool = False,
        stock: Optional[StockFilters] = None,
        store_name: Optional[str] = None,
        all_products: bool = False,
    ) -> List[ProductSchema]:
        stmt = self._filtered(
            keyword=keyword,
            scale=scale,
            brand=brand,
            barcode=barcode,
            in_inventory_only=in_inventory_only,
            stock=stock,
            store_name=store_name,
            scope_store=None if all_products else self._list_scope_store(store_name),
        ).options(
            selectinload(Product.inventories),
        )
        stmt = stmt.order_by(Product.sku.asc())
        products = list(self.db.scalars(stmt).unique().all())
        return self._to_schemas(products, store_name)

    # 同樣的篩選，但只回一頁，並附上符合條件的總筆數。
    # 排序 sku ASC、id ASC，翻頁時順序固定。
    def search_page(
        self,
        *,
        page: int,
        page_size: int,
        keyword: Optional[str] = None,
        scale: Optional[str] = None,
        brand: Optional[str] = None,
        barcode: Optional[str] = None,
        in_inventory_only: bool = False,
        stock: Optional[StockFilters] = None,
        store_name: Optional[str] = None,
        all_products: bool = False,
    ) -> ProductPage:
        filtered = self._filtered(
            keyword=keyword,
            scale=scale,
            brand=brand,
            barcode=barcode,
            in_inventory_only=in_inventory_only,
            stock=stock,
            store_name=store_name,
            scope_store=None if all_products else self._list_scope_store(store_name),
        )
        total = self.db.scalar(select(func.count()).select_from(filtered.subquery())) or 0
        stmt = (
            filtered.options(
                selectinload(Product.inventories),
            )
            .order_by(Product.sku.asc(), Product.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        products = list(self.db.scalars(stmt).unique().all())
        return ProductPage(
            items=self._to_schemas(products, store_name),
            page=page,
            pageSize=page_size,
            total=total,
        )
