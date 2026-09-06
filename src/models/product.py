from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base_class import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    """Catalog metadata. totalStock / preOrderPendingCount are computed on read."""

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    normalized_sku: Mapped[str] = mapped_column(String(128), nullable=False)
    barcode: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    scale: Mapped[str] = mapped_column(String(32), nullable=False)
    material: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    list_price: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False)
    vip_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    stocks: Mapped[List["ProductStock"]] = relationship(
        "ProductStock",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    pre_order_pending: Mapped[Optional["ProductPreOrderPending"]] = relationship(
        "ProductPreOrderPending",
        back_populates="product",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_product_normalized_sku", "normalized_sku"),
        Index("ix_product_brand", "brand"),
    )


class ProductStock(Base):
    """One stock row per product location."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location: Mapped[str] = mapped_column(String(32), nullable=False)
    location_name: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product: Mapped["Product"] = relationship("Product", back_populates="stocks")

    __table_args__ = (
        UniqueConstraint("product_id", "location", name="uq_product_stock_product_location"),
    )


class ProductPreOrderPending(Base):
    """1:1 pending preorder aggregate. Catalog endpoints are read-only for this table."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product: Mapped["Product"] = relationship(
        "Product", back_populates="pre_order_pending"
    )
