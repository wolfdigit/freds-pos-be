from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from src.core.exceptions import BusinessException
from src.models.customer import Customer
from src.models.preorder import PreOrder, PreOrderItem
from src.models.product import Product
from src.schemas.common import BusinessErrorCode
from src.schemas.preorder import (
    CreatePreOrderRequest,
    FulfillPreOrderRequest,
    MarkItemsArrivedRequest,
    PreOrder as PreOrderSchema,
    PreOrderItem as PreOrderItemSchema,
    UpdatePreOrderRequest,
)

TAIPEI = ZoneInfo("Asia/Taipei")


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


def _derive_status(order: PreOrder) -> str:
    if order.status == "cancelled":
        return "cancelled"
    if not order.items:
        return "pending"
    fully_delivered = all(item.qty_delivered >= item.qty_ordered for item in order.items)
    any_delivered = any(item.qty_delivered > 0 for item in order.items)
    any_arrived = any(item.qty_arrived > 0 for item in order.items)
    if fully_delivered:
        return "completed"
    if any_delivered:
        return "partially_completed"
    if any_arrived:
        return "partially_arrived"
    return "pending"


def _to_schema(order: PreOrder) -> PreOrderSchema:
    return PreOrderSchema(
        id=order.id,
        orderNumber=order.order_number,
        customerId=order.customer_id or "",
        customerName=order.customer_name or "",
        customerPhone=order.customer_phone or "",
        orderDate=order.order_date.isoformat(),
        expectedArrivalDate=order.expected_arrival_date.isoformat() if order.expected_arrival_date else None,
        status=order.status,
        source=order.source,
        items=[
            PreOrderItemSchema(
                id=item.id,
                productId=item.product_id,
                sku=item.sku,
                productName=item.product_name,
                scale=item.scale or None,
                brand=item.brand,
                quotedPrice=item.quoted_price,
                qtyOrdered=item.qty_ordered,
                qtyArrived=item.qty_arrived,
                qtyDelivered=item.qty_delivered,
            )
            for item in order.items
        ],
        note=order.note,
        operatorName=order.operator_name,
        updatedAt=order.updated_at.isoformat(),
    )


class PreOrderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _get(self, pre_order_id: str) -> PreOrder:
        order = self.db.scalar(
            select(PreOrder).where(PreOrder.id == pre_order_id).options(selectinload(PreOrder.items))
        )
        if order is None:
            _raise(404, BusinessErrorCode.ORDER_NOT_FOUND, "找不到預購單")
        return order

    def search_open(self, query: str) -> List[PreOrderSchema]:
        needle = f"%{query.strip()}%"
        rows = self.db.scalars(
            select(PreOrder)
            .where(PreOrder.status.notin_(("completed", "cancelled")))
            .where(
                or_(
                    PreOrder.customer_phone.ilike(needle),
                    PreOrder.customer_name.ilike(needle),
                    PreOrder.order_number.ilike(needle),
                )
            )
            .options(selectinload(PreOrder.items))
            .order_by(PreOrder.updated_at.desc())
        ).unique().all()
        return [_to_schema(row) for row in rows]

    def by_customer(self, customer_id: str) -> List[PreOrderSchema]:
        rows = self.db.scalars(
            select(PreOrder)
            .where(PreOrder.customer_id == customer_id)
            .options(selectinload(PreOrder.items))
            .order_by(PreOrder.updated_at.desc())
        ).unique().all()
        return [_to_schema(row) for row in rows]

    def get(self, pre_order_id: str) -> PreOrderSchema:
        return _to_schema(self._get(pre_order_id))

    def create(self, data: CreatePreOrderRequest) -> PreOrderSchema:
        customer: Optional[Customer] = None
        if data.customer_id:
            customer = self.db.get(Customer, data.customer_id)
            if customer is None:
                _raise(404, BusinessErrorCode.CUSTOMER_NOT_FOUND, "找不到指定的會員")
        now = datetime.now(TAIPEI)
        order_date = datetime.fromisoformat(data.order_date).date() if data.order_date else now.date()
        expected = (
            datetime.fromisoformat(data.expected_arrival_date).date() if data.expected_arrival_date else None
        )
        prefix = f"PO-{now.strftime('%Y%m')}-"
        existing = self.db.scalar(
            select(PreOrder.order_number).where(PreOrder.order_number.like(f"{prefix}%")).order_by(PreOrder.order_number.desc())
        )
        seq = int(existing.rsplit("-", 1)[-1]) + 1 if existing else 1
        order = PreOrder(
            id=f"po-{uuid.uuid4().hex}",
            order_number=f"{prefix}{seq:04d}",
            customer_id=customer.id if customer else data.customer_id,
            customer_name=(customer.name if customer else data.customer_name) or "",
            customer_phone=(customer.phone if customer else data.customer_phone) or "",
            status="pending",
            source=data.source or "in_store",
            note=data.note,
            operator_name=data.operator_name,
            order_date=order_date,
            expected_arrival_date=expected,
            updated_at=datetime.now(timezone.utc),
        )
        for raw in data.items:
            product = self.db.get(Product, raw.product_id)
            if product is None:
                _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, "找不到指定商品")
            order.items.append(
                PreOrderItem(
                    id=raw.id or f"poi-{uuid.uuid4().hex}",
                    product_id=product.id,
                    sku=product.sku,
                    product_name=product.name,
                    scale=product.scale,
                    brand=product.brand,
                    quoted_price=raw.quoted_price,
                    qty_ordered=raw.qty_ordered,
                    qty_arrived=raw.qty_arrived,
                    qty_delivered=raw.qty_delivered,
                )
            )
        order.status = _derive_status(order)
        self.db.add(order)
        self.db.commit()
        return self.get(order.id)

    def update(self, pre_order_id: str, data: UpdatePreOrderRequest) -> PreOrderSchema:
        order = self._get(pre_order_id)
        if data.customer_name is not None:
            order.customer_name = data.customer_name
        if data.customer_phone is not None:
            order.customer_phone = data.customer_phone
        if data.note is not None:
            order.note = data.note
        if data.source is not None:
            order.source = data.source
        if data.operator_name is not None:
            order.operator_name = data.operator_name
        if data.expected_arrival_date:
            order.expected_arrival_date = datetime.fromisoformat(data.expected_arrival_date).date()
        if data.status:
            order.status = data.status
        else:
            order.status = _derive_status(order)
        order.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return self.get(order.id)

    def mark_arrived(self, pre_order_id: str, data: MarkItemsArrivedRequest) -> None:
        order = self._get(pre_order_id)
        by_product = {item.product_id: item for item in order.items}
        for arrived in data.arrived_items:
            item = by_product.get(arrived.product_id)
            if item is None:
                _raise(404, BusinessErrorCode.PRODUCT_NOT_FOUND, "預購單沒有這個商品")
            item.qty_arrived += arrived.qty
        order.status = _derive_status(order)
        order.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    def fulfill(self, pre_order_id: str, data: FulfillPreOrderRequest) -> None:
        order = self._get(pre_order_id)
        by_id = {item.id: item for item in order.items}
        for fulfilled in data.fulfilled_items:
            item = by_id.get(fulfilled.pre_order_item_id)
            if item is None:
                _raise(404, BusinessErrorCode.ORDER_NOT_FOUND, "找不到預購品項")
            if item.qty_delivered + fulfilled.qty > item.qty_arrived:
                _raise(409, BusinessErrorCode.PREORDER_QTY_EXCEEDED, "交貨數量超過已到貨數量")
            item.qty_delivered += fulfilled.qty
        order.status = _derive_status(order)
        order.updated_at = datetime.now(timezone.utc)
        self.db.commit()
