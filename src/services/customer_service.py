from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import BusinessException
from src.models.customer import Customer
from src.schemas.common import BusinessErrorCode
from src.schemas.customer import (
    CreateCustomerRequest,
    Customer as CustomerSchema,
    CustomerSearchResponse,
    UpdateCustomerRequest,
    VipTier,
)

# VIP 等級對應的顯示名稱（與前端 getVipTierName 相同）。
VIP_TIER_NAME_MAP = {
    VipTier.PLATINUM: "白金黑卡 (9折)",
    VipTier.GOLD: "金卡會員 (95折)",
    VipTier.SILVER: "銀卡會員 (98折)",
    VipTier.REGULAR: "一般會員",
}

_PHONE_STRIP = re.compile(r"[\s\-()]")


# 將手機號碼轉成儲存／比對用的正規形式。
# 去頭尾空白後再去掉空白、連字號、括號；不轉換國碼。
# 空字串或只剩分隔符時回傳 None（存 SQL NULL）。
def canonicalize_phone(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    canonical = _PHONE_STRIP.sub("", value.strip())
    return canonical or None


# LIKE 子字串比對：跳脫 % / _ / \，行為對齊 Python `in`。
def _contains_like(column: ColumnElement, value: str) -> ColumnElement:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.like(f"%{escaped}%", escape="\\")


# 產生新會員主鍵，格式為 cust-{32 位 hex uuid}（去掉 UUID 中的 dash）。
def _new_customer_id() -> str:
    return f"cust-{uuid.uuid4().hex}"


# 依 vip_tier 組出回傳用 vipTierName，不落庫，避免與前端文案漂移。
def _vip_tier_name(vip_tier: str) -> str:
    try:
        return VIP_TIER_NAME_MAP[VipTier(vip_tier)]
    except ValueError:
        return VIP_TIER_NAME_MAP[VipTier.REGULAR]


# 將 ORM Customer 轉成 API 的 CustomerSchema（含衍生 vipTierName）。
def _to_customer_schema(customer: Customer) -> CustomerSchema:
    return CustomerSchema(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        vipTier=customer.vip_tier,
        vipTierName=_vip_tier_name(customer.vip_tier),
        totalSpent=customer.total_spent,
        note=customer.note if customer.note is not None else "",
        createdAt=customer.created_at,
        updatedAt=customer.updated_at,
    )


# 正規化寫入用電子信箱：None / 空白 → None；其餘 trim + lowercase。
def _normalize_email(value: object) -> Optional[str]:
    if value is None:
        return None
    email = str(value).strip().lower()
    return email or None


class CustomerService:
    # 綁定此 service 使用的資料庫 session，後續 CRUD 都走這個連線。
    def __init__(self, db: Session) -> None:
        self.db = db

    # 依主鍵查會員列；找不到則拋 404 CUSTOMER_NOT_FOUND。
    def _get_by_id_or_raise(self, customer_id: str) -> Customer:
        customer = self.db.get(Customer, customer_id)
        if customer is None:
            raise BusinessException(
                status_code=404,
                code=BusinessErrorCode.CUSTOMER_NOT_FOUND,
                message="找不到指定的會員",
            )
        return customer

    # 確認正規化後的非空手機號碼未被其他會員使用；重複則拋 409。
    def _ensure_phone_unique(
        self, phone: str, exclude_id: Optional[str] = None
    ) -> None:
        stmt = select(Customer.id).where(Customer.phone == phone)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        existing = self.db.scalar(stmt)
        if existing is not None:
            raise BusinessException(
                status_code=409,
                code=BusinessErrorCode.CUSTOMER_PHONE_DUPLICATE,
                message="手機號碼已存在",
            )

    # 確認小寫電子信箱未被其他會員使用；重複則拋 409。
    def _ensure_email_unique(
        self, email: str, exclude_id: Optional[str] = None
    ) -> None:
        stmt = select(Customer.id).where(Customer.email == email)
        if exclude_id is not None:
            stmt = stmt.where(Customer.id != exclude_id)
        existing = self.db.scalar(stmt)
        if existing is not None:
            raise BusinessException(
                status_code=409,
                code=BusinessErrorCode.CUSTOMER_EMAIL_DUPLICATE,
                message="電子信箱已存在",
            )

    # 在 SELECT 上套用 keyword / vipTier 的 SQL WHERE（不在 Python 過濾）。
    def _apply_search_filters(
        self,
        stmt: Select[tuple[Customer]],
        *,
        keyword: Optional[str],
        vip_tier: Optional[str],
    ) -> Select[tuple[Customer]]:
        if vip_tier and vip_tier != "ALL":
            stmt = stmt.where(Customer.vip_tier == vip_tier)

        trimmed = (keyword or "").strip()
        if not trimmed:
            return stmt

        name_match = _contains_like(func.lower(Customer.name), trimmed.lower())

        phone_parts = [_contains_like(Customer.phone, trimmed)]
        canonical = canonicalize_phone(trimmed)
        if canonical:
            phone_parts.append(_contains_like(Customer.phone, canonical))
        phone_match = and_(Customer.phone.is_not(None), or_(*phone_parts))

        email_match = and_(
            Customer.email.is_not(None),
            _contains_like(func.lower(Customer.email), trimmed.lower()),
        )
        return stmt.where(or_(name_match, phone_match, email_match))

    # 新增會員：伺服器發 id、createdAt、updatedAt；totalSpent 固定 0；缺 vipTier 則 regular。
    # phone / email 可省略或 null，空白與 canonicalize 後為空則存 NULL。
    def create(self, data: CreateCustomerRequest) -> CustomerSchema:
        phone = canonicalize_phone(data.phone)
        email = _normalize_email(data.email)
        if phone is not None:
            self._ensure_phone_unique(phone)
        if email is not None:
            self._ensure_email_unique(email)

        vip_tier = (
            data.vip_tier.value if data.vip_tier is not None else VipTier.REGULAR.value
        )
        now = datetime.now(timezone.utc)
        customer = Customer(
            id=_new_customer_id(),
            name=data.name.strip(),
            phone=phone,
            email=email,
            vip_tier=vip_tier,
            total_spent=0,
            note=data.note,
            created_at=now,
            updated_at=now,
        )
        self.db.add(customer)
        self.db.commit()
        return _to_customer_schema(self._get_by_id_or_raise(customer.id))

    # 依主鍵取得單一會員的 API 資料；找不到則 404。
    def get_by_id(self, customer_id: str) -> CustomerSchema:
        return _to_customer_schema(self._get_by_id_or_raise(customer_id))

    # 部分更新會員基本資料。不接受 id / createdAt / vipTierName / totalSpent。
    # phone / email 傳 null 或空白則清成 NULL。
    def update(self, customer_id: str, data: UpdateCustomerRequest) -> CustomerSchema:
        customer = self._get_by_id_or_raise(customer_id)
        updates = data.model_dump(exclude_unset=True)

        if "phone" in updates:
            new_phone = canonicalize_phone(updates["phone"])
            if new_phone != customer.phone:
                if new_phone is not None:
                    self._ensure_phone_unique(new_phone, exclude_id=customer.id)
                customer.phone = new_phone

        if "email" in updates:
            new_email = _normalize_email(updates["email"])
            if new_email != customer.email:
                if new_email is not None:
                    self._ensure_email_unique(new_email, exclude_id=customer.id)
                customer.email = new_email

        if "name" in updates and updates["name"] is not None:
            customer.name = updates["name"]
        if "note" in updates:
            customer.note = updates["note"]
        if "vip_tier" in updates and updates["vip_tier"] is not None:
            vip_tier = updates["vip_tier"]
            customer.vip_tier = vip_tier.value if hasattr(vip_tier, "value") else vip_tier

        customer.updated_at = datetime.now(timezone.utc)
        self.db.add(customer)
        self.db.commit()
        return _to_customer_schema(self._get_by_id_or_raise(customer_id))

    # 硬刪除會員列。此階段尚無訂單／預購表，未完成訂單的 409 不會觸發。
    def delete(self, customer_id: str) -> None:
        customer = self._get_by_id_or_raise(customer_id)
        self.db.delete(customer)
        self.db.commit()

    # 依條件搜尋會員：SQL WHERE + ORDER BY name ASC, id ASC + LIMIT/OFFSET。
    # 空 keyword 不過濾關鍵字；vipTier 缺省或 ALL 不過濾等級。
    def search(
        self,
        *,
        keyword: Optional[str] = None,
        vip_tier: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CustomerSearchResponse:
        stmt = self._apply_search_filters(
            select(Customer),
            keyword=keyword,
            vip_tier=vip_tier,
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(
            stmt.order_by(Customer.name.asc(), Customer.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return CustomerSearchResponse(
            items=[_to_customer_schema(c) for c in rows],
            page=page,
            pageSize=page_size,
            total=total,
        )
