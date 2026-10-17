from __future__ import annotations

import json
import uuid
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.models.location import StockAdjustmentLog, StockLocation
from src.models.product import Product, ProductStock
from src.schemas.common import BusinessErrorCode
from src.schemas.inventory import (
    BatchStockAdjustRequest,
    CreateStockLocationRequest,
    DeleteStockLocationRequest,
    DeleteStockLocationResponse,
    InventoryTransferRequest,
    StockAdjustRequest,
    StockAdjustmentLog as StockAdjustmentLogSchema,
    StockItemAdjustment,
    StockLocationDto,
    UpdateStockLocationRequest,
)

DEFAULT_LOCATIONS = (
    ("e1a10001-0000-4000-8000-000000000001", "門市現貨", "🏪", True, 1, "store"),
    ("e1a10002-0000-4000-8000-000000000002", "後方倉庫", "📦", False, 2, "warehouse"),
    ("e1a10003-0000-4000-8000-000000000003", "公司總倉", "🏢", False, 3, "company"),
    ("e1a10004-0000-4000-8000-000000000004", "調度暫存", "🚚", False, 4, "other"),
)
DEFAULT_STORE_LOCATION_ID = DEFAULT_LOCATIONS[0][0]
LEGACY_LOCATION_IDS = {legacy: loc_id for loc_id, *_rest, legacy in DEFAULT_LOCATIONS}


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


def _to_dto(row: StockLocation) -> StockLocationDto:
    return StockLocationDto(
        id=row.id,
        name=row.name,
        icon=row.icon,
        isDefault=row.is_default,
        displayOrder=row.display_order,
        isActive=row.is_active,
    )


def list_locations(db: Session) -> List[StockLocation]:
    return list(
        db.scalars(select(StockLocation).order_by(StockLocation.display_order, StockLocation.id)).all()
    )


def ensure_locations(db: Session) -> List[StockLocation]:
    rows = list_locations(db)
    if rows:
        return rows
    for loc_id, name, icon, is_default, order, _legacy in DEFAULT_LOCATIONS:
        db.add(
            StockLocation(
                id=loc_id,
                name=name,
                icon=icon,
                is_default=is_default,
                display_order=order,
                is_active=True,
            )
        )
    db.flush()
    return list_locations(db)


def resolve_location_id(db: Session, raw: str) -> StockLocation:
    key = LEGACY_LOCATION_IDS.get(raw, raw)
    row = db.get(StockLocation, key)
    if row is None:
        _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到庫存地點")
    return row


def _stock_row(db: Session, product_id: str, location: StockLocation, lock: bool = False) -> ProductStock:
    stmt = select(ProductStock).where(
        ProductStock.product_id == product_id,
        ProductStock.location == location.id,
    )
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        row = ProductStock(
            product_id=product_id,
            location=location.id,
            location_name=location.name,
            quantity=0,
        )
        db.add(row)
        db.flush()
    return row


class InventoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_locations(self) -> List[StockLocationDto]:
        return [_to_dto(row) for row in ensure_locations(self.db)]

    def create_location(self, data: CreateStockLocationRequest) -> StockLocationDto:
        name = data.name.strip()
        if not name:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "地點名稱不可空白")
        current = ensure_locations(self.db)
        row = StockLocation(
            id=str(uuid.uuid4()),
            name=name,
            icon=data.icon or "📍",
            is_default=False,
            display_order=data.display_order if data.display_order is not None else len(current) + 1,
            is_active=data.is_active,
        )
        self.db.add(row)
        self.db.commit()
        return _to_dto(row)

    def update_location(self, location_id: str, data: UpdateStockLocationRequest) -> StockLocationDto:
        row = self.db.get(StockLocation, location_id)
        if row is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到庫存地點")
        if data.name is not None:
            row.name = data.name.strip() or row.name
        if data.icon is not None:
            row.icon = data.icon
        if data.display_order is not None:
            row.display_order = data.display_order
        if data.is_active is not None:
            row.is_active = data.is_active
        self.db.add(row)
        self.db.commit()
        return _to_dto(row)

    def delete_location(self, location_id: str, data: DeleteStockLocationRequest) -> DeleteStockLocationResponse:
        source = self.db.get(StockLocation, location_id)
        if source is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到欲刪除的庫存地點")
        if location_id == data.transfer_to_location:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "轉移目標地點不能與被刪除地點相同")
        target = resolve_location_id(self.db, data.transfer_to_location)
        rows = list(self.db.scalars(select(ProductStock).where(ProductStock.location == source.id)).all())
        affected = 0
        moved = 0
        for row in rows:
            if row.quantity == 0:
                self.db.delete(row)
                continue
            dest = _stock_row(self.db, row.product_id, target, lock=True)
            dest.quantity += row.quantity
            dest.location_name = target.name
            affected += 1
            moved += row.quantity
            self.db.delete(row)
        if source.is_default:
            target.is_default = True
        self.db.delete(source)
        self.db.commit()
        return DeleteStockLocationResponse(
            deletedLocation=source.id,
            transferredToLocation=target.id,
            affectedProductsCount=affected,
            totalQuantityTransferred=moved,
            message=f"成功刪除地點並將 {affected} 項商品共 {moved} 台庫存轉移",
        )

    def transfer(self, data: InventoryTransferRequest) -> None:
        if self.db.get(Product, data.product_id) is None:
            _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, "找不到指定商品")
        source = resolve_location_id(self.db, data.from_location)
        target = resolve_location_id(self.db, data.to_location)
        if source.id == target.id:
            _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "調出與調入地點不可相同")
        src_row = _stock_row(self.db, data.product_id, source, lock=True)
        if src_row.quantity < data.quantity:
            _raise(400, BusinessErrorCode.INSUFFICIENT_STORE_STOCK, "調出地點庫存不足")
        dest_row = _stock_row(self.db, data.product_id, target, lock=True)
        src_row.quantity -= data.quantity
        dest_row.quantity += data.quantity
        self.db.commit()

    def adjust(self, data: StockAdjustRequest) -> None:
        if self.db.get(Product, data.product_id) is None:
            _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, "找不到指定商品")
        location = resolve_location_id(self.db, data.location)
        row = _stock_row(self.db, data.product_id, location, lock=True)
        row.quantity = data.new_quantity
        row.location_name = location.name
        self.db.commit()

    def batch_adjust(self, data: BatchStockAdjustRequest) -> None:
        total_diff = 0
        for item in data.adjustments:
            if self.db.get(Product, item.product_id) is None:
                _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, "找不到指定商品")
            for change in item.changes:
                location = resolve_location_id(self.db, change.location)
                row = _stock_row(self.db, item.product_id, location, lock=True)
                row.quantity = change.new_qty
                row.location_name = location.name
                total_diff += change.diff
        log = StockAdjustmentLog(
            id=f"adj-{uuid.uuid4().hex}",
            operator_name=data.operator_name,
            items_json=json.dumps([item.model_dump(by_alias=True) for item in data.adjustments], ensure_ascii=False),
            total_qty_change=total_diff,
            note=data.note,
        )
        self.db.add(log)
        self.db.commit()

    def logs(self) -> List[StockAdjustmentLogSchema]:
        rows: Sequence[StockAdjustmentLog] = self.db.scalars(
            select(StockAdjustmentLog).order_by(StockAdjustmentLog.timestamp.desc())
        ).all()
        result: List[StockAdjustmentLogSchema] = []
        for row in rows:
            raw_items = json.loads(row.items_json)
            result.append(
                StockAdjustmentLogSchema(
                    id=row.id,
                    timestamp=row.timestamp,
                    operatorName=row.operator_name,
                    items=[StockItemAdjustment.model_validate(item) for item in raw_items],
                    totalQtyChange=row.total_qty_change,
                    note=row.note,
                )
            )
        return result
