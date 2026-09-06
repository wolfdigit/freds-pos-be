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
    DISCONTINUED = "discontinued"


class StockLocation(str, Enum):
    STORE = "store"
    WAREHOUSE = "warehouse"
    COMPANY = "company"
    OTHER = "other"


class LocationStock(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location: StockLocation
    location_name: str = Field(..., alias="locationName")
    quantity: int = Field(..., ge=0)


class Product(BaseModel):
    """Full product response matching FE Product type."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    sku: str
    normalized_sku: str = Field(..., alias="normalizedSku")
    barcode: str
    brand: str
    name: str
    scale: ModelScale
    material: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    list_price: int = Field(..., alias="listPrice", ge=0)
    cost_price: int = Field(..., alias="costPrice", ge=0)
    vip_price: Optional[int] = Field(None, alias="vipPrice", ge=0)
    stocks: List[LocationStock]
    total_stock: int = Field(..., alias="totalStock", ge=0)
    pre_order_pending_count: int = Field(..., alias="preOrderPendingCount", ge=0)
    note: Optional[str] = None
    status: ProductStatus


class CreateProductRequest(BaseModel):
    """Create body: metadata only — no stocks / quantities / server-owned fields."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    sku: str
    barcode: str
    brand: str
    name: str
    scale: ModelScale
    list_price: int = Field(..., alias="listPrice", ge=0)
    cost_price: int = Field(..., alias="costPrice", ge=0)
    status: ProductStatus
    material: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
    vip_price: Optional[int] = Field(None, alias="vipPrice", ge=0)
    note: Optional[str] = None

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
    list_price: Optional[int] = Field(None, alias="listPrice", ge=0)
    cost_price: Optional[int] = Field(None, alias="costPrice", ge=0)
    vip_price: Optional[int] = Field(None, alias="vipPrice", ge=0)
    note: Optional[str] = None
    status: Optional[ProductStatus] = None
    material: Optional[str] = None
    color: Optional[str] = None
    image_url: Optional[str] = Field(None, alias="imageUrl")
