# Inventory — Decisions

Date: 2026-11-08.

| # | Question | Decision |
| --- | --- | --- |
| 1 | Where checkout deducts | The login store's `inventoryLocationId`. A store field in the body is ignored. |
| 2 | Where a return lands | The login store's `returnedInventoryLocationId`, when `restock` is omitted or `true`. Not the original sale store unless that store is the one processing the return. |
| 3 | Existing stores | `台北旗艦店` and `官網` share `門市現貨` for normal goods and `退貨品` for returned goods. |
| 4 | Creating a store | `inventoryLocationId` and `returnedInventoryLocationId` are both required. They may be the same location. The server does not create a location and does not fill a missing binding. |
| 5 | What is sellable | Quantity at a location some store uses as `inventoryLocationId`. Checkout does not deduct `returnedInventoryLocationId`. |
| 6 | How returned goods become sellable | Transfer them from the returned location to a normal location. There is no condition label and no condition-change call. |
| 7 | `totalInventory` | Sum of quantity at every location, including warehouses, returned locations, and negatives. `inInventoryOnly` uses that same sum. |
| 8 | Negative stock | A sale may go below zero and still succeeds. A manual edit may set a negative absolute quantity. A short transfer still fails. |
| 9 | Delete | Delete does not move quantity. Any quantity other than exactly `0` refuses the delete, including negatives. The caller names one existing rebind target. The last location must remain. |
| 10 | Lock order | Delete, rebind, create, and checkout lock location rows in id order before the store row. A store foreign key failure on delete rolls back as `INVENTORY_LOCATION_IN_USE`. |
| 11 | Receipt lines | `inventory_receipt_item` is removed. A receipt line is a `inventory_movement`. |
| 12 | `is_active` | The column is removed. A location is not deactivated. |
| 13 | Move a whole location | Every non-zero quantity moves, including negatives. Bindings stay. |
| 14 | Staff | Staff may read and write inventory, including delete. Store create, rebind, and delete stay admin-only. |
