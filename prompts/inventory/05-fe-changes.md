# Inventory — Frontend Changes

BE contract lives in [`../openapi.yaml`](../openapi.yaml). FE `docs/openapi.yaml` needs the same changes when the FE pass lands.

## Contract the FE must follow

| Item | Change |
| --- | --- |
| `StockLocationDto` | Remove `isActive`. Add `storeNames` and `returnedStoreNames`. |
| `POST /system/stores` | Required `name`, `stockLocationId`, and `returnedStockLocationId`. Remove `newLocation`. The two location ids must differ. |
| `PUT /system/stores/{storeName}` | Body `{ stockLocationId, returnedStockLocationId }`. Both required. |
| Store DTO | Add `returnedStockLocationId` and `returnedStockLocationName` beside the normal pair. |
| `LocationStock` | `quantity` only. Remove `returnedQuantity`. |
| Product | `totalStock` sums normal-location bindings. Add `loginStoreReturnedQuantity`. Keep `loginStoreQuantity`. |
| Transfer and adjust | Remove `condition`. `newQuantity` may be negative. |
| `POST /inventory/transfers/all` | Moves every non-zero quantity, including negatives. |
| Remove `POST /inventory/condition-changes` | Returned goods become sellable by a transfer from the returned location to the normal location. |
| `StockMovement` | Remove `condition`. Receipt rows include `sku` and `name`. |
| Checkout sale | Deduct `stockLocationId`. A negative result still succeeds. |
| Checkout return | `restock` omitted or `true` adds quantity at `returnedStockLocationId`. `restock: false` changes no stock. |
| Delete location | Body `rebindToLocation` when `storeNames` or `returnedStoreNames` is not empty. `409` `LAST_LOCATION` when two or fewer locations exist. `409` `LOCATION_NOT_EMPTY` when any quantity is not exactly `0`, including negatives. |
| `BusinessErrorCode` | Add `INSUFFICIENT_STOCK`, `LOCATION_NOT_EMPTY`, `LAST_LOCATION`, `LOCATION_NAME_TAKEN`, and `STOCK_LOCATION_IN_USE`. |

## Types

| File | Change |
| --- | --- |
| `src/types/inventory.ts` | Drop `isActive` and any condition union. Location DTO gains the two store-name lists. |
| `src/types/system.ts` | Store create, rebind, and DTO carry both location ids and names. |
| `src/types/product.ts` | `LocationStock.quantity` only. Product gains `loginStoreReturnedQuantity`. |
| Checkout line | Keep `stockLocationId` and `stockLocationName`. Remove `stockCondition`. |

## Services

| Symbol | Change |
| --- | --- |
| `ILocationService.deleteLocation` | Send `rebindToLocation` when either store list is not empty. Handle `LAST_LOCATION` and `LOCATION_NOT_EMPTY`. |
| `IProductService.transferStock` | No condition. `INSUFFICIENT_STOCK` when the source is short. |
| `IProductService.adjustStock` | Set that location to `newQuantity`. |
| Store service | Create and rebind send both ids. |

## UI

| Screen | Change |
| --- | --- |
| Store create / edit | Two required location pickers. They cannot be the same location. No control that creates a location inline. |
| Location list | Show which stores use the location for normal goods and which use it for returns. No deactivate control. |
| Delete location | Disable delete when only two locations exist. If any quantity is not `0`, including a negative, point at transfer or manual zero. When stores are bound, require another existing location and send `rebindToLocation`. Show `reboundStoreNames` with `binding`. |
| Product table | One quantity column per location. Show `totalStock`, `loginStoreQuantity`, and `loginStoreReturnedQuantity` separately. |
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
| Same id for both bindings | 400 | `INVALID_LOCATION_TRANSFER` | keep the two pickers different |
| Delete the last pair | 409 | `LAST_LOCATION` | disable delete when the list has two locations |
| Delete with quantity, including negative | 409 | `LOCATION_NOT_EMPTY` | point at transfer or manual zero |
| Delete without a rebind target | 400 | `INVALID_LOCATION_TRANSFER` | require another location |
| Mapping still attached at commit | 409 | `STOCK_LOCATION_IN_USE` | ask the user to retry |
| Short transfer | 409 | `INSUFFICIENT_STOCK` | leave both locations unchanged |
| Sale below zero | 201 | | show the negative `loginStoreQuantity` |
| Restocked return | 201 | | quantity appears at `returnedStockLocationId` |
