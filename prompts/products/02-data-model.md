# Products Catalog — Data Model

Persistence design for catalog endpoints. Tables: `product`, `product_stock`, `product_pre_order_pending`. Response DTO maps snake_case DB → camelCase JSON to match FE / OpenAPI `Product`.

## ER sketch

```mermaid
erDiagram
  product ||--o{ product_stock : has
  product ||--o| product_pre_order_pending : has
  product {
    string id PK
    string sku UK
    string normalized_sku
    string barcode
    string brand
    string name
    string scale
    string material
    string color
    string image_url
    int list_price
    int cost_price
    int vip_price
    string status
    string note
    datetime created_at
    datetime updated_at
  }
  product_stock {
    int id PK
    string product_id FK
    string location
    string location_name
    int quantity
  }
  product_pre_order_pending {
    int id PK
    string product_id FK UK
    int quantity
  }
```

---

## Table: `product`

Catalog metadata only. **Does not** store `total_stock` or `pre_order_pending_count`.

| Column | Type (suggested) | Constraints / notes |
|--------|------------------|---------------------|
| `id` | `VARCHAR` / `String` PK | Opaque `prod-{uuid4}` without dashes; seed may use `prod-001` style |
| `sku` | `String` | **UNIQUE**, required |
| `normalized_sku` | `String` | Server-maintained; same rules as FE `normalizeSku` |
| `barcode` | `String` | Required; **not** unique |
| `brand` | `String` | |
| `name` | `String` | |
| `scale` | `String` | Enum values: `1:18`, `1:43`, `1:64`, `1:24`, `1:12`, `配件周邊` |
| `material` | `String` nullable | |
| `color` | `String` nullable | |
| `image_url` | `String` nullable | → JSON `imageUrl` |
| `list_price` | `Integer` | TWD ≥ 0 → `listPrice` |
| `cost_price` | `Integer` | TWD ≥ 0 → `costPrice` |
| `vip_price` | `Integer` nullable | TWD ≥ 0 → `vipPrice` |
| `status` | `String` | `active` \| `discontinued` |
| `note` | `Text` / `String` nullable | |
| `created_at` | `DateTime` TZ | Server set on insert |
| `updated_at` | `DateTime` TZ | Server set on insert/update |

### Indexes / uniqueness

| Index | Columns | Unique? | Purpose |
|-------|---------|---------|---------|
| PK | `id` | yes | |
| UK | `sku` | yes | Duplicate SKU → API conflict |
| IX | `barcode` | **no** | Keyword search by barcode (confirmed) |
| IX | `normalized_sku` | no (optional) | Faster SKU-contains keyword search |
| IX | `brand` | no (optional) | Brand filter |
| IX | `created_at` / `sku` | — | Default list sort `sku ASC` |

**Confirmed:** `barcode` is **not** unique — multiple products may share a barcode; keyword search may return multiple rows.

---

## Table: `product_stock`

One row per product per location. Catalog create **always inserts** all four locations at **`quantity: 0`** (no client quantities on `POST /products`).

| Column | Type (suggested) | Constraints / notes |
|--------|------------------|---------------------|
| `id` | `Integer` PK / serial | Surrogate key |
| `product_id` | `String` FK → `product.id` | `ON DELETE CASCADE` recommended |
| `location` | `String` | `store` \| `warehouse` \| `company` \| `other` |
| `location_name` | `String` | Fixed display map (門市現貨 / 後方倉庫 / 公司總倉 / 調度暫存) |
| `quantity` | `Integer` | ≥ 0; default `0` |

### Indexes / uniqueness

| Index | Columns | Unique? | Purpose |
|-------|---------|---------|---------|
| UK | `(product_id, location)` | yes | One row per location |
| IX | `product_id` | no | Load stocks for a product |

Catalog **PUT** must not change these rows. Stock mutations belong to future `/inventory/*` APIs.

---

## Table: `product_pre_order_pending`

Separate from catalog columns. Holds pending preorder quantity for API field `preOrderPendingCount`.

| Column | Type (suggested) | Constraints / notes |
|--------|------------------|---------------------|
| `id` | `Integer` PK / serial | |
| `product_id` | `String` FK → `product.id` | **UNIQUE** (default **1:1** with product) |
| `quantity` | `Integer` | ≥ 0; pending count source |

### Behavior

- No row for a product ⇒ API returns `preOrderPendingCount: 0`.
- With 1:1 unique `product_id`, lookup is a single row (equivalent to SUM of one value).
- Catalog endpoints are **read-only** for this table.
- Catalog create/update must **not** accept client overwrite of pending count and must **not** insert/update rows here.
- Writes belong to a future preorder module.

Evolution (decided path): keep **1:1** for this phase; later may replace with summing real `pre_order` / line-item rows; keep computed response field so the API shape stays stable.

---

## Server-computed response fields

Not stored on `product`:

| API field | Computation |
|-----------|-------------|
| `totalStock` | `SUM(product_stock.quantity)` for the product (missing rows treated as absent; create always ensures four rows) |
| `preOrderPendingCount` | Pending row `quantity`, or `0` if no row |
| `normalizedSku` | Stored on `product.normalized_sku` but always derived from `sku` on write (`upper` + strip non `[A-Z0-9]`); never trust client |
| `stocks` | Assembled from `product_stock` rows → camelCase `LocationStock[]` |

---

## ORM / module map (planned, not implemented)

| Piece | Path |
|-------|------|
| Models | `src/models/product.py` (or split `product_stock` / `product_pre_order_pending`) |
| Schemas | `src/schemas/product.py` |
| Service | `src/services/product_service.py` |
| Endpoints | `src/api/v1/endpoints/products.py` |
| Router | `src/api/v1/api.py` |
| Migration | `alembic/versions/…` |

Register models in `src/models/__init__.py` / `src/db/base.py` so Alembic autogenerate sees them.

---

## Alembic notes

1. First revision: **schema only** — all three tables + indexes/constraints above (no seed data).
2. Prefer explicit FK + unique constraints in migration (not only ORM).
3. **Seed later (decision B):** Alembic data migration and/or management script — insert `product` + four `product_stock` rows per item; omit pending rows unless seed needs non-zero pending. See [`04-open-questions.md`](./04-open-questions.md).
4. `created_at` / `updated_at`: use timezone-aware UTC; update `updated_at` in service on metadata PUT.

---

## Mapping cheatsheet (DB → JSON)

| DB | JSON |
|----|------|
| `normalized_sku` | `normalizedSku` |
| `image_url` | `imageUrl` |
| `list_price` | `listPrice` |
| `cost_price` | `costPrice` |
| `vip_price` | `vipPrice` |
| `location_name` | `locationName` |
| (computed) | `totalStock`, `preOrderPendingCount` |
