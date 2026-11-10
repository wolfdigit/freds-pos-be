# Inventory — Frontend Changes

BE contract lives in [`../openapi.yaml`](../openapi.yaml). FE `docs/openapi.yaml` needs the same changes when the FE pass lands.

## Contract the FE must follow

| Item | Change |
| --- | --- |
| `InventoryLocationDto` | Remove `isActive`. Add `storeNames` and `returnedStoreNames`. |
| `POST /system/stores` | Admin only. Required `name`, `inventoryLocationId`, and `returnedInventoryLocationId`. Remove `newLocation`. The two ids may be the same. |
| Admin session | An admin token may call `GET /inventory/locations` and the other business APIs before a store is selected. `POST /checkout/orders` without a selected store is `403` `AUTH_STORE_REQUIRED`. `loginStoreQuantity` and `loginStoreReturnedQuantity` are `0` until a store is selected. Staff without a store stay `403` `AUTH_STORE_REQUIRED`. |
| `PUT /system/stores/{storeName}` | Admin only. Body `{ inventoryLocationId, returnedInventoryLocationId }`. Both required. The two ids may be the same. |
| Store DTO | Add `returnedInventoryLocationId` and `returnedInventoryLocationName` beside the normal pair. |
| `LocationInventory` | `quantity` only. Remove `returnedQuantity`. |
| Product | `totalInventory` sums every location, including warehouses, returned locations, and negatives. `inInventoryOnly` uses that sum. Add `loginStoreReturnedQuantity`. The array field is `inventories`. |
| Transfer and adjust | Remove `condition`. `newQuantity` may be negative. |
| `POST /inventory/transfers/all` | Moves every non-zero quantity, including negatives. |
| Remove `POST /inventory/condition-changes` | Returned goods become sellable by a transfer from the returned location to the normal location. |
| `InventoryMovement` | Remove `condition`. Receipt rows include `sku` and `name`. |
| Checkout sale | Deduct `inventoryLocationId`. A negative result still succeeds. |
| Checkout return | `restock` omitted or `true` adds quantity at `returnedInventoryLocationId`. `restock: false` changes no stock. |
| Delete location | Body `rebindToLocation` when `storeNames` or `returnedStoreNames` is not empty. `409` `LAST_LOCATION` when this is the only location. `409` `LOCATION_NOT_EMPTY` when any quantity is not exactly `0`, including negatives. |
| `BusinessErrorCode` | Add `INSUFFICIENT_INVENTORY`, `LOCATION_NOT_EMPTY`, `LAST_LOCATION`, `LOCATION_NAME_TAKEN`, and `INVENTORY_LOCATION_IN_USE`. |

## Types

| File | Change |
| --- | --- |
| `src/types/inventory.ts` | Drop `isActive` and any condition union. Location DTO gains the two store-name lists. |
| `src/types/system.ts` | Store create, rebind, and DTO carry both location ids and names. |
| `src/types/product.ts` | `LocationInventory.quantity` only. Product gains `loginStoreReturnedQuantity`. |
| Checkout line | Keep `inventoryLocationId` and `inventoryLocationName`. Remove `stockCondition`. |

## Services

| Symbol | Change |
| --- | --- |
| `ILocationService.deleteLocation` | Send `rebindToLocation` when either store list is not empty. Handle `LAST_LOCATION` and `LOCATION_NOT_EMPTY`. |
| `IProductService.transferStock` | No condition. `INSUFFICIENT_INVENTORY` when the source is short. |
| `IProductService.adjustStock` | Set that location to `newQuantity`. |
| Store service | Create and rebind send both ids. |

## UI

| Screen | Change |
| --- | --- |
| Store create / edit | Two required location pickers. The same location may be chosen for both. No control that creates a location inline. |
| Location list | Show which stores use the location for normal goods and which use it for returns. No deactivate control. |
| Delete location | Disable delete when only one location exists. If any quantity is not `0`, including a negative, point at transfer or manual zero. When stores are bound, require another existing location and send `rebindToLocation`. Show `reboundStoreNames` with `binding`. |
| Product table | One quantity column per location. `totalInventory` is the sum of every column, including negatives. Also show `loginStoreQuantity` and `loginStoreReturnedQuantity`. |
| Transfer | Pick two locations. No normal/returned toggle. A separate action moves every non-zero quantity. |
| Receipt | Pick any location. Lines come back from movements. |
| Checkout stock | Sellable count is `loginStoreQuantity`. Returned count is `loginStoreReturnedQuantity`. Do not look up `location === 'store'`. |
| Order detail | A restocked return names the returned location. `restock: false` still skips stock. |

## Suggested order

1. Types and OpenAPI: two bindings, no condition, no `isActive`, receipt lines on movements.
2. Store form: both location ids required.
3. Inventory table, transfer, receipt, and delete.
4. Checkout display: normal location versus returned location.

## Error matrix

| Case | HTTP | Code | FE |
| --- | --- | --- | --- |
| Duplicate location name | 409 | `LOCATION_NAME_TAKEN` | show the message |
| Delete the last location | 409 | `LAST_LOCATION` | disable delete when the list has one location |
| Delete with quantity, including negative | 409 | `LOCATION_NOT_EMPTY` | point at transfer or manual zero |
| Delete without a rebind target | 400 | `INVALID_LOCATION_TRANSFER` | require another location |
| Mapping still attached at commit | 409 | `INVENTORY_LOCATION_IN_USE` | ask the user to retry |
| Short transfer | 409 | `INSUFFICIENT_INVENTORY` | leave both locations unchanged |
| Sale below zero | 201 | | show the negative `loginStoreQuantity` |
| Restocked return | 201 | | quantity appears at `returnedInventoryLocationId` |
| Returned location set below zero | 200 | | adjustment `newQuantity` may be negative |

## Existing calls to wire

These endpoints already exist. This section only says how the frontend calls them.

### `POST /api/v1/inventory/receipts`

Admin or staff. Body:

```json
{
  "locationId": "e1a10001-0000-4000-8000-000000000001",
  "supplier": "甲商",
  "note": "optional",
  "items": [{ "productId": "prod-...", "quantity": 4 }]
}
```

`locationId` and `items` are required. `quantity` is an integer of at least 1. Repeated lines for the same product are added together. `201` returns the receipt, including `items` copied from `inventory_movement` and `totalQuantity`.

### `GET /api/v1/inventory/receipts`

Query: `locationId`, `productId`, `page` (default 1), `pageSize` (default 20, maximum 100). Response:

```json
{ "items": [], "page": 1, "pageSize": 20, "total": 0 }
```

`items` are newest first.

### `GET /api/v1/inventory/movements`

Query: `productId`, `locationId`, `type`, `page`, `pageSize`. `type` is one of `receipt`, `transfer_out`, `transfer_in`, `adjust`, `sale`, `return_restock`. The page shape is the same as receipts. Receipt rows include `sku` and `name`. There is no `condition` filter.

### `POST /api/v1/inventory/batch-adjustments`

`note` is required and must not be blank. Do not send `operatorName` or `timestamp`; the server uses the login name and the server clock. `newQty` may be negative, including on a returned location.
