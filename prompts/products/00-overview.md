# Products Catalog — Overview

The **product catalog** phase of Fred's POS backend. Companion docs in this folder cover API contract, data model, search rules, and open questions. **No application code is produced by this planning pass.**

## Goals

- Expose a FastAPI catalog that matches the frontend `IProductService` catalog methods so the UI can switch from mock/localStorage to HTTP without rewriting screens.
- Persist products with multi-location stock rows and a separate preorder-pending aggregate (read-only on catalog endpoints).
- Keep **contract → frontend/mock** alignment: OpenAPI is the planned HTTP contract; the FE adapter already ships.



## Scope



### In scope (this phase)


| Method | Path                    | Maps to                          |
| ------ | ----------------------- | -------------------------------- |
| `GET`  | `/products`             | `IProductService.searchProducts` |
| `POST` | `/products`             | `IProductService.createProduct`  |
| `GET`  | `/products/{productId}` | `IProductService.getProductById` |
| `PUT`  | `/products/{productId}` | `IProductService.updateProduct`  |


Catalog responsibilities:

- Product **metadata** CRUD (sku, barcode, brand, name, scale, list price, optional vip price, note, optional material/color/imageUrl). The catalog does not record `costPrice`. `status` records soft delete: `active` or `deleted`.
- On create: do not insert inventory rows. A missing row reads as `0`. **No** client quantity fields on `POST /products`.
- Server-owned / response-only: `id`, `normalizedSku`, `totalInventory`, `preOrderPendingCount`, `inventories` (assembled on read). `totalInventory` sums every location, including negatives.
- Search filters aligned with the FE mock (`keyword`, `scale`, `brand`, `inInventoryOnly`); default sort **`sku ASC`**. Filters run **in SQL**, not in Python after load.

### Also in the OpenAPI

Inventory transfers, adjustments, locations, pre-orders, store branches, and OAuth accounts are in [`../openapi.yaml`](../openapi.yaml). Catalog create does not insert inventory rows.

Out of this catalog write-up:

- Seeding mock products via Alembic data migration / management script (**decision B**, later phase; see `04-open-questions.md`).

Auth stays optional/dummy for this phase (`src/api/deps.py`).

## Layered architecture

Target layout matches the backend README. Catalog is wired as a thin HTTP layer over a service that owns business rules and persistence.

```
HTTP (api/v1/endpoints/products.py)
  → ProductService (services/product_service.py)
    → ORM models (models/product*.py)
      → DB: product | product_inventory | product_pre_order_pending
```

| Layer | Role |
|-------|------|
| **API / endpoints** | Route handlers, query/body parsing, status codes, dependency injection (`get_db`, optional user). No business rules beyond HTTP mapping. |
| **Schemas** | Pydantic request/response DTOs; camelCase JSON (`normalizedSku`, `listPrice`, `preOrderPendingCount`, …) matching FE `Product`. |
| **Services** | SKU normalize, uniqueness, create-time stock upsert, computed `totalInventory` / `preOrderPendingCount`, search filters, ignore client overwrite of server-owned fields. |
| **Models + Alembic** | Tables, indexes, uniqueness; migration for `product`, `product_inventory`, `product_pre_order_pending`. |

### Planned backend file map (document only — not implemented yet)

| Piece | Path |
|-------|------|
| Schemas | `src/schemas/product.py` |
| Models | `src/models/product.py` (+ stock / preorder-pending) |
| Service | `src/services/product_service.py` |
| Endpoints | `src/api/v1/endpoints/products.py` |
| Router wire-up | `src/api/v1/api.py` |
| Migration | Alembic revision under `alembic/versions/` |

Base URL (planned): `/api/v1` (see [`../openapi.yaml`](../openapi.yaml) servers).

### Storage sketch (detail in `02-data-model.md`)

- **`product`** — catalog metadata; unique `sku`; `barcode` indexed but **not** unique; timestamps `created_at` / `updated_at`. Rows are not deleted. `PUT` sets `deleted` to hide or restore a product and leaves the id in place for checkout history and returns.
- **`product_inventory`** — one row per location; unique `(product_id, location)`.
- **`product_pre_order_pending`** — separate table (not a column on `product`); default 1:1 via unique `product_id`; no row ⇒ API returns `preOrderPendingCount: 0`.

`totalInventory` = sum of stock quantities; `preOrderPendingCount` = pending table quantity (or `0`). Neither is stored on `product`.

## Frontend alignment

Source of truth for shapes and catalog method signatures:

- FE interface: `freds-pos-fe/src/services/interfaces/IProductService.ts`
- Types: `freds-pos-fe/src/types/product.ts`
- Mock behavior: `freds-pos-fe/src/services/mock/mockProductService.ts`
- SKU normalize: `freds-pos-fe/src/utils/skuNormalizer.ts` (`upper` + strip non `[A-Z0-9]`)
- HTTP contract: [`../openapi.yaml`](../openapi.yaml) (products tag; merged with customers)

### Contract principles

1. OpenAPI is the HTTP source of truth ([`../openapi.yaml`](../openapi.yaml)); where it **narrows** vs today’s FE (`Partial<Product>`, create `stocks`), FE adapts — see [`05-fe-changes.md`](./05-fe-changes.md).
2. Response `Product` is camelCase, with one `inventories` entry per location that has a row, integer TWD `listPrice`. There is no `costPrice`. `status` is `active` or `deleted`, and `deleted` mirrors it.
3. Create request has **no** `inventories` / quantities. Server assigns `id`, `normalizedSku`, `preOrderPendingCount: 0`, and `totalInventory: 0`.
4. Search semantics mirror the mock (empty keyword = no keyword filter; `scale`/`brand` missing or `ALL` = no filter; `inInventoryOnly` → `totalInventory > 0`). Sort: **`sku ASC`**. Filters run **in SQL**. Details in `03-search-rules.md`.
5. Catalog `PUT` uses **`UpdateProductRequest`** (metadata only in OpenAPI); stock / preorder never part of that schema.

### ID and create defaults (summary)

- Server assigns opaque `prod-{uuid4}` (no dashes). Do not accept client `id` on create. Seed-style `prod-001` remains valid only as imported data (later seed phase).
- Create does not insert inventory rows. Quantity appears after a receipt, transfer, adjustment, or checkout.

## Doc map

| File | Purpose |
|------|---------|
| `00-overview.md` | This file — goals, scope, architecture, FE alignment |
| `01-api-contract.md` | Endpoint contracts, errors, proposed OpenAPI patch list |
| `02-data-model.md` | Tables, indexes, uniqueness, computed fields, Alembic notes |
| `03-search-rules.md` | Keyword / scale / brand / inInventoryOnly rules |
| `04-open-questions.md` | Decision log (open questions resolved) |
| `05-fe-changes.md` | FE + OpenAPI change checklist |
| [`../openapi.yaml`](../openapi.yaml) | Merged HTTP contract (products + customers) |

## Non-goals for this planning pass

- Implementing endpoints, models, or migrations.
- Inventory / preorder write APIs.
