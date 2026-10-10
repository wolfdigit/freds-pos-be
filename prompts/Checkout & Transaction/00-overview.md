# Transactions — Overview

Planning doc for the **checkout / transaction** phase of Fred's POS backend. The backend checkout API is implemented in this pass. The frontend adapter is still a later checklist.

A transaction is one completed checkout: the lines on the counter, the prices the cashier actually charged, who bought, who rang it up, when, and at which branch. The open ticket itself stays in the frontend cart until submit.

## Goals

- Let the counter find a product by barcode, SKU, or name through the existing catalog search, `GET /products`. The dropdown is a frontend view of that list.
- Let the cashier change the open ticket (quantity, sold price, buyer, note, shipping, payments) on the client, then submit one payload.
- Persist an immutable sale record that snapshots product, price, buyer, cashier, datetime, and branch, and apply stock and member spending in the same database transaction.

## Three functions

| Function | Where it lives | What it does |
|----------|----------------|--------------|
| **Product search (autocomplete)** | `GET /products` | The catalog search. The counter dropdown shows those rows. This phase does not add a second search API. |
| **POS modifying** | Frontend cart (`cartStore`) until submit | Add, remove, change quantity, switch SKU, manual price, bind or clear the buyer, the NT$360 points discount, shipping, note, payments. The server does not store a draft ticket. |
| **Information recording** | `POST /checkout/orders` | Writes the sale, its lines, and its tenders. Copies snapshots. Deducts or restocks `store` inventory. Updates `customer.total_spent` when a member is bound. |

History lookup (`GET /checkout/orders`, `GET /checkout/orders/{orderId}`) is part of recording: reprints, return lookup, and the member history tab read the same rows.

## Scope

### In scope (this phase)

| Method | Path | Maps to |
|--------|------|---------|
| `GET` | `/products` | Already the catalog. The counter uses it for autocomplete. Rules stay in the product docs. |
| `POST` | `/checkout/orders` | `ICheckoutService.createCheckoutOrder` |
| `GET` | `/checkout/orders` | `ICheckoutService.getOrderHistory` |
| `GET` | `/checkout/orders/{orderId}` | `ICheckoutService.getOrderById` |

Recording responsibilities:

- One database transaction for the order, its lines, its tenders, `store` stock movement, member `total_spent`, and return counters on the original lines.
- Server-assigned `id`, `orderNumber`, `createdAt`, line ids, and totals. `orderNumber` is `SO-YYYYMMDD-HHMMSS-####` in `Asia/Taipei`. The `####` sequence is the max suffix already stored for that exact second, plus 1. The second in the prefix is the concurrency control. There is no retry when two sales share a second.
- Snapshots copied by the server, never trusted from the client for identity fields: product sku / name / scale / brand, list price as `originalPrice`, buyer name and phone, cashier id and name (from the current user, not the body), branch id and name.
- Sold `unitPrice` comes from the client when `isManualPrice` is true, and when `pointsDiscountApplied` is true (the frontend already subtracted NT$360). Otherwise the server sets it from the current `listPrice`. The server does not subtract 360 again.
- A bound member may redeem points for **NT$360 off a product**, at most once for that product on the sale. Each redeemed line stores `pointsDiscountApplied`. Buying several different products can redeem several times. Quantity does not multiply the discount: two units of one product are still one exchange. The frontend reduces that line's `unitPrice` by 360 before submit. If that reduction would make the line `subtotal` negative, the line `subtotal` is **0**. `totalAmount` does not apply a second points floor. The system does not store or check a points balance. The cashier confirms the points in the real world, then sets the flag.
- Positive quantity deducts `store` stock. When the shelf quantity is short, the counter shows a warning popup and the cashier decides whether to complete the sale. The server does not block the sale.
- Negative quantity is a return. It must point at the earlier sale line whose units are being returned, must not exceed the remaining returnable quantity, and restocks `store` when `restock` is true. The refund uses that line's `unitPrice` only (already reduced by 360 when the original sale redeemed points). It does not subtract 360 again. The original line keeps `pointsDiscountApplied` and `pointsDiscountAmount`.
- `X-Idempotency-Key` so a double submit returns the original order JSON. A lookup before insert is not enough. If the insert hits the unique constraint on `idempotency_key`, catch it, re-select the stored order, and replay that JSON when the cashier and body match.

### Out of scope

- Changing `GET /products`. The counter calls it as it exists. Catalog CRUD stays in the product phase.
- Customer profile CRUD. Binding a buyer uses `GET /customers?keyword=`.
- Branch administration. This phase only knows two branches: the physical counter and the online store. Auth stays optional/dummy (`src/api/deps.py`). There is still no staff table. The cashier snapshot is the current user from that dependency. Until login exists, every request is the demo cashier `staff-001` / `店長 Fred`.
- A points balance. No `reward_points` column, no earn rule, and no check that the member has enough points.
- Draft / parked tickets on the server. Refresh keeps the cart in frontend storage only.
- Editing a completed order (price, buyer, lines, payments). Later returns append a new order and only then change `returnedQuantity` and `status` on the original.
- VIP auto-pricing. A bound member does not change the price. `vipPrice` and tier discounts stay for a later pass.
- Preorders. This phase does not record, pick up, or author preorders.
- Invoices. There is no invoice number, invoice type, carrier, tax id, or buyer title on the request, the order, history search, or the receipt.
- A server-rendered receipt. `POST /checkout/orders` returns the order fields as JSON. The frontend composes the slip.
- Seeding historical orders.

## Layered architecture

```
HTTP (api/v1/endpoints/checkout.py)
  → CheckoutService (services/checkout_service.py)
    → ORM models (models/checkout.py)
      → DB: checkout_order | checkout_order_item | checkout_payment
    → ProductService / product_stock   (read + store quantity)
    → customer.total_spent             (member spending only)
```

| Layer | Role |
|-------|------|
| **API / endpoints** | Routes, query and body parsing, idempotency header, status codes. |
| **Schemas** | CamelCase DTOs aligned with FE `CheckoutOrder` and `CreateOrderPayload`. |
| **Services** | Price resolution, total math, stock updates, return checks, snapshots, one commit. |
| **Models + Alembic** | The three checkout tables. No change to `customer` columns except `total_spent`. No points column. |

### Backend file map

| Piece | Path |
|-------|------|
| Schemas | `src/schemas/checkout.py` |
| Models | `src/models/checkout.py` |
| Service | `src/services/checkout_service.py` |
| Endpoints | `src/api/v1/endpoints/checkout.py` |
| Router wire-up | `src/api/v1/api.py` |
| Migration | Alembic revision under `alembic/versions/` |

Base URL: `/api/v1` (see [`../openapi.yaml`](../openapi.yaml) servers).

### What is snapshotted

| Fact | Source at commit | Stored on |
|------|------------------|-----------|
| Product identity and display | `product` row | `checkout_order_item` |
| List price (`originalPrice`) | `product.list_price` | line |
| Sold price (`unitPrice`) | Request price when `isManualPrice` or `pointsDiscountApplied` is true, otherwise current list price | line |
| Buyer | `customer` row, or empty for a walk-in | order `customer_id` + name/phone snapshots |
| Cashier | Current user (`id`, `name`). Demo user today: `staff-001` / `店長 Fred` | order |
| Branch | One of the two known branches. Counter default `branch-store` / `台北旗艦店`. Online store `branch-online` / `官網`. | order |
| When | Server clock, UTC `createdAt`; business date in `Asia/Taipei` | order |

`customer_id` is nullable and **`ON DELETE SET NULL`**. Name and phone snapshots stay, matching the customer decision log. A catalog product is not removed. `PUT /products/{productId}` sets `product.deleted`: `true` hides it, `false` shows it again. `checkout_order_item.product_id` stays set and is **`ON DELETE RESTRICT`**, so a return always compares the request `productId` with the original sale line's `product_id`. Stock locations stay the catalog four (`store`, `warehouse`, `company`, `other`). Both branches sell from that same `store` shelf. The branch on the order says where the sale happened. It does not pick a different stock row.

## Frontend alignment

- Cart and ticket edits: `freds-pos-fe/src/store/cartStore.ts`
- Submit: `freds-pos-fe/src/features/checkout/hooks/useCheckoutWorkflow.ts`
- Counter search box: `freds-pos-fe/src/features/checkout/components/ProductSearchBar.tsx`, `useProductSearch.ts`, `CheckoutPage.tsx` — already calls `GET /products`
- Buyer autocomplete (already on customers): `CustomerBindCard.tsx` → `GET /customers`
- Types: `freds-pos-fe/src/types/checkout.ts`
- Service: `freds-pos-fe/src/services/interfaces/ICheckoutService.ts`
- Header display until login exists: `freds-pos-fe/src/store/sessionStore.ts` (`storeName`, `cashierId`, `cashierName`). That store is not the source of the recorded cashier. `POST /checkout/orders` copies `cashierId` and `cashierName` from the current user.
- Flows this contract follows: `freds-pos-fe/prompts/04-business-flows-and-state-machines.md` (stock warning, returns, manual price, multi-tender)
- Product keyword rules: [`../products/03-search-rules.md`](../products/03-search-rules.md)
- Member spending owner: [`../customers/00-overview.md`](../customers/00-overview.md) — checkout writes `totalSpent`; it does not write points onto `customer`

### Contract principles

1. The open ticket is client state. `POST /checkout/orders` is the only write that records a sale.
2. The server recomputes `subtotal`, `itemsSubtotal`, `discountAmount`, and `totalAmount`. A mismatched client total is not stored.
3. Completed commercial fields are immutable. Returns are new orders with negative quantities.
4. Counter product search is `GET /products`. Keyword rules stay in the product search doc. The screen can wait for typed text before calling it; the API itself is unchanged.
5. Integer TWD only. No fractional currency.
6. The NT$360 points reduction is already in the line `unitPrice` from the frontend. If that reduction would make a line `subtotal` negative, that line `subtotal` is **0**. `totalAmount` is the sum of line subtotals plus shipping. It does not floor the points discount again. A return line keeps a negative `subtotal` so the refund still reduces the total. A ticket may contain sale lines and return lines together.
7. Walk-in sales omit `customerId`. Snapshots are null. `total_spent` is unchanged.
8. The receipt is the order JSON. The server does not send HTML.

## Doc map

| File | Purpose |
|------|---------|
| `00-overview.md` | This file |
| `01-api-contract.md` | Endpoints, bodies, errors |
| `02-data-model.md` | Tables, snapshots, stock and spending writes |
| `03-search-rules.md` | Autocomplete ranking and order history filters |
| `04-open-questions.md` | Decision log |
| `05-fe-changes.md` | Later FE checklist |
| [`../openapi.yaml`](../openapi.yaml) | Merged HTTP contract, including the checkout tag |
