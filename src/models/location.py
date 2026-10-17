from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base_class import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StockLocation(Base):
    """Inventory place. `id` is the stock location key stored on product_stock."""

    __tablename__ = "stock_location"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StockAdjustmentLog(Base):
    __tablename__ = "stock_adjustment_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    operator_name: Mapped[str] = mapped_column(String(128), nullable=False)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)
    total_qty_change: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
