# Inventory — Data Model

Quantity changes and their documents commit in one database transaction. Stock rows do not store a second copy of the total for convenience. The product API computes `totalStock` when it reads.

## `stock_location`

The location master does not store which store uses it. Stores point at a location.

| Column | Notes |
| --- | --- |
| `id` | Primary key. The existing four locations keep their current ids. |
| `name` | Required |
| `icon` | Nullable |
| `is_default` | Display only |
| `display_order` | |
| `is_active` | Stays `true`. This design does not deactivate a location. |

Existing locations stay: `門市現貨`, `後方倉庫`, `公司總倉`, `調度暫存`. Quantity in `門市現貨` stays there and is not split.

## `store_branch`

Add the checkout binding. The store name remains the primary key.

| Column | Notes |
| --- | --- |
| `name` | Primary key |
| `is_default` | Unchanged |
| `stock_location_id` | Required. References `stock_location.id`. Many stores may share one id. |

A new store is stored with `stock_location_id` set. `台北旗艦店` and `官網` are both set to the existing `門市現貨` location. They share its `normal` and `returned` quantities until one of them is rebound or that location is deleted. Deleting it is refused while any quantity there is not `0`. After the quantity has been moved, each of those stores is bound to a new location of its own. The name is the store name, or the next numbered name when that name is taken.

## `product_stock`

One row is one product, one location, and one condition.

| Column | Notes |
| --- | --- |
| `id` | Surrogate key |
| `product_id` | References `product.id`, `ON DELETE RESTRICT` |
| `location` | References `stock_location.id` |
| `condition` | `normal` or `returned` |
| `quantity` | Required. A checkout sale may set `normal` below `0`. A manual edit may set either bucket below `0`. A transfer refuses to take a source below the moved amount. |
| `location_name` | Copy of the location name. A rename updates these copies. |

Unique key: `(product_id, location, condition)`.

A missing row means quantity `0`. The first receipt, transfer, manual edit, condition change, or checkout that touches a bucket inserts it.

Soft-deleting a product does not delete these rows. A product with `status: deleted` cannot be sold as new stock. It can still be received, transferred, adjusted, and restocked from a return.

## `stock_receipt` / `stock_receipt_item`

A receiving document. Deleting a product or a location does not delete the history. The location columns keep the id and the name from that time.

`stock_receipt`: `id`, `location_id`, `location_name`, `supplier`, `note`, `operator_name`, `created_at`.

`stock_receipt_item`: `id`, `receipt_id`, `product_id`, `sku`, `name`, `quantity`. `quantity` ≥ 1.

## `stock_movement`

One change to one bucket.

| Column | Notes |
| --- | --- |
| `id` | `mov-` plus 32 hex characters |
| `type` | `receipt`, `transfer_out`, `transfer_in`, `adjust`, `condition_out`, `condition_in`, `sale`, `return_restock` |
| `product_id` | |
| `location_id` | |
| `condition` | The bucket this row changes |
| `quantity_delta` | May be negative |
| `quantity_after` | That bucket's quantity after the change |
| `reason` | Nullable |
| `source_type` | `receipt`, `transfer`, `adjustment`, `condition_change`, `checkout_order` |
| `source_id` | Id of the related document |
| `operator_name` | Checkout uses the cashier snapshot. Other writes use the session. |
| `created_at` | |

A transfer writes two rows with the same `source_id`: `transfer_out` at the source (negative delta) and `transfer_in` at the target (positive delta). A condition change writes `condition_out` and `condition_in` the same way.

## `stock_adjustment_log`

Manual and batch edits still write this summary for the current adjustment-log API. Receipts, transfers, checkout, and condition changes write `stock_movement` only.

## Checkout keeps a snapshot, not a live link

`checkout_order.branch_name` still stores the login store name. Each line that changes stock also stores the location used at that moment: `stock_location_id`, `stock_location_name`, and `stock_condition`. If the store is later bound to a different location, old lines still point at the location they used.

A sale line's `stock_condition` is `normal`. A restocked return line's is `returned`. A return line with `restock: false` leaves both location fields empty.
