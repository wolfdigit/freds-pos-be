from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentMethodType(str, Enum):
    CASH = "cash"
    BANK_TRANSFER_CTBC = "bank_transfer_ctbc"
    BANK_TRANSFER_UBOT = "bank_transfer_ubot"
    CREDIT_CARD_PHYSICAL = "credit_card_physical"
    CREDIT_CARD_ONLINE = "credit_card_online"
    LINE_PAY = "line_pay"
    COD = "cod"


class OrderStatus(str, Enum):
    COMPLETED = "completed"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"


class BranchId(str, Enum):
    STORE = "branch-store"
    ONLINE = "branch-online"


class PaymentTender(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: PaymentMethodType
    amount: int


class CheckoutOrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    product_id: Optional[str] = Field(None, alias="productId")
    sku: str
    name: str
    scale: str
    brand: str
    original_price: int = Field(..., alias="originalPrice")
    unit_price: int = Field(..., alias="unitPrice")
    is_manual_price: bool = Field(..., alias="isManualPrice")
    price_diff_reason: Optional[str] = Field(None, alias="priceDiffReason")
    quantity: int
    subtotal: int
    points_discount_applied: bool = Field(..., alias="pointsDiscountApplied")
    points_discount_amount: int = Field(..., alias="pointsDiscountAmount")
    returned_quantity: int = Field(..., alias="returnedQuantity")
    original_order_id: Optional[str] = Field(None, alias="originalOrderId")
    original_order_item_id: Optional[str] = Field(None, alias="originalOrderItemId")
    restock: Optional[bool] = None
    return_reason: Optional[str] = Field(None, alias="returnReason")


class CheckoutOrder(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    order_number: str = Field(..., alias="orderNumber")
    branch_id: str = Field(..., alias="branchId")
    branch_name: str = Field(..., alias="branchName")
    cashier_id: str = Field(..., alias="cashierId")
    cashier_name: str = Field(..., alias="cashierName")
    status: OrderStatus
    customer_id: Optional[str] = Field(None, alias="customerId")
    customer_name: Optional[str] = Field(None, alias="customerName")
    customer_phone: Optional[str] = Field(None, alias="customerPhone")
    items: List[CheckoutOrderItem]
    items_subtotal: int = Field(..., alias="itemsSubtotal")
    discount_amount: int = Field(..., alias="discountAmount")
    points_discount_amount: int = Field(..., alias="pointsDiscountAmount")
    shipping_fee: int = Field(..., alias="shippingFee")
    total_amount: int = Field(..., alias="totalAmount")
    payments: List[PaymentTender]
    note: str = ""
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")


class CheckoutReceipt(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order: CheckoutOrder
    receipt_print_html: str = Field(..., alias="receiptPrintHtml")


class CreateOrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str = Field(..., alias="productId")
    quantity: int
    unit_price: Optional[int] = Field(None, alias="unitPrice")
    is_manual_price: bool = Field(False, alias="isManualPrice")
    price_diff_reason: Optional[str] = Field(None, alias="priceDiffReason")
    points_discount_applied: bool = Field(False, alias="pointsDiscountApplied")
    original_order_id: Optional[str] = Field(None, alias="originalOrderId")
    original_order_item_id: Optional[str] = Field(None, alias="originalOrderItemId")
    restock: Optional[bool] = None
    return_reason: Optional[str] = Field(None, alias="returnReason")

    @field_validator("quantity")
    @classmethod
    def quantity_not_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity must not be 0")
        return value


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    customer_id: Optional[str] = Field(None, alias="customerId")
    branch_id: BranchId = Field(BranchId.STORE, alias="branchId")
    items: List[CreateOrderItem] = Field(..., min_length=1)
    shipping_fee: int = Field(..., alias="shippingFee", ge=0)
    payments: List[PaymentTender] = Field(..., min_length=1)
    note: str = ""


class CheckoutOrderSearchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: List[CheckoutOrder]
    page: int
    page_size: int = Field(..., alias="pageSize")
    total: int
