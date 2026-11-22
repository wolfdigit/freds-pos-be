# Inventory — Data Model

## `inventory_location`

| Column | Notes |
| --- | --- |
| `id` | Primary key |
| `name` | Unique, trimmed, at most 64 characters in the API. The column is `varchar(128)`. The limit matches the pre-widening width of the copied `location_name`, so downgrade can narrow that copy. |
| `icon` | |
| `is_default` | |
| `display_order` | |

There is no `is_active` column.

Seeded rows:

| id | name |
| --- | --- |
| `e1a10001-0000-4000-8000-000000000001` | 門市現貨 |
| `e1a10002-0000-4000-8000-000000000002` | 後方倉庫 |
| `e1a10003-0000-4000-8000-000000000003` | 公司總倉 |
| `e1a10004-0000-4000-8000-000000000004` | 調度暫存 |
| `e1a10005-0000-4000-8000-000000000005` | 退貨品 |

`門市現貨` quantity is not split. Returned quantity that used to sit in a `condition = returned` row is summed onto `退貨品` for the same product.

## `store_branch`

| Column | Notes |
| --- | --- |
| `name` | Primary key |
| `is_default` | |
| `inventory_location_id` | Required. Normal goods. FK `fk_store_branch_inventory_location`. |
| `returned_inventory_location_id` | Required. Returned goods. FK `fk_store_branch_returned_inventory_location`. |
| `preorder_inventory_location_id` | Required. 預購保留. FK `fk_store_branch_preorder_inventory_location`. Migration backfills existing stores to 預購保留; new stores default to it. |

All three foreign keys use `ON DELETE RESTRICT`. One store may store the same id in both columns. `台北旗艦店` and `官網` both use `門市現貨` and `退貨品` until an admin rebinds them.

Deleting a location is refused for a system location (`SYSTEM_LOCATION`), while any quantity there is not exactly `0`, and while it is the only location. Stores that pointed at it are updated to `rebindToLocation` on the binding they used.

## `product_inventory`

One row is one product and one location.

| Column | Notes |
| --- | --- |
| `product_id` | |
| `location` | FK to `inventory_location.id` |
| `location_name` | Copy of the location name |
| `quantity` | Integer. May be negative. |

Unique key: `(product_id, location)`. A missing row means `0`. The first receipt, transfer, manual edit, or checkout that touches the pair inserts it.

## `inventory_receipt`

The receipt header: location, optional supplier, optional note, operator, and time. Lines are not stored in a separate item table.

## `inventory_movement`

One row is one quantity change. A receipt line is a movement with `type = receipt`, `source_type = receipt`, `source_id` equal to the receipt id, and `sku` / `name` filled in.

| Column | Notes |
| --- | --- |
| `type` | `receipt`, `transfer_out`, `transfer_in`, `adjust`, `sale`, `return_restock` |
| `product_id` | |
| `sku`, `name` | Set for receipt lines |
| `location_id` | |
| `quantity_delta` | Signed |
| `quantity_after` | |
| `source_type` | `receipt`, `transfer`, `adjustment`, `checkout_order` |
| `source_id` | Groups the rows of one operation |
| `operator_name` | Session operator |

A transfer writes `transfer_out` and `transfer_in` with the same `source_id`.

## `inventory_adjustment_log`

Manual and batch edits still write this summary. The change entries have location, old quantity, new quantity, and diff. They do not carry a condition.

## Checkout line

`checkout_order.branch_name` stores the login store name. A line that changes inventory stores `inventory_location_id` and `inventory_location_name` for the location used at that moment. A later rebind does not rewrite the line or move quantity already posted. A return with `restock` omitted or `true` records the normal location. `restock: false` records the returned location.

Revision `f8c4e2a17b63` renames the earlier `stock_*` tables, columns, constraints, and indexes to these `inventory_*` names. Downgrade renames them back. It does not drop an index that is already gone.

## `inventory_location.system_role`

`String(16)` nullable, unique. `company` / `preorder` / `defective`; ordinary locations are `NULL`.

三個系統地點一開始就存在，不能刪（`409` `SYSTEM_LOCATION`），可以改名、改圖示。系統只認 `system_role`，不認名稱。

| `system_role` | 預設名稱 | id |
| --- | --- | --- |
| `company` | 公司總倉 | `e1a10003-0000-4000-8000-000000000003`（沿用） |
| `defective` | 退貨品 | `e1a10005-0000-4000-8000-000000000005`（沿用，不改名） |
| `preorder` | 預購保留 | `e1a10006-0000-4000-8000-000000000006`（新建） |

`ensure_locations` 與 migration 會補齊缺的系統地點：先接管同 id（公司總倉、退貨品），再接管同名地點，都沒有才用預設名稱新建。後方倉庫、調度暫存是一般地點，可以刪。

## `checkout_order_item.preorder_pickup`

`Boolean NOT NULL DEFAULT false`. 銷售列標記為預購取貨時為 `true`，該列從門市的預購保留地點扣庫存，並快照那個地點。
