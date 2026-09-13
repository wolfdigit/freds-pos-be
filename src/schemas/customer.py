from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class VipTier(str, Enum):
    REGULAR = "regular"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


def _blank_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


class Customer(BaseModel):
    """Full customer response matching the member-catalog contract."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    vip_tier: VipTier = Field(..., alias="vipTier")
    vip_tier_name: str = Field(..., alias="vipTierName")
    total_spent: int = Field(..., alias="totalSpent", ge=0)
    note: str = ""
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")


class CreateCustomerRequest(BaseModel):
    """Create body: profile only — no id / timestamps / vipTierName / totalSpent."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    vip_tier: Optional[VipTier] = Field(None, alias="vipTier")
    note: Optional[str] = None

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def blank_phone_to_none(cls, v: object) -> object:
        return _blank_to_none(v)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, v: object) -> object:
        blanked = _blank_to_none(v)
        if blanked is None:
            return None
        if isinstance(blanked, str):
            return blanked.strip().lower()
        return blanked


class UpdateCustomerRequest(BaseModel):
    """Partial profile update — excludes id / timestamps / vipTierName / totalSpent."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    vip_tier: Optional[VipTier] = Field(None, alias="vipTier")
    note: Optional[str] = None

    @field_validator("name")
    @classmethod
    def non_empty_optional_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def blank_phone_to_none(cls, v: object) -> object:
        return _blank_to_none(v)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, v: object) -> object:
        blanked = _blank_to_none(v)
        if blanked is None:
            return None
        if isinstance(blanked, str):
            return blanked.strip().lower()
        return blanked


class CustomerSearchResponse(BaseModel):
    """Paged search result for GET /customers."""

    model_config = ConfigDict(populate_by_name=True)

    items: List[Customer]
    page: int
    page_size: int = Field(..., alias="pageSize")
    total: int
