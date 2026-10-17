from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base_class import Base


class StoreBranch(Base):
    __tablename__ = "store_branch"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class OAuthAccount(Base):
    __tablename__ = "oauth_account"

    email: Mapped[str] = mapped_column(String(256), primary_key=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
