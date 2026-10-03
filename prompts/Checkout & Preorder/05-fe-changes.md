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
- Line `productId`, `quantity`, `isManualPrice`, `unitPrice` (required if manual), `priceDiffReason`, preorder ids, and for returns `originalOrderId` + `originalOrderItemId` equal to the server line `id`
- On a line, `pointsDiscountApplied` when that product uses the NT$360 exchange. At most one product once, even if quantity is more than 1. Several different products may each be flagged. Only with a bound member.
- `shippingFee`, `payments`, `invoice` (including a non-empty `invoiceNumber`), `note`
- Header `Idempotency-Key`

Stop sending fields the server ignores for non-manual lines as if they were authoritative. The response `originalPrice`, `subtotal`, and `totalAmount` replace client estimates.

## History and returns

- `getOrderHistory` uses query params, including `page` and `pageSize`, not a single string argument. Exact `invoiceNumber` returns the sale and every refund that reused that number. A history keyword also matches the invoice number.
- A refund sends the original sale's `invoiceNumber`. A new sale sends a number that no other sale already uses. Do not put a sale line and a return line on the same ticket.
- `getOrderById` treats `404` as the missing-order toast. It does not treat an empty list as success.
- Return import must keep `originalOrderItemId` from `CheckoutOrderItem.id`. Matching on `productId` alone is not the contract.
- After a return order is created, refresh the original order if it is on screen. `status` and `returnedQuantity` move only because of that new order.

## Display gaps vs this contract

The current `CheckoutOrder` type has no `branchId`, `branchName`, line `id`, `updatedAt`, or `invoice.invoiceNumber`. Add them when the adapter is wired. Show branch, cashier, and invoice number on the receipt. `branchName` is `台北旗艦店` or `官網`.

`costPrice` is stored on the line and is not part of this JSON. Do not add a cashier-facing cost column from this API.

Do not send `usedPoints`, `earnedPoints`, or a member points balance. Each redeemed product line sends `pointsDiscountApplied`. The server stores 360 on that line and subtracts it from the sale total, which cannot go below 0. The receipt shows that flag on the line.

A return line does not send `pointsDiscountApplied`. The refund follows `unitPrice`. The original sale still shows the NT$360 flag after the return.

A preorder pickup is charged at the current list price. The quoted price is not the sale price unless the cashier sets `isManualPrice` and sends that `unitPrice`.

## Explicitly not in the first FE pass

- Repricing the cart from `vipPrice` or tier on `attachCustomer`
- A server-side parked ticket
- Calling an e-invoice API from the payment modal
