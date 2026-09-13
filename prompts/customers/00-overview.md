# Customers — Overview

Planning doc for the **customer / member** phase of Fred's POS backend. Companion docs in this folder cover API contract, data model, search rules, and open questions.

## Goals

- Expose a FastAPI member catalog that matches the frontend `ICustomerService` member methods so the UI can switch from mock/localStorage to HTTP without rewriting screens.
- Persist customers with unique server-assigned ids, unique phone numbers, optional email, VIP tier, and a checkout-owned spending aggregate.
- Keep **contract → frontend/mock** alignment: OpenAPI is the HTTP contract; the FE HTTP adapter already ships and will be tightened where the contract narrows.

## Scope

### In scope (this phase)

| Method | Path | Maps to |
|--------|------|---------|
| `GET` | `/customers` | `ICustomerService.searchCustomers` |
| `POST` | `/customers` | `ICustomerService.createCustomer` |
| `GET` | `/customers/{customerId}` | `ICustomerService.getCustomerById` |
| `PUT` | `/customers/{customerId}` | `ICustomerService.updateCustomer` |
| `DELETE` | `/customers/{customerId}` | `ICustomerService.deleteCustomer` |

Member-catalog responsibilities:

- Customer **profile** CRUD including **delete** (name, phone, optional email, vip tier, note).
- On create: server assigns `id`, `createdAt`, `updatedAt`; always sets `totalSpent: 0`; derives `vipTierName` from `vipTier`. **No** client `id` / `createdAt` / `updatedAt` / `vipTierName` / `totalSpent` on `POST /customers`.
- Server-owned / response-only: `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent` (stored, but checkout-owned after create).
- **No `rewardPoints`** on the member catalog (column, request, response, or search filter). Checkout later owns any sale-time points on orders, not on `customer`.
- Search: query param **`keyword`** (name / phone / email); optional **`vipTier`**; **paged**. Default sort **`name ASC`**. Phone lookup uses this search (substring); **no** `GET /customers/by-phone/{phone}`.
- Filters run **in SQL**, not in Python after load.

### Out of scope (future follow-up)

- `updateCustomerSpending` / `POST /customers/{customerId}/spending` — checkout owns `totalSpent` (and any order-level points) atomically.
- Writes to `totalSpent` from any catalog endpoint (create always `0`; update schema excludes the field).
- `rewardPoints`, `minPoints`, `POST .../reward-points`, `GET .../by-phone/{phone}`.
- Preorder / order history nested under a customer.
- Seeding mock customers (**decision B**, later phase).

Auth stays optional/dummy for this phase (`src/api/deps.py`).

## Layered architecture

```
HTTP (api/v1/endpoints/customers.py)
  → CustomerService (services/customer_service.py)
    → ORM models (models/customer.py)
      → DB: customer
```

| Layer | Role |
|-------|------|
| **API / endpoints** | Route handlers, query/body parsing, status codes, dependency injection (`get_db`, optional user). |
| **Schemas** | Pydantic DTOs; camelCase JSON (`vipTier`, `vipTierName`, `totalSpent`, `createdAt`, `updatedAt`). |
| **Services** | Phone / email normalize, uniqueness, `vipTierName` map, create defaults, **SQL** search + paging, hard delete. |
| **Models + Alembic** | Table, indexes, uniqueness; migration for `customer`. |

| Piece | Path |
|-------|------|
| Schemas | `src/schemas/customer.py` |
| Models | `src/models/customer.py` |
| Service | `src/services/customer_service.py` |
| Endpoints | `src/api/v1/endpoints/customers.py` |
| Router wire-up | `src/api/v1/api.py` |
| Migration | Alembic revision under `alembic/versions/` |

Base URL: `/api/v1` (see [`../openapi.yaml`](../openapi.yaml) servers).

### Storage sketch (detail in `02-data-model.md`)

- **`customer`** — PK **`id`**; unique `phone`; optional unique `email` (lowercased when set; `NULL` allowed); timestamps `created_at` / `updated_at` (both in JSON).
- **`vip_tier_name` is not stored** — assembled on read.
- **`total_spent`** stored; create initializes `0`; catalog update must not accept it.
- **No `reward_points` column.**

## Frontend alignment

- FE interface: `freds-pos-fe/src/services/interfaces/ICustomerService.ts`
- Types: `freds-pos-fe/src/types/customer.ts`
- Mock: `freds-pos-fe/src/services/mock/mockCustomerService.ts`
- HTTP adapter: `freds-pos-fe/src/services/api/httpCustomerService.ts`
- UI: `CustomerModal`, `CustomersPage`, checkout `CustomerBindCard`
- HTTP contract: [`../openapi.yaml`](../openapi.yaml)

### Contract principles

1. OpenAPI is the HTTP source of truth ([`../openapi.yaml`](../openapi.yaml)). FE adapts later — [`05-fe-changes.md`](./05-fe-changes.md).
2. Response `Customer`: camelCase, integer TWD `totalSpent`, **optional** `email` (`null` allowed), `vipTier` ∈ `regular` \| `silver` \| `gold` \| `platinum`, `vipTierName` from the map, **`createdAt` and `updatedAt`** ISO 8601. **No `rewardPoints`.**
3. Create: **required** `name`, `phone`. **Optional** `email` (omit / `null` → store `NULL`), `vipTier` (omit → `regular`), `note` (optional string).
4. Search: `keyword` + `vipTier` + **`page` / `pageSize`**. Keyword matches name / phone / email (skip email when `NULL`). Phone bind uses `keyword` (no separate by-phone API). SQL-only filters. Sort `name ASC`. See `03-search-rules.md`.
5. `PUT` profile-only: `name`, `phone`, `email` (may be `null` to clear), `vipTier`, `note`. Never `id` / `createdAt` / `updatedAt` / `vipTierName` / `totalSpent`.
6. `DELETE` hard-delete; API-only UI this phase; `409` if unfinished orders once those tables exist.

### ID and create defaults

- Server assigns `cust-{uuid4}` (no dashes) into PK **`id`**.
- Create always `totalSpent: 0`, derives `vipTierName`. Missing **`vipTier` → `regular`**.
- Phone stored canonical (strip spaces / hyphens / parentheses); unique.
- Email optional: omit / `null` / whitespace → `NULL`. Non-null: trim + lowercase, valid format, unique among non-null rows. Duplicate → `409` `CUSTOMER_EMAIL_DUPLICATE`; malformed → `422`.

## Doc map

| File | Purpose |
|------|---------|
| `00-overview.md` | This file |
| `01-api-contract.md` | Endpoint contracts, errors |
| `02-data-model.md` | Table, indexes, uniqueness |
| `03-search-rules.md` | Keyword / vipTier / paging / SQL filters |
| `04-open-questions.md` | Decision log |
| `05-fe-changes.md` | FE checklist (later) |
| [`../openapi.yaml`](../openapi.yaml) | Merged HTTP contract |
