from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StoreDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    is_default: bool = Field(False, alias="isDefault")
    stock_location_id: str = Field(..., alias="stockLocationId")
    stock_location_name: str = Field(..., alias="stockLocationName")


class CreateStoreRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    stock_location_id: Optional[str] = Field(None, alias="stockLocationId")


class UpdateStoreStockLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    stock_location_id: str = Field(..., alias="stockLocationId", min_length=1)


class OAuthAccountDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
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
