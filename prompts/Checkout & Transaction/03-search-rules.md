# Transactions — Search Rules

Two reads. Both run in SQL. Neither loads a table and filters in Python.

1. **Product search** for the counter. This is the catalog endpoint, unchanged.
2. **Order history** for reprints, returns, and the member history tab.

Buyer lookup while building a ticket is `GET /customers?keyword=` ([`../customers/03-search-rules.md`](../customers/03-search-rules.md)).

## Product search

`GET /products`, as specified in [`../products/03-search-rules.md`](../products/03-search-rules.md) and [`../products/01-api-contract.md`](../products/01-api-contract.md).

The counter autocomplete and the result grid both use that list. This phase does not add rank, a smaller limit, or a second route.

What the screen does with the list:

- The search box sends `keyword` and the selected `brand`.
- The dropdown and the grid render `sku`, `name`, `brand`, `scale`, `listPrice`, and the `store` quantity from `stocks`.
- Sort stays **`sku ASC`**, which is the catalog rule.
- An empty keyword means no keyword filter, same as the catalog. The screen may skip the call until the cashier types, but that is a frontend choice.
- Enter adds a row the cashier has highlighted, or the single returned product when the list has one row. The server does not define a special scan rank.
- Stock in the list is a hint. The commit rechecks `store` under a lock.

Adding to the cart, changing quantity, switching SKU, and manual price stay in `cartStore`.

## Order history

`GET /checkout/orders`. Filters AND together. Inside `keyword`, fields are OR. Inside `productKeyword`, sku and name are OR.

| Param | Match |
|-------|--------|
| `customerId` | `checkout_order.customer_id` equals |
| `orderNumber` | `order_number` equals |
| `productId` | A line `product_id` equals |
| `keyword` | `order_number`, `customer_name`, or `customer_phone` contains the trimmed text. Phone also tries the canonical form (strip spaces, hyphens, parentheses), same idea as customer search. Null name or phone does not match that branch. There is no invoice number to match. |
| `productKeyword` | A line `name` contains (case-insensitive), or a line `sku` contains after `normalizeSku` on both sides when the normalized query is non-empty |
| `startDate` | `created_at >=` |
| `endDate` | `created_at <` |
| `minAmount` / `maxAmount` | Inclusive bounds on `total_amount` |
| `status` | Exact, unless missing or `all` |

Sort: `created_at DESC`, `id DESC`.

Paging: `page` default `1`, `pageSize` default `20`, max `100`. `OFFSET` / `LIMIT` after the order by. Response `total` is the full match count.

`GET /checkout/orders/{orderId}` is a primary-key read, not a search.

## What search does not do

- Autocomplete does not search orders.
- Order search does not search the live catalog price. It searches snapshots on the lines.
- Neither endpoint writes stock, spending, or the cart.
