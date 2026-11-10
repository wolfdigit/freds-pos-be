from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


StoreBindingRole = Literal["normal", "returned"]


class OkResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ok: bool = True


class InventoryLocationDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    icon: Optional[str] = None
    is_default: bool = Field(False, alias="isDefault")
    display_order: int = Field(1, alias="displayOrder")
    store_names: List[str] = Field(default_factory=list, alias="storeNames")
    returned_store_names: List[str] = Field(default_factory=list, alias="returnedStoreNames")


class CreateInventoryLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str
    icon: Optional[str] = None
    display_order: Optional[int] = Field(None, alias="displayOrder")


class UpdateInventoryLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: Optional[str] = None
    icon: Optional[str] = None
    display_order: Optional[int] = Field(None, alias="displayOrder")


class DeleteInventoryLocationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rebind_to_location: Optional[str] = Field(None, alias="rebindToLocation")


class ReboundStore(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    binding: StoreBindingRole
    inventory_location_id: str = Field(..., alias="inventoryLocationId")


class DeleteInventoryLocationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    deleted_location: str = Field(..., alias="deletedLocation")
    rebound_store_names: List[ReboundStore] = Field(default_factory=list, alias="reboundStoreNames")


class InventoryTransferRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    product_id: str = Field(..., alias="productId")
    from_location: str = Field(..., alias="fromLocation")
    to_location: str = Field(..., alias="toLocation")
    quantity: int = Field(..., ge=1)
    reason: Optional[str] = None


class MoveAllStockRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_location: str = Field(..., alias="fromLocation")
    to_location: str = Field(..., alias="toLocation")
    reason: Optional[str] = None


class InventoryAdjustRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    location: str
    new_quantity: int = Field(..., alias="newQuantity")
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("reason must not be empty")
        return stripped


class InventoryLocationChange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location: str
    location_name: str = Field(..., alias="locationName")
    old_qty: int = Field(..., alias="oldQty")
    new_qty: int = Field(..., alias="newQty")
    diff: int


class InventoryItemAdjustment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    sku: str
    barcode: Optional[str] = None
    name: str
    brand: str
    changes: List[InventoryLocationChange]
    summary_text: str = Field(..., alias="summaryText")


class BatchInventoryAdjustRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    operator_name: Optional[str] = Field(None, alias="operatorName")
    timestamp: Optional[str] = None
    note: str
    adjustments: List[InventoryItemAdjustment]

    @field_validator("note")
    @classmethod
    def note_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("note must not be empty")
        return stripped


class InventoryAdjustmentLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    timestamp: datetime
    operator_name: str = Field(..., alias="operatorName")
    items: List[InventoryItemAdjustment]
    total_qty_change: int = Field(..., alias="totalQtyChange")
    note: Optional[str] = None


class ReceiptLineRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    quantity: int = Field(..., ge=1)


class CreateInventoryReceiptRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    location_id: str = Field(..., alias="locationId")
    note: Optional[str] = None
    supplier: Optional[str] = None
    items: List[ReceiptLineRequest] = Field(..., min_length=1)


class InventoryReceiptItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    sku: str
    name: str
    quantity: int


class InventoryReceipt(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    location_id: str = Field(..., alias="locationId")
    location_name: str = Field(..., alias="locationName")
    supplier: Optional[str] = None
    note: Optional[str] = None
    operator_name: str = Field(..., alias="operatorName")
    created_at: datetime = Field(..., alias="createdAt")
    items: List[InventoryReceiptItem]
    total_quantity: int = Field(..., alias="totalQuantity")


class InventoryReceiptPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[InventoryReceipt]
    page: int
    page_size: int = Field(..., alias="pageSize")
    total: int


class InventoryMovement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    product_id: str = Field(..., alias="productId")
    sku: Optional[str] = None
    name: Optional[str] = None
    location_id: str = Field(..., alias="locationId")
    quantity_delta: int = Field(..., alias="quantityDelta")
    quantity_after: int = Field(..., alias="quantityAfter")
    reason: Optional[str] = None
    source_id: str = Field(..., alias="sourceId")
    operator_name: str = Field(..., alias="operatorName")
    created_at: datetime = Field(..., alias="createdAt")


class InventoryMovementPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[InventoryMovement]
    page: int
    page_size: int = Field(..., alias="pageSize")
    total: int
