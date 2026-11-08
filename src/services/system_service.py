from __future__ import annotations

from typing import List

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.models.location import StockLocation
from src.models.system import OAuthAccount, StoreBranch
from src.services.inventory_service import DEFAULT_STORE_LOCATION_ID, ensure_locations
from src.services.location_integrity import is_store_location_fk_violation
from src.schemas.common import BusinessErrorCode
from src.services.bootstrap import new_account_id
from src.schemas.system import (
    CreateOAuthAccountRequest,
    CreateStoreRequest,
    OAuthAccountDto,
    StoreDto,
    UpdateOAuthAccountRequest,
)

def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


class SystemService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def stores(self) -> List[StoreDto]:
        rows = list(self.db.scalars(select(StoreBranch).order_by(StoreBranch.name)).all())
        return [self._store_dto(row) for row in rows]

    def create_store(self, data: CreateStoreRequest, *, actor_role: str) -> StoreDto:
        self._require_actor_admin(actor_role)
        name = data.name.strip()
        if not name:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "門市名稱不可空白")
        if self.db.get(StoreBranch, name) is not None:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "門市已存在")
        location = self._location_for_store(data.stock_location_id, lock=True)
        row = StoreBranch(name=name, is_default=False, stock_location_id=location.id)
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self._reraise_missing_location(exc)
        return self._store_dto(row)

    def update_stock_location(
        self, store_name: str, stock_location_id: str, *, actor_role: str
    ) -> StoreDto:
        self._require_actor_admin(actor_role)
        # 與刪除地點相同，先鎖地點再鎖門市。
        location = self._existing_location(stock_location_id, lock=True)
        row = self.db.scalar(
            select(StoreBranch).where(StoreBranch.name == store_name).with_for_update()
        )
        if row is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市")
        row.stock_location_id = location.id
        try:
            self.db.commit()
        except IntegrityError as exc:
            self._reraise_missing_location(exc)
        return self._store_dto(row)

    def delete_store(self, name: str, *, actor_role: str) -> dict:
        self._require_actor_admin(actor_role)
        self._lock_stores()
        rows = list(
            self.db.scalars(select(StoreBranch).execution_options(populate_existing=True)).all()
        )
        row = next((item for item in rows if item.name == name), None)
        if row is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市")
        if len(rows) <= 1:
            _raise(409, BusinessErrorCode.LAST_STORE, "至少要保留一間門市")
        self.db.delete(row)
        self.db.commit()
        return {"deletedStore": name}

    def accounts(self) -> List[OAuthAccountDto]:
        rows = self.db.scalars(select(OAuthAccount).order_by(OAuthAccount.email)).all()
        return [_account_dto(row) for row in rows]

    def create_account(self, data: CreateOAuthAccountRequest, *, actor_role: str) -> OAuthAccountDto:
        self._require_actor_admin(actor_role)
        email = str(data.email).strip().lower()
        role = _normalize_role(data.role)
        name = _normalize_optional_name(data.name)
        if self.db.get(OAuthAccount, email) is not None:
            _raise(400, BusinessErrorCode.CUSTOMER_EMAIL_DUPLICATE, "帳號已存在")
        row = OAuthAccount(id=new_account_id(), email=email, role=role, name=name, note=data.note)
        self.db.add(row)
        self.db.commit()
        return _account_dto(row)

    def update_account(
        self,
        email: str,
        data: UpdateOAuthAccountRequest,
        *,
        actor_email: str,
        actor_role: str,
    ) -> OAuthAccountDto:
        self._lock_accounts()
        actor = self._locked_actor(actor_email, actor_role)
        row = self.db.get(OAuthAccount, email.strip().lower())
        if row is None:
            _raise(404, BusinessErrorCode.CUSTOMER_NOT_FOUND, "找不到帳號")
        if data.role is not None:
            role = _normalize_role(data.role)
            if (row.role or "").strip().lower() == "admin" and role != "admin":
                self._reject_admin_removal(row.email, actor.email, deleting=False)
            row.role = role
        if "name" in data.model_fields_set:
            row.name = _normalize_optional_name(data.name)
        if data.note is not None:
            row.note = data.note
        self.db.commit()
        return _account_dto(row)

    def delete_account(self, email: str, *, actor_email: str, actor_role: str) -> dict:
        self._lock_accounts()
        actor = self._locked_actor(actor_email, actor_role)
        key = email.strip().lower()
        row = self.db.get(OAuthAccount, key)
        if row is None:
            _raise(404, BusinessErrorCode.CUSTOMER_NOT_FOUND, "找不到帳號")
        if (row.role or "").strip().lower() == "admin":
            self._reject_admin_removal(row.email, actor.email, deleting=True)
        elif row.email == actor.email:
            _raise(409, BusinessErrorCode.ACCOUNT_SELF_PROTECTED, "不能刪除自己的帳號")
        self.db.delete(row)
        self.db.commit()
        return {"deletedEmail": key}

    def _lock_stores(self) -> None:
        # 更新成原值，讓同時刪除最後門市的請求在 SQLite 與 Postgres 都會排隊。
        self.db.execute(update(StoreBranch).values(is_default=StoreBranch.is_default))
        self.db.flush()

    def _lock_accounts(self) -> None:
        # 更新成原值，讓同時進行的降權／刪除在 SQLite 與 Postgres 都會排隊。
        self.db.execute(update(OAuthAccount).values(note=OAuthAccount.note))
        self.db.flush()

    def _locked_actor(self, actor_email: str, actor_role: str) -> OAuthAccount:
        if actor_role != "admin":
            _raise(403, BusinessErrorCode.AUTH_FORBIDDEN, "需要管理員權限")
        actor = self.db.scalar(
            select(OAuthAccount)
            .where(OAuthAccount.email == actor_email.strip().lower())
            .execution_options(populate_existing=True)
        )
        if actor is None or (actor.role or "").strip().lower() != "admin":
            _raise(403, BusinessErrorCode.AUTH_FORBIDDEN, "需要管理員權限")
        return actor

    def _store_dto(self, row: StoreBranch) -> StoreDto:
        location = self.db.get(StockLocation, row.stock_location_id)
        return StoreDto(
            name=row.name,
            isDefault=row.is_default,
            stockLocationId=row.stock_location_id,
            stockLocationName=location.name if location is not None else "",
        )

    def _location_for_store(self, requested_id: str | None, *, lock: bool) -> StockLocation:
        if requested_id is not None and requested_id.strip():
            return self._existing_location(requested_id, lock=lock)
        return self._shared_location(lock=lock)

    def _existing_location(self, location_id: str, *, lock: bool = False) -> StockLocation:
        stmt = select(StockLocation).where(StockLocation.id == location_id.strip())
        if lock:
            stmt = stmt.with_for_update()
        row = self.db.scalar(stmt)
        if row is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到庫存地點")
        return row

    def _shared_location(self, *, lock: bool) -> StockLocation:
        if self.db.scalar(select(func.count()).select_from(StockLocation)) == 0:
            ensure_locations(self.db)
        stmt = select(StockLocation).where(StockLocation.id == DEFAULT_STORE_LOCATION_ID)
        if lock:
            stmt = stmt.with_for_update()
        row = self.db.scalar(stmt)
        if row is None:
            _raise(
                409,
                BusinessErrorCode.STOCK_LOCATION_REQUIRED,
                "請指定 stockLocationId；既有的門市現貨庫存地點不存在",
            )
        return row

    def _reraise_missing_location(self, exc: IntegrityError) -> None:
        # store_branch 只有這一條外鍵。不是這條時，把原來的 IntegrityError 再丟出去。
        self.db.rollback()
        if is_store_location_fk_violation(exc):
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到庫存地點")
        raise exc

    def _require_actor_admin(self, actor_role: str) -> None:
        if actor_role != "admin":
            _raise(403, BusinessErrorCode.AUTH_FORBIDDEN, "需要管理員權限")

    def _reject_admin_removal(self, target_email: str, actor_email: str, *, deleting: bool) -> None:
        admins = list(
            self.db.scalars(
                select(OAuthAccount).where(OAuthAccount.role == "admin").execution_options(populate_existing=True)
            ).all()
        )
        others = [row for row in admins if row.email != target_email]
        if not others:
            _raise(409, BusinessErrorCode.ACCOUNT_LAST_ADMIN, "至少要保留一位管理員")
        if target_email == actor_email:
            message = "不能刪除自己的帳號" if deleting else "不能變更自己的角色"
            _raise(409, BusinessErrorCode.ACCOUNT_SELF_PROTECTED, message)


def _normalize_role(role: str) -> str:
    value = role.strip().lower()
    if value not in {"admin", "staff"}:
        _raise(400, BusinessErrorCode.ACCOUNT_ROLE_INVALID, "角色只允許 admin 或 staff")
    return value


def _normalize_optional_name(name: str | None) -> str | None:
    value = (name or "").strip()
    if not value:
        return None
    if len(value) > 128:
        _raise(400, BusinessErrorCode.ACCOUNT_NAME_REQUIRED, "顯示名稱不可超過 128 字")
    return value


def _account_dto(row: OAuthAccount) -> OAuthAccountDto:
    return OAuthAccountDto(id=row.id, email=row.email, role=row.role, name=row.name, note=row.note)
