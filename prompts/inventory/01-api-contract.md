# Inventory — API Contract

Prefix `/api/v1`. Amounts and quantities are integers. A business failure uses `BusinessError` (`code` + `message`). The operator comes from the login session. A cashier name in the body is ignored.

`staff` and `admin` may both read and write inventory. Creating, deleting, and rebinding stores stays admin-only. See [`../auth/01-fe-contract.md`](../auth/01-fe-contract.md).

## Store binding

`POST /system/stores` creates the store and its binding together.

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | New store name |
| `stockLocationId` | no | An existing location. Other stores may already use it. |
| `newLocation` | no | `{ name, icon?, displayOrder? }`. The server creates the location and binds it. |

Sending both is `422`. Sending neither creates a new location and binds it. An unknown id is `404` `LOCATION_NOT_FOUND`.

A location the server creates for a store uses the store name. When a location already has that name, the server uses the store name, a space, and the smallest integer from 2 upward that is not already a location name. A name typed in `newLocation`, `POST /inventory/locations`, or a location rename must not match an existing location name. A match is `409` `LOCATION_NAME_TAKEN`. The comparison is the trimmed name.

`PUT /system/stores/{storeName}` body `{ stockLocationId }` moves that store onto another location. The previous location and its quantities stay in place. `200` returns the store name and `stockLocationId`.

`GET /system/stores` and `GET /auth/stores` include `stockLocationId` and `stockLocationName`. `stockLocationId` is always set. Create, delete, and checkout each fill a missing binding with a new location, using the store name or the next numbered name.

## Stock locations

### `GET /inventory/locations`

Returns every location. A location is not deactivated; delete is the only way to remove one. Order by `displayOrder`, then `id`.

`StockLocationDto`:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Location id |
| `name` | string | Display name |
| `icon` | string? | |
| `isDefault` | boolean | Display default. It does not choose the checkout location. |
| `displayOrder` | integer | |
| `isActive` | boolean | Always `true`. Create and update do not accept this field. |
| `storeNames` | string[] | Read-only. Stores whose `stock_location_id` is this location. Empty when none. |

### `POST /inventory/locations`

Adds a location. Quantities already stored elsewhere stay where they are.

| Field | Required | Notes |
| --- | --- | --- |
| `name` | yes | Empty after trim is rejected. A name already used by another location is `409` `LOCATION_NAME_TAKEN`. |
| `icon` | no | |
| `displayOrder` | no | Omitted values sort last |
| `isActive` | no | Not accepted. A new location is always usable. |

Creating a location does not bind a store. `201` returns `StockLocationDto`.

### `PUT /inventory/locations/{locationId}`

May change `name`, `icon`, and `displayOrder`. A renamed name that another location already uses is `409` `LOCATION_NAME_TAKEN`. Keeping the same name is allowed. It cannot deactivate the location. Store bindings are changed on the store, not here.

### `DELETE /inventory/locations/{locationId}`

No body. This call does not move quantity.

Any `normal` or `returned` bucket that is not `0` rejects the delete with `409` `LOCATION_NOT_EMPTY`. Move that stock first with `POST /inventory/transfers/all`.

When every bucket is `0` or missing, each store whose `stock_location_id` was this location is bound to a new location. Its name is that store's name, or the next numbered name when that name is taken. Those new locations have no stock rows. The response lists them in `reboundStoreNames`, each with its new `stockLocationId`. The location is then deleted.

## Stock on a product

Each location on `GET /products` and `GET /products/{productId}` becomes:

| Field | Notes |
| --- | --- |
| `location` | Location id |
| `locationName` | |
| `quantity` | `normal` at that location. A missing row is `0`. |
| `returnedQuantity` | `returned` at that location. A missing row is `0`. |

`totalStock` is the sum of `quantity` across every location. `returnedQuantity` is excluded. Both may be negative. `loginStoreQuantity` is the `normal` quantity at the session store's bound location, or `0` when that row does not exist. Product create still accepts no quantities. A new location appears as `0` when a product is read.

## Receiving

### `POST /inventory/receipts`

Adds `normal` quantity. It does not change `returned`.

| Field | Required | Notes |
| --- | --- | --- |
| `locationId` | yes | Any location |
| `note` | no | |
| `supplier` | no | Supplier name, stored as a note only |
| `items` | yes | At least one line: `productId`, `quantity` (≥ 1) |

Repeated lines for the same product in one request add together.

`201`:

| Field | Notes |
| --- | --- |
| `id` | `rcv-` plus 32 hex characters |
| `locationId` | |
| `locationName` | |
| `supplier` | |
| `note` | |
| `operatorName` | Session display name, or the email when that name is blank |
| `createdAt` | |
| `items` | `productId`, `sku`, `name`, `quantity` |
| `totalQuantity` | Sum of line quantities |

| HTTP | code | When |
| --- | --- | --- |
| 404 | `LOCATION_NOT_FOUND` | The location is missing |
| 404 | `PRODUCT_NOT_FOUND` | The product does not exist. `status: deleted` can still be received. |

### `GET /inventory/receipts`

Newest `createdAt` first. Filters: `locationId`, `productId`. Page shape: `{ items, page, pageSize, total }`.

## Transfer

### `POST /inventory/transfers`

| Field | Required | Notes |
| --- | --- | --- |
| `productId` | yes | |
| `fromLocation` | yes | |
| `toLocation` | yes | Must differ from the source |
| `quantity` | yes | ≥ 1 |
| `condition` | no | `normal` or `returned`. Default `normal`. |
| `reason` | no | |

Source and target keep the same condition. A short source fails the whole transfer. There is no partial move.

`200` `{ "ok": true }`.

| HTTP | code | When |
| --- | --- | --- |
| 400 | `INVALID_LOCATION_TRANSFER` | Source and target are the same |
| 404 | `LOCATION_NOT_FOUND` | |
| 404 | `PRODUCT_NOT_FOUND` | |
| 409 | `INSUFFICIENT_STOCK` | That condition does not have enough quantity |

### `POST /inventory/transfers/all`

Moves every bucket at one location to another. This is the same pair of movements as a transfer, repeated for each product and each condition.

| Field | Required | Notes |
| --- | --- | --- |
| `fromLocation` | yes | |
| `toLocation` | yes | Must differ from the source |
| `reason` | no | |

Every `normal` and `returned` row whose quantity is not `0` moves. The condition stays the same. A negative `normal` quantity moves as well: the source bucket becomes `0`, and the target changes by that same amount. Rows at `0` are skipped. The source location remains, and store bindings do not change. One failure rolls the whole move back.

`200` `{ "ok": true }`.

| HTTP | code | When |
| --- | --- | --- |
| 400 | `INVALID_LOCATION_TRANSFER` | Source and target are the same |
| 404 | `LOCATION_NOT_FOUND` | |

## Manual quantity

### `POST /inventory/adjustments`

Sets one bucket to an absolute quantity.

| Field | Required | Notes |
| --- | --- | --- |
| `productId` | yes | |
| `location` | yes | An existing location |
| `condition` | no | Default `normal` |
| `newQuantity` | yes | Integer. It may be negative. It replaces the bucket. |
| `reason` | yes | Blank is rejected |

`200` `{ "ok": true }`. The change is written to the adjustment log.

### `POST /inventory/batch-adjustments`

Keeps the current batch shape. Each `changes[]` entry gains `condition` (default `normal`). Quantity and one log row commit together. An invalid location, product, or quantity rolls the whole batch back.

### `GET /inventory/adjustments/logs`

Keeps the current log list. Each change shows the location, condition, old quantity, new quantity, and difference.

## Return to sellable

### `POST /inventory/condition-changes`

Only `returned` → `normal` at the same location.

| Field | Required | Notes |
| --- | --- | --- |
| `productId` | yes | |
| `locationId` | yes | |
| `quantity` | yes | ≥ 1, and not more than `returned` at that location |
| `reason` | yes | |

On success, `returned` decreases and `normal` increases. `200` `{ "ok": true }`. A short `returned` bucket is `409` `INSUFFICIENT_STOCK`.

There is no `normal` → `returned` path. Goods enter `returned` only from a checkout return.

## Movement log

### `GET /inventory/movements`

Every quantity change writes one row: receipt, both ends of a transfer, manual edit, condition change, checkout deduction, and restocked return.

Filters: `productId`, `locationId`, `condition`, `type`, `page`, `pageSize`. Newest first.

`type`: `receipt`, `transfer_out`, `transfer_in`, `adjust`, `condition_out`, `condition_in`, `sale`, `return_restock`.

Each row has `id`, `type`, `productId`, `locationId`, `condition`, `quantityDelta`, `quantityAfter`, `reason`, `sourceId` (receipt, transfer, or checkout order id), `operatorName`, and `createdAt`.

## Stock during checkout

No new checkout path. `POST /checkout/orders` keeps the current order rules and changes only the stock step. The login store is still stored as `branchName`. A body `branchId` is still ignored.

Positive lines (`quantity > 0`):

1. Read the login store's `stock_location_id`. A store with none is bound first to a new location named as that store.
2. Lock that product's `normal` row at that location. Insert the row when it is missing.
3. Deduct `normal` even when the result is below zero, and write a `type=sale` movement.

A short quantity does not reject the order.

Return lines (`quantity < 0`):

| `restock` | Stock |
| --- | --- |
| omitted or `true` | Add the returned count to `returned` at the location bound to **this return order's login store** |
| `false` | Leave every stock row unchanged |

A return does not add `normal`, and it does not add stock back at the original sale location unless the store taking the return is that same store. A return may still name a soft-deleted product.

An exchange with both positive and negative lines deducts sellable stock for the positive lines and books `returned` for the negative lines. Each line is applied on its own.
