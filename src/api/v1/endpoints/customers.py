from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.customer import (
    CreateCustomerRequest,
    Customer,
    CustomerSearchResponse,
    UpdateCustomerRequest,
)
from src.schemas.inventory import OkResponse
from src.schemas.preorder import PreOrder
from src.services.customer_service import CustomerService
from src.services.preorder_service import PreOrderService

router = APIRouter()


class VipTierQuery(str, Enum):
    ALL = "ALL"
    S = "S"
    A = "A"
    B = "B"
    Retail = "Retail"


@router.get(
    "",
    response_model=CustomerSearchResponse,
    response_model_by_alias=True,
    summary="Search customers",
)
def search_customers(
    keyword: Optional[str] = Query(None, description="Name / phone / email fragment"),
    vipTier: Optional[VipTierQuery] = Query(None, description="VipTier or ALL"),
    page: int = Query(1, ge=1, description="1-based page index"),
    pageSize: int = Query(20, ge=1, le=100, description="Page length (max 100)"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> CustomerSearchResponse:
    """Default sort: name ASC, then id ASC. Filters run in SQL."""
    vip_tier = vipTier.value if vipTier is not None else None
    return CustomerService(db).search(
        keyword=keyword,
        vip_tier=vip_tier,
        page=page,
        page_size=pageSize,
    )


@router.post(
    "",
    response_model=Customer,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    summary="Create customer",
)
def create_customer(
    body: CreateCustomerRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).create(body, actor_name=str(user["name"]))


@router.get(
    "/{customerId}",
    response_model=Customer,
    response_model_by_alias=True,
    summary="Get customer by ID",
)
def get_customer(
    customerId: str = Path(..., description="Customer id"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).get_by_id(customerId)


@router.put(
    "/{customerId}",
    response_model=Customer,
    response_model_by_alias=True,
    summary="Update customer profile",
)
def update_customer(
    body: UpdateCustomerRequest,
    customerId: str = Path(..., description="Customer id"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).update(customerId, body, actor_name=str(user["name"]))


@router.delete(
    "/{customerId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete customer",
)
def delete_customer(
    customerId: str = Path(..., description="Customer id"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> Response:
    CustomerService(db).delete(customerId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class UpdateSpendingRequest(BaseModel):
    amount: int


@router.post(
    "/{customerId}/spending",
    response_model=OkResponse,
    summary="Update customer total spending",
)
def update_customer_spending(
    body: UpdateSpendingRequest,
    customerId: str = Path(..., description="Customer id"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> OkResponse:
    CustomerService(db).add_spending(customerId, body.amount)
    return OkResponse()


@router.get(
    "/{customerId}/preorders",
    response_model=List[PreOrder],
    response_model_by_alias=True,
    summary="List pre-orders for a customer",
)
def customer_preorders(
    customerId: str = Path(..., description="Customer id"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> List[PreOrder]:
    return PreOrderService(db).by_customer(customerId)
