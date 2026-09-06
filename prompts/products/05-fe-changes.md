# Products Catalog — Frontend & OpenAPI Change Notes

Checklist of **everything the frontend and `prompts/openapi.yaml` must change** to match the decided catalog contract. Backend implementation should treat this as the FE/contract sync list; apply YAML when BE implementation starts; FE can land in one or more PRs.

Related planning: [`00-overview.md`](./00-overview.md), [`01-api-contract.md`](./01-api-contract.md), [`04-open-questions.md`](./04-open-questions.md).

---

## 1. OpenAPI (`prompts/openapi.yaml`) — BE-owned, FE consumes

Apply when catalog implementation is approved (not before).

| Change | Detail |
|--------|--------|
| `CreateProductRequest.required` | Remove `normalizedSku`, `totalStock`, `preOrderPendingCount`, **`stocks`**. Keep: `sku`, `barcode`, `brand`, `name`, `scale`, `listPrice`, `costPrice`, `status`. |
| `CreateProductRequest` properties | Remove or stop documenting client `stocks` / any quantity fields. Optional metadata only: `material`, `color`, `imageUrl`, `vipPrice`, `note`. Server-owned fields (`normalizedSku`, `totalStock`, `preOrderPendingCount`, `id`) must not be required; if listed, mark as response-only / ignore on create. |
| `POST /products` description | Server assigns `id` (`prod-{uuid4}` no dashes); always creates four stock rows at qty `0`; does not write `product_pre_order_pending`; real stock qty via future inventory APIs. |
| New `UpdateProductRequest` | Replace opaque PUT `type: object` with named schema: metadata fields only (`sku`, `barcode`, `brand`, `name`, `scale`, `listPrice`, `costPrice`, `vipPrice`, `note`, `status`, `material`, `color`, `imageUrl`). **Exclude** `stocks`, `totalStock`, `id`, `normalizedSku`, `preOrderPendingCount`. |
| `PUT` description | Metadata only; stock / pending never mutated here. |
| `BusinessErrorCode` | Add `PRODUCT_SKU_DUPLICATE`. |
| Create/update responses | Document `409` + example `{ code: PRODUCT_SKU_DUPLICATE, message: 貨號已存在 }`. |
| `GET /products` | Note default sort `sku ASC`; keep search param semantics (`keyword`, `scale`/`ALL`, `brand`/`ALL`, `inStockOnly`). |
| Inventory paths | **Do not** add `/inventory/*` in this catalog phase (separate pass). |

---

## 2. FE types (`freds-pos-fe/src/types/…`)

| Change | Detail |
|--------|--------|
| Add `CreateProductRequest` (or equivalent) | Match OpenAPI create: no `id`, `normalizedSku`, `totalStock`, `preOrderPendingCount`, **no `stocks` / quantities**. |
| Add `UpdateProductRequest` | Metadata-only partial; **not** `Partial<Product>`. |
| Keep `Product` response type | Unchanged shape for list/detail responses (still includes `stocks`, `totalStock`, `preOrderPendingCount`). |

---

## 3. FE service layer

| File / API | Change |
|------------|--------|
| `IProductService.createProduct` | Argument type → create request without stocks/server fields (align signature with OpenAPI). |
| `IProductService.updateProduct` | Second arg → `UpdateProductRequest` instead of `Partial<Product>`. |
| `mockProductService.createProduct` | Stop relying on client `stocks` for initial qty; always persist four locations at `0` (mirror BE). Initial qty only via inventory mock methods after create. |
| `mockProductService.updateProduct` | Only apply metadata fields from update type. |
| `httpProductService` | POST/PUT bodies must match narrowed request types. |
| `utils/errors.ts` `BusinessErrorCode` | Add `PRODUCT_SKU_DUPLICATE`. Map HTTP `409` + code to toast / UI when wiring HTTP. |

---

## 4. FE UI

| UI | Change |
|----|--------|
| `CreateProductModal` | Remove `stocks` from create payload. After successful create, set initial quantities **only** via inventory flow (`adjustStock` / `batchAdjustStock` / draft save path already used today) — do not send qty on `POST /products`. |
| `ProductEditModal` | Send `UpdateProductRequest` fields only (already mostly metadata; drop any accidental `Partial<Product>` spread). |
| Error UX | Handle `PRODUCT_SKU_DUPLICATE` (e.g. toast「貨號已存在」). |
| `getProductById` | HTTP `404` → null / empty UX (adapter already catches); no FE contract change beyond ensuring BusinessError body is available if needed. |

---

## 5. FE behavior already compatible (no change required)

- Search query params (`keyword`, `scale`, `brand`, `inStockOnly`) as sent by `HttpProductService`.
- Response `Product` including four `stocks` and computed totals.
- Barcode may be shared across products (search can return multiple).
- Auth token header optional for this phase.

---

## 6. Suggested FE PR split

1. **Types + interface + mock** — create/update request types; mock create without stocks qty; `PRODUCT_SKU_DUPLICATE` enum.
2. **UI** — `CreateProductModal` / edit modal / duplicate-SKU toast; inventory path for initial qty.
3. **HTTP** — turn on after BE catalog + OpenAPI patches land (or behind feature flag).

---

## 7. Cross-check matrix

| Topic | OpenAPI | FE types | FE mock | FE UI | BE |
|-------|---------|---------|---------|-------|-----|
| No create stocks/qty | yes | yes | yes | yes | create rows at 0 |
| Update metadata-only schema | yes | yes | yes | yes | metadata PUT |
| `PRODUCT_SKU_DUPLICATE` | yes | `errors.ts` | throw BusinessError | toast | 409 |
| Seed data | n/a | n/a | localStorage seed | n/a | later Alembic/script (decision B) |
| Inventory qty APIs | later YAML | already on interface | already | CreateProductModal draft | later BE |
