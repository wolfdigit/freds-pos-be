# Transactions — Open Questions

Decisions for this planning pass. Do not reopen them without a reason. The last section lists items left for a later phase.

Today's date for this log: 2026-09-28.

Confirmed with you on 2026-09-28: the open cart is the only thing that can be modified; a completed sale stays fixed; saving a sale also updates store stock, member `totalSpent`, returns, preorder pickup, and payments; product search reuses `GET /products`; price is list price unless the cashier overrides it; the online store is a branch.

Added the same day, then corrected: the NT$360 points exchange is **per product line**, at most once for each product on the sale. Several products can each take one exchange. The amount due floors at 0. The system does not keep a points balance. The cashier checks points in the real world and sets the flag.

## Decision log

| # | Topic | Decision |
|---|--------|----------|
| 1 | Where the open ticket lives | **Client cart only.** No draft order table and no `PUT` of an in-progress sale. |
| 2 | What "POS modifying" writes | Cart actions stay local. The server sees the result once, on `POST /checkout/orders`. |
| 3 | Immutability | Prices, buyer, cashier, branch, lines, and tenders do not change after commit. Returns are new orders. |
| 4 | Product search | **Reuse `GET /products`.** No autocomplete endpoint, no separate rank, no separate limit. |
| 5 | Suggestion size | **Removed.** The catalog list is the counter list. |
| 6 | Discontinued products | Catalog search already returns them. Commit does not reject `discontinued`. |
| 7 | Charged price | Manual price only when `isManualPrice` is true. Otherwise **list price**, including a preorder pickup. Client `unitPrice` is ignored when the line is not manual. |
| 8 | VIP auto-price | **Deferred.** Current `attachCustomer` does not reprice the cart. Do not apply `vipPrice` or tier percent in this phase. |
| 9 | `originalPrice` | Always the list price at commit, so discount is list minus charged. |
| 10 | Cost | Copy `cost_price` onto the line. **Omit it from JSON** so the receipt payload does not expose cost. |
| 11 | Buyer snapshot | Copy `name` and `phone` at commit. `customer_id` nullable, **`ON DELETE SET NULL`**. Snapshots remain. Walk-in leaves all three empty. |
| 12 | Cashier | Snapshot of the current user, not a field on the create body. No staff table. Until login exists, `get_current_user_optional` is `staff-001` / `店長 Fred`. |
| 13 | Branch | Two fixed ids, no branch table. `branch-store` / `台北旗艦店` is the physical counter and the default. `branch-online` / `官網` is the online store. Server sets the name from the id. Both branches deduct the same `store` shelf. |
| 14 | Sale datetime | Server `createdAt`. `business_date` and `SO-` number use **`Asia/Taipei`**. Client clock is ignored. |
| 15 | Ids | Order `ord-…`, line `oli-…`, payment `pay-…`, uuid4 hex, no dashes. Same style as `prod-` and `cust-`. |
| 16 | Points discount | **Per product, once per sale.** Line columns `points_discount_applied` and `points_discount_amount` (360 or 0). Several products may each redeem once. Quantity does not multiply it. Requires a bound member. `totalAmount` floors at 0. **No points balance** and no points-cost check. No `usedPoints` / `earnedPoints`. Line `unitPrice` is unchanged. |
| 17 | `totalSpent` | Checkout adds `totalAmount` inside the sale transaction, floored at `0`. Catalog endpoints still cannot set it. |
| 18 | Stock | Positive lines and preorder pickups deduct **`store`** under a row lock. Short stock → `409` `INSUFFICIENT_STORE_STOCK`. Returns restock `store` unless `restock` is false. Other locations do not move. |
| 19 | Returns | Negative quantity requires `originalOrderId` and `originalOrderItemId`. Cap is `quantity - returnedQuantity`. A member sale cannot be returned onto a different member. A return refunds **`unitPrice` only**. It does not reverse the NT$360. The original line keeps its points-discount columns. |
| 20 | Preorder authoring | **No create/edit API.** This pass adds `pre_order` and `pre_order_item` so pickup can increment `qty_delivered` and derive status. |
| 21 | Payments | At least one tender. `cod` rejected. Non-negative totals require payment sum ≥ total. Negative totals require payment sum = total. |
| 22 | Idempotency | Optional `Idempotency-Key`. Same key, same current user, and same body replays the receipt. Same key with a different body or a different user → `409`. |
| 23 | History paging | `page` / `pageSize` like customers. Sort **`createdAt DESC`**. |
| 24 | Auth | Optional/dummy for this phase. |
| 25 | OpenAPI | Checkout paths and error codes are in [`../openapi.yaml`](../openapi.yaml). |
| 26 | Implementation | **Backend checkout API** in this pass: models, migration, `POST/GET /checkout/orders`, stock, `totalSpent`. Frontend wiring stays later. |
| 27 | Discount floor | Floor the sale total at 0 only when points discounts wipe out a non-negative gross. A return total stays negative. |
| 28 | Invoice number | Required and non-empty. A sale stores the client number, unique among sales. Another sale with that number → `409` `INVOICE_NUMBER_DUPLICATE`. A refund stores the original sale's number again, so the column is not unique. A different number on that refund, or lines from more than one invoice, is rejected. One ticket cannot both sell and return. No e-invoice gateway. Fixed after commit. `GET /checkout/orders?invoiceNumber=` returns the sale and its refunds. `keyword` also contains-matches it. |

## Left for later

- Staff login. Checkout already snapshots the current user. Login replaces the demo user in `src/api/deps.py`; it does not put cashier fields back on the body.
- VIP price and tier discounts when a member is bound and the line is not manually priced.
- Preorder create, arrival, and cancel APIs.
- E-invoice registration. A sale already stores the client-supplied invoice number, and a refund stores that same number, plus carrier / tax id fields. Calling the gateway is still later.
- Parking a ticket on the server across browsers.
- Editing or voiding a completed order in place.
