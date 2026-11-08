# Inventory — API Contract

Prefix `/api/v1`. Amounts and quantities are integers. A business failure uses `BusinessError` (`code` + `message`). The operator comes from the login session. A cashier name in the body is ignored.

`staff` and `admin` may both read and write inventory. Creating, deleting, and rebinding stores stays admin-only.

## Store binding

`POST /system/stores` and `PUT /system/stores/{storeName}` both require:

| Field | Required | Notes |
| --- | --- | --- |
| `name` | create only | New store name |
| `stockLocationId` | yes | Existing location for normal goods |
| `returnedStockLocationId` | yes | Existing location for returned goods |

The two ids must differ. An unknown id is `404` `LOCATION_NOT_FOUND`. The same id twice is `400` `INVALID_LOCATION_TRANSFER`. There is no `newLocation` field, and the server does not create a location during store create.

`GET /system/stores` and `GET /auth/stores` include `stockLocationId`, `stockLocationName`, `returnedStockLocationId`, and `returnedStockLocationName`.

A typed location name on `POST /inventory/locations` or a rename must not match an existing name. A match is `409` `LOCATION_NAME_TAKEN`. The comparison is the trimmed name.

## Stock locations

### `GET /inventory/locations`

Returns every location. Order by `displayOrder`, then `id`.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | |
| `name` | string | Unique |
| `icon` | string | |
| `isDefault` | boolean | |
| `displayOrder` | number | |
| `storeNames` | string[] | Stores that use this id as `stockLocationId` |
| `returnedStoreNames` | string[] | Stores that use this id as `returnedStockLocationId` |

There is no `isActive` field.

### `POST /inventory/locations` and `PUT /inventory/locations/{locationId}`

`name` is required on create. Optional `icon` and `displayOrder`. Creating a location does not bind a store.

### `DELETE /inventory/locations/{locationId}`

Body: optional `rebindToLocation`. This call does not move quantity.

`409` `LAST_LOCATION` when two or fewer locations exist. `409` `LOCATION_NOT_EMPTY` when any quantity is not exactly `0`. A negative quantity blocks the delete. Transfer it or set it to `0` first.

When every quantity is `0` or missing and at least three locations exist, each store that used this id for normal goods, returned goods, or both is bound to `rebindToLocation` on that same role. The field is required in this case, must be a different existing location, and must not make one store's two bindings identical. That failure is `400` `INVALID_LOCATION_TRANSFER`. The response `reboundStoreNames` lists `{ name, binding, stockLocationId }` where `binding` is `normal` or `returned`.

If a store mapping still lands after the locks, the delete rolls back and returns `409` `STOCK_LOCATION_IN_USE`.

## Product stock

`stocks[]` has one entry per location:

| Field | Notes |
| --- | --- |
| `location` | Location id |
| `locationName` | |
| `quantity` | That location's quantity. A missing row is `0`. May be negative. |

`totalStock` sums `quantity` at locations currently used as any store's normal location. `loginStoreQuantity` is the session store's normal location. `loginStoreReturnedQuantity` is the session store's returned location. Product create accepts no quantities.

## `POST /inventory/receipts`

Adds quantity at `locationId`. Repeated lines for the same product add together. Optional `supplier` and `note`. Deleted products can still be received. Each line is stored as a `stock_movement` with `type=receipt`, plus `sku` and `name`. `GET /inventory/receipts` reads those movements back as `items`.

## `POST /inventory/transfers`

| Field | Required | Notes |
| --- | --- | --- |
| `productId` | yes | |
| `fromLocation` | yes | |
| `toLocation` | yes | Must differ |
| `quantity` | yes | Integer ≥ 1 |
| `reason` | no | |

A short source is `409` `INSUFFICIENT_STOCK`. There is no partial move.

## `POST /inventory/transfers/all`

`fromLocation`, `toLocation`, optional `reason`. Every row whose quantity is not `0` moves, including negatives. The source location and its store bindings stay.

## `POST /inventory/adjustments`

| Field | Required | Notes |
| --- | --- | --- |
| `productId` | yes | |
| `location` | yes | |
| `newQuantity` | yes | Absolute. May be negative. |
| `reason` | yes | Blank is rejected |

## `POST /inventory/batch-adjustments`

Each `changes[]` entry sets one location to `newQty`. There is no condition field. One bad row rolls the whole batch back.

## `GET /inventory/movements`

Filters: `productId`, `locationId`, `type`, `page`, `pageSize`. Newest first. Types: `receipt`, `transfer_out`, `transfer_in`, `adjust`, `sale`, `return_restock`. Receipt rows include `sku` and `name`.

## Checkout stock

1. Lock locations, then the login store.
2. A positive line deducts `stockLocationId`. The result may be negative. The line snapshots that location.
3. A negative line with `restock` omitted or `true` adds the count to `returnedStockLocationId` and snapshots that location.
4. `restock: false` changes no stock and leaves the line's location fields empty.

There is no condition-change endpoint.
