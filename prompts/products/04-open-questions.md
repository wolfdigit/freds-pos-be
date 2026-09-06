# Products Catalog — Open Questions

Decisions from the planning discussion are recorded below. Items marked **Decided** should not be reopened without cause.

---

## Decision log

| # | Topic | Decision | Date |
|---|-------|----------|------|
| 1 | Duplicate SKU error | **A** — `409` + `{ code: PRODUCT_SKU_DUPLICATE, message: … }` (e.g. `貨號已存在`) | 2026-09-07 |
| 2 | PUT stock / computed fields | **Tighten OpenAPI** — `UpdateProductRequest` metadata-only; those fields are **not** in the contract (not “silent ignore” / not ad-hoc 422 on forbidden keys). FE must stop sending `Partial<Product>`. | 2026-09-07 |
| 3 | Pending table cardinality | **A** — 1:1 aggregate (`product_id` UNIQUE + `quantity`) for this phase; later may become SUM over real preorder rows without changing API field shape. | 2026-09-07 |
| 4 | Seeding mock products | **B** — Alembic data migration and/or management script in a **later phase** (not in the first schema-only migration). | 2026-09-07 |
| 5 | Create-time stock qty | **No quantities on `POST /products`** — create always inserts four `product_stock` rows at `0`; FE sets real qty via future inventory APIs. | 2026-09-07 |
| 6 | Search sort | **`sku ASC`**; still add `created_at` / `updated_at` for audit. | 2026-09-07 |
| 7 | Auth | Keep **optional/dummy** for this phase. | 2026-09-07 |
| 8 | FE / OpenAPI sync | Track all FE + contract changes in [`05-fe-changes.md`](./05-fe-changes.md). | 2026-09-07 |

---

## Decided detail

### 1. Duplicate SKU — `PRODUCT_SKU_DUPLICATE`

- HTTP `409`
- Body: `BusinessError` with `code: PRODUCT_SKU_DUPLICATE`
- Message (implement-time copy OK): `貨號已存在`
- Add to OpenAPI `BusinessErrorCode` and FE `BusinessErrorCode` (see `05-fe-changes.md`)

### 2. PUT body — contract excludes non-metadata fields

- Named schema `UpdateProductRequest`: only `sku`, `barcode`, `brand`, `name`, `scale`, `listPrice`, `costPrice`, `vipPrice`, `note`, `status`, `material`, `color`, `imageUrl`
- **Do not** document `stocks`, `totalStock`, `id`, `normalizedSku`, `preOrderPendingCount` on update
- FE: replace `Partial<Product>` update payload with a dedicated update type aligned to OpenAPI
- Implementation may use Pydantic `extra='ignore'` as a safety net; the **source of truth** is the narrowed OpenAPI schema

### 3. `product_pre_order_pending` — 1:1 now

- Unique `product_id` + `quantity`
- No row ⇒ `preOrderPendingCount: 0`
- Catalog read-only; future preorder module owns writes
- Optional later: replace with SUM over real preorder line items without changing response field name

### 4. Seed — later phase (B)

- First Alembic revision: **schema only** (tables + indexes)
- Later: data migration and/or management script to load mock-like products (`prod-001` style IDs OK for seed)

### 5. POST create — no stock quantities

- `CreateProductRequest` **does not** include `stocks` (or any quantity fields)
- Server always creates four location rows at `quantity: 0` + fixed `locationName`
- FE `CreateProductModal` must stop sending `stocks`; initial qty goes through inventory APIs after create
- Details for FE: [`05-fe-changes.md`](./05-fe-changes.md)

### 6–7. Sort and auth

- Default list/search order: `sku ASC`
- Auth: optional/dummy (`get_current_user_optional`); do not require JWT for catalog in this phase

### 8. FE change checklist

- Single tracking doc: [`05-fe-changes.md`](./05-fe-changes.md) (OpenAPI patches, types, service, UI)

---

## Closed / confirmed (do not reopen without cause)

| Topic | Decision |
|-------|----------|
| Scope | Catalog only: `GET/POST /products`, `GET/PUT /products/{id}` |
| Inventory APIs | Out of scope; future `/inventory/*` owns stock qty mutations |
| Storage | `product` + `product_stock` + `product_pre_order_pending` |
| Barcode uniqueness | **Not** unique; **non-unique index** for search |
| SKU uniqueness | Unique; duplicate → `PRODUCT_SKU_DUPLICATE` |
| Pending count storage | Separate 1:1 table; not a column on `product` |
| Contract direction | Align OpenAPI → FE (FE adapts where contract narrows) |
| Create `id` | Server `prod-{uuid4}` no dashes; no client `id` |
| Create stocks | Always four rows at qty `0`; no client quantities |
| PUT body | Metadata-only OpenAPI schema |
| `locationName` map | 門市現貨 / 後方倉庫 / 公司總倉 / 調度暫存 |
| Search sort | `sku ASC` |
| Auth (this phase) | Optional/dummy |
| Seed | Later phase (B), not first schema migration |
| YAML edits | Apply when implementation starts; FE notes in `05-fe-changes.md` |

---

## Remaining follow-ups (not blocking catalog design)

| Item | Notes |
|------|--------|
| Exact Chinese copy for `PRODUCT_SKU_DUPLICATE` | Default `貨號已存在` unless marketing/ops prefers otherwise |
| Seed script vs Alembic data revision | Choose when entering seed phase (both allowed under decision B) |
| Pending 1:1 → SUM over preorder lines | After preorder module exists |
| Inventory OpenAPI | Separate planning pass |
