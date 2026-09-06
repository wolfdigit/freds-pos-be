# Products Catalog — API Contract

HTTP contract for the four catalog endpoints. Align OpenAPI with decided catalog rules; where the contract **narrows** relative to today’s FE, FE adapts (see [`05-fe-changes.md`](./05-fe-changes.md)). Proposed YAML edits are listed at the end; **do not change** [`prompts/openapi.yaml`](../openapi.yaml) until implementation is approved.

Base path: `/api/v1` (see OpenAPI `servers`).

## Shared response: `Product`

CamelCase JSON matching FE `Product` (`freds-pos-fe/src/types/product.ts`).

| Field | Type | Notes |
|-------|------|--------|
| `id` | string | Server-assigned; opaque `prod-{uuid4}` without dashes |
| `sku` | string | Unique |
| `normalizedSku` | string | Server-owned: `normalizeSku(sku)` |
| `barcode` | string | Required; **not** unique |
| `brand` | string | |
| `name` | string | |
| `scale` | `ModelScale` | `1:18` \| `1:43` \| `1:64` \| `1:24` \| `1:12` \| `配件周邊` |
| `material` | string? | |
| `color` | string? | |
| `imageUrl` | string? | |
| `listPrice` | integer | TWD, ≥ 0 |
| `costPrice` | integer | TWD, ≥ 0 |
| `vipPrice` | integer? | TWD, ≥ 0 when present |
| `stocks` | `LocationStock[]` | Always four locations (see below) |
| `totalStock` | integer | Server-computed: sum of `stocks[].quantity` |
| `preOrderPendingCount` | integer | Server-computed from `product_pre_order_pending` (no row → `0`) |
| `note` | string? | |
| `status` | `active` \| `discontinued` | |

### `LocationStock`

| Field | Type | Notes |
|-------|------|--------|
| `location` | `store` \| `warehouse` \| `company` \| `other` | |
| `locationName` | string | Fixed map (server may overwrite client names) |
| `quantity` | integer | ≥ 0 |

Fixed `locationName` map:

| `location` | `locationName` |
|------------|----------------|
| `store` | 門市現貨 |
| `warehouse` | 後方倉庫 |
| `company` | 公司總倉 |
| `other` | 調度暫存 |

### Server-owned / response-only fields

Not accepted on create or update request schemas:

- `id` (create: never accept)
- `normalizedSku`
- `totalStock`
- `preOrderPendingCount`
- `stocks` (create: server initializes; update: not in contract)

---

## `GET /products` — `searchProducts`

**Maps to:** `IProductService.searchProducts`

### Query parameters

| Name | Type | Default / missing | Behavior |
|------|------|-------------------|----------|
| `keyword` | string | empty / missing | No keyword filter |
| `scale` | `ModelScale` \| `ALL` | missing or `ALL` | No scale filter |
| `brand` | string \| `ALL` | missing or `ALL` | No brand filter (`brand` exact match when set) |
| `inStockOnly` | boolean | `false` | When `true`, only products with `totalStock > 0` |

Search / filter semantics: see [`03-search-rules.md`](./03-search-rules.md).

### Responses

| Status | Body |
|--------|------|
| `200` | `Product[]` |

**Default sort:** `sku ASC` (confirmed). `created_at` / `updated_at` exist for audit only.

Auth: optional/dummy (`deps.get_current_user_optional`).

---

## `POST /products` — `createProduct`

**Maps to:** `IProductService.createProduct` (FE signature must drop stocks; see `05-fe-changes.md`).

### Request body — `CreateProductRequest`

**Required:** `sku`, `barcode`, `brand`, `name`, `scale`, `listPrice`, `costPrice`, `status`

**Optional:** `material`, `color`, `imageUrl`, `vipPrice`, `note`

**Not in request schema:** `id`, `normalizedSku`, `totalStock`, `preOrderPendingCount`, **`stocks` / any quantity fields**

#### Create-time stock rows (server-only)

- Always insert **all four** locations (`store`, `warehouse`, `company`, `other`) with **`quantity: 0`** and fixed `locationName`.
- Client cannot set quantities on create; FE uses future **inventory APIs** after create for initial stock.
- Do **not** insert `product_pre_order_pending` rows; response `preOrderPendingCount` = `0`.

#### `id` generation

Server assigns `prod-{uuid4}` with dashes stripped from the UUID.  
Seed-style `prod-001` remains valid only as imported/seeded data (later phase). Do not accept client `id`.

#### Validation

- `sku` unique → `409` `PRODUCT_SKU_DUPLICATE`.
- `barcode` required string; not unique.
- Prices: non-negative integers (TWD).

### Responses

| Status | Body |
|--------|------|
| `201` | `Product` |
| `409` | `BusinessError` `{ code: PRODUCT_SKU_DUPLICATE, message: 貨號已存在 }` |
| `422` | Validation errors (malformed body / negative prices / invalid enums) |

---

## `GET /products/{productId}` — `getProductById`

**Maps to:** `IProductService.getProductById`

### Path

| Name | Type |
|------|------|
| `productId` | string |

### Responses

| Status | Body |
|--------|------|
| `200` | `Product` |
| `404` | `{ code: PRODUCT_NOT_FOUND, message: 找不到指定商品 }` |

Note: FE mock returns `null` for missing id; HTTP adapter should map `404` → that UX. Backend always returns `404` + `BusinessError`.

---

## `PUT /products/{productId}` — `updateProduct`

**Maps to:** `IProductService.updateProduct` (FE must use `UpdateProductRequest`, not `Partial<Product>`).

### Path

| Name | Type |
|------|------|
| `productId` | string |

### Request body — `UpdateProductRequest` (metadata only)

All fields optional / partial:

`sku`, `barcode`, `brand`, `name`, `scale`, `listPrice`, `costPrice`, `vipPrice`, `note`, `status`, `material`, `color`, `imageUrl`

**Excluded from OpenAPI schema (not part of the contract):**

`stocks`, `totalStock`, `id`, `normalizedSku`, `preOrderPendingCount`

Rules:

- On `sku` change: recompute `normalizedSku`; duplicate → `409` `PRODUCT_SKU_DUPLICATE`.
- Never mutate stock rows or `product_pre_order_pending` via this endpoint.
- Prices: non-negative integers when provided.

### Responses

| Status | Body |
|--------|------|
| `200` | `Product` |
| `404` | `{ code: PRODUCT_NOT_FOUND, message: 找不到指定商品 }` |
| `409` | `{ code: PRODUCT_SKU_DUPLICATE, message: 貨號已存在 }` |
| `422` | Validation errors |

---

## Errors

### `BusinessError` shape

```json
{ "code": "PRODUCT_NOT_FOUND", "message": "找不到指定商品" }
```

### Catalog codes

| HTTP | `code` | When |
|------|--------|------|
| `404` | `PRODUCT_NOT_FOUND` | Missing `productId` on get/update |
| `409` | `PRODUCT_SKU_DUPLICATE` | Duplicate `sku` on create/update |
| `422` | (validation / FastAPI default) | Invalid body or enums |

Auth remains optional/dummy for this phase.

---

## OpenAPI patch recommendations (do not apply yet)

Proposed edits to [`prompts/openapi.yaml`](../openapi.yaml) when implementation is approved. Full FE sync list: [`05-fe-changes.md`](./05-fe-changes.md).

### 1. `CreateProductRequest`

- **Remove from `required`:** `normalizedSku`, `totalStock`, `preOrderPendingCount`, `stocks`
- **Remove `stocks` (and any quantity)** from the create request schema
- Required: `sku`, `barcode`, `brand`, `name`, `scale`, `listPrice`, `costPrice`, `status`
- Optional: `material`, `color`, `imageUrl`, `vipPrice`, `note`

### 2. `POST /products` description

- Server assigns `id` as `prod-{uuid4}` (no dashes)
- Always creates four stock rows at qty `0`; no client quantities
- Does not write `product_pre_order_pending`
- Initial / ongoing stock qty via future inventory APIs

### 3. `UpdateProductRequest`

Replace opaque PUT body with named schema — **metadata fields only**; exclude stock/computed/id fields from the schema entirely.

### 4. Errors

- Extend `BusinessErrorCode` with `PRODUCT_SKU_DUPLICATE`
- Add `409` responses on create/update with example body

### 5. Search

- Document default sort `sku ASC`

### 6. Out of scope (no YAML yet)

Do not add `/inventory/*` paths in this phase.
