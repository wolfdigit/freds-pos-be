# Inventory — Flows

Each flow below is one database transaction. If any step fails, the quantities and the documents roll back together.

## Add a location

1. Validate the name. Reject an empty name, and reject a name another location already uses.
2. Insert `stock_location`. Do not pre-create stock rows and do not bind a store.
3. Later product reads show `0` for both sellable and returned quantity at this location.
4. Checkout ignores this location until a store's `stock_location_id` points at it.

## Create a store

1. The store name must be new. This stays admin-only.
2. The body may carry `stockLocationId` or `newLocation`, and not both. When it carries neither, insert a location. Use the store name, or `門市名 2`, `門市名 3`, and so on when that name is already a location.
3. `stockLocationId` must be an existing location. `newLocation` inserts a location, then uses its id. A typed `newLocation.name` that is already used is `LOCATION_NAME_TAKEN` and creates neither the location nor the store.
4. Insert `store_branch` with that `stock_location_id`.
5. Another store may already use the same id. Both stores then sell from and restock into that one location.

## Receive stock

1. The location must exist. Each product must exist.
2. Sum quantities for the same product first.
3. For each product, lock the `normal` row at that location. Insert `0` when the row is missing.
4. Add the received count to `quantity`.
5. Write the receipt, its lines, and a `type=receipt` movement. `quantityDelta` is positive.

A receipt does not check the selling price and does not change the returned bucket.

## Transfer

1. Source and target must both exist and differ.
2. Lock the source bucket named by `condition`.
3. If the source quantity is below the transfer quantity, return `INSUFFICIENT_STOCK`.
4. Decrease the source and increase the same condition at the target. Insert `0` at the target when that row is missing.
5. Write two movements.

`returned` stock that moves to another location stays `returned`. A manual edit may also set a `returned` bucket to a new absolute quantity.

## Move a whole location

1. Source and target must both exist and differ.
2. Lock every non-zero `normal` and `returned` row at the source.
3. For each of those rows, set the source to `0` and add that quantity to the same condition at the target. A negative source quantity decreases the target.
4. Write `transfer_out` and `transfer_in` for each moved bucket. They share one source id.
5. Leave the source location in place. Do not change `store_branch`.

## Delete a location

1. If any `normal` or `returned` quantity at this location is not `0`, return `LOCATION_NOT_EMPTY`. Do not change stores and do not delete the location.
2. For every store that pointed here, insert a new location and set `stock_location_id` to it. Name it as in the create-store flow.
3. Delete the location.

## Manual edit

1. Lock the named location and condition.
2. `newQuantity` replaces that bucket, and it may be negative. It is not added to the current quantity.
3. Write one `type=adjust` movement. `quantityDelta` is the new value minus the old value, and it may be negative or `0`.
4. Write the adjustment log.

A batch edit does the same for every bucket. One bad bucket leaves no quantity change from that batch.

## Checkout sale

1. The order's login store comes from the session, as it does today.
2. Read that store's `stock_location_id`. If it is missing, create a location with the store's name, or the next numbered name, and bind it. Do not fall back to `門市現貨`.
3. For each positive line, lock that product's `normal` bucket. A hidden product still returns `PRODUCT_NOT_FOUND`.
4. Deduct `normal` even when the result is below zero, and write `type=sale`. `sourceId` is the checkout order id.

Checkout does not change a location unless the login store is bound to it. Two stores bound to the same location sell from the same `normal` quantity. A short location is allowed to go negative.

## Checkout return

1. Return eligibility, the original order, and the member check stay on the checkout contract. This flow does not relax them.
2. When `restock` is omitted or `true`: lock the `returned` bucket at **this return order's login store**, add the returned count, and write `type=return_restock`.
3. When `restock` is `false`: skip stock. The original sale line's `returnedQuantity` still increases under the checkout rules.
4. Do not increase `normal`. Putting the units back on the shelf is the next flow.

## Return to sellable

1. Lock `returned` and `normal` at the same location.
2. Decrease `returned` first, then increase `normal`.
3. Write `condition_out` and `condition_in`. The two absolute values match.

That store's next checkout can deduct these units only after this change.
