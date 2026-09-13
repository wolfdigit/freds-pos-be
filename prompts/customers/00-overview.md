# Customers — Overview

Planning doc for the **customer / member** phase of Fred's POS backend. Companion docs in this folder cover API contract, data model, search rules, and open questions. **No application code is produced by this planning pass.**

## Goals

- Expose a FastAPI member catalog that matches the frontend `ICustomerService` member methods so the UI can switch from mock/localStorage to HTTP without rewriting screens.
- Persist customers with unique server-assigned ids, unique phone numbers, a **required unique valid email**, VIP tier, cashier-adjustable reward points, and a checkout-owned spending aggregate.
- Keep **contract → frontend/mock** alignment: OpenAPI is the planned HTTP contract; the FE HTTP adapter already ships and will be tightened where the contract narrows.

## Scope

### In scope (this phase)

| Method | Path | Maps to |
|--------|------|---------|
| `GET` | `/customers` | `ICustomerService.searchCustomers` |
| `POST` | `/customers` | `ICustomerService.createCustomer` |
| `GET` | `/customers/{customerId}` | `ICustomerService.getCustomerById` |
| `PUT` | `/customers/{customerId}` | `ICustomerService.updateCustomer` |
| `DELETE` | `/customers/{customerId}` | `ICustomerService.deleteCustomer` |
| `GET` | `/customers/by-phone/{phone}` | `ICustomerService.getCustomerByPhone` |
| `POST` | `/customers/{customerId}/reward-points` | `ICustomerService.addRewardPoints` |

Member-catalog responsibilities:

- Customer **profile** CRUD including **delete** (name, phone, **required unique valid email**, vip tier, note, optional initial / cashier-set `rewardPoints`).
- On create: server assigns `id` and `createdAt`; always sets `totalSpent: 0`; derives `vipTierName` from `vipTier`. **No** client `id` / `createdAt` / `vipTierName` / `totalSpent` on `POST /customers`.
- Server-owned / response-only: `id`, `createdAt`, `vipTierName`, `totalSpent` (stored, but checkout-owned after create).
- **Reward points:** `PUT` **`rewardPoints` replaces** the balance; `POST .../reward-points` **`amount` adds** (integer; may be negative). Balance stays ≥ 0.
- Search aligned with products: query param **`keyword`**; match **name** / **phone** / **email**; optional **`vipTier`** and **`minPoints`**; default sort **`name ASC`**.
- Exact phone lookup for checkout bind (`getCustomerByPhone`).

### Out of scope (future follow-up)

Spending / points mutation as a side-effect of checkout, plus related member APIs, are **not** part of this phase; mention only as later work:

- `updateCustomerSpending` / `POST /customers/{customerId}/spending` — **including incrementing `totalSpent` and checkout-earned points**. Checkout owns this atomically. Catalog still has **replace** (`PUT rewardPoints`) and **add** (`POST .../reward-points`) for cashier adjustments.
- Writes to `totalSpent` from any catalog endpoint (create always `0`; update schema excludes the field).
- Preorder / order history nested under a customer (`GET /customers/{id}/preorders`, history tabs) — those belong to preorder / checkout modules; this phase only returns the `Customer` profile.
- Seeding mock customers via Alembic data migration / management script (**decision B**, later phase; see `04-open-questions.md`).

Auth stays optional/dummy for this phase (`src/api/deps.py`).

## Layered architecture

Target layout matches the backend README and the products catalog. Members are wired as a thin HTTP layer over a service that owns business rules and persistence.

```
HTTP (api/v1/endpoints/customers.py)
  → CustomerService (services/customer_service.py)
    → ORM models (models/customer.py)
      → DB: customer
```

| Layer | Role |
|-------|------|
| **API / endpoints** | Route handlers, query/body parsing, status codes, dependency injection (`get_db`, optional user). No business rules beyond HTTP mapping. |
| **Schemas** | Pydantic request/response DTOs; camelCase JSON (`vipTier`, `vipTierName`, `rewardPoints`, `totalSpent`, `createdAt`) matching FE `Customer`. |
| **Services** | Phone / email normalize, uniqueness, `vipTierName` map, create defaults, search filters, `rewardPoints` replace vs add, hard delete, ignore client overwrite of server-owned fields. |
| **Models + Alembic** | Table, indexes, uniqueness; migration for `customer`. |

### Planned backend file map (document only — not implemented yet)

| Piece | Path |
|-------|------|
| Schemas | `src/schemas/customer.py` |
| Models | `src/models/customer.py` |
| Service | `src/services/customer_service.py` |
| Endpoints | `src/api/v1/endpoints/customers.py` |
| Router wire-up | `src/api/v1/api.py` |
| Migration | Alembic revision under `alembic/versions/` |

Base URL (planned): `/api/v1` (see [`../openapi.yaml`](../openapi.yaml) servers).

### Storage sketch (detail in `02-data-model.md`)

- **`customer`** — member profile; PK **`id`** (same pattern as `product.id`); unique `phone` (canonical digits); unique `email` (lowercased, required, valid format); timestamps `created_at` / `updated_at`.
- **`vip_tier_name` is not stored** — assembled on read from a fixed `vipTier` map (same copy as FE `getVipTierName`).
- **`total_spent`** is stored on `customer` (running aggregate). Catalog create initializes `0`; catalog update must not accept it; checkout later increments it.
- **`reward_points`** is stored on `customer`. Create may set it; `PUT` **replaces**; `POST .../reward-points` **adds**; checkout later also adds/subtracts.

`vipTierName` is derived; `id` / `createdAt` are server-assigned. None of those are accepted on create/update request schemas.

## Frontend alignment

Source of truth for shapes and member method signatures:

- FE interface: `freds-pos-fe/src/services/interfaces/ICustomerService.ts`
- Types: `freds-pos-fe/src/types/customer.ts` (`Customer`, `VipTier`, `getVipTierName`)
- Mock behavior: `freds-pos-fe/src/services/mock/mockCustomerService.ts`
- HTTP adapter (already shipped): `freds-pos-fe/src/services/api/httpCustomerService.ts`
- UI: `CustomerModal`, `CustomersPage`, checkout `CustomerBindCard`
- HTTP contract: [`../openapi.yaml`](../openapi.yaml) (customers tag; merged with products)

### Contract principles

1. OpenAPI is the HTTP source of truth ([`../openapi.yaml`](../openapi.yaml)); where it **narrows** vs today’s FE (`Omit<Customer, 'id' | 'createdAt'>`, `Partial<Customer>`, create `vipTierName` / `totalSpent`), FE adapts later — see [`05-fe-changes.md`](./05-fe-changes.md).
2. Response `Customer` matches FE: camelCase, integer TWD `totalSpent`, integer `rewardPoints`, required `email`, `vipTier` ∈ `regular` \| `silver` \| `gold` \| `platinum`, `vipTierName` from the fixed map.
3. Create request has **no** `id` / `createdAt` / `vipTierName` / `totalSpent`; server assigns `id`, `createdAt`, `vipTierName`, `totalSpent: 0`. **Required:** `name`, `phone`, `email`. **`vipTier` optional** — omit → `regular`.
4. Search: empty / missing **`keyword`** = no keyword filter; name case-insensitive contains; phone substring; email contains. Optional **`vipTier`** (`ALL` / missing = no filter, else exact) and **`minPoints`** (`rewardPoints >= minPoints`). Filters AND-combined. Sort: **`name ASC`**. Details in `03-search-rules.md`.
5. Catalog `PUT` uses **`UpdateCustomerRequest`**; `id` / `createdAt` / `vipTierName` / `totalSpent` never part of that schema. `rewardPoints` on PUT **replaces**. Add uses `POST /customers/{id}/reward-points`.
6. `DELETE /customers/{customerId}` hard-deletes the row. **API-only** this phase (no FE delete control). Denied with `409` if any related order/preorder is **unfinished** (not `completed`, `refunded`, or `cancelled`). Terminal history is kept: later `customer_id` **`SET NULL`**, **name/phone snapshots stay**. This phase has none of those tables, so the check cannot fire yet.

### ID and create defaults (summary)

- Server assigns opaque `cust-{uuid4}` (no dashes) into PK column **`id`** (JSON `id`, path `{customerId}` — same three-way identity as products’ `prod-…` / `id` / `{productId}`). Do not accept client `id` on create. Seed-style `cust-001` remains valid only as imported data (later seed phase).
- Create always sets `totalSpent: 0`, derives `vipTierName`. Missing `rewardPoints` → `0`. Missing **`vipTier` → `regular`**.
- Phone is stored in canonical form (strip spaces / hyphens / parentheses); uniqueness is on that canonical value.
- Email is required: trim + lowercase, valid format, **unique**. Duplicate → `409` `CUSTOMER_EMAIL_DUPLICATE`; missing / invalid → `422`.

## Doc map

| File | Purpose |
|------|---------|
| `00-overview.md` | This file — goals, scope, architecture, FE alignment |
| `01-api-contract.md` | Endpoint contracts, errors, proposed OpenAPI patch list |
| `02-data-model.md` | Table, indexes, uniqueness, computed fields, Alembic notes |
| `03-search-rules.md` | Query `keyword` / `vipTier` / `minPoints` / name / phone / email / exact-phone rules |
| `04-open-questions.md` | Decision log (open questions resolved) |
| `05-fe-changes.md` | FE checklist (later pass; this implement pass is backend only) |
| [`../openapi.yaml`](../openapi.yaml) | Merged HTTP contract (products + customers) |

## Non-goals for this planning pass

- Implementing endpoints, models, or migrations.
- Changing frontend code (this implement pass is backend only).
- Nested preorder or order-history endpoints under a customer.
