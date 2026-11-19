# Transactions — Frontend checklist

The counter, return search, and mock checkout follow this contract. The HTTP adapter does too when `USE_MOCK` is off.

## Search

- Keep the counter box on `GET /products` (`keyword`, `brand`). Do not add a suggestion client.
- The dropdown can show the same rows as the grid: sku, name, price, and store quantity.
- Enter adds the highlighted row, or the only row when the list has one product.

## Submit payload

`createCheckoutOrder` should send:

- Do not send `cashierId` or `cashierName`. The server copies them from the current user. The header can keep showing `sessionStore` until login exists.
- `branchId`: `branch-store` for the counter, `branch-online` for an online-store sale. Omit it on the counter and the server uses `branch-store`.
- `customerId` only (server copies name and phone)
- Line `productId`, `quantity`, `isManualPrice`, `unitPrice` (required if manual), `priceDiffReason`, and for returns `originalOrderId` + `originalOrderItemId` equal to the server line `id`. Do not send `preOrderId` or `preOrderItemId`.
- On a line, `pointsDiscountApplied` when that unit uses the points exchange (up to NT$360 off, floored at 0). Split one unit onto its own line with `quantity: 1` and the already-reduced `unitPrice`. At most once per product. Several different products may each be flagged. Only with a bound member.
- `shippingFee`, `payments` (`type`, `name`, `amount`, and when present `tenderedCash`, `changeAmount`, `transactionRef`), `note`
- Header `X-Idempotency-Key`. A retried submit reuses the same key. The server replays the stored order when that key was already inserted.

Stop sending fields the server ignores for non-manual lines as if they were authoritative. The response `originalPrice`, `subtotal`, and `totalAmount` replace client estimates.

## History and returns

- `getOrderHistory` uses query params, including `page` and `pageSize`, not a single string argument. There is no `invoiceNumber` filter. A history keyword matches order number, buyer name, or buyer phone.
- A ticket may contain sale lines and return lines together. Do not send an invoice.
- `getOrderById` treats `404` as the missing-order toast. It does not treat an empty list as success.
- Return import must keep `originalOrderItemId` from `CheckoutOrderItem.id`. Matching on `productId` alone is not the contract.
- After a return order is created, refresh the original order if it is on screen. `status` and `returnedQuantity` move only because of that new order.

## Display gaps vs this contract

The current `CheckoutOrder` type has no `branchId`, `branchName`, line `id`, or `updatedAt`. Add them when the adapter is wired. Do not add an invoice. The `201` body is `{ order }`. The server does not return receipt HTML. `branchName` is `台北旗艦店` or `官網`. `orderNumber` looks like `SO-20261011-014430-0001`. Writable payment types match the frontend: `cash`, `bank_transfer_ctbc`, `bank_transfer_ubot`, `credit_card_physical`, `credit_card_online`, `line_pay`, `cod`. A migration converts stored `credit_card` to `credit_card_physical` and `bank_transfer` to `bank_transfer_ctbc`, so listed orders no longer return the legacy types.

The catalog and the sale line do not record `costPrice`. Do not add a cashier-facing cost column from this API.

Do not send `usedPoints`, `earnedPoints`, or a member points balance. Each redeemed product line sends `pointsDiscountApplied` with the reduced `unitPrice`. The server stores only the flag; it never subtracts anything itself. The order's `pointsDiscountAmount` is the gap `(originalPrice − unitPrice)` on flagged lines, and `discountAmount` (折讓) excludes those lines. Show 商品原價, then 折讓, then 點數折抵; they add up to `itemsSubtotal`. The receipt shows that flag on the line.

A return line does not send `pointsDiscountApplied`. The server copies the flag from the original line, the refund follows `unitPrice`, and the return order's `pointsDiscountAmount` is negative. The original sale still shows the flag after the return.

## Explicitly not in the first FE pass

- Repricing the cart from `vipPrice` or tier on `attachCustomer`
- A server-side parked ticket
- An invoice field, an invoice number, or an e-invoice call
- `preOrderId` or `preOrderItemId` on a checkout line
