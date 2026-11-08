from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from src.api.deps import get_db, require_business_user
from src.schemas.inventory import (
    BatchStockAdjustRequest,
    CreateStockLocationRequest,
    CreateStockReceiptRequest,
    DeleteStockLocationRequest,
    DeleteStockLocationResponse,
    InventoryTransferRequest,
    MoveAllStockRequest,
    OkResponse,
    StockAdjustRequest,
    StockAdjustmentLog,
    StockLocationDto,
    StockMovementPage,
    StockReceipt,
    StockReceiptPage,
    UpdateStockLocationRequest,
)
from src.services.auth_service import Principal
from src.services.inventory_service import InventoryService

router = APIRouter()


@router.get("/locations", response_model=List[StockLocationDto], response_model_by_alias=True)
def get_locations(db: Session = Depends(get_db), _user: Principal = Depends(require_business_user)):
    return InventoryService(db).get_locations()


@router.post("/locations", response_model=StockLocationDto, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_location(
    body: CreateStockLocationRequest,
    db: Session = Depends(get_db),
    _user: Principal = Depends(require_business_user),
):
    return InventoryService(db).create_location(body)


@router.put("/locations/{locationId}", response_model=StockLocationDto, response_model_by_alias=True)
def update_location(
    body: UpdateStockLocationRequest,
    locationId: str = Path(...),
    db: Session = Depends(get_db),
    _user: Principal = Depends(require_business_user),
):
    return InventoryService(db).update_location(locationId, body)


@router.delete("/locations/{locationId}", response_model=DeleteStockLocationResponse, response_model_by_alias=True)
def delete_location(
    body: DeleteStockLocationRequest,
    locationId: str = Path(...),
    db: Session = Depends(get_db),
    _user: Principal = Depends(require_business_user),
):
    return InventoryService(db).delete_location(locationId, body)


@router.post("/transfers", response_model=OkResponse)
def transfer_stock(
    body: InventoryTransferRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_business_user),
):
    InventoryService(db).transfer(body, operator_name=user.name)
    return OkResponse()


@router.post("/transfers/all", response_model=OkResponse)
def move_all_stock(
    body: MoveAllStockRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_business_user),
):
    InventoryService(db).move_all(body, operator_name=user.name)
    return OkResponse()


@router.post("/adjustments", response_model=OkResponse)
def adjust_stock(
    body: StockAdjustRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_business_user),
):
    InventoryService(db).adjust(body, operator_name=user.name)
    return OkResponse()


@router.post("/batch-adjustments", response_model=OkResponse)
def batch_adjust(
    body: BatchStockAdjustRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_business_user),
):
    InventoryService(db).batch_adjust(body, operator_name=user.name)
    return OkResponse()


@router.get("/adjustments/logs", response_model=List[StockAdjustmentLog], response_model_by_alias=True)
def adjustment_logs(db: Session = Depends(get_db), _user: Principal = Depends(require_business_user)):
    return InventoryService(db).logs()


@router.post("/receipts", response_model=StockReceipt, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
def create_receipt(
    body: CreateStockReceiptRequest,
    db: Session = Depends(get_db),
    user: Principal = Depends(require_business_user),
):
    return InventoryService(db).create_receipt(body, operator_name=user.name)


@router.get("/receipts", response_model=StockReceiptPage, response_model_by_alias=True)
def search_receipts(
    locationId: Optional[str] = Query(None),
    productId: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: Principal = Depends(require_business_user),
):
    return InventoryService(db).search_receipts(
        location_id=locationId,
        product_id=productId,
        page=page,
        page_size=pageSize,
    )


@router.get("/movements", response_model=StockMovementPage, response_model_by_alias=True)
def search_movements(
    productId: Optional[str] = Query(None),
    locationId: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: Principal = Depends(require_business_user),
):
    return InventoryService(db).search_movements(
        product_id=productId,
        location_id=locationId,
        movement_type=type,
        page=page,
        page_size=pageSize,
    )
