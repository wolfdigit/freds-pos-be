from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StoreDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    is_default: bool = Field(False, alias="isDefault")


class CreateStoreRequest(BaseModel):
    name: str


class OAuthAccountDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    role: str
    name: Optional[str] = None
    note: Optional[str] = None


class CreateOAuthAccountRequest(BaseModel):
    email: EmailStr
    role: str
    name: Optional[str] = None
    note: Optional[str] = None


class UpdateOAuthAccountRequest(BaseModel):
    role: Optional[str] = None
    name: Optional[str] = None
    note: Optional[str] = None
