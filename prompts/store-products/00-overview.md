# Store Product List

Each store can sell either every product or only its own list. Example: the catalog has A–E and 台南快閃店 sells only A, B and D. When someone is logged into 台南快閃店, product search, the checkout search and barcode scan, and the inventory page show only A, B and D.

## Data model

| Table / column | Notes |
|----------------|-------|
| `store_branch.product_scope` | `all` (default; existing stores) or `list`. CHECK `ck_store_branch_product_scope`. |
| `store_product.store_name` | FK `store_branch.name`, `ON DELETE CASCADE`. Deleting a store deletes its list. |
| `store_product.product_id` | FK `product.id`, `ON DELETE RESTRICT`. Products are only soft-deleted. |
| `store_product.created_at` | Server time (UTC) when the row was added. |
| `store_product.created_by` | Display name of the signed-in account. Never taken from the request body. |
| PK `pk_store_product` | `(store_name, product_id)`. Index `ix_store_product_product_id`. |

Migration: `d6a2f9c3b1e8` (after `d7a2c4e9b156`). It does not change existing data. Every store starts as `all`.

Rows stay in `store_product` when the store is switched back to `all`, so switching to `list` again reuses them. A soft-deleted product stays in the list but is hidden in every list response and in `listedTotal`. Restoring the product shows it again.

## Where the list applies

| Area | `list` store behavior |
|------|-----------------------|
| `GET /products` (always paged, keyword, barcode, stock filters) | Only listed products. Any business user may pass `allProducts=true` to see every product, or `storeName=<store>` to apply another store's list (and its `loginStore*` fields) instead. |
| `GET /products/{productId}` | Not filtered. `soldInLoginStore` is `false` for unlisted products. |
| `POST /products` | A product created while logged into a `list` store is added to that store's list. It is not added to other `list` stores. |
| `POST /checkout/orders` | A positive line for an unlisted product → `409` `PRODUCT_NOT_IN_STORE`, no writes. Returns are allowed. |
| Inventory page | Uses `GET /products`, so only listed products. `inventories` (every location) and `totalInventory` keep their definitions. |
| Transfers, adjustments, restock | The screens list products through `GET /products`, so they are filtered. The inventory write APIs do not check the list. |

`productScope: all` stores and an admin with no selected store see every product. Every response has `soldInLoginStore` (`null` with no store).

## API

| Method | Path | Who | Notes |
|--------|------|-----|-------|
| `PUT` | `/system/stores/{storeName}/product-scope` | Any business user | `{ productScope: 'all' \| 'list' }` → `StoreDto` |
| `GET` | `/system/stores/{storeName}/products` | Any business user | `keyword`, `inList` (`true`/`false`/omit), `page`, `pageSize` (≤ 200). Searches the whole catalog and marks `inList`. |
| `POST` | `/system/stores/{storeName}/products/batch` | Any business user | `{ add: [...], remove: [...] }`, sent once when the editor saves (存檔). One transaction. Ids already in the list (add) or not in it (remove) are skipped. An unknown or deleted `add` id → `404` `PRODUCT_NOT_FOUND`, nothing changes. `remove` accepts deleted products. Both empty, an id in both, or more than 2000 ids in total → `422`. |
| `POST` | `/system/stores/{storeName}/products/copy` | Any business user | `{ sourceStoreName, replace? }`. Copies the source's listed, non-deleted products. `replace: true` also removes rows the source does not have. |

Write responses are `{ storeName, productScope, changed, added, removed, listedTotal }` (`changed = added + removed`). A missing store is `404` `LOCATION_NOT_FOUND`, the same as the other store routes. `StoreDto` (`GET /auth/stores`, `GET /system/stores`) includes `productScope`. `POST /system/stores` accepts an optional `productScope`.

## Permissions

- Editing a list (batch save, copy) is open to any business user, staff included, for any store.
- Switching `productScope` is open to any business user too. Creating, rebinding and deleting stores stay admin-only.
- `allProducts=true` and `storeName` on `GET /products` are open to any business user.

## Not included

- No select-all by brand or scale. The editor searches on the server and pages.
- No CSV import yet.
