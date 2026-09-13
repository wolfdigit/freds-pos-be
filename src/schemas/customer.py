import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

_PHONE_STRIP = re.compile(r"[\s\-()]")


def _require_canonical_phone(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be empty")
    if not _PHONE_STRIP.sub("", stripped):
        raise ValueError("must not be empty")
    return stripped


class VipTier(str, Enum):
    REGULAR = "regular"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class Customer(BaseModel):
    """Full customer response matching FE Customer type."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    name: str
    phone: str
    email: EmailStr
    vip_tier: VipTier = Field(..., alias="vipTier")
    vip_tier_name: str = Field(..., alias="vipTierName")
    reward_points: int = Field(..., alias="rewardPoints", ge=0)
    total_spent: int = Field(..., alias="totalSpent", ge=0)
    note: Optional[str] = None
    created_at: datetime = Field(..., alias="createdAt")


class CreateCustomerRequest(BaseModel):
    """Create body: profile only — no id / createdAt / vipTierName / totalSpent."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str
    phone: str
    email: EmailStr
    vip_tier: Optional[VipTier] = Field(None, alias="vipTier")
    note: Optional[str] = None
    reward_points: Optional[int] = Field(None, alias="rewardPoints", ge=0)

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("phone")
    @classmethod
    def non_empty_phone(cls, v: str) -> str:
        return _require_canonical_phone(v)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: object) -> object:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("must not be empty")
        return v.strip().lower()


class UpdateCustomerRequest(BaseModel):
    """Partial profile update — excludes id / createdAt / vipTierName / totalSpent."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    vip_tier: Optional[VipTier] = Field(None, alias="vipTier")
    note: Optional[str] = None
    reward_points: Optional[int] = Field(None, alias="rewardPoints", ge=0)

    @field_validator("name")
    @classmethod
    def non_empty_optional_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("phone")
    @classmethod
    def non_empty_optional_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _require_canonical_phone(v)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, v: object) -> object:
        if v is None:
            return v
        if not isinstance(v, str) or not v.strip():
            raise ValueError("must not be empty")
        return v.strip().lower()


class AddRewardPointsRequest(BaseModel):
    """Signed point delta. Positive adds, negative subtracts."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    amount: int
