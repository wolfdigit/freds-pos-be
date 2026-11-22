from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelScale(str, Enum):
    S_1_18 = "1:18"
    S_1_43 = "1:43"
    S_1_64 = "1:64"
    S_1_24 = "1:24"
    S_1_12 = "1:12"
    ACCESSORIES = "配件周邊"


class ProductStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"


class LocationInventory(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location: str
    location_name: str = Field(..., alias="locationName")
    quantity: int


class Product(BaseModel):
    """Full product response matching FE Product type."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    sku: str
    normalized_sku: str = Field(..., alias="normalizedSku")
    barcode: str
    brand: str
    name: str
    scale: Optional[str] = None
    spec: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    list_price: int = Field(..., alias="listPrice", ge=0)
    vip_price: Optional[int] = Field(None, alias="vipPrice", ge=0)
    inventories: List[LocationInventory]
    total_inventory: int = Field(..., alias="totalInventory")
    login_store_quantity: Optional[int] = Field(None, alias="loginStoreQuantity")
    login_store_returned_quantity: Optional[int] = Field(None, alias="loginStoreReturnedQuantity")
    # 登入門市「預購保留」綁定地點的數量；沒有選定門市時為 null。
    login_store_preorder_quantity: Optional[int] = Field(None, alias="loginStorePreorderQuantity")
    # 登入門市是否販售此商品。沒有登入門市時為 null；'all' 門市一律 true。
    sold_in_login_store: Optional[bool] = Field(None, alias="soldInLoginStore")
    note: Optional[str] = None
    status: ProductStatus = ProductStatus.ACTIVE
    deleted: bool = False
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    created_by: Optional[str] = Field(None, alias="createdBy")
    updated_at: Optional[datetime] = Field(None, alias="updatedAt")
    updated_by: Optional[str] = Field(None, alias="updatedBy")


class ProductPage(BaseModel):
    """One page of GET /products (only when page or pageSize is given)."""

    model_config = ConfigDict(populate_by_name=True)

    items: List[Product]
    page: int
    page_size: int = Field(..., alias="pageSize")
    total: int


class CreateProductRequest(BaseModel):
    """Create body: metadata only — no stocks / quantities / server-owned fields."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    sku: str
    barcode: str
    brand: str
    name: str
    scale: Optional[ModelScale] = None
    spec: Optional[str] = None
    list_price: int = Field(..., alias="listPrice", ge=0)
    material: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    vip_price: Optional[int] = Field(None, alias="vipPrice", ge=0)
    note: Optional[str] = None
    status: Optional[ProductStatus] = None

    @field_validator("sku", "barcode", "brand", "name")
    @classmethod
    def non_empty_strings(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v


class UpdateProductRequest(BaseModel):
    """Partial metadata update — excludes stocks / computed / id fields."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    sku: Optional[str] = None
    barcode: Optional[str] = None
    brand: Optional[str] = None
    name: Optional[str] = None
    scale: Optional[ModelScale] = None
    spec: Optional[str] = None
    list_price: Optional[int] = Field(None, alias="listPrice", ge=0)
    vip_price: Optional[int] = Field(None, alias="vipPrice", ge=0)
    note: Optional[str] = None
    status: Optional[ProductStatus] = None
    deleted: Optional[bool] = None
    material: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
