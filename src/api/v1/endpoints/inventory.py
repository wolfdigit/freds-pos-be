from typing import List

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from src.api.deps import get_current_user_optional, get_db
from src.schemas.inventory import (
    BatchStockAdjustRequest,
    CreateStockLocationRequest,
    DeleteStockLocationRequest,
    DeleteStockLocationResponse,
    InventoryTransferRequest,
    OkResponse,
    StockAdjustRequest,
    StockAdjustmentLog,
    StockLocationDto,
    UpdateStockLocationRequest,
)
from src.services.inventory_service import InventoryService

router = APIRouter()


@router.get("/locations", response_model=List[StockLocationDto], response_model_by_alias=True)
def get_locations(db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return InventoryService(db).get_locations()


@router.post("/locations", response_model=StockLocationDto, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_location(body: CreateStockLocationRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return InventoryService(db).create_location(body)


@router.put("/locations/{locationId}", response_model=StockLocationDto, response_model_by_alias=True)
def update_location(
    body: UpdateStockLocationRequest,
    locationId: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
):
    return InventoryService(db).update_location(locationId, body)


@router.delete("/locations/{locationId}", response_model=DeleteStockLocationResponse, response_model_by_alias=True)
def delete_location(
    body: DeleteStockLocationRequest,
    locationId: str = Path(...),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user_optional),
):
    return InventoryService(db).delete_location(locationId, body)


@router.post("/transfers", response_model=OkResponse)
def transfer_stock(body: InventoryTransferRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    InventoryService(db).transfer(body)
    return OkResponse()


@router.post("/adjustments", response_model=OkResponse)
def adjust_stock(body: StockAdjustRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    InventoryService(db).adjust(body)
    return OkResponse()


@router.post("/batch-adjustments", response_model=OkResponse)
def batch_adjust(body: BatchStockAdjustRequest, db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    InventoryService(db).batch_adjust(body)
    return OkResponse()


@router.get("/adjustments/logs", response_model=List[StockAdjustmentLog], response_model_by_alias=True)
def adjustment_logs(db: Session = Depends(get_db), _user=Depends(get_current_user_optional)):
    return InventoryService(db).logs()
