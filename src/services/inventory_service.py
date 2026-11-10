from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.exceptions import BusinessException
from src.models.location import InventoryAdjustmentLog, InventoryLocation, InventoryMovement, InventoryReceipt
from src.models.product import Product, ProductInventory
from src.models.system import StoreBranch
from src.schemas.common import BusinessErrorCode
from src.schemas.inventory import (
    BatchInventoryAdjustRequest,
    CreateInventoryLocationRequest,
    CreateInventoryReceiptRequest,
    DeleteInventoryLocationRequest,
    DeleteInventoryLocationResponse,
    InventoryTransferRequest,
    MoveAllStockRequest,
    ReboundStore,
    InventoryAdjustRequest,
    InventoryAdjustmentLog as InventoryAdjustmentLogSchema,
    InventoryItemAdjustment,
    InventoryLocationChange,
    InventoryLocationDto,
    InventoryMovement as InventoryMovementSchema,
    InventoryMovementPage,
    InventoryReceipt as InventoryReceiptSchema,
    InventoryReceiptItem as InventoryReceiptItemSchema,
    InventoryReceiptPage,
    UpdateInventoryLocationRequest,
)
from src.services.location_integrity import location_delete_blocked_by_store_fk

DEFAULT_LOCATIONS = (
    ("e1a10001-0000-4000-8000-000000000001", "門市現貨", "🏪", True, 1, "store"),
    ("e1a10002-0000-4000-8000-000000000002", "後方倉庫", "📦", False, 2, "warehouse"),
    ("e1a10003-0000-4000-8000-000000000003", "公司總倉", "🏢", False, 3, "company"),
    ("e1a10004-0000-4000-8000-000000000004", "調度暫存", "🚚", False, 4, "other"),
    ("e1a10005-0000-4000-8000-000000000005", "退貨品", "↩️", False, 5, "returned"),
)
DEFAULT_STORE_LOCATION_ID = DEFAULT_LOCATIONS[0][0]
RETURNED_LOCATION_ID = DEFAULT_LOCATIONS[4][0]
LEGACY_LOCATION_IDS = {legacy: loc_id for loc_id, *_rest, legacy in DEFAULT_LOCATIONS}
MIN_LOCATION_COUNT = 1


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def list_locations(db: Session) -> List[InventoryLocation]:
    return list(
        db.scalars(select(InventoryLocation).order_by(InventoryLocation.display_order, InventoryLocation.id)).all()
    )


def ensure_locations(db: Session) -> List[InventoryLocation]:
    rows = list_locations(db)
    if rows:
        return rows
    for loc_id, name, icon, is_default, order, _legacy in DEFAULT_LOCATIONS:
        db.add(
            InventoryLocation(
                id=loc_id,
                name=name,
                icon=icon,
                is_default=is_default,
                display_order=order,
            )
        )
    db.flush()
    return list_locations(db)


def lock_all_locations(db: Session) -> List[InventoryLocation]:
    """Lock every location in id order before a store row.

    Delete, rebind, and checkout share this order, so one waits for the other
    instead of each waiting for the other's row.
    """

    ids = list(db.scalars(select(InventoryLocation.id).order_by(InventoryLocation.id)).all())
    locked: List[InventoryLocation] = []
    for loc_id in ids:
        row = db.scalar(select(InventoryLocation).where(InventoryLocation.id == loc_id).with_for_update())
        if row is not None:
            locked.append(row)
    return locked


def resolve_location_id(db: Session, raw: str) -> InventoryLocation:
    key = LEGACY_LOCATION_IDS.get(raw, raw)
    row = db.get(InventoryLocation, key)
    if row is None:
        _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到庫存地點")
    return row


def require_two_locations(db: Session, normal_id: str, returned_id: str) -> tuple[InventoryLocation, InventoryLocation]:
    ensure_locations(db)
    lock_all_locations(db)
    normal = resolve_location_id(db, normal_id)
    returned = resolve_location_id(db, returned_id)
    return normal, returned


def _is_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if sqlstate == "23505":
        return True
    text = str(orig if orig is not None else exc).lower()
    return "unique constraint failed" in text


def _name_taken(db: Session, name: str, *, exclude_id: Optional[str] = None) -> bool:
    stmt = select(InventoryLocation.id).where(InventoryLocation.name == name)
    if exclude_id is not None:
        stmt = stmt.where(InventoryLocation.id != exclude_id)
    return db.scalar(stmt) is not None


def insert_location(
    db: Session,
    name: str,
    *,
    icon: Optional[str] = None,
    display_order: Optional[int] = None,
) -> InventoryLocation:
    ensure_locations(db)
    cleaned = name.strip()
    if not cleaned:
        _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "地點名稱不可空白")
    if _name_taken(db, cleaned):
        _raise(409, BusinessErrorCode.LOCATION_NAME_TAKEN, "庫存點名稱已存在")
    current = list_locations(db)
    pending = [obj for obj in db.new if isinstance(obj, InventoryLocation)]
    last_order = max([row.display_order for row in current] + [obj.display_order for obj in pending] + [0])
    row = InventoryLocation(
        id=str(uuid.uuid4()),
        name=cleaned,
        icon=icon or "📍",
        is_default=False,
        display_order=display_order if display_order is not None else last_order + 1,
    )
    db.add(row)
    db.flush()
    return row


def _lock_stock(db: Session, product_id: str, location: InventoryLocation) -> ProductInventory:
    stmt = (
        select(ProductInventory)
        .where(ProductInventory.product_id == product_id, ProductInventory.location == location.id)
        .with_for_update()
    )
    row = db.scalar(stmt)
    if row is None:
        row = ProductInventory(
            product_id=product_id,
            location=location.id,
            location_name=location.name,
            quantity=0,
        )
        db.add(row)
        db.flush()
    return row


def _require_product(db: Session, product_id: str) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, "找不到指定商品")
    return product


def _write_movement(
    db: Session,
    *,
    movement_type: str,
    product_id: str,
    location_id: str,
    quantity_delta: int,
    quantity_after: int,
    reason: Optional[str],
    source_type: str,
    source_id: str,
    operator_name: str,
    sku: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    db.add(
        InventoryMovement(
            id=_new_id("mov"),
            type=movement_type,
            product_id=product_id,
            sku=sku,
            name=name,
            location_id=location_id,
            quantity_delta=quantity_delta,
            quantity_after=quantity_after,
            reason=reason,
            source_type=source_type,
            source_id=source_id,
            operator_name=operator_name,
            created_at=datetime.now(timezone.utc),
        )
    )


def apply_checkout_stock(
    db: Session,
    *,
    product_id: str,
    quantity: int,
    restock: Optional[bool],
    store_name: str,
    order_id: str,
    operator_name: str,
) -> tuple[Optional[str], Optional[str]]:
    lock_all_locations(db)
    store = db.scalar(select(StoreBranch).where(StoreBranch.name == store_name).with_for_update())
    if store is None:
        _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市")
    if quantity > 0:
        location = db.get(InventoryLocation, store.inventory_location_id)
        if location is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市的正常庫存點")
        row = _lock_stock(db, product_id, location)
        row.quantity -= quantity
        row.location_name = location.name
        _write_movement(
            db,
            movement_type="sale",
            product_id=product_id,
            location_id=location.id,
            quantity_delta=-quantity,
            quantity_after=row.quantity,
            reason=None,
            source_type="checkout_order",
            source_id=order_id,
            operator_name=operator_name,
        )
        return location.id, location.name
    if restock is False:
        return None, None
    location = db.get(InventoryLocation, store.returned_inventory_location_id)
    if location is None:
        _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到門市的退貨庫存點")
    returned = abs(quantity)
    row = _lock_stock(db, product_id, location)
    row.quantity += returned
    row.location_name = location.name
    _write_movement(
        db,
        movement_type="return_restock",
        product_id=product_id,
        location_id=location.id,
        quantity_delta=returned,
        quantity_after=row.quantity,
        reason=None,
        source_type="checkout_order",
        source_id=order_id,
        operator_name=operator_name,
    )
    return location.id, location.name


def _bindings_by_location(db: Session) -> tuple[dict[str, List[str]], dict[str, List[str]]]:
    normal: dict[str, List[str]] = {}
    returned: dict[str, List[str]] = {}
    rows = db.scalars(select(StoreBranch).order_by(StoreBranch.name)).all()
    for store in rows:
        normal.setdefault(store.inventory_location_id, []).append(store.name)
        returned.setdefault(store.returned_inventory_location_id, []).append(store.name)
    return normal, returned


def _to_dto(row: InventoryLocation, normal_names: Sequence[str], returned_names: Sequence[str]) -> InventoryLocationDto:
    return InventoryLocationDto(
        id=row.id,
        name=row.name,
        icon=row.icon,
        isDefault=row.is_default,
        displayOrder=row.display_order,
        storeNames=list(normal_names),
        returnedStoreNames=list(returned_names),
    )


def _pair(source: InventoryLocation, target: InventoryLocation) -> None:
    if source.id == target.id:
        _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "調出與調入地點不可相同")


def _move_quantity(
    db: Session,
    *,
    product_id: str,
    source: InventoryLocation,
    target: InventoryLocation,
    quantity: int,
    source_id: str,
    reason: Optional[str],
    operator_name: str,
) -> None:
    src_row = _lock_stock(db, product_id, source)
    if src_row.quantity < quantity:
        _raise(409, BusinessErrorCode.INSUFFICIENT_INVENTORY, "調出地點庫存不足")
    dest_row = _lock_stock(db, product_id, target)
    src_row.quantity -= quantity
    dest_row.quantity += quantity
    src_row.location_name = source.name
    dest_row.location_name = target.name
    _write_movement(
        db,
        movement_type="transfer_out",
        product_id=product_id,
        location_id=source.id,
        quantity_delta=-quantity,
        quantity_after=src_row.quantity,
        reason=reason,
        source_type="transfer",
        source_id=source_id,
        operator_name=operator_name,
    )
    _write_movement(
        db,
        movement_type="transfer_in",
        product_id=product_id,
        location_id=target.id,
        quantity_delta=quantity,
        quantity_after=dest_row.quantity,
        reason=reason,
        source_type="transfer",
        source_id=source_id,
        operator_name=operator_name,
    )


class InventoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_locations(self) -> List[InventoryLocationDto]:
        rows = ensure_locations(self.db)
        normal, returned = _bindings_by_location(self.db)
        return [_to_dto(row, normal.get(row.id, []), returned.get(row.id, [])) for row in rows]

    def create_location(self, data: CreateInventoryLocationRequest) -> InventoryLocationDto:
        ensure_locations(self.db)
        lock_all_locations(self.db)
        row = insert_location(self.db, data.name, icon=data.icon, display_order=data.display_order)
        self._commit_location_name()
        return _to_dto(row, [], [])

    def update_location(self, location_id: str, data: UpdateInventoryLocationRequest) -> InventoryLocationDto:
        # Lock locations before stock rows. Checkout locks in that same order;
        # renaming first would wait on stock while checkout waits on the location.
        locked = lock_all_locations(self.db)
        row = next((item for item in locked if item.id == location_id), None)
        if row is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到庫存地點")
        if data.name is not None:
            cleaned = data.name.strip()
            if not cleaned:
                _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "地點名稱不可空白")
            if cleaned != row.name and _name_taken(self.db, cleaned, exclude_id=row.id):
                _raise(409, BusinessErrorCode.LOCATION_NAME_TAKEN, "庫存點名稱已存在")
            row.name = cleaned
            self.db.execute(
                update(ProductInventory).where(ProductInventory.location == row.id).values(location_name=cleaned)
            )
        if data.icon is not None:
            row.icon = data.icon
        if data.display_order is not None:
            row.display_order = data.display_order
        self._commit_location_name()
        normal, returned = _bindings_by_location(self.db)
        return _to_dto(row, normal.get(row.id, []), returned.get(row.id, []))

    def delete_location(self, location_id: str, data: DeleteInventoryLocationRequest) -> DeleteInventoryLocationResponse:
        locked = lock_all_locations(self.db)
        source = next((row for row in locked if row.id == location_id), None)
        if source is None:
            _raise(404, BusinessErrorCode.LOCATION_NOT_FOUND, "找不到欲刪除的庫存地點")
        if len(locked) <= MIN_LOCATION_COUNT:
            _raise(409, BusinessErrorCode.LAST_LOCATION, "至少要保留一個庫存點")
        stock_rows = list(
            self.db.scalars(
                select(ProductInventory).where(ProductInventory.location == source.id).with_for_update()
            ).all()
        )
        if any(row.quantity != 0 for row in stock_rows):
            _raise(409, BusinessErrorCode.LOCATION_NOT_EMPTY, "庫存點仍有數量（含負數），請先轉移或將數量改為 0")
        stores = list(
            self.db.scalars(
                select(StoreBranch)
                .where(
                    or_(
                        StoreBranch.inventory_location_id == source.id,
                        StoreBranch.returned_inventory_location_id == source.id,
                    )
                )
                .order_by(StoreBranch.name)
                .with_for_update()
            ).all()
        )
        rebound: List[ReboundStore] = []
        target: Optional[InventoryLocation] = None
        if stores:
            if not data.rebind_to_location:
                _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "請指定這些門市要改綁的庫存點")
            target = resolve_location_id(self.db, data.rebind_to_location)
            if target.id == source.id:
                _raise(400, BusinessErrorCode.INVALID_LOCATION_TRANSFER, "改綁目標不能是即將刪除的庫存點")
            for store in stores:
                if store.inventory_location_id == source.id:
                    store.inventory_location_id = target.id
                    rebound.append(ReboundStore(name=store.name, binding="normal", inventoryLocationId=target.id))
                if store.returned_inventory_location_id == source.id:
                    store.returned_inventory_location_id = target.id
                    rebound.append(ReboundStore(name=store.name, binding="returned", inventoryLocationId=target.id))
        for row in stock_rows:
            self.db.delete(row)
        deleted_id = source.id
        try:
            # RESTRICT is checked per statement. Flush the zero rows and the
            # store rebinds first; deleting the location in the same flush
            # emits that DELETE while the rows are still there.
            self.db.flush()
            self.db.delete(source)
            self.db.commit()
        except IntegrityError as exc:
            if location_delete_blocked_by_store_fk(self.db, exc, deleted_id):
                _raise(409, BusinessErrorCode.INVENTORY_LOCATION_IN_USE, "仍有門市對應此地點，請改綁後再刪")
            raise
        return DeleteInventoryLocationResponse(deletedLocation=deleted_id, reboundStoreNames=rebound)

    def _commit_location_name(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            if _is_unique_violation(exc):
                _raise(409, BusinessErrorCode.LOCATION_NAME_TAKEN, "庫存點名稱已存在")
            raise

    def transfer(self, data: InventoryTransferRequest, *, operator_name: str) -> None:
        lock_all_locations(self.db)
        _require_product(self.db, data.product_id)
        source = resolve_location_id(self.db, data.from_location)
        target = resolve_location_id(self.db, data.to_location)
        _pair(source, target)
        _move_quantity(
            self.db,
            product_id=data.product_id,
            source=source,
            target=target,
            quantity=data.quantity,
            source_id=_new_id("trf"),
            reason=data.reason,
            operator_name=operator_name,
        )
        self.db.commit()

    def move_all(self, data: MoveAllStockRequest, *, operator_name: str) -> None:
        lock_all_locations(self.db)
        source = resolve_location_id(self.db, data.from_location)
        target = resolve_location_id(self.db, data.to_location)
        _pair(source, target)
        rows = list(
            self.db.scalars(
                select(ProductInventory)
                .where(ProductInventory.location == source.id, ProductInventory.quantity != 0)
                .with_for_update()
            ).all()
        )
        source_id = _new_id("trf")
        for row in rows:
            moved = row.quantity
            dest = _lock_stock(self.db, row.product_id, target)
            row.quantity = 0
            dest.quantity += moved
            row.location_name = source.name
            dest.location_name = target.name
            _write_movement(
                self.db,
                movement_type="transfer_out",
                product_id=row.product_id,
                location_id=source.id,
                quantity_delta=-moved,
                quantity_after=0,
                reason=data.reason,
                source_type="transfer",
                source_id=source_id,
                operator_name=operator_name,
            )
            _write_movement(
                self.db,
                movement_type="transfer_in",
                product_id=row.product_id,
                location_id=target.id,
                quantity_delta=moved,
                quantity_after=dest.quantity,
                reason=data.reason,
                source_type="transfer",
                source_id=source_id,
                operator_name=operator_name,
            )
        self.db.commit()

    def adjust(self, data: InventoryAdjustRequest, *, operator_name: str) -> None:
        lock_all_locations(self.db)
        product = _require_product(self.db, data.product_id)
        location = resolve_location_id(self.db, data.location)
        row = _lock_stock(self.db, data.product_id, location)
        old_qty = row.quantity
        row.quantity = data.new_quantity
        row.location_name = location.name
        diff = data.new_quantity - old_qty
        log_id = _new_id("adj")
        change = InventoryLocationChange(
            location=location.id,
            locationName=location.name,
            oldQty=old_qty,
            newQty=data.new_quantity,
            diff=diff,
        )
        item = InventoryItemAdjustment(
            productId=product.id,
            sku=product.sku,
            barcode=product.barcode,
            name=product.name,
            brand=product.brand,
            changes=[change],
            summaryText=f"{location.name} {old_qty} → {data.new_quantity}",
        )
        self.db.add(
            InventoryAdjustmentLog(
                id=log_id,
                operator_name=operator_name,
                items_json=json.dumps([item.model_dump(by_alias=True)], ensure_ascii=False),
                total_qty_change=diff,
                note=data.reason,
            )
        )
        _write_movement(
            self.db,
            movement_type="adjust",
            product_id=product.id,
            location_id=location.id,
            quantity_delta=diff,
            quantity_after=row.quantity,
            reason=data.reason,
            source_type="adjustment",
            source_id=log_id,
            operator_name=operator_name,
        )
        self.db.commit()

    def batch_adjust(self, data: BatchInventoryAdjustRequest, *, operator_name: str) -> None:
        lock_all_locations(self.db)
        logged: List[InventoryItemAdjustment] = []
        total_diff = 0
        log_id = _new_id("adj")
        for item in data.adjustments:
            product = _require_product(self.db, item.product_id)
            changes: List[InventoryLocationChange] = []
            for change in item.changes:
                location = resolve_location_id(self.db, change.location)
                row = _lock_stock(self.db, item.product_id, location)
                old_qty = row.quantity
                row.quantity = change.new_qty
                row.location_name = location.name
                diff = change.new_qty - old_qty
                total_diff += diff
                changes.append(
                    InventoryLocationChange(
                        location=location.id,
                        locationName=location.name,
                        oldQty=old_qty,
                        newQty=change.new_qty,
                        diff=diff,
                    )
                )
            logged.append(
                InventoryItemAdjustment(
                    productId=product.id,
                    sku=product.sku,
                    barcode=product.barcode,
                    name=product.name,
                    brand=product.brand,
                    changes=changes,
                    summaryText=item.summary_text,
                )
            )
        self.db.add(
            InventoryAdjustmentLog(
                id=log_id,
                operator_name=operator_name,
                items_json=json.dumps([item.model_dump(by_alias=True) for item in logged], ensure_ascii=False),
                total_qty_change=total_diff,
                note=data.note,
            )
        )
        for item in logged:
            for change in item.changes:
                _write_movement(
                    self.db,
                    movement_type="adjust",
                    product_id=item.product_id,
                    location_id=change.location,
                    quantity_delta=change.diff,
                    quantity_after=change.new_qty,
                    reason=data.note,
                    source_type="adjustment",
                    source_id=log_id,
                    operator_name=operator_name,
                )
        self.db.commit()

    def logs(self) -> List[InventoryAdjustmentLogSchema]:
        rows: Sequence[InventoryAdjustmentLog] = self.db.scalars(
            select(InventoryAdjustmentLog).order_by(InventoryAdjustmentLog.timestamp.desc())
        ).all()
        result: List[InventoryAdjustmentLogSchema] = []
        for row in rows:
            raw_items = json.loads(row.items_json)
            result.append(
                InventoryAdjustmentLogSchema(
                    id=row.id,
                    timestamp=row.timestamp,
                    operatorName=row.operator_name,
                    items=[InventoryItemAdjustment.model_validate(item) for item in raw_items],
                    totalQtyChange=row.total_qty_change,
                    note=row.note,
                )
            )
        return result

    def create_receipt(self, data: CreateInventoryReceiptRequest, *, operator_name: str) -> InventoryReceiptSchema:
        lock_all_locations(self.db)
        location = resolve_location_id(self.db, data.location_id)
        totals: dict[str, int] = {}
        for line in data.items:
            totals[line.product_id] = totals.get(line.product_id, 0) + line.quantity
        receipt_id = _new_id("rcv")
        item_rows: List[InventoryReceiptItemSchema] = []
        for product_id, quantity in totals.items():
            product = _require_product(self.db, product_id)
            row = _lock_stock(self.db, product_id, location)
            row.quantity += quantity
            row.location_name = location.name
            _write_movement(
                self.db,
                movement_type="receipt",
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                location_id=location.id,
                quantity_delta=quantity,
                quantity_after=row.quantity,
                reason=data.note,
                source_type="receipt",
                source_id=receipt_id,
                operator_name=operator_name,
            )
            item_rows.append(
                InventoryReceiptItemSchema(productId=product.id, sku=product.sku, name=product.name, quantity=quantity)
            )
        created_at = datetime.now(timezone.utc)
        self.db.add(
            InventoryReceipt(
                id=receipt_id,
                location_id=location.id,
                location_name=location.name,
                supplier=(data.supplier or "").strip() or None,
                note=data.note,
                operator_name=operator_name,
                created_at=created_at,
            )
        )
        self.db.commit()
        return InventoryReceiptSchema(
            id=receipt_id,
            locationId=location.id,
            locationName=location.name,
            supplier=(data.supplier or "").strip() or None,
            note=data.note,
            operatorName=operator_name,
            createdAt=created_at,
            items=item_rows,
            totalQuantity=sum(item.quantity for item in item_rows),
        )

    def search_receipts(
        self,
        *,
        location_id: Optional[str],
        product_id: Optional[str],
        page: int,
        page_size: int,
    ) -> InventoryReceiptPage:
        stmt = select(InventoryReceipt)
        if location_id:
            stmt = stmt.where(InventoryReceipt.location_id == location_id)
        if product_id:
            stmt = stmt.where(
                InventoryReceipt.id.in_(
                    select(InventoryMovement.source_id).where(
                        InventoryMovement.source_type == "receipt",
                        InventoryMovement.product_id == product_id,
                    )
                )
            )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            self.db.scalars(
                stmt.order_by(InventoryReceipt.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return InventoryReceiptPage(
            items=[self._receipt_schema(row) for row in rows],
            page=page,
            pageSize=page_size,
            total=total,
        )

    def search_movements(
        self,
        *,
        product_id: Optional[str],
        location_id: Optional[str],
        movement_type: Optional[str],
        page: int,
        page_size: int,
    ) -> InventoryMovementPage:
        stmt = select(InventoryMovement)
        if product_id:
            stmt = stmt.where(InventoryMovement.product_id == product_id)
        if location_id:
            stmt = stmt.where(InventoryMovement.location_id == location_id)
        if movement_type:
            stmt = stmt.where(InventoryMovement.type == movement_type)
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(
            self.db.scalars(
                stmt.order_by(InventoryMovement.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return InventoryMovementPage(
            items=[
                InventoryMovementSchema(
                    id=row.id,
                    type=row.type,
                    productId=row.product_id,
                    sku=row.sku,
                    name=row.name,
                    locationId=row.location_id,
                    quantityDelta=row.quantity_delta,
                    quantityAfter=row.quantity_after,
                    reason=row.reason,
                    sourceId=row.source_id,
                    operatorName=row.operator_name,
                    createdAt=row.created_at,
                )
                for row in rows
            ],
            page=page,
            pageSize=page_size,
            total=total,
        )

    def _receipt_schema(self, row: InventoryReceipt) -> InventoryReceiptSchema:
        movements = list(
            self.db.scalars(
                select(InventoryMovement)
                .where(InventoryMovement.source_type == "receipt", InventoryMovement.source_id == row.id)
                .order_by(InventoryMovement.id)
            ).all()
        )
        schemas = [
            InventoryReceiptItemSchema(
                productId=item.product_id,
                sku=item.sku or "",
                name=item.name or "",
                quantity=item.quantity_delta,
            )
            for item in movements
        ]
        return InventoryReceiptSchema(
            id=row.id,
            locationId=row.location_id,
            locationName=row.location_name,
            supplier=row.supplier,
            note=row.note,
            operatorName=row.operator_name,
            createdAt=row.created_at,
            items=schemas,
            totalQuantity=sum(item.quantity for item in schemas),
        )
