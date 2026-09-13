# Customers — API Contract

HTTP contract for the five member-catalog endpoints. The YAML is [`../openapi.yaml`](../openapi.yaml). Where the contract narrows vs today’s FE, FE adapts later ([`05-fe-changes.md`](./05-fe-changes.md)).

Base path: `/api/v1`.

## Shared response: `Customer`

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server-assigned PK; `cust-{uuid4}` without dashes |
| `name` | string | Required |
| `phone` | string | Unique; stored canonical |
| `email` | string \| `null` | **Optional.** Unique among non-null values after trim + lowercase. Valid email when set |
| `vipTier` | `VipTier` | `regular` \| `silver` \| `gold` \| `platinum` |
| `vipTierName` | string | Derived map from `vipTier` |
| `totalSpent` | integer | TWD ≥ 0; server-owned after create (always `0` on create) |
| `note` | string | **Optional string.** Omit or `""`. Not OpenAPI `nullable` |
| `createdAt` | string | Server-assigned ISO 8601 |
| `updatedAt` | string | Server-assigned ISO 8601; set on insert and every profile update |

**Not in the contract:** `rewardPoints`.

### `VipTier` → `vipTierName` map

| `vipTier` | `vipTierName` |
|-----------|----------------|
| `platinum` | 白金黑卡 (9折) |
| `gold` | 金卡會員 (95折) |
| `silver` | 銀卡會員 (98折) |
| `regular` | 一般會員 |

### Server-owned / response-only

Not on create or update request schemas: `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent`.

---

## `GET /customers` — `searchCustomers`

**Maps to:** `ICustomerService.searchCustomers`

Phone lookup for checkout bind uses this endpoint (`keyword` = phone fragment). There is **no** `GET /customers/by-phone/{phone}`.

### Query parameters

| Name | Type | Default / missing | Behavior |
|------|------|-------------------|----------|
| `keyword` | string | empty / missing | No keyword filter |
| `vipTier` | `VipTier` \| `ALL` | missing or `ALL` | No VIP filter; otherwise exact match |
| `page` | integer ≥ 1 | `1` | 1-based page index |
| `pageSize` | integer 1–100 | `20` | Page length; `> 100` → `422` |

All filters run **in SQL** (`WHERE` + `ORDER BY` + `LIMIT`/`OFFSET`). Do not load the full table then filter in Python.

### Response `200` — `CustomerSearchResponse`

| Field | Type | Notes |
|-------|------|--------|
| `items` | `Customer[]` | Current page, sort `name ASC`, tie-break `id ASC` |
| `page` | integer | Echo of the request page (clamped to ≥ 1) |
| `pageSize` | integer | Echo of the request page size |
| `total` | integer | Total rows matching filters (not just this page) |

Empty page: `items: []`, `total` still set.

---

## `POST /customers` — `createCustomer`

**Required:** `name`, `phone`

**Optional:** `email` (omit / `null` → `NULL`), `vipTier` (default `regular`), `note`

**Not in request schema:** `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent`, `rewardPoints`

### Create-time defaults

- `totalSpent: 0`
- `vipTierName` from the map; missing `vipTier` → `regular`
- `createdAt` / `updatedAt` = UTC now
- `id` = `cust-{uuid4}` no dashes

### Validation

- `email` omitted, `null`, or whitespace-only → store `NULL` (not 422).
- Non-null email: trim + lowercase; invalid format → `422`; duplicate among non-null → `409` `CUSTOMER_EMAIL_DUPLICATE`.
- `phone` unique after canonicalize → `409` `CUSTOMER_PHONE_DUPLICATE`.
- `name` / canonical `phone` required non-empty.

### Responses

| Status | Body |
|--------|------|
| `201` | `Customer` |
| `409` | `CUSTOMER_PHONE_DUPLICATE` or `CUSTOMER_EMAIL_DUPLICATE` |
| `422` | Validation errors |

---

## `GET /customers/{customerId}` — `getCustomerById`

| Status | Body |
|--------|------|
| `200` | `Customer` |
| `404` | `CUSTOMER_NOT_FOUND` |

---

## `PUT /customers/{customerId}` — `updateCustomer`

Partial: `name`, `phone`, `email`, `vipTier`, `note`

**Excluded:** `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent`, `rewardPoints`

Rules:

- Phone change: canonicalize; duplicate → `409`.
- Email: omit → unchanged. `null` or whitespace → clear to `NULL`. Non-null must be valid unique (trim + lowercase).
- `vipTier` change: name derived on read.
- Never mutate `totalSpent` / `id` / `createdAt`. Bump `updatedAt`.
- `note`: optional string; omit → unchanged; `""` is a valid empty string.

| Status | Body |
|--------|------|
| `200` | `Customer` |
| `404` | `CUSTOMER_NOT_FOUND` |
| `409` | phone or email duplicate |
| `422` | Validation errors |

---

## `DELETE /customers/{customerId}` — `deleteCustomer`

Hard-delete. **FE API-only** this phase.

Unfinished order/preorder → `409` `CUSTOMER_HAS_UNFINISHED_ORDERS` (cannot fire until those tables exist). Terminal history: `SET NULL` + keep name/phone snapshots.

| Status | Body |
|--------|------|
| `204` | Empty |
| `404` | `CUSTOMER_NOT_FOUND` |
| `409` | `CUSTOMER_HAS_UNFINISHED_ORDERS` |

---

## Removed from this phase

| Path | Reason |
|------|--------|
| `GET /customers/by-phone/{phone}` | Phone lookup is `GET /customers?keyword=` |
| `POST /customers/{customerId}/reward-points` | No member `rewardPoints` |

---

## Errors

```json
{ "code": "CUSTOMER_NOT_FOUND", "message": "找不到指定的會員" }
```

| HTTP | `code` | When |
|------|--------|------|
| `404` | `CUSTOMER_NOT_FOUND` | Missing `customerId` on get/update/delete |
| `409` | `CUSTOMER_PHONE_DUPLICATE` | Duplicate canonical phone |
| `409` | `CUSTOMER_EMAIL_DUPLICATE` | Duplicate non-null lowercased email |
| `409` | `CUSTOMER_HAS_UNFINISHED_ORDERS` | Delete blocked (after checkout/preorder exist) |
| `422` | (FastAPI default) | Invalid body, empty name/phone, malformed email, bad page/pageSize, invalid enums |

Auth: optional/dummy.

---

## OpenAPI

Keep [`../openapi.yaml`](../openapi.yaml) in sync with this file.

- Search returns `CustomerSearchResponse`; params `keyword`, `vipTier`, `page`, `pageSize`.
- No `by-phone`, no `reward-points`, no `rewardPoints` / `minPoints`.
- `email` optional; OpenAPI 3.1 type `[string, null]` on response and request (always present on response, value may be `null`).
- `note` optional `string` only — do **not** mark `nullable: true` / `null` in the type.
- `createdAt` and `updatedAt` on `Customer`.
- Do not add spending / nested preorder paths.
