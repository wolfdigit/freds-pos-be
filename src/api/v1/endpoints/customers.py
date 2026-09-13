from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.customer import (
    AddRewardPointsRequest,
    CreateCustomerRequest,
    Customer,
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
    response_model=List[Customer],
    response_model_by_alias=True,
    summary="Search customers",
)
def search_customers(
    keyword: Optional[str] = Query(None, description="Name / phone / email"),
    vipTier: Optional[VipTierQuery] = Query(None, description="VipTier or ALL"),
    minPoints: Optional[int] = Query(None, ge=0, description="Minimum rewardPoints"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> List[Customer]:
    """Default sort: name ASC."""
    vip_tier = vipTier.value if vipTier is not None else None
    return CustomerService(db).search(
        keyword=keyword,
        vip_tier=vip_tier,
        min_points=minPoints,
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
    "/by-phone/{phone}",
    response_model=Customer,
    response_model_by_alias=True,
    summary="Get customer by exact phone",
)
def get_customer_by_phone(
    phone: str = Path(..., description="Phone; server canonicalizes before lookup"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).get_by_phone(phone)


@router.post(
    "/{customerId}/reward-points",
    response_model=Customer,
    response_model_by_alias=True,
    summary="Add or subtract reward points",
)
def add_reward_points(
    body: AddRewardPointsRequest,
    customerId: str = Path(..., description="Customer id"),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
) -> Customer:
    return CustomerService(db).add_reward_points(customerId, body)


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
