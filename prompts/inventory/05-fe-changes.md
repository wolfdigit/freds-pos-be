# Inventory — Frontend & OpenAPI Change Notes

Checklist of **everything the frontend and [`../openapi.yaml`](../openapi.yaml) must change** to match the decided inventory contract. Backend implementation should treat this as the FE/contract sync list; FE can land in one or more PRs.

Related planning: [`00-overview.md`](./00-overview.md), [`01-api-contract.md`](./01-api-contract.md), [`04-decisions.md`](./04-decisions.md).

---

## 1. OpenAPI (`prompts/openapi.yaml`) — BE-owned, FE consumes

BE contract lives in the merged [`../openapi.yaml`](../openapi.yaml). FE `docs/openapi.yaml` needs the same changes when the FE pass lands. Checkout text that still deducts the shared `門市現貨` shelf is replaced by the store-location rule below.

| Change | Detail |
|--------|--------|
| `StockLocationDto` | Add read-only `storeNames` (stores bound to this location). `isDefault` stays a display flag and does not choose the checkout location. |
| `CreateStockLocationRequest` | `name` required and unique. Optional `icon`, `displayOrder`. Do not send `isActive`. A duplicate name is `409` `LOCATION_NAME_TAKEN`. Creating a location does not bind a store. |
| `POST /system/stores` | Required `name`. Optional `stockLocationId` or `newLocation`, but not both. Neither means the server creates a location named as the store, or `門市名 2` when that name exists. Many stores may send the same `stockLocationId`. |
| `PUT /system/stores/{storeName}` | Admin rebind: `{ stockLocationId }` of an existing location. |
| Store list responses | `GET /system/stores` and `GET /auth/stores` add `stockLocationId` and `stockLocationName`. |
| `DELETE /inventory/locations/{locationId}` | No transfer body. `409` `LOCATION_NOT_EMPTY` while any bucket is not `0`. On success, each store that pointed here is bound to a new location named as that store. Response includes `reboundStoreNames`. |
| `LocationStock` | Keep `quantity` as the `normal` count (`0` when the row is missing). Add `returnedQuantity` (`0` when missing). |
| `Product.totalStock` | Sum of every location's `quantity` only. `returnedQuantity` is not included. |
| `Product.loginStoreQuantity` | Sellable `normal` quantity at the session store's bound location. `0` when the location has no row. May be negative. |
| `InventoryTransferRequest` | Add optional `condition` (`normal` \| `returned`, default `normal`). Source and target keep that condition. Drop `operatorId`; the server uses the session. |
| New `POST /inventory/transfers/all` | `fromLocation`, `toLocation`, optional `reason`. Moves every non-zero `normal` and `returned` bucket. A negative quantity moves with it. `200` `{ ok: true }`. |
| `StockAdjustRequest` | Add optional `condition` (default `normal`). `newQuantity` is the absolute value and may be negative. `reason` stays required. |
| `StockLocationChange` | Add `condition` so a log row shows which bucket changed, plus old, new, and diff. |
| New `CreateStockReceiptRequest` | `locationId`, optional `note` and `supplier`, `items[]` of `{ productId, quantity ≥ 1 }`. Adds `normal` only. |
| New `StockReceipt` | `201` body: `id` (`rcv-` + 32 hex), location, supplier, note, `operatorName`, `createdAt`, `items`, `totalQuantity`. |
| `GET /inventory/receipts` | Newest first. Filters `locationId`, `productId`. Page `{ items, page, pageSize, total }`. |
| New `ConditionChangeRequest` | `POST /inventory/condition-changes`. Same location, `returned` → `normal` only. Required `productId`, `locationId`, `quantity` ≥ 1, `reason`. `200` `{ ok: true }`. |
| New `StockMovement` | `GET /inventory/movements`. Filters `productId`, `locationId`, `condition`, `type`, `page`, `pageSize`. Newest first. Types: `receipt`, `transfer_out`, `transfer_in`, `adjust`, `condition_out`, `condition_in`, `sale`, `return_restock`. |
| `POST /checkout/orders` stock step | Deduct `normal` at the login store's `stockLocationId`, even when the result is negative. `台北旗艦店` and `官網` start on `門市現貨`. A missing binding is replaced with a new location named as the store, or the next numbered name. |
| Checkout return stock | `restock` omitted or `true` adds the count to `returned` at the return order's login store. `restock: false` changes no stock row. A return does not add `normal`. |
| `BusinessErrorCode` | Add `INSUFFICIENT_STOCK`, `LOCATION_NOT_EMPTY`, and `LOCATION_NAME_TAKEN`. Keep `LOCATION_NOT_FOUND` and `INVALID_LOCATION_TRANSFER`. Checkout no longer returns `INSUFFICIENT_STORE_STOCK`. Do not add `LOCATION_INACTIVE` or `STORE_STOCK_LOCATION_MISSING`. |

---

## 2. FE types (`freds-pos-fe/src/types/…`)

| Change | Detail |
|--------|--------|
| Add `StockCondition` | `'normal' \| 'returned'`. |
| `StockLocationDto` | Add `storeNames: string[]`. |
| `CreateStockLocationRequest` | Name and display fields only. No store binding. |
| Store create / rebind | `CreateStoreRequest` takes `stockLocationId` or `newLocation`. `UpdateStoreBindingRequest` takes `stockLocationId`. Store DTOs add `stockLocationId` and `stockLocationName`. |
| `LocationStock` | Add `returnedQuantity: number`. `quantity` remains sellable `normal`. |
| `Product` | Add `loginStoreQuantity: number`. It may be negative. |
| `InventoryTransferRequest` | Add optional `condition`. Remove `operatorId`. |
| `StockAdjustRequest` | Add optional `condition`. |
| `StockLocationChange` | Add `condition`. |
| Add receipt types | `CreateStockReceiptRequest`, `StockReceipt`, and paged `StockReceiptSearchResponse`. |
| Add `ConditionChangeRequest` | Fields in the table above. |
| Add `StockMovement` | Plus paged `StockMovementSearchResponse` and `type`. |
| `DeleteStockLocationResponse` | `reboundStoreNames` only. Delete does not transfer quantity. |
| Add `MoveAllStockRequest` | `fromLocation`, `toLocation`, optional `reason`. |

---

## 3. FE service layer

| File / API | Change |
|------------|--------|
| `ILocationService.createLocation` | Send the location name only. Binding happens on store create or rebind. |
| `ILocationService.deleteLocation` | Refuse a location that still has quantity. On success, read `reboundStoreNames`. |
| `IProductService.transferStock` | Pass `condition`. Reject a short source with `INSUFFICIENT_STOCK`. Keep the condition at the destination. |
| `IProductService.moveAllStock` | `POST /inventory/transfers/all`. Move every non-zero bucket. Leave the source location in place. |
| `IProductService.adjustStock` | Pass `condition`. Set that bucket to `newQuantity`. Default bucket is `normal`. |
| `IProductService` receipts | Add `createReceipt` and `searchReceipts`. `POST /inventory/receipts` adds `normal`. `GET /inventory/receipts` returns the page. |
| `IProductService.changeStockCondition` | `POST /inventory/condition-changes`. Decrease `returned` and increase `normal` at one location. |
| `IProductService.getStockMovements` | `GET /inventory/movements` with the filters above. |
| `mockProductService` / `mockLocationService` | Persist both buckets. A missing bucket is `0`. `totalStock` sums `normal` only. Checkout deducts the login store's `store` location and restocks `returned` there. |
| `httpProductService` / `httpLocationService` | Bodies match the narrowed requests. Do not send `operatorId` on a transfer. |
| `utils/errors.ts` `BusinessErrorCode` | Add `INSUFFICIENT_STOCK`, `LOCATION_NOT_EMPTY`, and `LOCATION_NAME_TAKEN`. |

---

## 4. FE UI

| UI | Change |
|----|--------|
| Location create | Name, icon, and order only. A duplicate name shows `LOCATION_NAME_TAKEN` and asks for another name. Show `storeNames` on the location so shared bindings are visible. |
| Store create | Admin picks an existing location, enters a new location name, or leaves both empty. A typed name that already exists is `LOCATION_NAME_TAKEN`. Empty creates a location named as the store, or `門市名 2` when that name is taken. Several stores may pick the same location. |
| Store rebind | Admin can point a store at another location. The old location's quantity stays there. |
| Location edit | No deactivate control. A location is removed only by delete, and only when its quantity is `0`. |
| Delete location | If any quantity remains, show `LOCATION_NOT_EMPTY` and leave the move-all action as the way to clear it. After a successful delete, show `reboundStoreNames`. |
| `ProductTable` | Show `quantity` and `returnedQuantity` for each location. Show company-wide `totalStock` and `loginStoreQuantity` separately. |
| `StockTransferModal` | Choose `normal` or `returned`. Both ends use that condition. A `returned` move stays labeled returned. A separate action moves every bucket at the source location. |
| `RestockModal` | Call `createReceipt` (add quantity). Stop using a batch adjustment that replaces the absolute quantity for a receipt. |
| Manual adjust | Keep the absolute edit. The number may be negative. The form names the bucket, default `normal`, and still requires a reason. |
| Return-to-sellable | New action on a location's `returnedQuantity`: amount + reason → `changeStockCondition`. |
| Checkout stock display | Read `quantity` at the login store's `stockLocationId`, not `stocks.find(location === 'store')`. Show `returnedQuantity` beside it and label it as not sellable. |
| Short stock | Submit still completes when the sale would make `normal` negative. Show that negative quantity. Warehouse quantity is not a substitute. |
| `OrderDetailModal` | Replace「回補至門市現貨」with the return order's store and the `returned` label. `restock: false` still skips stock. |

---

## 5. FE behavior already compatible (no change required)

- Location list, create, update, and delete-with-transfer already call `/inventory/locations`.
- Transfer and single adjust already exist on `IProductService`.
- Adjustment history already calls `GET /inventory/adjustments/logs`.
- Product create still sends no quantities.
- A return line already sends `restock`. The server decides the bucket.
- `staff` and `admin` can both use inventory screens. Store create/delete stays on the admin store screen.

---

## 6. Suggested FE PR split

1. **Types + OpenAPI** — `storeNames`, store binding, `condition`, `returnedQuantity`, receipt, condition change, and movement schemas. Error codes.
2. **Mock + HTTP** — two buckets, receipt adds `normal`, transfer keeps `condition`, checkout uses the login store location.
3. **Inventory UI** — store binding on create, table columns, transfer condition, receipt modal, return-to-sellable action.
4. **Checkout UI** — sellable count from the login store, returned label, and the missing-location toast.

---

## 7. Cross-check matrix

| Topic | OpenAPI | FE types | FE mock | FE UI | BE |
|-------|---------|----------|---------|-------|-----|
| Add a location without binding a store | yes | yes | yes | yes | insert `stock_location` |
| New store binds a location | yes | `stockLocationId` or `newLocation` | allow a shared id | store create form | `store_branch.stock_location_id` |
| Many stores, one location | yes | `storeNames` | shared buckets | show the store list | same `normal` / `returned` |
| `quantity` vs `returnedQuantity` | yes | `LocationStock` | two buckets | both columns | `normal` / `returned` |
| `totalStock` excludes returned | yes | response field | sum `normal` | company-wide total | computed on read |
| `loginStoreQuantity` | yes | `number` | session store | separate from `totalStock` | bound location's `normal`, may be negative |
| Receipt adds `normal` | yes | receipt types | add, not replace | `RestockModal` | `POST /inventory/receipts` |
| Transfer keeps condition | yes | `condition` | same bucket | condition select | no partial move |
| Move every bucket at a location | yes | `MoveAllStockRequest` | all non-zero buckets | separate action | `POST /inventory/transfers/all` |
| Manual absolute quantity | yes | `StockAdjustRequest` | set bucket | reason required | adjustment log |
| Returned → `normal` only | yes | `ConditionChangeRequest` | move buckets | release action | `POST /inventory/condition-changes` |
| Checkout deducts the bound location | yes | n/a | `stockLocationId` | that location's `quantity` | sale may go negative |
| Typed location name is unique | yes | `LOCATION_NAME_TAKEN` | reject | ask for another name | compare trimmed name |
| No deactivated location | yes | omit `isActive` on write | always usable | no deactivate control | `is_active` stays true |
| Delete refuses leftover quantity | yes | `LOCATION_NOT_EMPTY` | reject | point at move-all | no quantity change |
| Deleted location rebinds its stores | yes | `reboundStoreNames` | new location per store | show the new names | store name, or `門市名 2` when taken |
| Restocked return | yes | existing `restock` | add `returned` | label, not 門市現貨 | `return_restock` |
| `restock: false` | yes | existing flag | no stock write | unchanged control | no stock row |
| Movement log | yes | `StockMovement` | append | later list | `GET /inventory/movements` |
