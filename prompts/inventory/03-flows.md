# Inventory — Flows

## Create a location

1. Reject a blank or duplicate trimmed name with `LOCATION_NAME_TAKEN`.
2. Insert the location. Do not bind a store and do not insert stock rows.
3. Later product reads show `0` at this location.

## Create or rebind a store

1. Require `inventoryLocationId` and `returnedInventoryLocationId`. Both must already exist. They may be the same id.
2. Lock every location in id order, then lock the store row on rebind.
3. Save both ids. Do not move quantity and do not insert a location.
4. If the location disappears before commit, return `404` `LOCATION_NOT_FOUND`.

## Receive stock

1. Lock locations, then resolve `locationId`.
2. Sum repeated lines for the same product.
3. Add that quantity. Insert a `0` row when it is missing.
4. Insert one `inventory_receipt` and one `receipt` movement per product, with `sku` and `name`.

## Transfer one product

1. Lock locations.
2. Lock the source row. If its quantity is less than the requested amount, return `INSUFFICIENT_INVENTORY`.
3. Decrease the source and increase the target. Insert `0` at the target when that row is missing.
4. Write `transfer_out` and `transfer_in`.

## Move a whole location

1. Lock locations.
2. Lock every non-zero row at the source.
3. Set each source row to `0` and add that signed quantity to the same product at the target.
4. The source location and its store bindings stay.

## Delete a location

1. Lock every location in id order.
2. If this is the only location, return `LAST_LOCATION`.
3. Lock the stock rows at this location. If any quantity is not exactly `0`, return `LOCATION_NOT_EMPTY`.
4. Lock the stores that use this id as either binding. `rebindToLocation` must be a different existing location. Set the matching column. Refuse a result where one store's two ids match.
5. Delete the zero stock rows and the location.
6. If a store foreign key still fails, roll back and return `INVENTORY_LOCATION_IN_USE`.

## Manual quantity

1. Lock locations and the stock row.
2. Replace the quantity with `newQuantity`, which may be negative.
3. Write an adjustment log and an `adjust` movement. A blank reason is rejected.

## Checkout sale

1. Lock locations, then the login store.
2. Deduct the positive quantity at `inventory_location_id`. The result may be negative.
3. Write `sale`. Snapshot that location on the line. Idempotent replay does not deduct again.

## Checkout return

1. Use the return order's login store, not the original sale store.
2. When `restock` is omitted or `true`, add the count at `inventory_location_id` and write `return_restock`. Snapshot that location.
3. When `restock` is `false`, add the count at `returned_inventory_location_id` and write `return_restock`. Snapshot that location.
4. The original sale line's `returnedQuantity` still increases under the checkout rules.

A return with `restock: true` is already on the normal location. Goods that were put on the returned location become sellable by a transfer to a normal location.
