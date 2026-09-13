# Customers — Open Questions

Decisions from the planning discussion are recorded below. Items marked **Decided** should not be reopened without cause. Rows **27–34** (2026-09-13 revision) supersede earlier choices on points, email, phone, by-phone, `updatedAt`, `note`, paging, and SQL-only search.

---

## Decision log

| # | Topic | Decision | Date |
|---|-------|----------|------|
| 1 | Duplicate phone error | **A** — `409` + `{ code: CUSTOMER_PHONE_DUPLICATE, message: … }` (e.g. `手機號碼已存在`) | 2026-09-13 |
| 2 | PUT spending / computed fields | **Tighten OpenAPI** — `UpdateCustomerRequest` profile-only; `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent` are **not** in the request contract. FE must stop sending `Partial<Customer>`. | 2026-09-13 |
| 3 | `vipTierName` storage | **Derive on read** — fixed map from `vipTier`; do not persist a name column (avoids seed/FE copy drift). | 2026-09-13 |
| 4 | Seeding mock customers | **B** — Alembic data migration and/or management script in a **later phase** (not in the first schema-only migration). | 2026-09-13 |
| 5 | Create-time spending | **No `totalSpent` on `POST /customers`** — create always stores `0`; FE must not send it. Checkout later increments. | 2026-09-13 |
| 6 | Search sort | **`name ASC`**. Timestamps `created_at` / `updated_at` exist for audit. **Revised by #29:** both `createdAt` and `updatedAt` are in the JSON response. | 2026-09-13 |
| 7 | Auth | Keep **optional/dummy** for this phase. | 2026-09-13 |
| 8 | FE / OpenAPI sync | Track all FE + contract changes in [`05-fe-changes.md`](./05-fe-changes.md). | 2026-09-13 |
| 9 | Search query param | **`keyword`** — same as products. FE HTTP `q` and FE OpenAPI `query` both become `keyword`. | 2026-09-13 |
| 10 | Email | **Superseded by #28.** Was: required unique. Now: optional, `null` allowed. | 2026-09-13 |
| 11 | Phone uniqueness | **Unique among non-null** on canonical form. **Revised by #30:** no exact get-by-phone endpoint; search `keyword` covers phone. **Revised by #34:** phone is optional; `NULL` allowed; multiple `NULL` phones allowed. | 2026-09-13 |
| 12 | Spending HTTP | **Out of scope** — no `POST /customers/{id}/spending`. Checkout owns `totalSpent`. **Revised by #27:** catalog must not set `rewardPoints`. | 2026-09-13 |
| 13 | Email in keyword search | **Include** email contains (case-insensitive) when email is non-null. | 2026-09-13 |
| 14 | DB primary key | **`customer.id`** — same as `product.id`. JSON `id` / path `{customerId}` are that column. Future FKs reference `customer.id`. | 2026-09-13 |
| 15 | Create `vipTier` | **Optional** — omit / missing → default **`regular`**. | 2026-09-13 |
| 16 | Purchase / preorder this phase | **A** — profile only. Member detail tabs will see **empty lists** until checkout / preorder modules exist. | 2026-09-13 |
| 17 | Implementation timing | Contract YAML + planning docs stay in `prompts/`. Application code follows an explicit implement pass. | 2026-09-13 |
| 18 | Phone format | Canonicalize (strip spaces / hyphens / parentheses). Empty after canonicalize → `NULL`. Unique among non-null. **No** Taiwan-only `09xxxxxxxx` / E.164 rule. **Revised by #34:** optional. | 2026-09-13 |
| 19 | Search VIP / points | **`vipTier`** (`ALL` / missing = no filter). **`minPoints` superseded by #27** — removed. | 2026-09-13 |
| 20 | Reward points mutate | **Superseded by #27** — no member `rewardPoints`. | 2026-09-13 |
| 21 | Delete | **`DELETE /customers/{id}`** hard-delete. **API-only this phase**. `204` / `404`. Unfinished order/preorder → `409`. Completed history allowed; later FKs **`SET NULL`**. | 2026-09-13 |
| 22 | Add-points UI | **Superseded by #27** — no add-points API or UI. | 2026-09-13 |
| 23 | Unfinished statuses | **Block** unless status is `completed`, `refunded`, or **`cancelled`**. `partially_refunded` **does** block. **`cancelled` preorders do not block.** | 2026-09-13 |
| 24 | Delete with completed history | **Allowed.** Later `customer_id` FKs **`ON DELETE SET NULL`**. History rows **must keep** denormalized `customerName` / `customerPhone` snapshots. | 2026-09-13 |
| 25 | Implementation scope | **Backend only** this pass. No FE `05-fe-changes` except as a later checklist. | 2026-09-13 |
| 26 | OpenAPI file | **Merged** [`../openapi.yaml`](../openapi.yaml) — products + customers in one file. | 2026-09-13 |
| 27 | Cancel `rewardPoints` | **Remove** from member catalog: column, JSON, `minPoints`, PUT set, `POST .../reward-points`, `CUSTOMER_POINTS_INSUFFICIENT`, add-points UI. Checkout later may keep **order-level** points; not on `customer`. | 2026-09-13 |
| 28 | Email optional | Omit / JSON `null` / whitespace → SQL `NULL`. Non-null: trim + lowercase, valid format, unique among non-null. Duplicate → `409` `CUSTOMER_EMAIL_DUPLICATE`. Malformed → `422`. PUT may clear with `null`. | 2026-09-13 |
| 29 | `updatedAt` in API | Same as `createdAt`: ISO 8601, server-owned, **on the response**, not on create/update request. Set on insert; bump on profile PUT. | 2026-09-13 |
| 30 | Remove by-phone | Drop `GET /customers/by-phone/{phone}` and `getCustomerByPhone`. Phone lookup is `GET /customers?keyword=` (substring, including canonicalized phone). | 2026-09-13 |
| 31 | `note` type | Optional **`string`**. Omit or `""`. Do **not** document OpenAPI `nullable: true` / `null` on `note`. SQL `NULL` on omit is storage, not the JSON type. | 2026-09-13 |
| 32 | Search paging | `page` (default `1`, ≥ 1) + `pageSize` (default `20`, max `100`). Response `{ items, page, pageSize, total }`. SQL `LIMIT`/`OFFSET` after `ORDER BY name ASC, id ASC`. | 2026-09-13 |
| 33 | SQL-only search filters | Customer **and** product search: apply keyword/filters/sort/(paging) **in the database**. Do not load then filter or slice in Python. | 2026-09-13 |
| 34 | Phone optional | Omit / JSON `null` / whitespace / empty after canonicalize → SQL `NULL`. Non-null: unique after canonicalize. Duplicate → `409` `CUSTOMER_PHONE_DUPLICATE`. PUT may clear with `null`. Multiple `NULL` phones allowed. | 2026-09-13 |

---

## Decided detail

### 1. Duplicate phone — `CUSTOMER_PHONE_DUPLICATE`

- HTTP `409`
- Body: `BusinessError` with `code: CUSTOMER_PHONE_DUPLICATE`
- Message (implement-time copy OK): `手機號碼已存在`
- Add to OpenAPI `BusinessErrorCode` and FE `BusinessErrorCode` (see `05-fe-changes.md`)

### 2. PUT body — contract excludes server-owned fields

- Named schema `UpdateCustomerRequest`: only `name`, `phone`, `email`, `vipTier`, `note`
- **Do not** document `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent`, `rewardPoints` on update
- FE: replace `Partial<Customer>` update payload with a dedicated update type aligned to OpenAPI
- Implementation may use Pydantic `extra='ignore'` as a safety net; the **source of truth** is the narrowed OpenAPI schema

### 3. `vipTierName` — derived, not stored

- Map (must match FE `getVipTierName`):

  | `vipTier` | `vipTierName` |
  |-----------|----------------|
  | `platinum` | 白金黑卡 (9折) |
  | `gold` | 金卡會員 (95折) |
  | `silver` | 銀卡會員 (98折) |
  | `regular` | 一般會員 |

- Client must not send `vipTierName` on create/update
- Seed display strings that differ (e.g. mock `銀卡會員` without ` (98折)`) are **not** preserved; API always returns the map

### 4. Seed — later phase (B)

- First Alembic revision: **schema only** (table + indexes)
- Later: data migration and/or management script to load mock-like customers (`cust-001` style IDs OK for seed)

### 5. POST create — no spending / no client id

- `CreateCustomerRequest` **does not** include `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent`, `rewardPoints`
- Server always sets `totalSpent: 0`, assigns `cust-{uuid4}` (no dashes), sets `createdAt` and `updatedAt`
- `email` is **optional** (decision 28)
- `phone` is **optional** (decision 34)
- Missing `vipTier` → `regular`; still derive `vipTierName` from the stored tier
- FE `CustomerModal` must stop sending `vipTierName` and `totalSpent: 0`; email and phone are optional
- Details for FE: [`05-fe-changes.md`](./05-fe-changes.md)

### 6–7. Sort and auth

- Default list/search order: `name ASC` (tie-break `id ASC`)
- Auth: optional/dummy (`get_current_user_optional`); do not require JWT for members in this phase

### 8. FE change checklist

- Single tracking doc: [`05-fe-changes.md`](./05-fe-changes.md) (OpenAPI patches, types, service, UI)

### 9. Search param `keyword`

- Same query name as product catalog
- FE HTTP adapter currently uses `q`; change to `keyword`
- Empty `keyword` = no keyword filter (member page initial load)
- Phone bind uses this param (decision 30)

### 10–11 / 28 / 30 / 34. Uniqueness and lookup

- `phone` **optional**. Omit / `null` / whitespace / empty after canonicalize → SQL `NULL`. Non-null: unique after canonicalize (spaces / hyphens / parentheses stripped)
- `email` **optional**. Omit / `null` / whitespace → SQL `NULL`. Non-null: unique after trim + lowercase, valid format
- Duplicate non-null phone → `409` `{ code: CUSTOMER_PHONE_DUPLICATE, message: 手機號碼已存在 }`
- Duplicate non-null email → `409` `{ code: CUSTOMER_EMAIL_DUPLICATE, message: 電子信箱已存在 }`
- PUT may send `phone: null` or `email: null` to clear
- **No** `GET /customers/by-phone/{phone}`. Checkout bind: `GET /customers?keyword=`

### 12 / 27. Spending and points writes

- Catalog does **not** expose increment-spending
- Catalog does **not** store or mutate `rewardPoints`
- FE `HttpCustomerService.updateCustomerSpending` / `addRewardPoints` / `getCustomerByPhone` stay unused against this phase’s API (remove or no-op in the later FE pass)
- When checkout is implemented, the checkout transaction updates `total_spent` (and any **order-level** points) internally — not a column on `customer`

### 13. Email keyword

- Backend search OR-matches non-null email; FE mock should do the same so HTTP vs mock stay aligned

### 14. PK — `id`

- Column name in DB: **`id`** (same as `product.id`; **not** `customer_id`)
- Value: server `cust-{uuid4}` with dashes stripped (seed `cust-001` later)
- JSON `id` and path `{customerId}` are the same identifier
- No auto-increment integer PK alongside it

### 15. Create `vipTier` default

- **Not required** on `POST /customers`
- Missing / omitted → store `regular` (response `vipTierName` = `一般會員`)
- If the client sends a valid `VipTier`, persist that value
- Invalid enum → `422`
- Column `vip_tier` should default to `regular` in the ORM / DB as well

### 16. Purchase history / preorders — later modules

- This phase stores and serves **profile only**
- `GET /customers/{id}/preorders` and `GET /customers/{id}/orders` are **not** added
- UI tabs stay empty (or keep using mock checkout/preorder) until those modules write rows

### 17. Implement vs planning

- Contract YAML is [`../openapi.yaml`](../openapi.yaml) (merged products + customers)
- Existing backend still follows the **previous** contract until an explicit code pass (drop `reward_points`, nullable phone / email, paging, SQL keyword, `updatedAt` JSON, remove by-phone / add-points)

### 18. Phone format — keep current

- Canonicalize then unique among non-null; empty after canonicalize → `NULL`
- Do not add country-specific length or `+886` conversion

### 19 / 32. Search — `vipTier` + paging (no `minPoints`)

- `GET /customers` query params: `keyword`, `vipTier`, `page`, `pageSize`
- `vipTier`: missing or `ALL` → no filter; else exact match (same pattern as product `scale`)
- AND-combined with keyword
- Paged wrapper `{ items, page, pageSize, total }`
- FE today: `searchCustomers(query: string)` only — must become a params object (see `05-fe-changes.md`)

### 20 / 22 / 27. No member reward points

- Do not add `rewardPoints` to create/update/response
- Do not add `POST /customers/{id}/reward-points`
- Do not add `CUSTOMER_POINTS_INSUFFICIENT`
- Remove any add-points / set-points UI notes that assumed a member balance

### 21. Delete

- `DELETE /customers/{id}` → `204` or `404 CUSTOMER_NOT_FOUND`
- Hard delete (row gone). No soft-delete / `discontinued` flag
- **FE:** API-only this phase — no delete button / confirm dialog until a later FE pass
- After delete, unique non-null `phone` / non-null `email` are free for a new member
- Leftover `totalSpent` on the member row is discarded with the delete (history amounts stay on order/preorder rows)

### 23. Unfinished statuses (block delete)

**Terminal** (do **not** block; then `SET NULL` the FK, **keep** name/phone snapshots):

| Kind | Status |
|------|--------|
| Order | `completed`, `refunded` |
| Preorder | `completed`, **`cancelled`** (if `refunded` is added later, treat as terminal too) |

**Unfinished** (any other status → `409` `CUSTOMER_HAS_UNFINISHED_ORDERS`):

| Kind | Status (today’s FE) |
|------|---------------------|
| Order | `partially_refunded` |
| Preorder | `pending`, `partially_arrived`, `partially_completed` |

Rule for future statuses: terminal = `completed` \| `refunded` \| `cancelled`. Everything else blocks.

This catalog phase has no order/preorder tables, so the check cannot fire yet. Checkout/preorder modules implement the query before `DELETE`.

### 24. Completed / cancelled history — delete then `SET NULL` + snapshots

- A member **may** be deleted while terminal history remains (`completed` / `refunded` / `cancelled`)
- Later FKs: `customer_id` **nullable**, `ON DELETE SET NULL` (do **not** `CASCADE` history away; do **not** `RESTRICT` terminal rows)
- **Required snapshots:** each order/preorder row stores `customerName` and `customerPhone` at bind/create. Member delete **must not** clear those columns. Receipts / history still show the member after `customer_id` is `NULL`
- Service order when checkout exists: (1) if any unfinished row → `409` (2) delete `customer` (`customer_id` → `NULL`; name/phone snapshots unchanged)

### 25. Implementation scope — backend only

- Next implement pass: FastAPI + Alembic + [`../openapi.yaml`](../openapi.yaml) as contract
- Do **not** change `freds-pos-fe` in that pass (`05-fe-changes.md` remains a later checklist)
- Delete UI stays later even when FE is done

### 26. OpenAPI — merged file

- Source of truth: [`../openapi.yaml`](../openapi.yaml)
- Contains **products** and **customers** tags / paths / schemas
- Do **not** keep `prompts/products/openapi.yaml` or `prompts/customers/openapi.yaml`

### 29. `updatedAt`

- JSON field on `Customer`, same shape as `createdAt` (`format: date-time`)
- Not accepted on create/update request
- Insert: `created_at` = `updated_at` = UTC now
- Profile PUT: bump `updated_at` only

### 31. `note` vs nullable

- JSON type is `string`. Optional (omitted from `required`). Empty string is valid
- Do not use OpenAPI `nullable: true` on `note` — that is for fields that return JSON `null` (email)
- Internally, omitted note may persist as SQL `NULL`; map to `""` or omit on read if the implementation prefers a string; the contract type stays `string`

### 32. Paging

| Param | Default | Invalid |
|-------|---------|---------|
| `page` | `1` | `< 1` → `422` |
| `pageSize` | `20` | not in 1–100 → `422` |

- `total` is the filtered count, not the page length
- Empty catalog / empty match: `items: []`, `total: 0`

### 33. SQL-only filters (customers + products)

- Customer: `WHERE` + `ORDER BY` + `LIMIT`/`OFFSET` + `COUNT(*)` in the DB
- Product: keyword / scale / brand / inStockOnly in SQL (see [`../products/03-search-rules.md`](../products/03-search-rules.md)); do **not** load candidates then filter in Python

### 34. Phone optional

- Same shape as email (decision 28): omit / JSON `null` / whitespace / empty after canonicalize → SQL `NULL` (JSON `null`)
- Non-null: canonicalize, unique among non-null. Duplicate → `409` `CUSTOMER_PHONE_DUPLICATE`
- PUT may send `phone: null` to clear
- Multiple `NULL` phones allowed
- Keyword search skips the phone branch when `phone` is `NULL`
- `CreateCustomerRequest.required` is **`name` only**

---

## Closed / confirmed (do not reopen without cause)

| Topic | Decision |
|-------|----------|
| Scope | Member catalog: paged search, create, get/put/**delete** by id. **No** by-phone. **No** reward points. |
| PUT body | Profile-only OpenAPI schema (`name`, `phone`, `email`, `vipTier`, `note`); excludes `totalSpent` / timestamps / `vipTierName` |
| Points | **Removed** from `customer`. Checkout later owns any order-level points |
| Delete | Hard `DELETE`; API-only UI; `204` / `404`; `409` unless `completed`/`refunded`/`cancelled`; history `SET NULL` + **keep name/phone snapshots** |
| Search params | `keyword` + `vipTier` (`ALL`) + `page` / `pageSize` |
| Spending / checkout writes | Out of scope; future checkout owns `totalSpent` increments |
| Nested preorders / history | Out of scope this phase (**A**); empty until checkout/preorder modules |
| Phone format | Canonicalize; unique among non-null; empty → `NULL`; not TW-only / not E.164 |
| Phone lookup | `GET /customers?keyword=` only |
| YAML / code | Contract in `prompts/openapi.yaml`; next code pass must match **this** revision |
| OpenAPI file | `prompts/openapi.yaml` (merged products + customers) |
| Storage | Single `customer` table; PK **`id`**; **no** `reward_points` |
| Phone uniqueness | **Optional**; unique among non-null (canonical); `null` allowed; duplicate → `CUSTOMER_PHONE_DUPLICATE` |
| Email | **Optional**; unique among non-null (lowercased); `null` allowed; duplicate → `CUSTOMER_EMAIL_DUPLICATE` |
| `note` | Optional `string` (not OpenAPI nullable) |
| `vipTierName` | Derived map; not a column |
| Contract direction | Align OpenAPI → FE (FE adapts where contract narrows) |
| Create `id` | Server `cust-{uuid4}` no dashes stored in `id`; no client `id` |
| Create spending | Always `totalSpent: 0`; no client field |
| Create `vipTier` | Optional; default **`regular`** |
| `vipTierName` map | 一般會員 / 銀卡會員 (98折) / 金卡會員 (95折) / 白金黑卡 (9折) |
| Search sort | `name ASC`, tie-break `id ASC` |
| Search filters | **SQL only** (customers and products) |
| Auth (this phase) | Optional/dummy |
| Seed | Later phase (B), not first schema migration |
| YAML edits | Contract is [`../openapi.yaml`](../openapi.yaml); FE notes in `05-fe-changes.md` (later) |

---

## Remaining follow-ups (not blocking member-catalog design)

| Item | Notes |
|------|--------|
| Exact Chinese copy for `CUSTOMER_PHONE_DUPLICATE` | Default `手機號碼已存在` unless ops prefers otherwise |
| Exact Chinese copy for `CUSTOMER_EMAIL_DUPLICATE` | Default `電子信箱已存在` unless ops prefers otherwise |
| Exact Chinese copy for `CUSTOMER_HAS_UNFINISHED_ORDERS` | Default `該會員尚有未完成訂單，無法刪除` |
| Seed script vs Alembic data revision | Choose when entering seed phase (both allowed under decision B) |
| `createdAt` / `updatedAt` display | API emits ISO 8601 — FE detail panel should `formatDate` / `formatDateTime` (see `05-fe-changes.md`) |
| Follow-up Alembic | Existing `customer` table (if already migrated) needs a revision: drop `reward_points`; make `phone` and `email` nullable; unique non-null phone and email |
| Backend code vs this contract | Python still implements the **previous** contract until an explicit implement pass |
