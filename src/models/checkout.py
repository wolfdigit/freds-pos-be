from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base_class import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CheckoutOrder(Base):
    """Completed sale. Commercial fields stay fixed after insert."""

    __tablename__ = "checkout_order"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True
    )
    idempotency_body_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    branch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(128), nullable=False)
    cashier_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cashier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    customer_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("customer.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    items_subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    discount_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shipping_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    invoice_type: Mapped[str] = mapped_column(String(32), nullable=False)
    carrier_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    buyer_title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    items: Mapped[List["CheckoutOrderItem"]] = relationship(
        "CheckoutOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        foreign_keys="CheckoutOrderItem.order_id",
        order_by="CheckoutOrderItem.line_no",
    )
    payments: Mapped[List["CheckoutPayment"]] = relationship(
        "CheckoutPayment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="CheckoutPayment.line_no",
    )


class CheckoutOrderItem(Base):
    """One sold or returned line. Snapshots stay after the catalog row changes."""

    __tablename__ = "checkout_order_item"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("checkout_order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("product.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sku: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    scale: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    original_price: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_manual_price: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    price_diff_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    points_discount_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points_discount_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    returned_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pre_order_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("pre_order.id", ondelete="RESTRICT"),
        nullable=True,
    )
    pre_order_item_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("pre_order_item.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    original_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    original_order_item_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("checkout_order_item.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    restock: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    return_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    order: Mapped["CheckoutOrder"] = relationship(
        "CheckoutOrder",
        back_populates="items",
        foreign_keys=[order_id],
    )

    __table_args__ = (
        UniqueConstraint("order_id", "line_no", name="uq_checkout_order_item_line"),
    )


class CheckoutPayment(Base):
    """One tender on a sale."""

    __tablename__ = "checkout_payment"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("checkout_order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    tendered_cash: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    change_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    transaction_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    order: Mapped["CheckoutOrder"] = relationship("CheckoutOrder", back_populates="payments")

    __table_args__ = (
        UniqueConstraint("order_id", "line_no", name="uq_checkout_payment_line"),
    )
