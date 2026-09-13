# Customers — API Contract

HTTP contract for the seven member-catalog endpoints. Align OpenAPI with decided catalog rules; where the contract **narrows** relative to today’s FE, FE adapts later (see [`05-fe-changes.md`](./05-fe-changes.md)). The YAML is [`../openapi.yaml`](../openapi.yaml) (merged with products).

Base path: `/api/v1` (see OpenAPI `servers`).

## Shared response: `Customer`

CamelCase JSON matching FE `Customer` (`freds-pos-fe/src/types/customer.ts`).

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server-assigned PK (`customer.id`); opaque `cust-{uuid4}` without dashes |
| `name` | string | Required |
| `phone` | string | Unique; stored canonical (digits after strip spaces / hyphens / parentheses) |
| `email` | string | **Required**; unique (after trim + lowercase); valid email format |
| `vipTier` | `VipTier` | `regular` \| `silver` \| `gold` \| `platinum` |
| `vipTierName` | string | Server-owned: fixed map from `vipTier` (see below) |
| `rewardPoints` | integer | ≥ 0; create/PUT **set**; `POST .../reward-points` **add** |
| `totalSpent` | integer | TWD ≥ 0; server-owned after create (always `0` on create) |
| `note` | string? | |
| `createdAt` | string | Server-assigned ISO 8601 |

### `VipTier` → `vipTierName` map

Same copy as FE `getVipTierName`. Server **overwrites** any client-supplied name.

| `vipTier` | `vipTierName` |
|-----------|----------------|
| `platinum` | 白金黑卡 (9折) |
| `gold` | 金卡會員 (95折) |
| `silver` | 銀卡會員 (98折) |
| `regular` | 一般會員 |

### Server-owned / response-only fields

Not accepted on create or update request schemas:

- `id` (create: never accept)
- `createdAt`
- `vipTierName`
- `totalSpent` (create: server initializes `0`; update: not in contract)

---

## `GET /customers` — `searchCustomers`

**Maps to:** `ICustomerService.searchCustomers`

FE HTTP adapter currently calls `` `/customers?q=` `` — **change to `keyword`** (same name as product search). See [`05-fe-changes.md`](./05-fe-changes.md).

### Query parameters

| Name | Type | Default / missing | Behavior |
|------|------|-------------------|----------|
| `keyword` | string | empty / missing | No keyword filter |
| `vipTier` | `VipTier` \| `ALL` | missing or `ALL` | No VIP filter; otherwise exact `customer.vipTier === vipTier` |
| `minPoints` | integer ≥ 0 | missing | No points filter; when set, keep only `rewardPoints >= minPoints` |

Search / filter semantics: see [`03-search-rules.md`](./03-search-rules.md).

### Responses

| Status | Body |
|--------|------|
| `200` | `Customer[]` |

**Default sort:** `name ASC` (confirmed). `created_at` / `updated_at` exist for audit only.

Auth: optional/dummy (`deps.get_current_user_optional`).

---

## `POST /customers` — `createCustomer`

**Maps to:** `ICustomerService.createCustomer` (FE signature must drop server-owned fields; see `05-fe-changes.md`).

### Request body — `CreateCustomerRequest`

**Required:** `name`, `phone`, `email`

**Optional:** `vipTier` (default `regular`), `note`, `rewardPoints` (default `0`)

**Not in request schema:** `id`, `createdAt`, `vipTierName`, **`totalSpent`**

#### Create-time defaults (server-only)

- Always set **`totalSpent: 0`**. Client cannot set spending on create; checkout later increments it.
- Always set **`vipTierName`** from the `vipTier` map.
- Missing `vipTier` → `regular`.
- Missing `rewardPoints` → `0`.
- `email` is **required**: trim + lowercase before store; never `NULL`.

#### `id` generation

Server assigns `cust-{uuid4}` with dashes stripped from the UUID and stores it as PK **`id`**. JSON `id` is that same value.  
Seed-style `cust-001` remains valid only as imported/seeded data (later phase). Do not accept client `id`.

#### `createdAt`

Server sets timezone-aware UTC now; JSON is ISO 8601.

#### Validation

- `email` unique (after trim + lowercase) → `409` `CUSTOMER_EMAIL_DUPLICATE`.
- `email` required: non-empty after trim, valid email format (e.g. Pydantic `EmailStr`) → `422` if missing or malformed.
- `phone` unique (after canonicalize) → `409` `CUSTOMER_PHONE_DUPLICATE`.
- `phone` required non-empty after canonicalize.
- `name` required non-empty (trim).
- `rewardPoints`: non-negative integer when provided.

### Responses

| Status | Body |
|--------|------|
| `201` | `Customer` |
| `409` | `BusinessError` `{ code: CUSTOMER_PHONE_DUPLICATE, message: 手機號碼已存在 }` **or** `{ code: CUSTOMER_EMAIL_DUPLICATE, message: 電子信箱已存在 }` |
| `422` | Validation errors (malformed body / empty name / missing or invalid email / negative points / invalid enums) |

---

## `GET /customers/{customerId}` — `getCustomerById`

**Maps to:** `ICustomerService.getCustomerById`

### Path

| Name | Type | Notes |
|------|------|--------|
| `customerId` | string | Lookup on PK `customer.id` |

### Responses

| Status | Body |
|--------|------|
| `200` | `Customer` |
| `404` | `{ code: CUSTOMER_NOT_FOUND, message: 找不到指定的會員 }` |

Note: FE mock / HTTP adapter returns `null` for missing id; HTTP adapter should map `404` → that UX. Backend always returns `404` + `BusinessError`.

---

## `PUT /customers/{customerId}` — `updateCustomer`

**Maps to:** `ICustomerService.updateCustomer` (FE must use `UpdateCustomerRequest`, not `Partial<Customer>`).

### Path

| Name | Type | Notes |
|------|------|--------|
| `customerId` | string | Lookup on PK `customer.id` |

### Request body — `UpdateCustomerRequest` (profile only)

All fields optional / partial:

`name`, `phone`, `email`, `vipTier`, `note`, `rewardPoints`

**Excluded from OpenAPI schema (not part of the contract):**

`id`, `createdAt`, `vipTierName`, `totalSpent`

Rules:

- On `phone` change: canonicalize; duplicate → `409` `CUSTOMER_PHONE_DUPLICATE`.
- On `email` change: trim + lowercase; must remain a valid email; duplicate → `409` `CUSTOMER_EMAIL_DUPLICATE`.
- On `vipTier` change: recompute `vipTierName` on read (not stored).
- Never mutate `totalSpent` via this endpoint.
- `rewardPoints`: non-negative integer when provided — **replaces** the stored balance (cashier set). To **add**, use `POST /customers/{customerId}/reward-points`. Do not send both a replace and an add in one request (add is a different path).
- `email`: if sent, must be non-empty valid format — **do not** clear email (row always has an email). Omitting `email` on partial PUT leaves the stored value unchanged. Empty / whitespace-only → `422`.
- Never overwrite `id` / `createdAt`.

### Responses

| Status | Body |
|--------|------|
| `200` | `Customer` |
| `404` | `{ code: CUSTOMER_NOT_FOUND, message: 找不到指定的會員 }` |
| `409` | `{ code: CUSTOMER_PHONE_DUPLICATE, message: 手機號碼已存在 }` **or** `{ code: CUSTOMER_EMAIL_DUPLICATE, message: 電子信箱已存在 }` |
| `422` | Validation errors |

---

## `GET /customers/by-phone/{phone}` — `getCustomerByPhone`

**Maps to:** `ICustomerService.getCustomerByPhone` (checkout member bind / exact phone).

Today’s checkout `CustomerBindCard` uses `searchCustomers` (substring dropdown), not this method. The interface and FE OpenAPI already declare it; keep it so bind / lookup can use exact match without a list.

### Path

| Name | Type |
|------|------|
| `phone` | string | URL-encoded; server canonicalizes before lookup (so `0912-345-678` matches stored `0912345678`) |

### Responses

| Status | Body |
|--------|------|
| `200` | `Customer` |
| `404` | `{ code: CUSTOMER_NOT_FOUND, message: 找不到指定的會員 }` |

FE HTTP adapter already maps `404` → `null`.

Implement as a **distinct path** (`/customers/by-phone/{phone}`), not `/customers/{customerId}` with a special id. Member ids are `cust-…`, so they do not collide with the `by-phone` segment.

---

## `DELETE /customers/{customerId}` — `deleteCustomer`

**Maps to:** new `ICustomerService.deleteCustomer` (not on today’s interface).

Hard-delete the member row. **FE is API-only this phase** (no delete UI).

If the member has any **unfinished** order or preorder, deny delete. **Unfinished** = status is not `completed`, `refunded`, or **`cancelled`**. Today that includes `partially_refunded` and preorder `pending` / `partially_arrived` / `partially_completed`. A **cancelled** preorder does **not** block.

Terminal history does **not** block. When those tables exist, `customer_id` is **`ON DELETE SET NULL`**. Each history row **must keep** `customerName` / `customerPhone` snapshots (written at bind/create; not cleared on delete).

This catalog phase has no order/preorder tables, so that check cannot fire yet; document the `409` now so checkout/preorder can turn it on.

### Path

| Name | Type | Notes |
|------|------|--------|
| `customerId` | string | Lookup on PK `customer.id` |

### Responses

| Status | Body |
|--------|------|
| `204` | Empty |
| `404` | `{ code: CUSTOMER_NOT_FOUND, message: 找不到指定的會員 }` |
| `409` | `{ code: CUSTOMER_HAS_UNFINISHED_ORDERS, message: 該會員尚有未完成訂單，無法刪除 }` |

`409` is reserved for when checkout/preorder exist. Until then, a found member always deletes (`204`). When those modules exist: service checks for any related row whose status is not `completed`/`refunded`/`cancelled`; if none, delete the member, **`SET NULL`** `customer_id`, and **leave name/phone snapshots**. Do not `CASCADE` history.

---

## `POST /customers/{customerId}/reward-points` — `addRewardPoints`

**Maps to:** new `ICustomerService.addRewardPoints(id, amount)`.

Adds an integer to the stored balance. `PUT rewardPoints` remains **replace**.

### Path

| Name | Type | Notes |
|------|------|--------|
| `customerId` | string | Lookup on PK `customer.id` |

### Request body — `AddRewardPointsRequest`

| Field | Type | Notes |
|-------|------|--------|
| `amount` | integer | **Required.** Signed: positive adds, negative subtracts. |

Rules:

- `newBalance = stored + amount`
- If `newBalance < 0` → `422` `{ code: CUSTOMER_POINTS_INSUFFICIENT, message: 點數不足 }` (do not clamp silently)
- `amount: 0` is allowed (no-op, still `200` + current `Customer`)

### Responses

| Status | Body |
|--------|------|
| `200` | `Customer` (updated `rewardPoints`) |
| `404` | `{ code: CUSTOMER_NOT_FOUND, message: 找不到指定的會員 }` |
| `422` | `{ code: CUSTOMER_POINTS_INSUFFICIENT, message: 點數不足 }` or validation (missing `amount`) |

Checkout later still owns `totalSpent` + checkout-earned/used points atomically; this endpoint is cashier adjustment only.

---

## Errors

### `BusinessError` shape

```json
{ "code": "CUSTOMER_NOT_FOUND", "message": "找不到指定的會員" }
```

### Catalog codes

| HTTP | `code` | When |
|------|--------|------|
| `404` | `CUSTOMER_NOT_FOUND` | Missing `customerId` on get/update/delete/add-points, or no row for exact phone |
| `409` | `CUSTOMER_PHONE_DUPLICATE` | Duplicate canonical phone on create/update |
| `409` | `CUSTOMER_EMAIL_DUPLICATE` | Duplicate lowercased email on create/update |
| `409` | `CUSTOMER_HAS_UNFINISHED_ORDERS` | Delete blocked: related order/preorder is not `completed`/`refunded`/`cancelled` (live after checkout/preorder) |
| `422` | `CUSTOMER_POINTS_INSUFFICIENT` | Add-points would make `rewardPoints < 0` |
| `422` | (validation / FastAPI default) | Invalid body, empty name/phone, missing / invalid email, negative set-points, invalid enums |

Auth remains optional/dummy for this phase.

FE already declares `CUSTOMER_NOT_FOUND` in `freds-pos-fe/src/utils/errors.ts` (checkout mock). Add `CUSTOMER_PHONE_DUPLICATE`, `CUSTOMER_EMAIL_DUPLICATE`, `CUSTOMER_POINTS_INSUFFICIENT`, and `CUSTOMER_HAS_UNFINISHED_ORDERS` there when wiring HTTP.

---

## OpenAPI

Phase contract: [`../openapi.yaml`](../openapi.yaml) (customers + products). FE `docs/openapi.yaml` alignment is a later FE pass ([`05-fe-changes.md`](./05-fe-changes.md)).

The YAML already includes the tightenings below; keep it in sync if the markdown contract changes.

### 1. `CreateCustomerRequest`

- **Remove from `required`:** `vipTierName`, `totalSpent`, `rewardPoints`, **`vipTier`**
- **Remove** `vipTierName` and `totalSpent` from the create request schema
- Required: `name`, `phone`, `email`
- Optional: `vipTier` (default `regular`), `note`, `rewardPoints` (minimum `0`, default `0`)
- `email`: `format: email`; unique after lowercase

Also mark response `Customer.email` as **required** (`format: email`). Today’s FE OpenAPI lists it but omits it from `required`.

### 2. `POST /customers` description

- Server assigns `id` as `cust-{uuid4}` (no dashes), stored as PK `id`, and `createdAt` (ISO 8601)
- Always sets `totalSpent: 0`; missing `vipTier` → `regular`; derives `vipTierName` from `vipTier`
- Does not accept client `id` / `createdAt` / `vipTierName` / `totalSpent`
- Duplicate canonical phone → `409` `CUSTOMER_PHONE_DUPLICATE`
- Duplicate lowercased email → `409` `CUSTOMER_EMAIL_DUPLICATE`
- Missing / invalid email → `422`

### 3. `UpdateCustomerRequest`

Replace opaque / full-`Customer` PUT body with named schema — **profile fields only**; exclude `id`, `createdAt`, `vipTierName`, `totalSpent` from the schema entirely. If `email` is sent, it must be a valid unique email (cannot clear).

### 4. Search

- Query param name: **`keyword`** (same as products). FE HTTP adapter currently uses `q`; FE OpenAPI uses `query` — both become `keyword`.
- Empty / missing `keyword` returns all members that pass other filters
- Document default sort `name ASC`
- Keyword matches name, phone, **or email**
- Add `vipTier` (`VipTier` or `ALL`) and `minPoints` (integer ≥ 0)

### 5. Errors

- Extend `BusinessErrorCode` with `CUSTOMER_NOT_FOUND`, `CUSTOMER_PHONE_DUPLICATE`, `CUSTOMER_EMAIL_DUPLICATE`, `CUSTOMER_POINTS_INSUFFICIENT`, `CUSTOMER_HAS_UNFINISHED_ORDERS`
- Add `409` on create/update with examples `{ code: CUSTOMER_PHONE_DUPLICATE, message: 手機號碼已存在 }` and `{ code: CUSTOMER_EMAIL_DUPLICATE, message: 電子信箱已存在 }`
- Add `404` examples using `CUSTOMER_NOT_FOUND` (today’s generic NotFound example still says `PRODUCT_NOT_FOUND`)

### 6. `GET /customers/by-phone/{phone}`

- Keep path; document canonicalize-before-lookup
- `404` + `CUSTOMER_NOT_FOUND`

### 7. `DELETE /customers/{customerId}`

- `204` empty; `404` `CUSTOMER_NOT_FOUND`; `409` `CUSTOMER_HAS_UNFINISHED_ORDERS` when related status is not `completed`/`refunded`/`cancelled`; terminal history `SET NULL` + keep name/phone snapshots

### 8. `POST /customers/{customerId}/reward-points`

- Body `{ amount: integer }` (signed)
- `200` `Customer`; `404`; `422` `CUSTOMER_POINTS_INSUFFICIENT` if result &lt; 0

### 9. Out of scope (no YAML yet)

Do not add `POST /customers/{customerId}/spending` in this phase (checkout owns `totalSpent` + checkout point deltas).  
Do not add `GET /customers/{customerId}/preorders` in this customers phase (preorder module).
