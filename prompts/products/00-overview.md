# Products Catalog — Overview

Planning doc for the **product catalog** phase of Fred's POS backend. Companion docs in this folder cover API contract, data model, search rules, and open questions. **No application code is produced by this planning pass.**

## Goals

- Expose a FastAPI catalog that matches the frontend `IProductService` catalog methods so the UI can switch from mock/localStorage to HTTP without rewriting screens.
- Persist products with multi-location stock rows and a separate preorder-pending aggregate (read-only on catalog endpoints).
- Keep **contract → frontend/mock** alignment: OpenAPI is the planned HTTP contract; the FE adapter already ships.

## Scope

### In scope (this phase)

| Method | Path | Maps to |
|--------|------|---------|
| `GET` | `/products` | `IProductService.searchProducts` |
| `POST` | `/products` | `IProductService.createProduct` |
| `GET` | `/products/{productId}` | `IProductService.getProductById` |
| `PUT` | `/products/{productId}` | `IProductService.updateProduct` |

Catalog responsibilities:

- Product **metadata** CRUD (sku, barcode, brand, name, scale, prices, note, status, optional material/color/imageUrl).
- On create: always insert **four** `product_stock` rows at **`quantity: 0`** (`store`, `warehouse`, `company`, `other`). **No** client stock/quantity fields on `POST /products`.
- Server-owned / response-only: `id`, `normalizedSku`, `totalStock`, `preOrderPendingCount`, `stocks` (assembled on read).
- Search filters aligned with the FE mock (`keyword`, `scale`, `brand`, `inStockOnly`); default sort **`sku ASC`**.

### Out of scope (future follow-up)

Inventory and stock mutation APIs are **not** part of this phase; mention only as later work:

- `transferStock` / `adjustStock` / `batchAdjustStock` / `getStockAdjustmentLogs` (planned under `/inventory/*` or equivalent) — **including initial qty after create**.
- Writes to `product_pre_order_pending` (belong to a future preorder module).
- Seeding mock products via Alembic data migration / management script (**decision B**, later phase; see `04-open-questions.md`).

Auth stays optional/dummy for this phase (`src/api/deps.py`).

## Layered architecture

Target layout matches the backend README. Catalog is wired as a thin HTTP layer over a service that owns business rules and persistence.

```
HTTP (api/v1/endpoints/products.py)
  → ProductService (services/product_service.py)
    → ORM models (models/product*.py)
      → DB: product | product_stock | product_pre_order_pending
```

| Layer | Role |
|-------|------|
| **API / endpoints** | Route handlers, query/body parsing, status codes, dependency injection (`get_db`, optional user). No business rules beyond HTTP mapping. |
| **Schemas** | Pydantic request/response DTOs; camelCase JSON (`normalizedSku`, `listPrice`, `preOrderPendingCount`, …) matching FE `Product`. |
| **Services** | SKU normalize, uniqueness, create-time stock upsert, computed `totalStock` / `preOrderPendingCount`, search filters, ignore client overwrite of server-owned fields. |
| **Models + Alembic** | Tables, indexes, uniqueness; migration for `product`, `product_stock`, `product_pre_order_pending`. |

### Planned backend file map (document only — not implemented yet)

| Piece | Path |
|-------|------|
| Schemas | `src/schemas/product.py` |
| Models | `src/models/product.py` (+ stock / preorder-pending) |
| Service | `src/services/product_service.py` |
| Endpoints | `src/api/v1/endpoints/products.py` |
| Router wire-up | `src/api/v1/api.py` |
| Migration | Alembic revision under `alembic/versions/` |

Base URL (planned): `/api/v1` (see `prompts/openapi.yaml` servers).

### Storage sketch (detail in `02-data-model.md`)

- **`product`** — catalog metadata; unique `sku`; `barcode` indexed but **not** unique; timestamps `created_at` / `updated_at`.
- **`product_stock`** — one row per location; unique `(product_id, location)`.
- **`product_pre_order_pending`** — separate table (not a column on `product`); default 1:1 via unique `product_id`; no row ⇒ API returns `preOrderPendingCount: 0`.

`totalStock` = sum of stock quantities; `preOrderPendingCount` = pending table quantity (or `0`). Neither is stored on `product`.

## Frontend alignment

Source of truth for shapes and catalog method signatures:

- FE interface: `freds-pos-fe/src/services/interfaces/IProductService.ts`
- Types: `freds-pos-fe/src/types/product.ts`
- Mock behavior: `freds-pos-fe/src/services/mock/mockProductService.ts`
- SKU normalize: `freds-pos-fe/src/utils/skuNormalizer.ts` (`upper` + strip non `[A-Z0-9]`)
- HTTP contract draft: `prompts/openapi.yaml` (products tag)

### Contract principles

1. OpenAPI is the HTTP source of truth; where it **narrows** vs today’s FE (`Partial<Product>`, create `stocks`), FE adapts — see [`05-fe-changes.md`](./05-fe-changes.md). **Do not edit YAML until implementation is approved**.
2. Response `Product` matches FE: camelCase, four locations in `stocks`, integer TWD prices, `status` ∈ `active` \| `discontinued`.
3. Create request has **no** `stocks` / quantities; server assigns `id`, `normalizedSku`, zeros stocks, `preOrderPendingCount: 0`, `totalStock: 0`.
4. Search semantics mirror the mock (empty keyword = no keyword filter; `scale`/`brand` missing or `ALL` = no filter; `inStockOnly` → `totalStock > 0`). Sort: **`sku ASC`**. Details in `03-search-rules.md`.
5. Catalog `PUT` uses **`UpdateProductRequest`** (metadata only in OpenAPI); stock / preorder never part of that schema.

### ID and create defaults (summary)

- Server assigns opaque `prod-{uuid4}` (no dashes). Do not accept client `id` on create. Seed-style `prod-001` remains valid only as imported data (later seed phase).
- Create always inserts four stock locations at qty `0` with fixed `locationName` map (門市現貨 / 後方倉庫 / 公司總倉 / 調度暫存).

## Doc map

| File | Purpose |
|------|---------|
| `00-overview.md` | This file — goals, scope, architecture, FE alignment |
| `01-api-contract.md` | Endpoint contracts, errors, proposed OpenAPI patch list |
| `02-data-model.md` | Tables, indexes, uniqueness, computed fields, Alembic notes |
| `03-search-rules.md` | Keyword / scale / brand / inStockOnly rules |
| `04-open-questions.md` | Decision log (open questions resolved) |
| `05-fe-changes.md` | FE + OpenAPI change checklist |

## Non-goals for this planning pass

- Implementing endpoints, models, or migrations.
- Changing `prompts/openapi.yaml`.
- Inventory / preorder write APIs.
