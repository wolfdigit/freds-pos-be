# Transactions — API Contract

HTTP contract for counter autocomplete and recorded sales. Shapes follow `freds-pos-fe/src/types/checkout.ts` and `ICheckoutService`. Where this contract is narrower than the mock, the frontend adapts later ([`05-fe-changes.md`](./05-fe-changes.md)).

Base path: `/api/v1`.

Money fields are integers (TWD). Timestamps are ISO 8601 UTC.

## Shared: `CheckoutOrder`

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server `ord-{uuid4}` without dashes |
| `orderNumber` | string | Server `SO-YYYYMMDD-HHMMSS-####`. Date and clock are `Asia/Taipei`. `####` is the max suffix already stored for that second, plus 1, from `0001`. Unique. The per-second prefix is enough. There is no retry for two sales in the same second. |
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
| `discountAmount` | integer | Sum of `(originalPrice - unitPrice) * quantity` across manual-price lines only. The NT$360 points cut is already inside `unitPrice` and is reported separately as `pointsDiscountAmount`. May be negative on a return. |
| `pointsDiscountAmount` | integer | Sum of line `pointsDiscountAmount`. Server-owned record of the exchange. Not subtracted again from `totalAmount`. |
| `shippingFee` | integer | ≥ 0. Copied from the request. |
| `totalAmount` | integer | Sum of line `subtotal` + shipping. Points are not subtracted again, and this total is not floored for points. A ticket may mix sale lines and return lines, so the total may be negative. |
| `payments` | `PaymentTender[]` | At least one |
| `note` | string | Optional. Omit or `""`. |
| `createdAt` | string | Server time. The sale datetime. |
| `updatedAt` | string | Set on insert. Bumped only when a later return changes `status` or line `returnedQuantity`. |

There is no invoice and no `costPrice` on the order or the line.

### `CheckoutOrderItem`

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server `oli-{uuid4}` without dashes. Return payloads send this as `originalOrderItemId`. |
| `productId` | string | Catalog id. Required on every line, including a return. The product row is never removed; `deleted` only hides it. |
| `sku` | string | Snapshot |
| `name` | string | Snapshot |
| `scale` | `ModelScale` | Snapshot |
| `brand` | string | Snapshot |
| `originalPrice` | integer | `product.list_price` at commit. Not the client's number. |
| `unitPrice` | integer | Price actually charged. When `pointsDiscountApplied` is true, this is the frontend price already reduced by 360. The server stores it unchanged. |
| `isManualPrice` | boolean | |
| `priceDiffReason` | string | Optional. Present when the cashier entered a reason. |
| `quantity` | integer | Not zero. Positive sale. Negative when this line returns product from an earlier sale line. |
| `subtotal` | integer | `unitPrice * quantity`. If a points reduction would make this negative, **0**. A return line stays negative. |
| `pointsDiscountApplied` | boolean | True when this product used one points exchange. Always false on a return line. |
| `pointsDiscountAmount` | integer | **360** when applied, otherwise **0**. A record of the exchange, not a second deduction. A return line is **0**. |
| `returnedQuantity` | integer | Units of this sale line already returned. `0` on create. |
| `originalOrderId` | string | When `quantity < 0`, the earlier checkout order this line is returning product from. Required on a return line. |
| `originalOrderItemId` | string | When `quantity < 0`, the earlier sale line whose units are being returned. Required on a return line. |
| `restock` | boolean | Return only. Default `true`. |
| `returnReason` | string | Optional |

### `PaymentTender`

Same fields as the frontend tender:

`cash` | `credit_card` | `line_pay` | `bank_transfer` | `cod`

| Field | Type | Notes |
|-------|------|--------|
| `type` | `PaymentMethodType` | `cod` is rejected in this phase (`422`). |
| `name` | string | Required. Display name, such as `現金`. |
| `amount` | integer | This tender's applied amount. Negative on a refund tender. |
| `tenderedCash` | integer | Optional. Cash notes received. |
| `changeAmount` | integer | Optional. |
| `transactionRef` | string | Optional. Card last-4 or transfer last-5. |

The server stores these fields and returns them on the order. There is no invoice on the request or the response. Checkout does not accept `preOrderId` or `preOrderItemId`.

---

Product search on the counter is the existing `GET /products`. See [`03-search-rules.md`](./03-search-rules.md). This folder does not add a suggestion route.

## `POST /checkout/orders`

**Maps to:** `ICheckoutService.createCheckoutOrder`.

**Header:** `X-Idempotency-Key` optional. When present, a repeat with the same key, the same current user, and the same body returns the original `201` body and does not write again. A reuse with a different body or a different user → `409` `IDEMPOTENCY_CONFLICT`.

Do not rely on a lookup before insert. Two requests can both miss that lookup and both insert. The `idempotency_key` unique constraint is the lock. On that unique conflict, catch it, re-select the stored order, and apply the same replay rules: matching cashier and body returns that order JSON; a mismatch is `409` `IDEMPOTENCY_CONFLICT`.

### Request — `CreateOrderPayload`

| Field | Type | Notes |
|-------|------|--------|
| `customerId` | string | Optional. Omit for a walk-in. Unknown id → `404` `CUSTOMER_NOT_FOUND`. |
| `branchId` | `branch-store` \| `branch-online` | Optional. Omit → `branch-store`. Unknown value → `422`. |
| `items` | array | At least one. Sale lines and return lines may appear on the same ticket. |
| `shippingFee` | integer ≥ 0 | Required. `0` is valid. |
| `payments` | array | At least one |
| `note` | string | Optional |

**Item request fields:** `productId`, `quantity`, `unitPrice`, `isManualPrice`, `priceDiffReason`, `pointsDiscountApplied`, `originalOrderId`, `originalOrderItemId`, `restock`, `returnReason`. Do not send `preOrderId` or `preOrderItemId`.

**Payment request fields:** `type`, `name`, `amount`, and optionally `tenderedCash`, `changeAmount`, `transactionRef`.

`pointsDiscountApplied` defaults to false. The client does not send line `pointsDiscountAmount`.

The client does not send `id`, `orderNumber`, `createdAt`, `status`, totals, snapshots, `cashierId`, `cashierName`, `branchName`, `pointsDiscountAmount`, or `originalPrice`. Do not send `usedPoints` or `earnedPoints`. The server copies `cashierId` and `cashierName` from the current user (`src/api/deps.py`). Until staff login exists, that user is `staff-001` / `店長 Fred`. A body that still includes cashier fields is ignored.

### Price the server stores

| Line kind | `unitPrice` |
|-----------|-------------|
| `pointsDiscountApplied: true` | Request `unitPrice`. The frontend already subtracted 360. The server stores it and does not subtract 360 again. |
| `isManualPrice: true` | Request `unitPrice`, required, integer ≥ 0 |
| Otherwise | Current `product.list_price`. Client price is ignored. |

`originalPrice` is always `list_price`, including manual lines and points lines, so the discount column can compare list versus charged.

### Validation before any write

All checks run inside the database transaction. Any failure rolls back.

1. Every `productId` exists. Missing → `404` `PRODUCT_NOT_FOUND`. A positive line also requires `product.deleted` false. A return line may name a soft-deleted product, because the row is still there.
2. Positive lines deduct `store` stock even when the shelf quantity is short. Short stock is not an error. The counter shows a warning popup; the cashier decides. The server commits.
3. Negative lines return product from an earlier sale: both original ids present, that sale line exists, `abs(quantity) ≤ quantity - returnedQuantity` on that line. Else `409` `RETURN_QTY_EXCEEDED`. The earlier sale is missing → `404` `ORDER_NOT_FOUND`. The return `productId` must equal that sale line's `product_id`. This comparison always runs. It is not skipped when the product was hidden, because `product_id` is never cleared.
4. Return customer: if both the new order and the earlier sale have a `customerId`, they must be equal. A walk-in sale may be returned onto a member. A member sale may not be returned onto a different member. Else `409` `INVALID_RETURN_CUSTOMER`.
5. `branchId`, when sent, is `branch-store` or `branch-online`. Anything else → `422`.
6. A line with `pointsDiscountApplied: true` must have `quantity > 0` and a `customerId` on the order. Otherwise `422`. At most one such line per `productId` on the order. A second line for the same product with the flag set → `422`. The frontend already reduced `unitPrice` by 360. The server does not change `unitPrice` again and does not read a points balance. A return line (`quantity < 0`) is stored with `pointsDiscountApplied: false` and `pointsDiscountAmount: 0` even if the original line was discounted. The refund amount is that line's `unitPrice × quantity` only.
7. Payments: when `totalAmount ≥ 0`, the sum of `amount` must be ≥ `totalAmount`. Else `409` `PAYMENT_INSUFFICIENT`. When `totalAmount < 0`, the sum must equal `totalAmount`.
8. `cod` tender → `422`.
9. A checkout ticket can contain both sale lines (`quantity > 0`) and return lines (`quantity < 0`). That mix is valid.

### Writes on success

In one commit:

- Insert order, lines, payments.
- Positive lines: subtract `quantity` from `store`, even when that drives the shelf quantity below zero.
- Negative lines with `restock` not `false`: add `abs(quantity)` to `store` for the units being returned.
- Recompute nothing else on the product row. `totalStock` stays a read-time sum.
- Return: add `abs(quantity)` to the earlier sale line `returnedQuantity`. If every line on that earlier order is fully returned, its `status` becomes `refunded`. If any line has `returnedQuantity > 0`, `partially_refunded`. Otherwise leave `completed`. The earlier line's points-discount flag and 360 amount stay as they were.
- Bound customer: `total_spent = max(0, total_spent + totalAmount)`.
- Redeemed lines keep `pointsDiscountApplied` and `pointsDiscountAmount` of 360. Nothing is written to a points balance.

### Responses

| Status | Body |
|--------|------|
| `201` | `CheckoutReceipt`: `{ order }`. `order` is `CheckoutOrder`. |
| `404` | `PRODUCT_NOT_FOUND`, `CUSTOMER_NOT_FOUND`, `ORDER_NOT_FOUND` |
| `409` | Return quantity, return customer, payment, or idempotency conflicts |
| `422` | Malformed body, empty items, zero quantity, unknown branch, or `cod` |

The server does not return HTML. The client builds the slip from `order.branchName`, `order.orderNumber`, `order.cashierName`, `order.createdAt`, each item's `name`, `quantity`, `unitPrice`, and `subtotal`, `order.shippingFee`, `order.payments`, and `order.totalAmount`. There is no invoice on the slip.

---

## `GET /checkout/orders`

**Maps to:** `getOrderHistory`.

| Query | Default | Notes |
|-------|---------|--------|
| `customerId` | — | Exact. Includes orders whose member was later deleted only when the id still matches; deleted members are found by `keyword` on the name/phone snapshot. |
| `orderNumber` | — | Exact |
| `productId` | — | Order has a line with this product |
| `keyword` | — | Order number, buyer name, or buyer phone contains |
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
