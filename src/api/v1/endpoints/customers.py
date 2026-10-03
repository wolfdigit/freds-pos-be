from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.customer import (
    CreateCustomerRequest,
    Customer,
    CustomerSearchResponse,
    UpdateCustomerRequest,
)
from src.services.customer_service import CustomerService

router = APIRouter()


class VipTierQuery(str, Enum):
    ALL = "ALL"
    regular = "regular"
    silver = "silver"
    gold = "gold"
    platinum = "platinum"


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
    _user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).create(body)


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
    _user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).update(customerId, body)


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
