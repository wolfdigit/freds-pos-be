# Inventory — Overview

Design for Fred's POS inventory. This folder defines the rules, the HTTP contract, and the data model. **No application code is part of this pass.**

Checkout today deducts the shared shelf `門市現貨`, and the login store is only copied onto the order. This design deducts the stock location bound to **the login store on that order**. Several stores may share one location. `台北旗艦店` and `官網` both start bound to `門市現貨`.

## Six rules

1. **Locations can be added.** A location is a warehouse, a store shelf, or any other place. A location is not deactivated. Delete is refused while any quantity there is not zero, so deleting it does not discard quantity.
2. **Stock can move between locations.** One transfer moves one product, one pair of locations, and one condition, and that quantity cannot go below zero. A second call moves every bucket at one location to another location.
3. **Receiving increases stock.** A receipt adds quantity and keeps a receipt document. It does not replace a location's quantity with a new absolute number.
4. **Checkout deducts that store.** A positive line deducts sellable quantity at the location bound to the order's login store. The sale still completes when that quantity becomes negative.
5. **Returns stay at that store, apart from sellable goods.** A restocked return adds to the `returned` quantity at the same store location. Sellable quantity stays unchanged, and the two counts stay visible side by side.
6. **Quantity can be typed in.** A manual adjustment sets one product, one location, and one condition to a new absolute quantity, which may be negative, and requires a reason.

## Two quantities

One product at one location has at most two buckets:

| Condition | Meaning | Checkout may deduct |
| --- | --- | --- |
| `normal` | Sellable stock | Yes |
| `returned` | Returned goods, not yet sellable | No |

`totalStock` sums `normal` across every location. Returned quantity is not included. Either figure may be negative after a sale. The product response also has `loginStoreQuantity`: the `normal` quantity at the location bound to the session's login store. A missing stock row is `0`.

Returned goods become sellable only through a condition change. Transfers, receipts, and checkout never turn `returned` into `normal` on their own.

## Locations and stores

The store list (`store_branch`) and stock locations (`stock_location`) are created separately. Creating a store binds it to a stock location: an existing one, a new one named in that same request, or, when neither is sent, a new location named as the store. A taken automatic name becomes `門市名 2`. Many stores may point at the same location. They then share that location's `normal` and `returned` quantities.

Every store has a location. If a store has none, or its location is deleted, the server creates a new location and binds the store to it. The new name is the store name. If that name is already used, the server appends the smallest free number: `門市名 2`, then `門市名 3`. Checkout uses only that binding. A location with no store pointing at it can still take receipts, transfers, and manual edits. `台北旗艦店` and `官網` both start on `門市現貨`, so they share that location until an admin rebinds one of them or that location is deleted. Rebind leaves the old location's quantity where it is.

## This folder

| File | Contents |
| --- | --- |
| [`01-api-contract.md`](./01-api-contract.md) | Paths, fields, and error codes |
| [`02-data-model.md`](./02-data-model.md) | Tables |
| [`03-flows.md`](./03-flows.md) | Steps for receipt, transfer, checkout, return, and manual edit |
| [`04-decisions.md`](./04-decisions.md) | Adopted interpretations |
| [`05-fe-changes.md`](./05-fe-changes.md) | OpenAPI and frontend sync list |

The live contract remains [`../openapi.yaml`](../openapi.yaml). That file still says checkout deducts the shared `門市現貨` shelf. Implementing this design includes updating that contract. This pass only writes this folder.
