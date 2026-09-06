from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BusinessErrorCode(str, Enum):
    INSUFFICIENT_STORE_STOCK = "INSUFFICIENT_STORE_STOCK"
    PREORDER_QTY_EXCEEDED = "PREORDER_QTY_EXCEEDED"
    PAYMENT_INSUFFICIENT = "PAYMENT_INSUFFICIENT"
    PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
    PRODUCT_SKU_DUPLICATE = "PRODUCT_SKU_DUPLICATE"
    STORAGE_CORRUPTED = "STORAGE_CORRUPTED"


class BusinessError(BaseModel):
    """HTTP 4xx business failure body matching OpenAPI BusinessError."""

    model_config = ConfigDict(use_enum_values=True)

    code: BusinessErrorCode
    message: str = Field(..., examples=["找不到指定商品"])
