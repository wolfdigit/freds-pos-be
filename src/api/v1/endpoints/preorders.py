from typing import List

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.inventory import OkResponse
from src.schemas.preorder import (
    CreatePreOrderRequest,
    FulfillPreOrderRequest,
    MarkItemsArrivedRequest,
    PreOrder,
    UpdatePreOrderRequest,
)
from src.services.preorder_service import PreOrderService

router = APIRouter()


@router.get("", response_model=List[PreOrder], response_model_by_alias=True)
def search_preorders(query: str = Query(...), db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return PreOrderService(db).search_open(query)


@router.post("", response_model=PreOrder, response_model_by_alias=True, status_code=201)
def create_preorder(body: CreatePreOrderRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return PreOrderService(db).create(body)


@router.get("/{preOrderId}", response_model=PreOrder, response_model_by_alias=True)
def get_preorder(preOrderId: str = Path(...), db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return PreOrderService(db).get(preOrderId)


@router.put("/{preOrderId}", response_model=PreOrder, response_model_by_alias=True)
def update_preorder(
    body: UpdatePreOrderRequest,
    preOrderId: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
):
    return PreOrderService(db).update(preOrderId, body)


@router.post("/{preOrderId}/arrived", response_model=OkResponse)
def mark_arrived(
    body: MarkItemsArrivedRequest,
    preOrderId: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
):
    PreOrderService(db).mark_arrived(preOrderId, body)
    return OkResponse()


@router.post("/{preOrderId}/fulfill", response_model=OkResponse)
def fulfill(
    body: FulfillPreOrderRequest,
    preOrderId: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
):
    PreOrderService(db).fulfill(preOrderId, body)
    return OkResponse()
