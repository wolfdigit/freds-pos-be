# Customers — Open Questions

Decisions from the planning discussion are recorded below. Items marked **Decided** should not be reopened without cause.

---

## Decision log

| # | Topic | Decision | Date |
|---|-------|----------|------|
| 1 | Duplicate phone error | **A** — `409` + `{ code: CUSTOMER_PHONE_DUPLICATE, message: … }` (e.g. `手機號碼已存在`) | 2026-09-13 |
| 2 | PUT spending / computed fields | **Tighten OpenAPI** — `UpdateCustomerRequest` profile-only; `id`, `createdAt`, `vipTierName`, `totalSpent` are **not** in the contract (not “silent ignore” / not ad-hoc 422 on forbidden keys). FE must stop sending `Partial<Customer>`. | 2026-09-13 |
| 3 | `vipTierName` storage | **Derive on read** — fixed map from `vipTier`; do not persist a name column (avoids seed/FE copy drift). | 2026-09-13 |
| 4 | Seeding mock customers | **B** — Alembic data migration and/or management script in a **later phase** (not in the first schema-only migration). | 2026-09-13 |
| 5 | Create-time spending | **No `totalSpent` on `POST /customers`** — create always stores `0`; FE must not send it. Checkout later increments. | 2026-09-13 |
| 6 | Search sort | **`name ASC`**; still add `created_at` / `updated_at` for audit (`updated_at` not in JSON). | 2026-09-13 |
| 7 | Auth | Keep **optional/dummy** for this phase. | 2026-09-13 |
| 8 | FE / OpenAPI sync | Track all FE + contract changes in [`05-fe-changes.md`](./05-fe-changes.md). | 2026-09-13 |
| 9 | Search query param | **`keyword`** — same as products. FE HTTP `q` and FE OpenAPI `query` both become `keyword`. | 2026-09-13 |
| 10 | Email | **Required, unique, valid format** (trim + lowercase). Duplicate → `409` `CUSTOMER_EMAIL_DUPLICATE`. Missing / malformed → `422`. Cannot clear on PUT. | 2026-09-13 |
| 11 | Phone uniqueness | **Unique** on canonical form; exact get-by-phone returns one row. | 2026-09-13 |
| 12 | Spending HTTP | **Out of scope** — no `POST /customers/{id}/spending` in this phase. Checkout module owns `totalSpent` / checkout point deltas. Catalog `PUT` may still **set** `rewardPoints` (cashier override). | 2026-09-13 |
| 13 | Email in keyword search | **Include** email contains (case-insensitive) as an extension vs today’s mock; update mock for parity. | 2026-09-13 |
| 14 | DB primary key | **`customer.id`** — same as `product.id`. JSON `id` / path `{customerId}` are that column. No `customer_id` column. Future FKs reference `customer.id`. (**Revised:** earlier draft used `customer_id`.) | 2026-09-13 |
| 15 | Create `vipTier` | **Optional** — omit / missing → default **`regular`**. Still accepted if the client sends a valid tier (FE modal does). | 2026-09-13 |
| 16 | Purchase / preorder this phase | **A** — profile only. Member detail tabs will see **empty lists** until checkout / preorder modules exist. Do not add order/preorder tables or nested read APIs now. | 2026-09-13 |
| 17 | Implementation timing | Stay on **planning** until explicitly approved. Do not patch YAML or write application code yet. | 2026-09-13 |
| 18 | Phone format | Keep current: canonicalize (strip spaces / hyphens / parentheses), non-empty, unique. **No** Taiwan-only `09xxxxxxxx` / E.164 rule. | 2026-09-13 |
| 19 | Search VIP / points | Add `vipTier` (`ALL` / missing = no filter, else exact) and `minPoints` (`rewardPoints >= N`). AND with `keyword`. FE must extend `searchCustomers`. | 2026-09-13 |
| 20 | Reward points mutate | **Replace** via `PUT` `rewardPoints`. **Add** via `POST /customers/{id}/reward-points` `{ amount }` (**signed** integer; negative subtracts). Result &lt; 0 → `422 CUSTOMER_POINTS_INSUFFICIENT` (deny, no clamp). | 2026-09-13 |
| 21 | Delete | **`DELETE /customers/{id}`** hard-delete. **API-only this phase** (no FE delete control). `204` / `404`. Unfinished order/preorder → `409`. Completed history allowed; later FKs **`SET NULL`**. Check is a no-op until checkout/preorder exist. | 2026-09-13 |
| 22 | Add-points UI | **Specify in** [`05-fe-changes.md`](./05-fe-changes.md); **do not implement** the UI in this phase. Service + HTTP still land with the catalog. | 2026-09-13 |
| 23 | Unfinished statuses | **Block** unless status is `completed`, `refunded`, or **`cancelled`**. Today that blocks checkout `partially_refunded` and preorder `pending` / `partially_arrived` / `partially_completed`. **`cancelled` preorders do not block.** | 2026-09-13 |
| 24 | Delete with completed history | **Allowed.** Later `customer_id` FKs **`ON DELETE SET NULL`**. History rows **must keep** denormalized `customerName` / `customerPhone` snapshots (written at bind/create; not cleared on delete). | 2026-09-13 |
| 25 | Implementation scope | **Backend only** this pass (models, Alembic, schemas, service, endpoints). No FE `05-fe-changes` except as a later checklist. | 2026-09-13 |
| 26 | OpenAPI file | **Merged** [`../openapi.yaml`](../openapi.yaml) — products + customers in one file. Do not keep per-feature YAML copies. | 2026-09-13 |

---

## Decided detail

### 1. Duplicate phone — `CUSTOMER_PHONE_DUPLICATE`

- HTTP `409`
- Body: `BusinessError` with `code: CUSTOMER_PHONE_DUPLICATE`
- Message (implement-time copy OK): `手機號碼已存在`
- Add to OpenAPI `BusinessErrorCode` and FE `BusinessErrorCode` (see `05-fe-changes.md`)

### 2. PUT body — contract excludes server-owned fields

- Named schema `UpdateCustomerRequest`: only `name`, `phone`, `email`, `vipTier`, `note`, `rewardPoints`
- **Do not** document `id`, `createdAt`, `vipTierName`, `totalSpent` on update
- FE: replace `Partial<Customer>` update payload with a dedicated update type aligned to OpenAPI
- Implementation may use Pydantic `extra='ignore'` as a safety net; the **source of truth** is the narrowed OpenAPI schema
- `rewardPoints` on PUT **replaces** the stored balance (cashier set)
- **Add** is a separate `POST /customers/{id}/reward-points` with `{ amount }` — not a second field on PUT

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

- `CreateCustomerRequest` **does not** include `id`, `createdAt`, `vipTierName`, `totalSpent`
- Server always sets `totalSpent: 0`, assigns `cust-{uuid4}` (no dashes), sets `createdAt`
- `email` is required on create (valid unique)
- Missing `vipTier` → `regular`; still derive `vipTierName` from the stored tier
- FE `CustomerModal` must stop sending `vipTierName` and `totalSpent: 0`, and must require email (modal may still send `vipTier`; not required by the API)
- Details for FE: [`05-fe-changes.md`](./05-fe-changes.md)

### 6–7. Sort and auth

- Default list/search order: `name ASC`
- Auth: optional/dummy (`get_current_user_optional`); do not require JWT for members in this phase

### 8. FE change checklist

- Single tracking doc: [`05-fe-changes.md`](./05-fe-changes.md) (OpenAPI patches, types, service, UI)

### 9. Search param `keyword`

- Same query name as product catalog
- FE HTTP adapter currently uses `q`; change to `keyword`
- Empty `keyword` = no keyword filter (member page initial load)

### 10–11. Uniqueness

- `phone` unique after canonicalize (spaces / hyphens / parentheses stripped)
- `email` **required**, unique after trim + lowercase, valid format (`EmailStr`)
- Duplicate email → `409` `{ code: CUSTOMER_EMAIL_DUPLICATE, message: 電子信箱已存在 }`
- PUT must not clear email; omit field to leave unchanged

### 12. Spending writes

- Catalog does **not** expose increment-spending
- FE `HttpCustomerService.updateCustomerSpending` stays unused against this phase’s API
- When checkout is implemented, the checkout transaction updates `total_spent` and `reward_points` internally (as FE OpenAPI checkout lifecycle already describes)
- Until then, mock checkout + HTTP customers cannot sync spending over HTTP — keep customer mock if that mix is required, or wait for checkout BE

### 13. Email keyword

- Backend search OR-matches email; FE mock should do the same so HTTP vs mock stay aligned

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

### 17. Do not implement until approved

- No models, endpoints, or Alembic until an explicit go-ahead
- Contract YAML is [`../openapi.yaml`](../openapi.yaml) (merged products + customers)

### 18. Phone format — keep current

- Canonicalize then unique / non-empty only
- Do not add country-specific length or `+886` conversion

### 19. Search — `vipTier` + `minPoints`

- `GET /customers` query params in addition to `keyword`
- `vipTier`: missing or `ALL` → no filter; else exact match (same pattern as product `scale`)
- `minPoints`: missing → no filter; else `rewardPoints >= minPoints` (integer ≥ 0)
- AND-combined with keyword
- FE today: `searchCustomers(query: string)` only — must become a params object (see `05-fe-changes.md`)

### 20. Reward points — replace and add

- **Replace:** `PUT /customers/{id}` field `rewardPoints` (absolute, ≥ 0)
- **Add:** `POST /customers/{id}/reward-points` `{ amount: integer }` (**signed**; negative subtracts)
- If `stored + amount < 0` → `422 CUSTOMER_POINTS_INSUFFICIENT` (no silent clamp)
- Create may still set an initial `rewardPoints` (default `0`)
- Checkout later still owns sale-time earned/used points; this add endpoint is cashier adjustment
- Add-points **UI** is specified in `05-fe-changes.md` but **not built** in this phase

### 21. Delete

- `DELETE /customers/{id}` → `204` or `404 CUSTOMER_NOT_FOUND`
- Hard delete (row gone). No soft-delete / `discontinued` flag
- **FE:** API-only this phase — no delete button / confirm dialog until a later FE pass
- After delete, unique `phone` / `email` are free for a new member
- Leftover `rewardPoints` / `totalSpent` on the member row are discarded with the delete (history amounts stay on order/preorder rows)

### 22. Add-points UI — document only

- Write the cashier UX in [`05-fe-changes.md`](./05-fe-changes.md)
- Do **not** implement that UI (or wire it to `addRewardPoints`) until a later FE pass
- BE + OpenAPI + service methods still belong to this catalog phase

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
- Add-points UI and delete UI stay later even when FE is done

### 26. OpenAPI — merged file

- Source of truth: [`../openapi.yaml`](../openapi.yaml)
- Contains **products** and **customers** tags / paths / schemas
- Do **not** keep `prompts/products/openapi.yaml` or `prompts/customers/openapi.yaml`

---

## Closed / confirmed (do not reopen without cause)

| Topic | Decision |
|-------|----------|
| Scope | Member catalog: search/create, get/put/**delete** by id, get-by-phone, **add reward points** |
| PUT body | Profile-only OpenAPI schema (`rewardPoints` = **replace**; excludes `totalSpent`) |
| Points add | `POST .../reward-points` `{ amount }` **signed**; result &lt; 0 → `CUSTOMER_POINTS_INSUFFICIENT` (deny) |
| Add-points UI | Specified in `05-fe-changes.md`; **not implemented** this phase |
| Delete | Hard `DELETE`; API-only UI; `204` / `404`; `409` unless `completed`/`refunded`/`cancelled`; history `SET NULL` + **keep name/phone snapshots** |
| Search params | `keyword` + `vipTier` (`ALL`) + `minPoints` |
| Spending / checkout writes | Out of scope; future checkout owns `totalSpent` increments and checkout point deltas |
| Nested preorders / history | Out of scope this phase (**A**); empty until checkout/preorder modules |
| Phone format | Canonicalize + unique; not TW-only / not E.164 |
| YAML / code | Planning only until explicit approval; implement **backend only** |
| OpenAPI file | `prompts/openapi.yaml` (merged products + customers) |
| Storage | Single `customer` table; PK **`id`** (same as `product.id`) |
| Phone uniqueness | **Unique** (canonical); duplicate → `CUSTOMER_PHONE_DUPLICATE` |
| Email | **Required**, unique (lowercased), valid format; duplicate → `CUSTOMER_EMAIL_DUPLICATE` |
| `vipTierName` | Derived map; not a column |
| Contract direction | Align OpenAPI → FE (FE adapts where contract narrows) |
| Create `id` | Server `cust-{uuid4}` no dashes stored in `id`; no client `id` |
| Create spending | Always `totalSpent: 0`; no client field |
| Create `vipTier` | Optional; default **`regular`** |
| `vipTierName` map | 一般會員 / 銀卡會員 (98折) / 金卡會員 (95折) / 白金黑卡 (9折) |
| Search sort | `name ASC` |
| Auth (this phase) | Optional/dummy |
| Seed | Later phase (B), not first schema migration |
| YAML edits | Contract is [`../openapi.yaml`](../openapi.yaml); FE notes in `05-fe-changes.md` (later) |

---

## Remaining follow-ups (not blocking member-catalog design)


| Item | Notes |
|------|--------|
| Exact Chinese copy for `CUSTOMER_PHONE_DUPLICATE` | Default `手機號碼已存在` unless ops prefers otherwise |
| Exact Chinese copy for `CUSTOMER_EMAIL_DUPLICATE` | Default `電子信箱已存在` unless ops prefers otherwise |
| Exact Chinese copy for `CUSTOMER_POINTS_INSUFFICIENT` | Default `點數不足` unless ops prefers otherwise |
| Exact Chinese copy for `CUSTOMER_HAS_UNFINISHED_ORDERS` | Default `該會員尚有未完成訂單，無法刪除` |
| Seed script vs Alembic data revision | Choose when entering seed phase (both allowed under decision B) |
| `createdAt` display | Seed used `YYYY-MM-DD`; API will emit ISO 8601 — FE detail panel should `formatDate` (see `05-fe-changes.md`) |
| Pagination | Not in mock; add only if member volume requires it |
