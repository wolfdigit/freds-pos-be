from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class StoreDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    is_default: bool = Field(False, alias="isDefault")
    inventory_location_id: str = Field(..., alias="inventoryLocationId")
    inventory_location_name: str = Field(..., alias="inventoryLocationName")
    returned_inventory_location_id: str = Field(..., alias="returnedInventoryLocationId")
    returned_inventory_location_name: str = Field(..., alias="returnedInventoryLocationName")
    preorder_inventory_location_id: str = Field(..., alias="preorderInventoryLocationId")
    preorder_inventory_location_name: str = Field(..., alias="preorderInventoryLocationName")


class CreateStoreRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    inventory_location_id: str = Field(..., alias="inventoryLocationId", min_length=1)
    returned_inventory_location_id: str = Field(..., alias="returnedInventoryLocationId", min_length=1)
    # 沒送時綁系統地點「預購保留」。
    preorder_inventory_location_id: Optional[str] = Field(None, alias="preorderInventoryLocationId", min_length=1)


class UpdateStoreBindingRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    inventory_location_id: str = Field(..., alias="inventoryLocationId", min_length=1)
    returned_inventory_location_id: str = Field(..., alias="returnedInventoryLocationId", min_length=1)
    # 沒送時維持目前的預購保留綁定。
    preorder_inventory_location_id: Optional[str] = Field(None, alias="preorderInventoryLocationId", min_length=1)


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
