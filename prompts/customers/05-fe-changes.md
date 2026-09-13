# Customers — Frontend & OpenAPI Change Notes

Checklist of **frontend** changes to match the decided member-catalog contract. The HTTP contract is [`../openapi.yaml`](../openapi.yaml). **This implement pass is backend only** — do not apply FE changes until a later pass.

Related planning: [`00-overview.md`](./00-overview.md), [`01-api-contract.md`](./01-api-contract.md), [`04-open-questions.md`](./04-open-questions.md).

---

## 1. OpenAPI (`prompts/openapi.yaml`) — BE-owned, FE consumes later

Customers paths live in the merged [`../openapi.yaml`](../openapi.yaml) alongside products. FE `docs/openapi.yaml` is updated when the FE pass lands.

| Change | Detail |
|--------|--------|
| `CreateCustomerRequest.required` | `name`, `phone` only. **Email is not required.** No `vipTierName`, `totalSpent`, `rewardPoints`, `vipTier`. |
| `CreateCustomerRequest` properties | Optional: `email` (`type: [string, null]`, `format: email`), `vipTier` (default `regular`), `note` (optional **string**, not nullable). No `rewardPoints`. No client `id` / `createdAt` / `updatedAt` / `vipTierName` / `totalSpent`. |
| `POST /customers` description | Server assigns `id`, `createdAt`, `updatedAt`; always `totalSpent: 0`; missing `vipTier` → `regular`; derives `vipTierName`; omit/`null` email → `NULL`; duplicate phone → 409; duplicate non-null email → 409; invalid email → 422. |
| `UpdateCustomerRequest` | Profile fields only (`name`, `phone`, `email`, `vipTier`, `note`). **Exclude** `id`, `createdAt`, `updatedAt`, `vipTierName`, `totalSpent`, `rewardPoints`. `email` may be `null` to clear. |
| `PUT` description | Profile only; never mutate `totalSpent`; bump `updatedAt`; phone/email uniqueness; `vipTierName` follows the map. |
| `GET /customers` | Params **`keyword`**, **`vipTier`** (`VipTier` \| `ALL`), **`page`** (default 1), **`pageSize`** (default 20, max 100). **No `minPoints`.** Response **`CustomerSearchResponse`** `{ items, page, pageSize, total }`. SQL-only filters. Sort `name ASC`. |
| `GET /customers/by-phone/{phone}` | **Remove.** Phone lookup is search `keyword`. |
| `POST /customers/{customerId}/reward-points` | **Remove.** No member `rewardPoints`. |
| `DELETE /customers/{customerId}` | Keep. `204`; `404` `CUSTOMER_NOT_FOUND`; `409` `CUSTOMER_HAS_UNFINISHED_ORDERS`. FE **does not** expose delete UI this phase. |
| `Customer` | Optional `email` as `[string, null]`; required `createdAt` + `updatedAt`; **no `rewardPoints`**. `note` optional string (not nullable). |
| `BusinessErrorCode` | Keep `CUSTOMER_NOT_FOUND`, `CUSTOMER_PHONE_DUPLICATE`, `CUSTOMER_EMAIL_DUPLICATE`, `CUSTOMER_HAS_UNFINISHED_ORDERS`. **Remove** `CUSTOMER_POINTS_INSUFFICIENT`. |
| Spending / preorder-under-customer paths | **Do not** add `POST /customers/{id}/spending` or `GET /customers/{id}/preorders`. |

---

## 2. FE types (`freds-pos-fe/src/types/…`)

| Change | Detail |
|--------|--------|
| Add `CreateCustomerRequest` | Required `name`, `phone`. Optional `email: string \| null`, `vipTier`, `note`. No `id` / `createdAt` / `updatedAt` / `vipTierName` / `totalSpent` / `rewardPoints`. |
| Add `UpdateCustomerRequest` | Profile-only partial; **not** `Partial<Customer>`. `email` may be `null` to clear. |
| Add `CustomerSearchParams` | `{ keyword?: string; vipTier?: VipTier \| 'ALL'; page?: number; pageSize?: number }`. **No `minPoints`.** |
| Add `CustomerSearchResponse` | `{ items: Customer[]; page: number; pageSize: number; total: number }`. |
| `Customer` response | `email: string \| null`; add `updatedAt`; **remove `rewardPoints`**. |
| Remove `AddRewardPointsRequest` | No add-points API. |
| Keep `getVipTierName` | Server is source of truth on HTTP responses — do not send the name in create/update bodies. |

---

## 3. FE service layer

| File / API | Change |
|------------|--------|
| `ICustomerService.searchCustomers` | Argument → `CustomerSearchParams`. Return `CustomerSearchResponse` (or at least paged `items` + `total`). Pass `keyword` / `vipTier` / `page` / `pageSize`. |
| `ICustomerService.createCustomer` | Create request without `id` / timestamps / `vipTierName` / `totalSpent` / `rewardPoints`. Email optional. |
| `ICustomerService.updateCustomer` | Second arg → `UpdateCustomerRequest`. No `rewardPoints`. |
| `ICustomerService.deleteCustomer` | **Keep.** HTTP `204`. **No UI caller this phase.** Map `409` `CUSTOMER_HAS_UNFINISHED_ORDERS` when checkout/preorder exist. |
| `ICustomerService.getCustomerByPhone` | **Remove** (or stop calling). Bind via `searchCustomers({ keyword: phone })`. |
| `ICustomerService.addRewardPoints` | **Remove.** |
| `mockCustomerService.createCustomer` | Stop persisting client `vipTierName` / `totalSpent` / `rewardPoints`; always `totalSpent: 0`; missing `vipTier` → `regular`; set `vipTierName` from map; id `cust-{uuid}`; optional email (`null` OK); unique canonical phone; unique non-null email. |
| `mockCustomerService.updateCustomer` | Profile fields only; recompute `vipTierName` on tier change; unique phone and non-null email; allow `email: null`; never copy `totalSpent` / `id` / timestamps; bump `updatedAt`. |
| `mockCustomerService.searchCustomers` | `keyword` + exact `vipTier` (ignore `ALL`) + **page/pageSize**; match name / phone / email; **no minPoints**. Return `{ items, page, pageSize, total }`. |
| `mockCustomerService.deleteCustomer` | Remove member from localStorage. |
| `httpCustomerService.searchCustomers` | `` `/customers?keyword=&vipTier=&page=&pageSize=` `` (omit empty / `ALL`). Parse paged body. |
| `httpCustomerService.deleteCustomer` | `DELETE /customers/{id}`. |
| `httpCustomerService` (other) | Drop `getCustomerByPhone` and `addRewardPoints`. POST/PUT bodies match narrowed request types. `updateCustomerSpending` remains for later checkout. |
| `utils/errors.ts` `BusinessErrorCode` | Add `CUSTOMER_PHONE_DUPLICATE`, `CUSTOMER_EMAIL_DUPLICATE`, `CUSTOMER_HAS_UNFINISHED_ORDERS`. **Do not** add `CUSTOMER_POINTS_INSUFFICIENT`. |

---

## 4. FE UI

| UI | Change |
|----|--------|
| `CustomerModal` create | Remove `vipTierName`, `totalSpent`, `rewardPoints` from payload. **Email optional** (no `*` required). Blank / whitespace email → omit or `null`. Send `name`, `phone`, optional `email` / `vipTier` / `note`. |
| `CustomerModal` edit | `UpdateCustomerRequest` only. Allow clearing email. **Remove 累積點數** field (no member points). |
| Error UX | `CUSTOMER_PHONE_DUPLICATE` → toast「手機號碼已存在」; `CUSTOMER_EMAIL_DUPLICATE` → toast「電子信箱已存在」. |
| `getCustomerById` | HTTP `404` → null / empty UX. |
| `CustomerDetailPanel` | Format `createdAt` / `updatedAt` with `formatDate` / `formatDateTime`. Hide member points. |
| `CustomerBindCard` | Search with `{ keyword }` only. Drop `getCustomerByPhone`. Pick from paged `items`. |
| `CustomerListPanel` / `useCustomerSearch` | VIP select (`ALL` + four tiers); **no min-points**. Pass `page` / `pageSize`; render pager from `total`. Query param `keyword` not `q`. |
| Delete UI | **Do not implement this phase.** |
| Add-points UI | **Cancelled** — no member `rewardPoints`. |

---

## 5. FE behavior already compatible (no change required)

- Auth token header optional for this phase.
- Phone-or-name substring search (backend adds email; bind uses the same search).

**No longer compatible without FE work:** empty search returning an unpaged full list; `rewardPoints` on `Customer`; `getCustomerByPhone`; search returning a bare array.

---

## 6. Suggested FE PR split

1. **Types + interface + mock** — create/update/search types (`keyword`, paging); optional unique email; mock create without `totalSpent` / `rewardPoints` / client `vipTierName`; unique phone; `deleteCustomer`; drop `addRewardPoints` / `getCustomerByPhone`; error enums without `CUSTOMER_POINTS_INSUFFICIENT`.
2. **UI (this phase)** — `CustomerModal` optional email, no points field; list-panel VIP + pager; duplicate-phone / duplicate-email toasts; timestamp formatting. **No** delete control.
3. **HTTP** — turn on after BE catalog + OpenAPI patches land. Keep mock checkout on mock customers until checkout BE exists (spending writes).
4. **Later FE** — delete confirm + `CUSTOMER_HAS_UNFINISHED_ORDERS` toast.

---

## 7. Cross-check matrix

| Topic | OpenAPI | FE types | FE mock | FE UI | BE |
|-------|---------|---------|---------|-------|-----|
| No create `totalSpent` / `vipTierName` / `id` | yes | yes | yes | yes | create `totalSpent: 0`, derive name, assign id |
| Create `vipTier` optional | yes | optional | default `regular` | may still send | default `regular` |
| Update profile-only schema | yes | yes | yes | yes | metadata PUT; no `totalSpent` |
| Unique canonical phone | yes | n/a | throw BusinessError | toast | 409 |
| Optional email (`null` OK) | yes | `string \| null` | unique when set | optional field | 409 / 422 / SQL NULL |
| `CUSTOMER_PHONE_DUPLICATE` | yes | `errors.ts` | throw | toast | 409 |
| `CUSTOMER_EMAIL_DUPLICATE` | yes | `errors.ts` | throw | toast | 409 |
| Search param `keyword` | yes | `CustomerSearchParams` | function arg | keyword state | `keyword` |
| Search `vipTier` + paging | yes | params | mock page | list pager | SQL LIMIT/OFFSET |
| Email in keyword | yes | n/a | yes (parity) | no extra UI | OR-match non-null email |
| No `rewardPoints` | yes | removed | removed | hide points | no column |
| No by-phone | yes | removed | search only | bind via keyword | no path |
| `updatedAt` on response | yes | yes | yes | format dates | bump on PUT |
| DELETE customer | yes | `deleteCustomer` | yes | **later UI** | hard delete; `409` unfinished; `SET NULL` + snapshots |
| Seed data | n/a | n/a | localStorage seed | n/a | later Alembic/script (decision B) |
| Spending increment API | later YAML | already on interface | already | checkout | later checkout BE |
