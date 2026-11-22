# Inventory — Overview

Each store is bound to three inventory locations. `inventoryLocationId` holds normal goods. `returnedInventoryLocationId` holds returned goods. `preorderInventoryLocationId` holds stock reserved for preorders (預購保留); a checkout line with `preorderPickup: true` deducts there instead of the normal location. The ids may be the same. Several stores may share either location. Checkout deducts the login store's normal location. A return with `restock` omitted or `true` adds quantity back there. `restock: false` adds it at the returned location.

`台北旗艦店` and `官網` both start with normal stock on `門市現貨` (`e1a10001-0000-4000-8000-000000000001`) and returned stock on `退貨品` (`e1a10005-0000-4000-8000-000000000005`).

## Rules

1. **Locations can be added.** A location is not labeled normal or returned by itself. The store binding decides which role it plays. There is no active flag. Delete is the only way to retire a location.
2. **Stock can move between locations.** One transfer moves one product. A second call moves every non-zero quantity at one location, including negatives. Moving quantity from a returned location to a normal location is how returned goods become sellable.
3. **Receiving increases inventory.** A receipt adds quantity at the chosen location. Each line is an `inventory_movement` row. The receipt header keeps the supplier and note.
4. **Checkout deducts the login store's normal location.** The sale still completes when that quantity becomes negative.
5. **A return always adds quantity.** `restock` omitted or `true` adds it at the login store's normal location, so it can be sold again. `restock: false` adds it at that store's returned location. Checkout does not deduct the returned location.
6. **Quantity can be typed in.** A manual adjustment sets one product at one location to an absolute quantity, which may be negative, and requires a reason.

## Quantities

One product has one quantity per location. A missing row is `0`.

`totalInventory` sums quantity at every location, including warehouses, returned locations, and negative quantities. Store bindings do not change that sum. `loginStoreQuantity` is the session store's normal location. `loginStoreReturnedQuantity` is that store's returned location. Both are `null` when the session has no selected store. With a store selected they are that store's quantity, including `0` and negatives. An admin may read products and locations with no store selected. Checkout create still requires a selected store.

## Stores and locations

Stores and locations are created separately. `POST /system/stores` requires `inventoryLocationId` and `returnedInventoryLocationId`. The server does not create a location for a new store.

Deleting a location does not move quantity. Any quantity that is not exactly `0` refuses the delete, and a negative quantity is not `0`. Clear it with a transfer or a manual adjustment first. Stores that used the location, as either binding, are rebound to the existing location named in the request. The last remaining location cannot be deleted. One store may use the same location for normal goods and returned goods.

Rebind, delete, and rename lock every location row in id order before a store row or a stock row. Checkout uses that same location order. A foreign key that still points at the deleted location rolls the delete back as `409` `INVENTORY_LOCATION_IN_USE`.

## This folder

| File | Contents |
| --- | --- |
| [`01-api-contract.md`](./01-api-contract.md) | Paths, fields, and error codes |
| [`02-data-model.md`](./02-data-model.md) | Tables |
| [`03-flows.md`](./03-flows.md) | Steps for receipt, transfer, checkout, return, and manual edit |
| [`04-decisions.md`](./04-decisions.md) | Adopted interpretations |
| [`05-fe-changes.md`](./05-fe-changes.md) | Frontend sync list |

The live contract is [`../openapi.yaml`](../openapi.yaml).

## 預購保留與系統地點

預購清單不由本系統維護；系統只保留預購數量。

三個系統地點一開始就存在，不能刪（`409` `SYSTEM_LOCATION`），可以改名、改圖示。系統只認 `system_role`，不認名稱。

| `system_role` | 預設名稱 | id |
| --- | --- | --- |
| `company` | 公司總倉 | `e1a10003-0000-4000-8000-000000000003`（沿用） |
| `defective` | 退貨品 | `e1a10005-0000-4000-8000-000000000005`（沿用，不改名） |
| `preorder` | 預購保留 | `e1a10006-0000-4000-8000-000000000006`（新建） |

`ensure_locations` 與 migration 會補齊缺的系統地點：先接管同 id（公司總倉、退貨品），再接管同名地點，都沒有才用預設名稱新建。後方倉庫、調度暫存是一般地點，可以刪。
