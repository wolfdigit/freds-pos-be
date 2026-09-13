# Customers — Frontend & OpenAPI Change Notes

Checklist of **frontend** changes to match the decided member-catalog contract. The HTTP contract is [`../openapi.yaml`](../openapi.yaml). **This implement pass is backend only** — do not apply FE changes until a later pass.

Related planning: [`00-overview.md`](./00-overview.md), [`01-api-contract.md`](./01-api-contract.md), [`04-open-questions.md`](./04-open-questions.md).

---

## 1. OpenAPI (`prompts/openapi.yaml`) — BE-owned, FE consumes later

Customers paths live in the merged [`../openapi.yaml`](../openapi.yaml) alongside products. FE `docs/openapi.yaml` is updated when the FE pass lands.

| Change | Detail |
|--------|--------|
| `CreateCustomerRequest.required` | Remove `vipTierName`, `totalSpent`, `rewardPoints`, **`vipTier`**. Keep: `name`, `phone`, `email`. |
| `CreateCustomerRequest` properties | Remove client `vipTierName` / `totalSpent`. **Required `email`** (`format: email`). Optional: `vipTier` (default `regular`), `note`, `rewardPoints` (`minimum: 0`). Server-owned fields (`id`, `createdAt`, `vipTierName`, `totalSpent`) must not be required; do not list them on create. |
| `POST /customers` description | Server assigns `id` (`cust-{uuid4}` no dashes, stored as PK `id`) and `createdAt`; always `totalSpent: 0`; missing `vipTier` → `regular`; derives `vipTierName`; duplicate phone → 409; duplicate email → 409; invalid email → 422. |
| New / tightened `UpdateCustomerRequest` | Profile fields only (`name`, `phone`, `email`, `vipTier`, `note`, `rewardPoints`). **Exclude** `id`, `createdAt`, `vipTierName`, `totalSpent`. Sent `email` must stay valid unique; cannot clear. |
| `PUT` description | Profile only; `rewardPoints` **replaces**; never mutate `totalSpent`; on phone/email change canonicalize + uniqueness; on `vipTier` change response name follows the map; cannot clear email. |
| `GET /customers` | Param **`keyword`** (not FE HTTP `q`, not FE OpenAPI `query`); empty/missing = no keyword filter; match name / phone / email; **`vipTier`** (`VipTier` \| `ALL`); **`minPoints`** (integer ≥ 0); default sort `name ASC`. |
| `GET /customers/by-phone/{phone}` | Keep; document canonicalize-before-lookup; `404` `CUSTOMER_NOT_FOUND`. |
| `DELETE /customers/{customerId}` | New. `204` empty; `404` `CUSTOMER_NOT_FOUND`; `409` `CUSTOMER_HAS_UNFINISHED_ORDERS` when related status is not `completed`/`refunded`/`cancelled` (live after checkout/preorder; terminal history `SET NULL` + **keep name/phone snapshots**). FE **does not** expose delete UI this phase. |
| `POST /customers/{customerId}/reward-points` | New. Body `{ amount: integer }` (signed). `200` `Customer`; `404`; `422` `CUSTOMER_POINTS_INSUFFICIENT`. |
| `BusinessErrorCode` | Add `CUSTOMER_NOT_FOUND`, `CUSTOMER_PHONE_DUPLICATE`, `CUSTOMER_EMAIL_DUPLICATE`, `CUSTOMER_POINTS_INSUFFICIENT`, `CUSTOMER_HAS_UNFINISHED_ORDERS` (FE already has `CUSTOMER_NOT_FOUND`). |
| Create/update responses | Document `409` + examples `{ code: CUSTOMER_PHONE_DUPLICATE, message: 手機號碼已存在 }` and `{ code: CUSTOMER_EMAIL_DUPLICATE, message: 電子信箱已存在 }`. |
| Get-by-id / get-by-phone / update / delete / add-points `404` | Example `{ code: CUSTOMER_NOT_FOUND, message: 找不到指定的會員 }`. |
| Add-points `422` | Example `{ code: CUSTOMER_POINTS_INSUFFICIENT, message: 點數不足 }`. |
| Spending / preorder-under-customer paths | **Do not** add `POST /customers/{id}/spending` or `GET /customers/{id}/preorders` in this catalog phase (separate passes). |

---

## 2. FE types (`freds-pos-fe/src/types/…`)

| Change | Detail |
|--------|--------|
| Add `CreateCustomerRequest` (or equivalent) | Match OpenAPI create: no `id`, `createdAt`, `vipTierName`, **no `totalSpent`**. Required `name`, `phone`, `email`; optional `vipTier` (default `regular`), `note`, `rewardPoints`. |
| Add `UpdateCustomerRequest` | Profile-only partial; **not** `Partial<Customer>`. Sent `email` must remain a valid unique address. `rewardPoints` = **replace**. |
| Add `AddRewardPointsRequest` | `{ amount: number }` — signed integer for `POST .../reward-points`. |
| Add `CustomerSearchParams` | `{ keyword?: string; vipTier?: VipTier \| 'ALL'; minPoints?: number }` — same idea as `ProductSearchParams`. |
| Keep `Customer` response type | Make `email` **required** (today it is `email?: string`). Still includes `vipTierName`, `totalSpent`, `createdAt`, `rewardPoints`. |
| Keep `getVipTierName` | Still used for UI labels; **server** is source of truth on HTTP responses — do not send the name in create/update bodies. |

---

## 3. FE service layer

| File / API | Change |
|------------|--------|
| `ICustomerService.searchCustomers` | Argument → `CustomerSearchParams`. Must pass `keyword` / `vipTier` / `minPoints` as query params. |
| `ICustomerService.createCustomer` | Argument type → create request without `id` / `createdAt` / `vipTierName` / `totalSpent`. |
| `ICustomerService.updateCustomer` | Second arg → `UpdateCustomerRequest` instead of `Partial<Customer>`. PUT `rewardPoints` **replaces**. |
| `ICustomerService.deleteCustomer` | **New.** `deleteCustomer(id: string): Promise<void>` — HTTP `204`; mock removes the row. **No UI caller this phase.** Map `409` `CUSTOMER_HAS_UNFINISHED_ORDERS` when checkout/preorder exist. Mock this phase has no orders — always allow. |
| `ICustomerService.addRewardPoints` | **New.** `addRewardPoints(id: string, amount: number): Promise<Customer>` — HTTP `POST .../reward-points`. **No UI caller this phase** (see §4a). |
| `mockCustomerService.createCustomer` | Stop persisting client `vipTierName` / `totalSpent`; always `totalSpent: 0`; missing `vipTier` → `regular`; set `vipTierName` from `getVipTierName(vipTier)`; id `cust-{uuid}` (or keep `cust-${Date.now()}` until HTTP cutover — prefer uuid for parity). Require valid unique email; enforce unique canonical phone; throw `CUSTOMER_PHONE_DUPLICATE` / `CUSTOMER_EMAIL_DUPLICATE`. |
| `mockCustomerService.updateCustomer` | Only apply profile fields; recompute `vipTierName` on tier change; unique phone and email; reject empty email; never copy `totalSpent` / `id` / `createdAt` from the payload. `rewardPoints` **replaces**. |
| `mockCustomerService.searchCustomers` | Read `params.keyword`; match `email` (case-insensitive contains); apply exact `vipTier` (ignore `ALL`); apply `minPoints` as `rewardPoints >= N`. |
| `mockCustomerService.deleteCustomer` | Remove member from localStorage; missing id → no-op or throw `CUSTOMER_NOT_FOUND` (match HTTP `404` via adapter). |
| `mockCustomerService.addRewardPoints` | `rewardPoints += amount`; if result &lt; 0 throw `CUSTOMER_POINTS_INSUFFICIENT`. |
| `httpCustomerService.searchCustomers` | `` `/customers?keyword=&vipTier=&minPoints=` `` (omit empty / `ALL` / missing minPoints). |
| `httpCustomerService.deleteCustomer` | `DELETE /customers/{id}`; map `404` as needed. |
| `httpCustomerService.addRewardPoints` | `POST /customers/{id}/reward-points` with `{ amount }`. |
| `httpCustomerService` (other) | POST/PUT bodies must match narrowed request types. Keep `getCustomerByPhone` `404` → `null`. `updateCustomerSpending` remains for later checkout; do not call a missing catalog endpoint. |
| `utils/errors.ts` `BusinessErrorCode` | Add `CUSTOMER_PHONE_DUPLICATE`, `CUSTOMER_EMAIL_DUPLICATE`, `CUSTOMER_POINTS_INSUFFICIENT`, `CUSTOMER_HAS_UNFINISHED_ORDERS` (`CUSTOMER_NOT_FOUND` already exists). Map HTTP `409` / `422` + code to toast / UI when wiring HTTP. |

---

## 4. FE UI

| UI | Change |
|----|--------|
| `CustomerModal` create | Remove `vipTierName` and `totalSpent: 0` from create payload. **Require email** (same as name/phone: trim + toast if empty; `type="email"` already on the input). Send `name`, `phone`, `email`, optional `vipTier` (modal may still send `regular` by default), `note?`, `rewardPoints`. Mark the email label with `*`. `vipTier` is **not** required by the API. |
| `CustomerModal` edit | Send `UpdateCustomerRequest` fields only (already mostly profile; drop any accidental `Partial<Customer>` spread including `vipTierName`). Do not allow saving with a blank email. Edit **累積點數** still **replaces** via PUT. Do **not** call `addRewardPoints` from this modal in this phase (see §4a). |
| Error UX | Handle `CUSTOMER_PHONE_DUPLICATE` (toast「手機號碼已存在」), `CUSTOMER_EMAIL_DUPLICATE` (toast「電子信箱已存在」). `CUSTOMER_POINTS_INSUFFICIENT` / `CUSTOMER_HAS_UNFINISHED_ORDERS` toasts land with the later UIs that call those APIs. |
| `getCustomerById` / `getCustomerByPhone` | HTTP `404` → null / empty UX (adapter already catches). |
| `CustomerDetailPanel` `createdAt` | Seed showed `YYYY-MM-DD`; API ISO 8601 will look noisy if printed raw — use `formatDate` / `formatDateTime` from `utils/date.ts`. |
| `CustomerBindCard` | Checkout bind can keep sending only `{ keyword }`. Optional later: exact bind via `getCustomerByPhone`. |
| `CustomerListPanel` / `useCustomerSearch` | Add VIP select (`ALL` + four tiers) and min-points input; pass through `CustomerSearchParams` (`keyword` not `q`). |
| Delete UI | **Do not implement this phase.** API + `ICustomerService.deleteCustomer` exist; no list/detail delete button or confirm dialog until a later FE pass. When built: confirm, then `deleteCustomer`; toast `CUSTOMER_HAS_UNFINISHED_ORDERS` as「該會員尚有未完成訂單，無法刪除」. |

---

## 4a. Add-points UI (specify now; **do not implement this phase**)

Cashier **adjust** (delta) is a different action from **set** (replace). Keep them visually separate so “更新資料” never silently adds.

**Where:** `CustomerModal` **edit** mode (not create), under the existing 累積點數 field — or a compact block on `CustomerDetailPanel` next to 「點數餘額」. Prefer the **edit modal** so create stays a single initial-set field.

**Create (unchanged role):** 累積點數 remains an integer ≥ 0 on `POST /customers` (`rewardPoints`, default `0`). No add control on create.

**Edit — set (this phase, already there):** keep 累積點數 as the **replace** field. Saving the form sends `UpdateCustomerRequest.rewardPoints` and **sets** the balance. Label it clearly, e.g. 「點數餘額（設定）」 / helper 「儲存後會改成這個數字，不是加減」。

**Edit — add (later UI; do not build now):**

| Control | Behavior |
|---------|----------|
| Label | 「調整點數」 |
| Input | integer `amount`, **signed**. Placeholder e.g. `+100` 或 `-50`. Helper: 正數加點、負數扣點。 |
| Preview | `目前餘額 {current} → 調整後 {current + amount}` (local math). If preview &lt; 0, disable submit and/or show 「點數不足」 before the request. |
| Submit | Separate button 「調整點數」 — **not** the profile 「更新資料」 button. Calls `addRewardPoints(customer.id, amount)` only. Does not PUT the rest of the form. |
| Success | Toast e.g. 「已調整點數（餘額 {newBalance}）」; refresh the member in the modal / detail / list from the `Customer` response. Clear the amount input. |
| `amount === 0` | No-op is allowed by API; UI should treat 0 as empty / disable the button. |
| Error | `CUSTOMER_POINTS_INSUFFICIENT` → toast「點數不足」 (balance unchanged). `CUSTOMER_NOT_FOUND` → toast「找不到指定的會員」. |

Do **not** send both a PUT replace and a POST add in one click. Do **not** fold `amount` into `UpdateCustomerRequest`.

**Out of this UI:** checkout earn/use points (`updateCustomerSpending`) stays on the checkout module, not this control.

---

## 5. FE behavior already compatible (no change required)

- Empty search returns the full member list (`useCustomerSearch` initial `keyword === ''`).
- Response `Customer` including `id` (from DB `id`), `vipTier`, `vipTierName`, `rewardPoints`, `totalSpent`.
- Phone-or-name substring search (backend adds email).
- Auth token header optional for this phase.
- `GET /customers/by-phone/{phone}` path already in `HttpCustomerService`.

---

## 6. Suggested FE PR split

1. **Types + interface + mock** — create/update/search request types (`keyword`); required unique email; mock create without `totalSpent` / client `vipTierName`; unique phone; email + `vipTier` + `minPoints` in search; `deleteCustomer` + `addRewardPoints`; `CUSTOMER_PHONE_DUPLICATE` / `CUSTOMER_EMAIL_DUPLICATE` / `CUSTOMER_POINTS_INSUFFICIENT` / `CUSTOMER_HAS_UNFINISHED_ORDERS` enums.
2. **UI (this phase)** — `CustomerModal` required email + payload; list-panel VIP / min-points filters; duplicate-phone / duplicate-email toasts; `createdAt` formatting. **No** add-points control. **No** delete control.
3. **HTTP** — turn on after BE catalog + OpenAPI patches land (or behind feature flag). Keep mock checkout on mock customers until checkout BE exists (spending writes).
4. **Later FE** — add-points UI per §4a; delete confirm + `CUSTOMER_HAS_UNFINISHED_ORDERS` toast.

---

## 7. Cross-check matrix

| Topic | OpenAPI | FE types | FE mock | FE UI | BE |
|-------|---------|---------|---------|-------|-----|
| No create `totalSpent` / `vipTierName` / `id` | yes | yes | yes | yes | create `totalSpent: 0`, derive name, assign id |
| Create `vipTier` optional | yes | optional | default `regular` | may still send | default `regular` |
| Update profile-only schema | yes | yes | yes | yes | metadata PUT; no `totalSpent` |
| Unique canonical phone | yes | n/a | throw BusinessError | toast | 409 |
| Unique valid email | yes | `email` required | throw BusinessError | required field + toast | 409 / 422 |
| `CUSTOMER_PHONE_DUPLICATE` | yes | `errors.ts` | throw | toast | 409 |
| `CUSTOMER_EMAIL_DUPLICATE` | yes | `errors.ts` | throw | toast | 409 |
| Search param `keyword` | yes | `CustomerSearchParams` | function arg | keyword state | `keyword` |
| Search `vipTier` / `minPoints` | yes | params | mock filters | list panel | AND filters |
| Email in keyword | yes | n/a | yes (parity) | no extra UI | OR-match email |
| PUT `rewardPoints` replace | yes | update type | yes | modal set | replace |
| POST add points | yes | `addRewardPoints` | yes | **later UI (§4a)** | add |
| DELETE customer | yes | `deleteCustomer` | yes | **later UI** | hard delete; `409` unless `completed`/`refunded`/`cancelled`; `SET NULL` + snapshots |
| Seed data | n/a | n/a | localStorage seed | n/a | later Alembic/script (decision B) |
| Spending increment API | later YAML | already on interface | already | checkout | later checkout BE |
