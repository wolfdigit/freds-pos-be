from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.models.product import Product
from src.models.system import StoreBranch, StoreProduct
from src.schemas.common import BusinessErrorCode
from src.schemas.store_product import (
    CopyStoreProductsRequest,
    StoreProductBatchRequest,
    StoreProductChangeResult,
    StoreProductItem,
    StoreProductPage,
)
from src.services.product_service import keyword_predicate


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


def _unique(ids: Iterable[str]) -> List[str]:
    seen: dict[str, None] = {}
    for raw in ids:
        value = (raw or "").strip()
        if value:
            seen.setdefault(value, None)
    return list(seen)


class StoreProductService:
    """門市商品清單（store_product）的讀寫。任何業務使用者都可以編輯。

    已刪除（status = deleted）的商品留在清單裡但一律隱藏：不出現在列表，也不算進 listedTotal。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def _store(self, store_name: str) -> StoreBranch:
        store = self.db.get(StoreBranch, store_name)
        if store is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市")
        return store

    def _listed_total(self, store_name: str) -> int:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(StoreProduct)
                .join(Product, Product.id == StoreProduct.product_id)
                .where(StoreProduct.store_name == store_name, Product.status != "deleted")
            )
            or 0
        )

    def _result(self, store: StoreBranch, added: int, removed: int) -> StoreProductChangeResult:
        return StoreProductChangeResult(
            storeName=store.name,
            productScope=store.product_scope or "all",
            changed=added + removed,
            added=added,
            removed=removed,
            listedTotal=self._listed_total(store.name),
        )

    # 勾選畫面用：在整個商品目錄裡搜尋（伺服器端分頁），每筆標示是否在清單。
    # in_list: None 全部；True 只看清單內；False 只看清單外。
    def page(
        self,
        store_name: str,
        *,
        keyword: Optional[str],
        in_list: Optional[bool],
        page: int,
        page_size: int,
    ) -> StoreProductPage:
        store = self._store(store_name)
        stmt = (
            select(Product, StoreProduct)
            .outerjoin(
                StoreProduct,
                (StoreProduct.product_id == Product.id) & (StoreProduct.store_name == store.name),
            )
            .where(Product.status != "deleted")
        )
        predicate = keyword_predicate(keyword)
        if predicate is not None:
            stmt = stmt.where(predicate)
        if in_list is True:
            stmt = stmt.where(StoreProduct.product_id.is_not(None))
        elif in_list is False:
            stmt = stmt.where(StoreProduct.product_id.is_(None))
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.execute(
            stmt.order_by(Product.sku.asc(), Product.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        items = [
            StoreProductItem(
                productId=product.id,
                sku=product.sku,
                barcode=product.barcode,
                brand=product.brand,
                name=product.name,
                scale=product.scale or None,
                listPrice=product.list_price,
                imageUrl=product.image_url,
                inList=link is not None,
                addedAt=link.created_at if link is not None else None,
                addedBy=link.created_by if link is not None else None,
            )
            for product, link in rows
        ]
        return StoreProductPage(
            storeName=store.name,
            productScope=store.product_scope or "all",
            listedTotal=self._listed_total(store.name),
            items=items,
            page=page,
            pageSize=page_size,
            total=total,
        )

    # 勾選畫面「存檔」：加入與移出在同一個交易裡套用，任何一筆失敗整批不寫入。
    # add 裡的商品必須存在且未刪除；remove 不檢查（已刪除商品也能移出）。
    def batch(
        self, store_name: str, data: StoreProductBatchRequest, *, actor_name: str
    ) -> StoreProductChangeResult:
        store = self._store(store_name)
        add_ids = _unique(data.add)
        remove_ids = _unique(data.remove)
        if add_ids:
            found = set(
                self.db.scalars(
                    select(Product.id).where(Product.id.in_(add_ids), Product.status != "deleted")
                ).all()
            )
            missing = [pid for pid in add_ids if pid not in found]
            if missing:
                _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, f"找不到商品或商品已刪除 (ID: {missing[0]})")
        added, removed = self._apply(store.name, add_ids, remove_ids, actor_name=actor_name)
        return self._result(store, added, removed)

    # 從另一間門市複製清單（只複製未刪除的商品）。不看來源門市的 productScope。
    # replace=True 時移除本門市清單裡來源沒有的商品；兩邊都有的保留原本的加入時間與加入者。
    def copy_from(
        self, store_name: str, data: CopyStoreProductsRequest, *, actor_name: str
    ) -> StoreProductChangeResult:
        store = self._store(store_name)
        source = self._store(data.source_store_name.strip())
        source_ids = list(
            self.db.scalars(
                select(StoreProduct.product_id)
                .join(Product, Product.id == StoreProduct.product_id)
                .where(StoreProduct.store_name == source.name, Product.status != "deleted")
            ).all()
        )
        if source.name == store.name:
            return self._result(store, 0, 0)
        remove_ids: List[str] = []
        if data.replace:
            keep = set(source_ids)
            remove_ids = [
                pid
                for pid in self.db.scalars(
                    select(StoreProduct.product_id).where(StoreProduct.store_name == store.name)
                ).all()
                if pid not in keep
            ]
        added, removed = self._apply(store.name, source_ids, remove_ids, actor_name=actor_name)
        return self._result(store, added, removed)

    # 同一個交易：先移出、再寫入還不在清單裡的商品，最後 commit 一次，回 (新增數, 移出數)。
    # 別人同時加入同一商品撞到主鍵時整批 rollback 重試一次。
    def _apply(
        self, store_name: str, add_ids: List[str], remove_ids: List[str], *, actor_name: str
    ) -> tuple[int, int]:
        for attempt in range(2):
            removed = 0
            if remove_ids:
                removed = (
                    self.db.execute(
                        delete(StoreProduct).where(
                            StoreProduct.store_name == store_name, StoreProduct.product_id.in_(remove_ids)
                        )
                    ).rowcount
                    or 0
                )
            existing = set(
                self.db.scalars(
                    select(StoreProduct.product_id).where(
                        StoreProduct.store_name == store_name, StoreProduct.product_id.in_(add_ids)
                    )
                ).all()
            ) if add_ids else set()
            now = datetime.now(timezone.utc)
            new_ids = [pid for pid in add_ids if pid not in existing]
            for pid in new_ids:
                self.db.add(
                    StoreProduct(store_name=store_name, product_id=pid, created_at=now, created_by=actor_name)
                )
            try:
                self.db.commit()
                return len(new_ids), removed
            except IntegrityError:
                self.db.rollback()
                if attempt == 1:
                    raise
        return 0, 0
