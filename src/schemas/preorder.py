from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PreOrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    product_id: str = Field(..., alias="productId")
    sku: str
    product_name: str = Field(..., alias="productName")
    scale: Optional[str] = None
    brand: str
    quoted_price: int = Field(..., alias="quotedPrice")
    qty_ordered: int = Field(..., alias="qtyOrdered")
    qty_arrived: int = Field(..., alias="qtyArrived")
    qty_delivered: int = Field(..., alias="qtyDelivered")


class PreOrder(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    order_number: str = Field(..., alias="orderNumber")
    customer_id: str = Field(..., alias="customerId")
    customer_name: str = Field(..., alias="customerName")
    customer_phone: str = Field(..., alias="customerPhone")
    order_date: str = Field(..., alias="orderDate")
    expected_arrival_date: Optional[str] = Field(None, alias="expectedArrivalDate")
    status: str
    source: str
    items: List[PreOrderItem]
    note: Optional[str] = None
    operator_name: Optional[str] = Field(None, alias="operatorName")
    updated_at: str = Field(..., alias="updatedAt")


class CreatePreOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    customer_id: Optional[str] = Field(None, alias="customerId")
    customer_name: Optional[str] = Field(None, alias="customerName")
    customer_phone: Optional[str] = Field(None, alias="customerPhone")
    order_date: Optional[str] = Field(None, alias="orderDate")
    expected_arrival_date: Optional[str] = Field(None, alias="expectedArrivalDate")
    source: Optional[str] = "in_store"
    items: List[PreOrderItem] = Field(default_factory=list)
    note: Optional[str] = None
    operator_name: Optional[str] = Field(None, alias="operatorName")


class UpdatePreOrderRequest(CreatePreOrderRequest):
    status: Optional[str] = None


class ArrivedItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    qty: int = Field(..., ge=1)


class MarkItemsArrivedRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    arrived_items: List[ArrivedItem] = Field(..., alias="arrivedItems")


class FulfilledItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pre_order_item_id: str = Field(..., alias="preOrderItemId")
    qty: int = Field(..., ge=1)


class FulfillPreOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fulfilled_items: List[FulfilledItem] = Field(..., alias="fulfilledItems")
