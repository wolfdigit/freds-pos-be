# Transactions — API Contract

HTTP contract for counter autocomplete and recorded sales. Shapes follow `freds-pos-fe/src/types/checkout.ts` and `ICheckoutService`. Where this contract is narrower than the mock, the frontend adapts later ([`05-fe-changes.md`](./05-fe-changes.md)).

Base path: `/api/v1`.

Money fields are integers (TWD). Timestamps are ISO 8601 UTC.

## Shared: `CheckoutOrder`

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server `ord-{uuid4}` without dashes |
| `orderNumber` | string | Server `SO-YYYYMMDD-####`, business date `Asia/Taipei`, unique |
| `branchId` | `branch-store` \| `branch-online` | Physical counter, or the online store |
| `branchName` | string | `台北旗艦店` or `官網`. Server sets this from `branchId`. |
| `cashierId` | string | Snapshot of the current user `id`. Not sent by the client. |
| `cashierName` | string | Snapshot of the current user `name`. Not sent by the client. |
| `status` | `completed` \| `partially_refunded` \| `refunded` | New sale starts `completed`. Later return orders move this. |
| `customerId` | string \| null | Bound member, or null for a walk-in. Null after the member row is deleted. |
| `customerName` | string \| null | Snapshot. Stays after member delete. |
| `customerPhone` | string \| null | Snapshot. Null when the member has no phone. |
| `items` | `CheckoutOrderItem[]` | At least one |
| `itemsSubtotal` | integer | Sum of line `subtotal` |
| `discountAmount` | integer | Sum of `(originalPrice - unitPrice) * quantity` across lines. May be negative on a return. This is the manual/list gap only. It does not include points discounts. |
| `pointsDiscountAmount` | integer | Sum of line `pointsDiscountAmount`. Server-owned. |
| `shippingFee` | integer | ≥ 0. Copied from the request. |
| `totalAmount` | integer | Merchandise + shipping − points discounts. Floors at 0 only when that gross amount is ≥ 0. A refund total stays negative. |
| `payments` | `PaymentTender[]` | At least one |
| `invoice` | `InvoiceInfo` | Includes `invoiceNumber`. A sale stores the number the client sent. A refund stores the original sale's number. No gateway call. |
| `note` | string | Optional. Omit or `""`. |
| `createdAt` | string | Server time. The sale datetime. |
| `updatedAt` | string | Set on insert. Bumped only when a later return changes `status` or line `returnedQuantity`. |

**Not on the response:** `costPrice`. It is stored on the line for later margin reports and is not part of the cashier contract.

### `CheckoutOrderItem`

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server `oli-{uuid4}` without dashes. Return payloads send this as `originalOrderItemId`. |
| `productId` | string | Catalog id. Required. |
| `sku` | string | Snapshot |
| `name` | string | Snapshot |
| `scale` | `ModelScale` | Snapshot |
| `brand` | string | Snapshot |
| `originalPrice` | integer | `product.list_price` at commit. Not the client's number. |
| `unitPrice` | integer | Price actually charged. ≥ 0. |
| `isManualPrice` | boolean | |
| `priceDiffReason` | string | Optional. Present when the cashier entered a reason. |
| `quantity` | integer | Not zero. Positive sale, negative return. |
| `subtotal` | integer | `unitPrice * quantity` before the points discount |
| `pointsDiscountApplied` | boolean | True when this product used one points exchange. Always false on a return line. |
| `pointsDiscountAmount` | integer | **360** when applied, otherwise **0**. Server-owned. A return line is **0**. |
| `returnedQuantity` | integer | Units already returned against this line. `0` on create. |
| `preOrderId` | string | Optional pickup link |
| `preOrderItemId` | string | Optional pickup link |
| `originalOrderId` | string | Required when `quantity < 0` |
| `originalOrderItemId` | string | Required when `quantity < 0` |
| `restock` | boolean | Return only. Default `true`. |
| `returnReason` | string | Optional |

### `PaymentTender`

Matches the current frontend union:

`cash` | `bank_transfer_ctbc` | `bank_transfer_ubot` | `credit_card_physical` | `credit_card_online` | `line_pay` | `cod`

| Field | Type | Notes |
|-------|------|--------|
| `type` | `PaymentMethodType` | `cod` is rejected in this phase (`422`). |
| `name` | string | Display label the client sent |
| `amount` | integer | This tender's applied amount. Negative on a refund tender. |
| `tenderedCash` | integer | Cash only. Bills received. |
| `changeAmount` | integer | Cash only. Server sets `tenderedCash - amount` when `tenderedCash` is sent. Must be ≥ 0. |
| `transactionRef` | string | Optional. Card last digits or transfer reference. |

### `InvoiceInfo`

| Field | Type | Notes |
|-------|------|--------|
| `invoiceNumber` | string | Required. Non-empty after trim. On a sale, the client sends it and it is unique among sales. On a refund, it must be the original sale's number, and that number is stored again. This phase does not call an e-invoice gateway. |
| `type` | `none` \| `carrier` \| `tax_id` \| `paper` | |
| `carrierCode` | string | When `type` is `carrier` |
| `taxId` | string | When `type` is `tax_id`. 8 digits. |
| `buyerTitle` | string | Optional title for a tax id |

---

Product search on the counter is the existing `GET /products`. See [`03-search-rules.md`](./03-search-rules.md). This folder does not add a suggestion route.

## `POST /checkout/orders`

**Maps to:** `ICheckoutService.createCheckoutOrder`.

**Header:** `Idempotency-Key` optional. When present, a repeat with the same key, the same current user, and the same body returns the original `201` body and does not write again. A reuse with a different body or a different user → `409` `IDEMPOTENCY_CONFLICT`.

### Request — `CreateOrderPayload`

| Field | Type | Notes |
|-------|------|--------|
| `customerId` | string | Optional. Omit for a walk-in. Unknown id → `404` `CUSTOMER_NOT_FOUND`. |
| `branchId` | `branch-store` \| `branch-online` | Optional. Omit → `branch-store`. Unknown value → `422`. |
| `items` | array | At least one |
| `shippingFee` | integer ≥ 0 | Required. `0` is valid. |
| `payments` | array | At least one |
| `invoice` | `InvoiceInfo` | Required |
| `note` | string | Optional |

**Item request fields:** `productId`, `quantity`, `unitPrice`, `isManualPrice`, `priceDiffReason`, `pointsDiscountApplied`, `preOrderId`, `preOrderItemId`, `originalOrderId`, `originalOrderItemId`, `restock`, `returnReason`.

`pointsDiscountApplied` defaults to false. The client does not send line `pointsDiscountAmount`.

The client does not send `id`, `orderNumber`, `createdAt`, `status`, totals, snapshots, `cashierId`, `cashierName`, `branchName`, `pointsDiscountAmount`, or `originalPrice`. Do not send `usedPoints` or `earnedPoints`. The server copies `cashierId` and `cashierName` from the current user (`src/api/deps.py`). Until staff login exists, that user is `staff-001` / `店長 Fred`. A body that still includes cashier fields is ignored.

### Price the server stores

| Line kind | `unitPrice` |
|-----------|-------------|
| `isManualPrice: true` | Request `unitPrice`, required, integer ≥ 0 |
| Otherwise | Current `product.list_price`. Client price is ignored. A preorder pickup follows this same rule. |

`originalPrice` is always `list_price`, including preorder and manual lines, so the discount column can compare list versus charged.

### Validation before any write

All checks run inside the database transaction. Any failure rolls back.

1. Every `productId` exists. Missing → `404` `PRODUCT_NOT_FOUND`.
2. Positive lines that are not preorder pickups: locked `store` quantity ≥ `quantity`. Short → `409` `INSUFFICIENT_STORE_STOCK`.
3. Preorder pickup: both ids present, line exists, `1 ≤ quantity ≤ qtyArrived - qtyDelivered`. Else `409` `PREORDER_QTY_EXCEEDED`.
4. Negative lines: both original ids present, original line exists, `abs(quantity) ≤ quantity - returnedQuantity` on that line. Else `409` `RETURN_QTY_EXCEEDED`. Original sale missing → `404` `ORDER_NOT_FOUND`.
5. Return customer: if both the new order and the original order have a `customerId`, they must be equal. A walk-in original may be returned onto a member. A member original may not be returned onto a different member. Else `409` `INVALID_RETURN_CUSTOMER`.
6. `branchId`, when sent, is `branch-store` or `branch-online`. Anything else → `422`.
7. A line with `pointsDiscountApplied: true` must have `quantity > 0` and a `customerId` on the order. Otherwise `422`. At most one such line per `productId` on the order. A second line for the same product with the flag set → `422`. The flag does not change `unitPrice`. The server does not read a points balance. A return line (`quantity < 0`) is stored with `pointsDiscountApplied: false` and `pointsDiscountAmount: 0` even if the original line was discounted. The refund amount is `unitPrice × quantity` only.
8. Payments: when `totalAmount ≥ 0`, the sum of `amount` must be ≥ `totalAmount`. Else `409` `PAYMENT_INSUFFICIENT`. When `totalAmount < 0`, the sum must equal `totalAmount`.
9. `cod` tender → `422`.
10. Cash with `tenderedCash` set and `tenderedCash < amount` → `422`.
11. A ticket is either a sale or a refund. One order cannot contain both a positive line and a negative line. That mix → `422`.
12. `invoice.invoiceNumber` is required and non-empty after trim. Blank → `422`. A sale whose number is already stored on another sale → `409` `INVOICE_NUMBER_DUPLICATE`. A refund must send the original sale's number; a different number, or return lines from more than one invoice, → `422`. That refund stores the original number again.

### Writes on success

In one commit:

- Insert order, lines, payments.
- Positive non-preorder lines, and preorder pickup lines: subtract `quantity` from `store`.
- Negative lines with `restock` not `false`: add `abs(quantity)` to `store`.
- Recompute nothing else on the product row. `totalStock` stays a read-time sum.
- Preorder pickup: add `quantity` to `qty_delivered`, then derive status (`pending`, `partially_arrived`, `partially_completed`, `completed`) with the same rules as the frontend `derivePreOrderStatus`.
- Return: add `abs(quantity)` to the original line `returnedQuantity`. If every original line is fully returned, original `status` becomes `refunded`. If any line has `returnedQuantity > 0`, `partially_refunded`. Otherwise leave `completed`. The original line's points-discount flag and 360 amount stay as they were.
- Bound customer: `total_spent = max(0, total_spent + totalAmount)`.
- Redeemed lines keep `pointsDiscountApplied` and `pointsDiscountAmount` of 360. Nothing is written to a points balance.

### Responses

| Status | Body |
|--------|------|
| `201` | `CheckoutReceipt`: `{ order, receiptPrintHtml }` |
| `404` | `PRODUCT_NOT_FOUND`, `CUSTOMER_NOT_FOUND`, `ORDER_NOT_FOUND` |
| `409` | Stock, preorder, return, payment, an invoice number already used by another sale, or idempotency conflicts |
| `422` | Malformed body, empty items, zero quantity, unknown branch, `cod`, bad cash, blank `invoiceNumber`, or a ticket that both sells and returns |

`receiptPrintHtml` is a simple HTML slip (store name, order number, invoice number, cashier, lines, total). It is not a fiscal invoice.

---

## `GET /checkout/orders`

**Maps to:** `getOrderHistory`.

| Query | Default | Notes |
|-------|---------|--------|
| `customerId` | — | Exact. Includes orders whose member was later deleted only when the id still matches; deleted members are found by `keyword` on the name/phone snapshot. |
| `orderNumber` | — | Exact |
| `invoiceNumber` | — | Exact match on the stored invoice number, after trim. Returns the sale and every refund that reused that number. |
| `productId` | — | Order has a line with this product |
| `keyword` | — | Order number, invoice number, buyer name, or buyer phone contains |
| `productKeyword` | — | A line sku or name contains. SKU uses the catalog normalizer. |
| `startDate` | — | Inclusive `createdAt`, ISO 8601 |
| `endDate` | — | Exclusive upper bound, ISO 8601 |
| `minAmount` | — | `totalAmount ≥` |
| `maxAmount` | — | `totalAmount ≤` |
| `status` | missing or `all` | Exact status filter |
| `page` | `1` | ≥ 1 |
| `pageSize` | `20` | Max `100` |

Response `200`: `{ items, page, pageSize, total }`. Sort `createdAt DESC`, tie-break `id DESC`. Filters in SQL. Details in [`03-search-rules.md`](./03-search-rules.md).

The frontend method still accepts a bare string in the mock. HTTP accepts query params only.

## `GET /checkout/orders/{orderId}`

| Status | Body |
|--------|------|
| `200` | `CheckoutOrder` |
| `404` | `ORDER_NOT_FOUND` |

Lookup is the order `id`, not `orderNumber`. Exact number search is the list endpoint.

There is no `PUT` or `DELETE` for an order.
