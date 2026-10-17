from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base_class import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PreOrder(Base):
    """Preorder header. Checkout only updates item qty_delivered and derived status."""

    __tablename__ = "pre_order"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("customer.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="in_store")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operator_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_arrival_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    items: Mapped[List["PreOrderItem"]] = relationship(
        "PreOrderItem",
        back_populates="pre_order",
        cascade="all, delete-orphan",
    )


class PreOrderItem(Base):
    """One preorder line. qty_delivered is incremented when checkout picks it up."""

    __tablename__ = "pre_order_item"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pre_order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("pre_order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    scale: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    quoted_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_ordered: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_arrived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_delivered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    pre_order: Mapped["PreOrder"] = relationship("PreOrder", back_populates="items")
