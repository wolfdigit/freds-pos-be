from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OkResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ok: bool = True


class StockLocationDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    icon: Optional[str] = None
    is_default: bool = Field(False, alias="isDefault")
    display_order: int = Field(1, alias="displayOrder")
    is_active: bool = Field(True, alias="isActive")


class CreateStockLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    icon: Optional[str] = None
    display_order: Optional[int] = Field(None, alias="displayOrder")
    is_active: bool = Field(True, alias="isActive")


class UpdateStockLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = Field(None, alias="displayOrder")
    is_active: Optional[bool] = Field(None, alias="isActive")


class DeleteStockLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    transfer_to_location: str = Field(..., alias="transferToLocation")
    reason: Optional[str] = None


class DeleteStockLocationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    success: bool = True
    deleted_location: str = Field(..., alias="deletedLocation")
    transferred_to_location: str = Field(..., alias="transferredToLocation")
    affected_products_count: int = Field(..., alias="affectedProductsCount")
    total_quantity_transferred: int = Field(..., alias="totalQuantityTransferred")
    message: Optional[str] = None


class InventoryTransferRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    from_location: str = Field(..., alias="fromLocation")
    to_location: str = Field(..., alias="toLocation")
    quantity: int = Field(..., ge=1)
    reason: Optional[str] = None
    operator_id: Optional[str] = Field(None, alias="operatorId")


class StockAdjustRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    location: str
    new_quantity: int = Field(..., alias="newQuantity", ge=0)
    reason: str


class StockLocationChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location: str
    location_name: str = Field(..., alias="locationName")
    old_qty: int = Field(..., alias="oldQty")
    new_qty: int = Field(..., alias="newQty")
    diff: int


class StockItemAdjustment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    sku: str
    barcode: Optional[str] = None
    name: str
    brand: str
    changes: List[StockLocationChange]
    summary_text: str = Field(..., alias="summaryText")


class BatchStockAdjustRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    operator_name: str = Field(..., alias="operatorName")
    timestamp: str
    note: Optional[str] = None
    adjustments: List[StockItemAdjustment]


class StockAdjustmentLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    timestamp: datetime
    operator_name: str = Field(..., alias="operatorName")
    items: List[StockItemAdjustment]
    total_qty_change: int = Field(..., alias="totalQtyChange")
    note: Optional[str] = None
