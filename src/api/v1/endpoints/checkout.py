from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.checkout import (
    CheckoutOrder,
    CheckoutOrderSearchResponse,
    CreateOrderRequest,
    OrderStatus,
)
from src.services.checkout_service import CheckoutService

router = APIRouter()


class OrderStatusQuery(str, Enum):
    all = "all"
    completed = OrderStatus.COMPLETED.value
    partially_refunded = OrderStatus.PARTIALLY_REFUNDED.value
    refunded = OrderStatus.REFUNDED.value


@router.post(
    "/orders",
    response_model=CheckoutReceipt,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create checkout order",
)
def create_checkout_order(
    body: CreateOrderRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> CheckoutReceipt:
    return CheckoutService(db).create(
        body,
        idempotency_key,
        cashier_id=str(user["id"]),
        cashier_name=str(user["name"]),
    )


@router.get(
    "/orders",
    response_model=CheckoutOrderSearchResponse,
    response_model_by_alias=True,
    summary="Search checkout orders",
)
def search_checkout_orders(
    customerId: Optional[str] = Query(None),
    orderNumber: Optional[str] = Query(None),
    productId: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    productKeyword: Optional[str] = Query(None),
    startDate: Optional[datetime] = Query(None),
    endDate: Optional[datetime] = Query(None),
    minAmount: Optional[int] = Query(None),
    maxAmount: Optional[int] = Query(None),
    status_filter: Optional[OrderStatusQuery] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> CheckoutOrderSearchResponse:
    status_value = status_filter.value if status_filter is not None else None
    return CheckoutService(db).search(
        customer_id=customerId,
        order_number=orderNumber,
        product_id=productId,
        keyword=keyword,
        product_keyword=productKeyword,
        start_date=startDate,
        end_date=endDate,
        min_amount=minAmount,
        max_amount=maxAmount,
        status=status_value,
        page=page,
        page_size=pageSize,
    )


@router.get(
    "/orders/{orderId}",
    response_model=CheckoutOrder,
    response_model_by_alias=True,
    summary="Get checkout order",
)
def get_checkout_order(
    orderId: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> CheckoutOrder:
    return CheckoutService(db).get_by_id(orderId)
