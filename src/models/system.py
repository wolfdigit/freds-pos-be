from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base_class import Base


class StoreBranch(Base):
    __tablename__ = "store_branch"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inventory_location_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("inventory_location.id", name="fk_store_branch_inventory_location", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    returned_inventory_location_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "inventory_location.id",
            name="fk_store_branch_returned_inventory_location",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    # 預購保留：會員來門市取預購時從這裡扣。新門市預設綁系統地點「預購保留」。
    preorder_inventory_location_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "inventory_location.id",
            name="fk_store_branch_preorder_inventory_location",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    # 'all'：販售全部商品（預設，既有門市不變）。'list'：只販售 store_product 裡的商品。
    product_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="all", server_default="all"
    )

    __table_args__ = (
        CheckConstraint("product_scope IN ('all', 'list')", name="ck_store_branch_product_scope"),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StoreProduct(Base):
    """門市商品清單。只在 store_branch.product_scope = 'list' 時生效。"""

    __tablename__ = "store_product"

    store_name: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("store_branch.name", name="fk_store_product_store", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("product.id", name="fk_store_product_product", ondelete="RESTRICT"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("store_name", "product_id", name="pk_store_product"),
        Index("ix_store_product_product_id", "product_id"),
    )


class OAuthAccount(Base):
    __tablename__ = "oauth_account"

    email: Mapped[str] = mapped_column(String(256), primary_key=True)
    # 穩定收銀員 id。結帳快照用這個值，不用 email，也不用 Google sub。
    id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
