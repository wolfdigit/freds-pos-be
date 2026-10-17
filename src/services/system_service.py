from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.models.system import OAuthAccount, StoreBranch
from src.schemas.common import BusinessErrorCode
from src.schemas.system import (
    CreateOAuthAccountRequest,
    CreateStoreRequest,
    OAuthAccountDto,
    StoreDto,
    UpdateOAuthAccountRequest,
)

DEFAULT_STORES = (
    ("台北旗艦店", True),
    ("官網", False),
)


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


class SystemService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stores(self) -> List[StoreDto]:
        rows = list(self.db.scalars(select(StoreBranch).order_by(StoreBranch.name)).all())
        if not rows:
            for name, is_default in DEFAULT_STORES:
                self.db.add(StoreBranch(name=name, is_default=is_default))
            self.db.commit()
            rows = list(self.db.scalars(select(StoreBranch).order_by(StoreBranch.name)).all())
        return [StoreDto(name=row.name, isDefault=row.is_default) for row in rows]

    def create_store(self, data: CreateStoreRequest) -> StoreDto:
        name = data.name.strip()
        if not name:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "門市名稱不可空白")
        if self.db.get(StoreBranch, name) is not None:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "門市已存在")
        row = StoreBranch(name=name, is_default=False)
        self.db.add(row)
        self.db.commit()
        return StoreDto(name=row.name, isDefault=row.is_default)

    def delete_store(self, name: str) -> dict:
        row = self.db.get(StoreBranch, name)
        if row is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市")
        self.db.delete(row)
        self.db.commit()
        return {"deletedStore": name}

    def accounts(self) -> List[OAuthAccountDto]:
        rows = self.db.scalars(select(OAuthAccount).order_by(OAuthAccount.email)).all()
        return [
            OAuthAccountDto(email=row.email, role=row.role, name=row.name, note=row.note) for row in rows
        ]

    def create_account(self, data: CreateOAuthAccountRequest) -> OAuthAccountDto:
        email = str(data.email).strip().lower()
        if self.db.get(OAuthAccount, email) is not None:
            _raise(400, BusinessErrorCode.CUSTOMER_EMAIL_DUPLICATE, "帳號已存在")
        row = OAuthAccount(email=email, role=data.role, name=data.name, note=data.note)
        self.db.add(row)
        self.db.commit()
        return OAuthAccountDto(email=row.email, role=row.role, name=row.name, note=row.note)

    def update_account(self, email: str, data: UpdateOAuthAccountRequest) -> OAuthAccountDto:
        row = self.db.get(OAuthAccount, email.strip().lower())
        if row is None:
            _raise(404, BusinessErrorCode.CUSTOMER_NOT_FOUND, "找不到帳號")
        if data.role is not None:
            row.role = data.role
        if data.name is not None:
            row.name = data.name
        if data.note is not None:
            row.note = data.note
        self.db.commit()
        return OAuthAccountDto(email=row.email, role=row.role, name=row.name, note=row.note)

    def delete_account(self, email: str) -> dict:
        key = email.strip().lower()
        row = self.db.get(OAuthAccount, key)
        if row is None:
            _raise(404, BusinessErrorCode.CUSTOMER_NOT_FOUND, "找不到帳號")
        self.db.delete(row)
        self.db.commit()
        return {"deletedEmail": key}
