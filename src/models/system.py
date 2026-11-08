from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base_class import Base


class StoreBranch(Base):
    __tablename__ = "store_branch"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stock_location_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("stock_location.id", name="fk_store_branch_stock_location", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    returned_stock_location_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "stock_location.id",
            name="fk_store_branch_returned_stock_location",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )


class OAuthAccount(Base):
    __tablename__ = "oauth_account"

    email: Mapped[str] = mapped_column(String(256), primary_key=True)
    # 穩定收銀員 id。結帳快照用這個值，不用 email，也不用 Google sub。
    id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
