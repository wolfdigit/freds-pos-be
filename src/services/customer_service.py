from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.models.customer import Customer
from src.schemas.common import BusinessErrorCode
from src.schemas.customer import (
    AddRewardPointsRequest,
    CreateCustomerRequest,
    Customer as CustomerSchema,
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


# 將手機號碼轉成儲存／比對用的正規形式，供唯一性與精確查詢使用。
# 去頭尾空白後再去掉空白、連字號、括號；不轉換國碼。
# value: 原始電話字串。
def canonicalize_phone(value: str) -> str:
    return _PHONE_STRIP.sub("", value.strip())


# 產生新會員主鍵，格式為 cust-{32 位 hex uuid}（去掉 UUID 中的 dash）。
def _new_customer_id() -> str:
    return f"cust-{uuid.uuid4().hex}"


# 依 vip_tier 組出回傳用 vipTierName，不落庫，避免與前端文案漂移。
# vip_tier: 儲存的等級字串（regular / silver / gold / platinum）。
def _vip_tier_name(vip_tier: str) -> str:
    try:
        return VIP_TIER_NAME_MAP[VipTier(vip_tier)]
    except ValueError:
        return VIP_TIER_NAME_MAP[VipTier.REGULAR]


# 將 ORM Customer 轉成 API 的 CustomerSchema（含衍生 vipTierName）。
# customer: 已查到的會員資料列。
def _to_customer_schema(customer: Customer) -> CustomerSchema:
    return CustomerSchema(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        vipTier=customer.vip_tier,
        vipTierName=_vip_tier_name(customer.vip_tier),
        rewardPoints=customer.reward_points,
        totalSpent=customer.total_spent,
        note=customer.note,
        createdAt=customer.created_at,
    )


# 判斷會員是否符合關鍵字；姓名、電話、電子信箱任一命中即可。
# 空字串視為不過濾。電話同時比對原始輸入與 canonicalize 後的字串。
# customer: 待比對的會員列。
# keyword: 搜尋字串（姓名 / 電話 / 電子信箱片段）。
def _keyword_matches(customer: Customer, keyword: str) -> bool:
    trimmed = keyword.strip()
    if not trimmed:
        return True

    lower = trimmed.lower()
    matches_name = lower in customer.name.lower()
    matches_email = lower in customer.email.lower()
    matches_phone = trimmed in customer.phone
    canonical = canonicalize_phone(trimmed)
    if canonical:
        matches_phone = matches_phone or canonical in customer.phone
    return matches_name or matches_email or matches_phone


class CustomerService:
    # 綁定此 service 使用的資料庫 session，後續 CRUD 都走這個連線。
    # db: 被綁定的 SQLAlchemy Session。
    def __init__(self, db: Session) -> None:
        self.db = db

    # 依主鍵查會員列；找不到則拋 404 CUSTOMER_NOT_FOUND。
    # customer_id: 會員主鍵（JSON id / 路徑 {customerId}）。
    def _get_by_id_or_raise(self, customer_id: str) -> Customer:
        customer = self.db.get(Customer, customer_id)
        if customer is None:
            raise BusinessException(
                status_code=404,
                code=BusinessErrorCode.CUSTOMER_NOT_FOUND,
                message="找不到指定的會員",
            )
        return customer

    # 確認正規化後的手機號碼未被其他會員使用；重複則拋 409。
    # phone: 已 canonicalize 的號碼。
    # exclude_id: 更新時排除自身的會員 id；新增時不傳。
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
    # email: 已 trim + lowercase 的信箱。
    # exclude_id: 更新時排除自身的會員 id；新增時不傳。
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

    # 新增會員：伺服器發 id、createdAt；totalSpent 固定 0；缺 vipTier 則 regular。
    # data: 建立會員的請求內容（姓名、電話、信箱等，不含伺服器欄位）。
    def create(self, data: CreateCustomerRequest) -> CustomerSchema:
        phone = canonicalize_phone(data.phone)
        email = str(data.email).strip().lower()
        self._ensure_phone_unique(phone)
        self._ensure_email_unique(email)

        vip_tier = data.vip_tier.value if data.vip_tier is not None else VipTier.REGULAR.value
        now = datetime.now(timezone.utc)
        customer = Customer(
            id=_new_customer_id(),
            name=data.name.strip(),
            phone=phone,
            email=email,
            vip_tier=vip_tier,
            reward_points=data.reward_points if data.reward_points is not None else 0,
            total_spent=0,
            note=data.note,
            created_at=now,
            updated_at=now,
        )
        self.db.add(customer)
        self.db.commit()
        return _to_customer_schema(self._get_by_id_or_raise(customer.id))

    # 依主鍵取得單一會員的 API 資料；找不到則 404。
    # customer_id: 會員主鍵。
    def get_by_id(self, customer_id: str) -> CustomerSchema:
        return _to_customer_schema(self._get_by_id_or_raise(customer_id))

    # 依正規化電話精確查詢（結帳綁定用）；找不到則拋 404。
    # phone: 路徑上的電話字串，查詢前會再 canonicalize。
    def get_by_phone(self, phone: str) -> CustomerSchema:
        canonical = canonicalize_phone(phone)
        stmt = select(Customer).where(Customer.phone == canonical)
        customer = self.db.scalar(stmt)
        if customer is None:
            raise BusinessException(
                status_code=404,
                code=BusinessErrorCode.CUSTOMER_NOT_FOUND,
                message="找不到指定的會員",
            )
        return _to_customer_schema(customer)

    # 部分更新會員基本資料；rewardPoints 為覆蓋餘額，不是加減。
    # 不接受 id / createdAt / vipTierName / totalSpent。
    # customer_id: 要更新的會員主鍵。
    # data: 部分更新請求（只套用有送到的欄位）。
    def update(self, customer_id: str, data: UpdateCustomerRequest) -> CustomerSchema:
        customer = self._get_by_id_or_raise(customer_id)
        updates = data.model_dump(exclude_unset=True)

        if "phone" in updates and updates["phone"] is not None:
            new_phone = canonicalize_phone(updates["phone"])
            if new_phone != customer.phone:
                self._ensure_phone_unique(new_phone, exclude_id=customer.id)
                customer.phone = new_phone

        if "email" in updates and updates["email"] is not None:
            new_email = str(updates["email"]).strip().lower()
            if new_email != customer.email:
                self._ensure_email_unique(new_email, exclude_id=customer.id)
                customer.email = new_email

        if "name" in updates and updates["name"] is not None:
            customer.name = updates["name"]
        if "note" in updates:
            customer.note = updates["note"]
        if "reward_points" in updates and updates["reward_points"] is not None:
            customer.reward_points = updates["reward_points"]
        if "vip_tier" in updates and updates["vip_tier"] is not None:
            vip_tier = updates["vip_tier"]
            customer.vip_tier = vip_tier.value if hasattr(vip_tier, "value") else vip_tier

        customer.updated_at = datetime.now(timezone.utc)
        self.db.add(customer)
        self.db.commit()
        return _to_customer_schema(self._get_by_id_or_raise(customer_id))

    # 硬刪除會員列。此階段尚無訂單／預購表，未完成訂單的 409 不會觸發。
    # customer_id: 要刪除的會員主鍵。
    def delete(self, customer_id: str) -> None:
        customer = self._get_by_id_or_raise(customer_id)
        self.db.delete(customer)
        self.db.commit()

    # 以帶正負號的 amount 加減點數；結果小於 0 則拒絕，不靜默歸零。
    # customer_id: 要調整點數的會員主鍵。
    # data: 含 signed amount 的請求（正數加點、負數扣點）。
    def add_reward_points(
        self, customer_id: str, data: AddRewardPointsRequest
    ) -> CustomerSchema:
        customer = self._get_by_id_or_raise(customer_id)
        new_balance = customer.reward_points + data.amount
        if new_balance < 0:
            raise BusinessException(
                status_code=422,
                code=BusinessErrorCode.CUSTOMER_POINTS_INSUFFICIENT,
                message="點數不足",
            )
        customer.reward_points = new_balance
        customer.updated_at = datetime.now(timezone.utc)
        self.db.add(customer)
        self.db.commit()
        return _to_customer_schema(self._get_by_id_or_raise(customer_id))

    # 依條件搜尋會員，預設 name ASC、id ASC；過濾條件為 AND。
    # 空 keyword 不過濾關鍵字；vipTier 缺省或 ALL 不過濾等級。
    # keyword: 姓名／電話／電子信箱片段；空或未傳則不加關鍵字條件。
    # vip_tier: 精確等級，或 ALL／未傳表示不過濾。
    # min_points: 點數下限（rewardPoints >= N）；未傳則不過濾。
    def search(
        self,
        *,
        keyword: Optional[str] = None,
        vip_tier: Optional[str] = None,
        min_points: Optional[int] = None,
    ) -> List[CustomerSchema]:
        stmt = select(Customer)

        if vip_tier and vip_tier != "ALL":
            stmt = stmt.where(Customer.vip_tier == vip_tier)
        if min_points is not None:
            stmt = stmt.where(Customer.reward_points >= min_points)

        stmt = stmt.order_by(Customer.name.asc(), Customer.id.asc())
        customers = list(self.db.scalars(stmt).all())

        trimmed_keyword = (keyword or "").strip()
        if trimmed_keyword:
            customers = [c for c in customers if _keyword_matches(c, trimmed_keyword)]

        return [_to_customer_schema(c) for c in customers]
