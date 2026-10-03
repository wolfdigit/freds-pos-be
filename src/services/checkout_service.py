from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.core.exceptions import BusinessException
from src.models.checkout import CheckoutOrder, CheckoutOrderItem, CheckoutPayment
from src.models.customer import Customer
from src.models.preorder import PreOrder, PreOrderItem
from src.models.product import Product, ProductStock
from src.schemas.checkout import (
    CheckoutOrder as CheckoutOrderSchema,
    CheckoutOrderItem as CheckoutOrderItemSchema,
    CheckoutOrderSearchResponse,
    CheckoutReceipt,
    CreateOrderItem,
    CreateOrderRequest,
    InvoiceInfo,
    InvoiceType,
    OrderStatus,
    PaymentMethodType,
    PaymentTender,
)
from src.schemas.common import BusinessErrorCode
from src.services.customer_service import canonicalize_phone
from src.services.product_service import normalize_sku

POINTS_DISCOUNT_TWD = 360
STORE_LOCATION = "store"
TAIPEI = ZoneInfo("Asia/Taipei")
BRANCH_NAMES = {
    "branch-store": "台北旗艦店",
    "branch-online": "官網",
}


@dataclass
class _DraftLine:
    product: Product
    quantity: int
    unit_price: int
    original_price: int
    cost_price: int
    is_manual_price: bool
    price_diff_reason: Optional[str]
    points_applied: bool
    points_amount: int
    subtotal: int
    sku: str
    name: str
    scale: str
    brand: str
    pre_order_item: Optional[PreOrderItem]
    original_item: Optional[CheckoutOrderItem]
    restock: Optional[bool]
    return_reason: Optional[str]


def sale_total(items_subtotal: int, shipping_fee: int, points_discount: int) -> int:
    """Floor at 0 only when a non-negative sale is wiped out by points discounts.

    A negative merchandise total (a refund) stays negative.
    """
    gross = items_subtotal + shipping_fee
    raw = gross - points_discount
    if gross >= 0 and raw < 0:
        return 0
    return raw


def derive_preorder_status(items: Sequence[PreOrderItem]) -> str:
    if all(item.qty_arrived == 0 for item in items):
        return "pending"
    if all(item.qty_delivered == item.qty_ordered for item in items):
        return "completed"
    if any(item.qty_delivered > 0 for item in items):
        return "partially_completed"
    return "partially_arrived"


def _contains_like(column: ColumnElement, value: str) -> ColumnElement:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.like(f"%{escaped}%", escape="\\")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _body_hash(data: CreateOrderRequest) -> str:
    payload = data.model_dump(mode="json", by_alias=True)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _order_options():
    return (
        selectinload(CheckoutOrder.items),
        selectinload(CheckoutOrder.payments),
    )


def _to_item_schema(item: CheckoutOrderItem) -> CheckoutOrderItemSchema:
    return CheckoutOrderItemSchema(
        id=item.id,
        productId=item.product_id,
        sku=item.sku,
        name=item.name,
        scale=item.scale,
        brand=item.brand,
        originalPrice=item.original_price,
        unitPrice=item.unit_price,
        isManualPrice=item.is_manual_price,
        priceDiffReason=item.price_diff_reason,
        quantity=item.quantity,
        subtotal=item.subtotal,
        pointsDiscountApplied=item.points_discount_applied,
        pointsDiscountAmount=item.points_discount_amount,
        returnedQuantity=item.returned_quantity,
        preOrderId=item.pre_order_id,
        preOrderItemId=item.pre_order_item_id,
        originalOrderId=item.original_order_id,
        originalOrderItemId=item.original_order_item_id,
        restock=item.restock,
        returnReason=item.return_reason,
    )


def _to_order_schema(order: CheckoutOrder) -> CheckoutOrderSchema:
    return CheckoutOrderSchema(
        id=order.id,
        orderNumber=order.order_number,
        branchId=order.branch_id,
        branchName=order.branch_name,
        cashierId=order.cashier_id,
        cashierName=order.cashier_name,
        status=OrderStatus(order.status),
        customerId=order.customer_id,
        customerName=order.customer_name,
        customerPhone=order.customer_phone,
        items=[_to_item_schema(item) for item in order.items],
        itemsSubtotal=order.items_subtotal,
        discountAmount=order.discount_amount,
        pointsDiscountAmount=sum(item.points_discount_amount for item in order.items),
        shippingFee=order.shipping_fee,
        totalAmount=order.total_amount,
        payments=[
            PaymentTender(
                type=PaymentMethodType(payment.type),
                name=payment.name,
                amount=payment.amount,
                tenderedCash=payment.tendered_cash,
                changeAmount=payment.change_amount,
                transactionRef=payment.transaction_ref,
            )
            for payment in order.payments
        ],
        invoice=InvoiceInfo(
            invoiceNumber=order.invoice_number,
            type=InvoiceType(order.invoice_type),
            carrierCode=order.carrier_code,
            taxId=order.tax_id,
            buyerTitle=order.buyer_title,
        ),
        note=order.note or "",
        createdAt=order.created_at,
        updatedAt=order.updated_at,
    )


def _receipt_html(order: CheckoutOrderSchema) -> str:
    rows = "".join(
        f"<tr><td>{item.name}</td><td>{item.quantity}</td><td>{item.unit_price}</td>"
        f"<td>{item.subtotal}</td></tr>"
        for item in order.items
    )
    discount = (
        f"<p>點數折抵: NT$ {order.points_discount_amount}</p>"
        if order.points_discount_amount
        else ""
    )
    return (
        "<div class=\"receipt\">"
        f"<h2>{order.branch_name}</h2>"
        f"<p>單號: {order.order_number}</p>"
        f"<p>發票號碼: {order.invoice.invoice_number}</p>"
        f"<p>收銀員: {order.cashier_name}</p>"
        f"<table>{rows}</table>"
        f"{discount}"
        f"<p>應收總額: NT$ {order.total_amount}</p>"
        "</div>"
    )


def _raise(status_code: int, code: BusinessErrorCode, message: str) -> None:
    raise BusinessException(status_code=status_code, code=code, message=message)


class CheckoutService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        data: CreateOrderRequest,
        idempotency_key: Optional[str],
        *,
        cashier_id: str,
        cashier_name: str,
    ) -> CheckoutReceipt:
        cashier_id = cashier_id.strip()
        cashier_name = cashier_name.strip()
        if not cashier_id or not cashier_name:
            raise RuntimeError("目前使用者沒有收銀員身分")
        key = (idempotency_key or "").strip() or None
        body_hash = _body_hash(data)
        if key is not None:
            existing = self.db.scalar(
                select(CheckoutOrder)
                .where(CheckoutOrder.idempotency_key == key)
                .options(*_order_options())
            )
            if existing is not None:
                if (
                    existing.idempotency_body_hash != body_hash
                    or existing.cashier_id != cashier_id
                ):
                    _raise(409, BusinessErrorCode.IDEMPOTENCY_CONFLICT, "重複的結帳請求內容不一致")
                order = _to_order_schema(existing)
                return CheckoutReceipt(order=order, receiptPrintHtml=_receipt_html(order))

        self._validate_invoice(data.invoice)
        self._reject_cod(data.payments)
        customer = self._load_customer(data.customer_id)
        drafts = self._build_lines(data, customer)
        invoice_number = self._resolve_invoice_number(data.invoice, drafts)
        self._apply_writes(
            data, customer, drafts, key, body_hash, cashier_id, cashier_name, invoice_number
        )
        stored = self._get_by_id_or_raise(self._last_order_id)
        order = _to_order_schema(stored)
        return CheckoutReceipt(order=order, receiptPrintHtml=_receipt_html(order))

    def get_by_id(self, order_id: str) -> CheckoutOrderSchema:
        return _to_order_schema(self._get_by_id_or_raise(order_id))

    def search(
        self,
        *,
        customer_id: Optional[str],
        order_number: Optional[str],
        invoice_number: Optional[str],
        product_id: Optional[str],
        keyword: Optional[str],
        product_keyword: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        min_amount: Optional[int],
        max_amount: Optional[int],
        status: Optional[str],
        page: int,
        page_size: int,
    ) -> CheckoutOrderSearchResponse:
        stmt = select(CheckoutOrder)
        if customer_id:
            stmt = stmt.where(CheckoutOrder.customer_id == customer_id)
        if order_number:
            stmt = stmt.where(CheckoutOrder.order_number == order_number)
        invoice_text = (invoice_number or "").strip()
        if invoice_text:
            stmt = stmt.where(CheckoutOrder.invoice_number == invoice_text)
        if product_id:
            stmt = stmt.where(
                CheckoutOrder.items.any(CheckoutOrderItem.product_id == product_id)
            )
        if status and status != "all":
            stmt = stmt.where(CheckoutOrder.status == status)
        if start_date is not None:
            stmt = stmt.where(CheckoutOrder.created_at >= start_date)
        if end_date is not None:
            stmt = stmt.where(CheckoutOrder.created_at < end_date)
        if min_amount is not None:
            stmt = stmt.where(CheckoutOrder.total_amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(CheckoutOrder.total_amount <= max_amount)
        trimmed = (keyword or "").strip()
        if trimmed:
            phone = canonicalize_phone(trimmed)
            clauses = [
                _contains_like(CheckoutOrder.order_number, trimmed),
                _contains_like(CheckoutOrder.invoice_number, trimmed),
                _contains_like(CheckoutOrder.customer_name, trimmed),
                _contains_like(CheckoutOrder.customer_phone, trimmed),
            ]
            if phone and phone != trimmed:
                clauses.append(_contains_like(CheckoutOrder.customer_phone, phone))
            stmt = stmt.where(or_(*clauses))
        product_text = (product_keyword or "").strip()
        if product_text:
            name_match = _contains_like(func.lower(CheckoutOrderItem.name), product_text.lower())
            item_clauses = [name_match]
            normalized = normalize_sku(product_text)
            if normalized:
                normalized_column = func.replace(
                    func.replace(
                        func.replace(func.upper(CheckoutOrderItem.sku), "-", ""),
                        "_",
                        "",
                    ),
                    " ",
                    "",
                )
                item_clauses.append(_contains_like(normalized_column, normalized))
            stmt = stmt.where(CheckoutOrder.items.any(or_(*item_clauses)))

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(
            stmt.options(*_order_options())
            .order_by(CheckoutOrder.created_at.desc(), CheckoutOrder.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).unique().all()
        return CheckoutOrderSearchResponse(
            items=[_to_order_schema(row) for row in rows],
            page=page,
            pageSize=page_size,
            total=total,
        )

    def _get_by_id_or_raise(self, order_id: str) -> CheckoutOrder:
        order = self.db.scalar(
            select(CheckoutOrder)
            .where(CheckoutOrder.id == order_id)
            .options(*_order_options())
        )
        if order is None:
            _raise(404, BusinessErrorCode.ORDER_NOT_FOUND, "找不到原始銷售單據")
        return order

    def _load_customer(self, customer_id: Optional[str]) -> Optional[Customer]:
        if not customer_id:
            return None
        customer = self.db.get(Customer, customer_id)
        if customer is None:
            _raise(404, BusinessErrorCode.CUSTOMER_NOT_FOUND, "找不到指定的會員")
        return customer

    def _validate_invoice(self, invoice: InvoiceInfo) -> None:
        if not invoice.invoice_number:
            _raise(422, BusinessErrorCode.INVALID_PAYMENT, "請填寫發票號碼")
        if invoice.type == InvoiceType.TAX_ID:
            tax_id = (invoice.tax_id or "").strip()
            if len(tax_id) != 8 or not tax_id.isdigit():
                _raise(422, BusinessErrorCode.INVALID_PAYMENT, "統一編號須為 8 碼數字")
        if invoice.type == InvoiceType.CARRIER and not (invoice.carrier_code or "").strip():
            _raise(422, BusinessErrorCode.INVALID_PAYMENT, "請填寫載具條碼")

    def _resolve_invoice_number(self, invoice: InvoiceInfo, drafts: Sequence[_DraftLine]) -> str:
        """A sale owns a unique invoice number. A refund order reuses the original sale's."""
        returns = [line for line in drafts if line.quantity < 0]
        sales = [line for line in drafts if line.quantity > 0]
        if returns and sales:
            _raise(422, BusinessErrorCode.INVALID_PAYMENT, "同一張單不能同時銷售與退貨")
        if returns:
            numbers = {
                line.original_item.order.invoice_number
                for line in returns
                if line.original_item is not None
            }
            if len(numbers) != 1:
                _raise(422, BusinessErrorCode.INVALID_PAYMENT, "退貨品項必須屬於同一張發票")
            original_number = next(iter(numbers))
            if invoice.invoice_number != original_number:
                _raise(422, BusinessErrorCode.INVALID_PAYMENT, "退貨須沿用原銷售單的發票號碼")
            return original_number
        taken = self.db.scalar(
            select(CheckoutOrder.id)
            .join(CheckoutOrder.items)
            .where(
                CheckoutOrder.invoice_number == invoice.invoice_number,
                CheckoutOrderItem.quantity > 0,
            )
        )
        if taken is not None:
            _raise(409, BusinessErrorCode.INVOICE_NUMBER_DUPLICATE, "發票號碼已存在")
        return invoice.invoice_number

    def _reject_cod(self, payments: Sequence[PaymentTender]) -> None:
        if any(payment.type == PaymentMethodType.COD for payment in payments):
            _raise(422, BusinessErrorCode.INVALID_PAYMENT, "此階段不接受取貨付款")

    def _lock_store_stock(self, product_id: str) -> Optional[ProductStock]:
        return self.db.scalar(
            select(ProductStock)
            .where(
                ProductStock.product_id == product_id,
                ProductStock.location == STORE_LOCATION,
            )
            .with_for_update()
        )

    def _build_lines(
        self, data: CreateOrderRequest, customer: Optional[Customer]
    ) -> List[_DraftLine]:
        redeemed_products: set[str] = set()
        reserved_store: dict[str, int] = {}
        reserved_preorder: dict[str, int] = {}
        reserved_return: dict[str, int] = {}
        drafts: List[_DraftLine] = []
        for raw in data.items:
            product = self.db.get(Product, raw.product_id)
            if product is None:
                _raise(
                    404,
                    BusinessErrorCode.PRODUCT_NOT_FOUND,
                    f"找不到商品 (ID: {raw.product_id})",
                )
            pre_order_item = self._lock_preorder_item(raw, reserved_preorder)
            original_item = self._lock_original_item(raw, data.customer_id, reserved_return)
            if raw.quantity < 0:
                assert original_item is not None
                unit_price = original_item.unit_price
                original_price = original_item.original_price
                is_manual = original_item.is_manual_price
                reason = original_item.price_diff_reason
                sku, name, scale, brand = (
                    original_item.sku,
                    original_item.name,
                    original_item.scale,
                    original_item.brand,
                )
                cost_price = original_item.cost_price
                points_applied = False
                if raw.points_discount_applied:
                    _raise(422, BusinessErrorCode.INVALID_PAYMENT, "退貨品項不能使用點數折抵")
            else:
                original_price = product.list_price
                if raw.is_manual_price:
                    if raw.unit_price is None:
                        _raise(422, BusinessErrorCode.INVALID_PAYMENT, "手動改價必須提供單價")
                    unit_price = raw.unit_price
                    is_manual = True
                else:
                    unit_price = product.list_price
                    is_manual = False
                reason = raw.price_diff_reason
                sku, name, scale, brand = product.sku, product.name, product.scale, product.brand
                cost_price = product.cost_price
                points_applied = raw.points_discount_applied
                if points_applied:
                    if customer is None:
                        _raise(422, BusinessErrorCode.INVALID_PAYMENT, "散客不能使用點數折抵")
                    if raw.product_id in redeemed_products:
                        _raise(422, BusinessErrorCode.INVALID_PAYMENT, "同一商品只能折抵一次")
                    redeemed_products.add(raw.product_id)
            if raw.quantity > 0:
                stock = self._lock_store_stock(product.id)
                available = stock.quantity if stock is not None else 0
                reserved = reserved_store.get(product.id, 0) + raw.quantity
                if available < reserved:
                    _raise(
                        409,
                        BusinessErrorCode.INSUFFICIENT_STORE_STOCK,
                        "門市現貨不足，請先從倉庫調撥",
                    )
                reserved_store[product.id] = reserved
            drafts.append(
                _DraftLine(
                    product=product,
                    quantity=raw.quantity,
                    unit_price=unit_price,
                    original_price=original_price,
                    cost_price=cost_price,
                    is_manual_price=is_manual,
                    price_diff_reason=reason,
                    points_applied=points_applied,
                    points_amount=POINTS_DISCOUNT_TWD if points_applied else 0,
                    subtotal=unit_price * raw.quantity,
                    sku=sku,
                    name=name,
                    scale=scale,
                    brand=brand,
                    pre_order_item=pre_order_item,
                    original_item=original_item,
                    restock=raw.restock,
                    return_reason=raw.return_reason,
                )
            )
        return drafts

    def _lock_preorder_item(
        self, raw: CreateOrderItem, reserved_preorder: dict[str, int]
    ) -> Optional[PreOrderItem]:
        if raw.pre_order_id is None and raw.pre_order_item_id is None:
            return None
        if not raw.pre_order_id or not raw.pre_order_item_id or raw.quantity <= 0:
            _raise(409, BusinessErrorCode.PREORDER_QTY_EXCEEDED, "找不到對應的預購單品項")
        item = self.db.scalar(
            select(PreOrderItem)
            .where(
                PreOrderItem.id == raw.pre_order_item_id,
                PreOrderItem.pre_order_id == raw.pre_order_id,
            )
            .options(selectinload(PreOrderItem.pre_order).selectinload(PreOrder.items))
            .with_for_update()
        )
        if item is None or item.pre_order.status == "cancelled":
            _raise(409, BusinessErrorCode.PREORDER_QTY_EXCEEDED, "找不到對應的預購單品項")
        if item.product_id != raw.product_id:
            _raise(409, BusinessErrorCode.PREORDER_QTY_EXCEEDED, "預購品項與結帳商品不符")
        already = reserved_preorder.get(item.id, 0)
        available = item.qty_arrived - item.qty_delivered
        if raw.quantity + already > available:
            _raise(
                409,
                BusinessErrorCode.PREORDER_QTY_EXCEEDED,
                f"超過可取數量上限：{item.product_name}",
            )
        reserved_preorder[item.id] = already + raw.quantity
        return item

    def _lock_original_item(
        self,
        raw: CreateOrderItem,
        customer_id: Optional[str],
        reserved_return: dict[str, int],
    ) -> Optional[CheckoutOrderItem]:
        if raw.quantity >= 0:
            return None
        if not raw.original_order_id or not raw.original_order_item_id:
            _raise(409, BusinessErrorCode.RETURN_QTY_EXCEEDED, "退貨必須指定原始銷售品項")
        original = self.db.scalar(
            select(CheckoutOrderItem)
            .where(CheckoutOrderItem.id == raw.original_order_item_id)
            .options(selectinload(CheckoutOrderItem.order))
            .with_for_update()
        )
        if original is None or original.order_id != raw.original_order_id:
            _raise(404, BusinessErrorCode.ORDER_NOT_FOUND, "找不到原始銷售單據")
        if original.quantity <= 0 or original.product_id != raw.product_id:
            _raise(409, BusinessErrorCode.RETURN_QTY_EXCEEDED, "退貨商品與原單品項不符")
        already = reserved_return.get(original.id, 0)
        remaining = original.quantity - original.returned_quantity
        if abs(raw.quantity) + already > remaining:
            _raise(
                409,
                BusinessErrorCode.RETURN_QTY_EXCEEDED,
                f"退貨數量超過原單剩餘可退上限 ({remaining} 件)",
            )
        reserved_return[original.id] = already + abs(raw.quantity)
        original_customer = original.order.customer_id
        if customer_id and original_customer and original_customer != customer_id:
            _raise(
                409,
                BusinessErrorCode.INVALID_RETURN_CUSTOMER,
                "原單屬於其他會員，不可在當前會員的交易中退貨",
            )
        return original

    def _apply_writes(
        self,
        data: CreateOrderRequest,
        customer: Optional[Customer],
        drafts: Sequence[_DraftLine],
        idempotency_key: Optional[str],
        body_hash: str,
        cashier_id: str,
        cashier_name: str,
        invoice_number: str,
    ) -> None:
        items_subtotal = sum(line.subtotal for line in drafts)
        discount_amount = sum(
            (line.original_price - line.unit_price) * line.quantity for line in drafts
        )
        points_discount = sum(line.points_amount for line in drafts)
        total_amount = sale_total(items_subtotal, data.shipping_fee, points_discount)
        prepared_payments = self._prepare_payments(data.payments, total_amount)

        now = datetime.now(timezone.utc)
        business_date = datetime.now(TAIPEI).date()
        order_id = _new_id("ord")
        self._last_order_id = order_id
        branch_id = data.branch_id.value
        order = CheckoutOrder(
            id=order_id,
            order_number=self._next_order_number(business_date),
            idempotency_key=idempotency_key,
            idempotency_body_hash=body_hash if idempotency_key else None,
            branch_id=branch_id,
            branch_name=BRANCH_NAMES[branch_id],
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            status=OrderStatus.COMPLETED.value,
            customer_id=customer.id if customer is not None else None,
            customer_name=customer.name if customer is not None else None,
            customer_phone=customer.phone if customer is not None else None,
            items_subtotal=items_subtotal,
            discount_amount=discount_amount,
            shipping_fee=data.shipping_fee,
            total_amount=total_amount,
            invoice_number=invoice_number,
            invoice_type=data.invoice.type.value,
            carrier_code=data.invoice.carrier_code,
            tax_id=data.invoice.tax_id,
            buyer_title=data.invoice.buyer_title,
            note=data.note or None,
            business_date=business_date,
            created_at=now,
            updated_at=now,
        )
        self.db.add(order)

        touched_orders: dict[str, CheckoutOrder] = {}
        touched_preorders: dict[str, PreOrder] = {}
        for index, line in enumerate(drafts, start=1):
            self._move_stock(line)
            if line.pre_order_item is not None:
                line.pre_order_item.qty_delivered += line.quantity
                touched_preorders[line.pre_order_item.pre_order_id] = line.pre_order_item.pre_order
            if line.original_item is not None:
                line.original_item.returned_quantity += abs(line.quantity)
                touched_orders[line.original_item.order_id] = line.original_item.order
            self.db.add(
                CheckoutOrderItem(
                    id=_new_id("oli"),
                    order_id=order_id,
                    line_no=index,
                    product_id=line.product.id,
                    sku=line.sku,
                    name=line.name,
                    scale=line.scale,
                    brand=line.brand,
                    original_price=line.original_price,
                    unit_price=line.unit_price,
                    cost_price=line.cost_price,
                    is_manual_price=line.is_manual_price,
                    price_diff_reason=line.price_diff_reason,
                    quantity=line.quantity,
                    subtotal=line.subtotal,
                    points_discount_applied=line.points_applied,
                    points_discount_amount=line.points_amount,
                    returned_quantity=0,
                    pre_order_id=line.pre_order_item.pre_order_id if line.pre_order_item else None,
                    pre_order_item_id=line.pre_order_item.id if line.pre_order_item else None,
                    original_order_id=line.original_item.order_id if line.original_item else None,
                    original_order_item_id=line.original_item.id if line.original_item else None,
                    restock=False if line.quantity < 0 and line.restock is False else (
                        True if line.quantity < 0 else None
                    ),
                    return_reason=line.return_reason,
                )
            )
        for index, payment in enumerate(prepared_payments, start=1):
            self.db.add(
                CheckoutPayment(
                    id=_new_id("pay"),
                    order_id=order_id,
                    line_no=index,
                    type=payment.type.value,
                    name=payment.name,
                    amount=payment.amount,
                    tendered_cash=payment.tendered_cash,
                    change_amount=payment.change_amount,
                    transaction_ref=payment.transaction_ref,
                )
            )
        for pre_order in touched_preorders.values():
            pre_order.status = derive_preorder_status(pre_order.items)
            pre_order.updated_at = now
        for original in touched_orders.values():
            positive = list(
                self.db.scalars(
                    select(CheckoutOrderItem).where(
                        CheckoutOrderItem.order_id == original.id,
                        CheckoutOrderItem.quantity > 0,
                    )
                ).all()
            )
            if positive and all(item.returned_quantity >= item.quantity for item in positive):
                original.status = OrderStatus.REFUNDED.value
            elif any(item.returned_quantity > 0 for item in positive):
                original.status = OrderStatus.PARTIALLY_REFUNDED.value
            original.updated_at = now
        if customer is not None:
            customer.total_spent = max(0, customer.total_spent + total_amount)
            customer.updated_at = now
        self.db.commit()

    def _move_stock(self, line: _DraftLine) -> None:
        if line.quantity > 0:
            delta = -line.quantity
        elif line.restock is False:
            return
        else:
            delta = abs(line.quantity)
        stock = self._lock_store_stock(line.product.id)
        if stock is None:
            if delta < 0:
                _raise(409, BusinessErrorCode.INSUFFICIENT_STORE_STOCK, "門市現貨不足，請先從倉庫調撥")
            return
        stock.quantity += delta

    def _prepare_payments(
        self, payments: Sequence[PaymentTender], total_amount: int
    ) -> List[PaymentTender]:
        prepared: List[PaymentTender] = []
        paid = 0
        for payment in payments:
            change = payment.change_amount
            if payment.type == PaymentMethodType.CASH and payment.tendered_cash is not None:
                if payment.amount >= 0 and payment.tendered_cash < payment.amount:
                    _raise(422, BusinessErrorCode.INVALID_PAYMENT, "現金實收不足")
                change = payment.tendered_cash - payment.amount
            prepared.append(payment.model_copy(update={"change_amount": change}))
            paid += payment.amount
        if total_amount >= 0 and paid < total_amount:
            _raise(409, BusinessErrorCode.PAYMENT_INSUFFICIENT, "支付總額不足")
        if total_amount < 0 and paid != total_amount:
            _raise(409, BusinessErrorCode.PAYMENT_INSUFFICIENT, "退款金額須等於應退總額")
        return prepared

    def _next_order_number(self, business_date) -> str:
        prefix = f"SO-{business_date.strftime('%Y%m%d')}-"
        existing = self.db.scalars(
            select(CheckoutOrder.order_number).where(
                CheckoutOrder.order_number.like(f"{prefix}%")
            )
        ).all()
        seq = 0
        for number in existing:
            suffix = number.rsplit("-", 1)[-1]
            if suffix.isdigit():
                seq = max(seq, int(suffix))
        return f"{prefix}{seq + 1:04d}"
