# Inventory — Adopted interpretations

Date: 2026-11-08. These lock this design so it stays distinct from the current shared-shelf contract for `門市現貨`.

| # | Topic | Decision |
| --- | --- | --- |
| 1 | Where checkout deducts | The location bound on the login store of that order. The shared `門市現貨` shelf is no longer the source. A store field in the body is still ignored. |
| 2 | Stores and locations | Created separately. A new store binds an existing location, creates one named in the request, or, when neither is sent, gets a new location named as the store. Many stores may bind the same location and then share its quantities. |
| 3 | Existing stores | Bind both `台北旗艦店` and `官網` to the existing `門市現貨` location. Do not split its quantity and do not create a second location for `官網`. |
| 4 | A store always has a location | A missing binding is filled by a new location. The name is the store name, or `門市名 2`, `門市名 3`, and so on when that name is already taken. Checkout does not fall back to `門市現貨`. |
| 5 | Where a return lands | The login store processing that return, condition `returned`. It is not put back at the original sale store unless those two stores are the same. |
| 6 | A return that is not restocked | `restock: false` changes no stock row. |
| 7 | What is sellable | `normal` only. Checkout excludes `returned`. `totalStock` is the company-wide sum of `normal`. `loginStoreQuantity` is the login store's `normal` quantity. |
| 8 | How goods become sellable again | Only `POST /inventory/condition-changes`, and only `returned` → `normal`. A transfer keeps the condition. |
| 9 | Receipt versus manual edit | A receipt adds `normal`. A manual edit sets one bucket to an absolute quantity. The default bucket is `normal`. |
| 10 | Hidden products | A new sale still rejects `status: deleted`. Receipts, transfers, manual edits, and restocked returns may use that product id. |
| 11 | Negative stock | A checkout sale may leave `normal` below zero and still succeeds. A manual edit may set either bucket to a negative absolute quantity. A short transfer or condition change still fails the whole operation. |
| 12 | Contract file | [`../openapi.yaml`](../openapi.yaml) is unchanged in this pass. Before implementation, its checkout stock text must replace the shared `門市現貨` rule with the rules above. |
| 13 | Returned stock movement | Returned quantity can be transferred and stays `returned`. It can also be set to an absolute quantity by a manual edit. |
| 14 | Where a receipt lands | Any location, including a store shelf and a warehouse. |
| 15 | Rebind | A store can move to another location. Quantity stays at the old location. |
| 16 | Delete a location | Delete does not move quantity. Any non-zero bucket rejects the delete. Move the location first with `POST /inventory/transfers/all`. After that, each store that pointed here is bound to a new location named as that store. |
| 17 | Move a whole location | One call moves every non-zero `normal` and `returned` bucket to another location and keeps each condition. A negative `normal` quantity moves too: the source becomes `0` and the target changes by that same amount. The source location and its store bindings stay. |
| 18 | No deactivated location | A location is not turned off. Delete is the only way to retire it, and only after its quantity is `0`. |
| 19 | Location names | A name a person types must be unique. A duplicate is `409` `LOCATION_NAME_TAKEN`. A name the server chooses for a store may become `門市名 2`. |
