# Google 登入 — 前端契約

後端已要求業務 API 先登入並選好門市。這份是前端要接的契約。後端不存購物車。

## 傳輸

- 登入只送 Google ID token 到 `POST /api/v1/auth/google`。
- 之後每個請求：`Authorization: Bearer <token>`。
- `token` 是 POS session，不是 Google token。
- 不要把 Google client secret 放到前端。不要向 Google 要 Gmail 範圍。
- 現有 `httpClient` 讀的是 `localStorage['AUTH_TOKEN']`。登入成功後把回應的 `token` 寫進這個鍵。
- 不要用 cookie。兩個 `*.vercel.app` 站點帶不到對方的 cookie。
- 同一個瀏覽器的分頁共用這把 `localStorage`。登出或 401 時清掉 `AUTH_TOKEN`，並聽 `storage` 事件，讓其他分頁一起關掉登入狀態。
- 後端登出只作廢目前這個 token。其他裝置若有自己的 token，不受影響。

## 登入與選門市

`POST /api/v1/auth/google`

```json
{ "credential": "<Google ID token>" }
```

成功 `200`：

```json
{
  "token": "<session>",
  "tokenType": "Bearer",
  "expiresAt": "2026-11-07T19:00:00+00:00",
  "storeSelected": false,
  "storeName": null,
  "user": {
    "id": "acct-...",
    "email": "person@example.com",
    "name": "白名單顯示名稱",
    "role": "admin"
  }
}
```

- `user.id` 是白名單穩定 id。收銀員 id、每帳購物車都用它。不要用 Google `sub`。
- `user.name` 是畫面上的顯示名稱。白名單 `name` 有值就用去掉空白後的內容；沒有則用帳號 email。不使用 Google 個人檔名稱。建立或更新時超過 128 字回 `400` `ACCOUNT_NAME_REQUIRED`。登入時若這個顯示結果仍超過 128 字，回 `403` `ACCOUNT_NAME_REQUIRED`。
- `role` 只有 `admin` 或 `staff`。
- Session 從這次登入起算 12 小時，使用中不會延長，也沒有閒置逾時。
- 此時還沒選門市。業務 API 會回 `403` `AUTH_STORE_REQUIRED`。

失敗：

| HTTP | code | 何時 |
| --- | --- | --- |
| 401 | `AUTH_INVALID_CREDENTIAL` | 簽章、iss、aud、過期、`email_verified` 不是 true |
| 403 | `AUTH_ACCOUNT_NOT_ALLOWED` | email 不在 `oauth_account`。不會自動建帳 |
| 403 | `AUTH_FORBIDDEN` | 角色不是 admin / staff |
| 403 | `ACCOUNT_NAME_REQUIRED` | 登入時算出的顯示名稱超過 128 字 |
| 503 | `AUTH_NOT_CONFIGURED` | 伺服器沒有 `GOOGLE_CLIENT_ID` |
| 503 | `AUTH_PROVIDER_UNAVAILABLE` | 暫時拿不到 Google 公鑰 |

`GET /api/v1/auth/stores`  
需要 Bearer。還沒選門市也可以。回應 `[{ "name", "isDefault" }]`。這是唯一在選門市前要拿的門市清單。不要改打其他業務 API。

`POST /api/v1/auth/store`

```json
{ "storeName": "奇可門市" }
```

成功 `200` 是 `AuthState`，沒有新的 `token`：

```json
{
  "expiresAt": "...",
  "storeSelected": true,
  "storeName": "奇可門市",
  "user": { "id": "acct-...", "email": "...", "name": "...", "role": "staff" }
}
```

門市必須已存在於 `store_branch`。不存在回 `400` `AUTH_STORE_INVALID`。登入後換門市也打這支，不必重新跟 Google 驗證。

`GET /api/v1/auth/me` 回同樣的 `AuthState`。  
`POST /api/v1/auth/logout` 回 `{ "loggedOut": true }`，只作廢目前 token。

## 業務 API

除了 `GET /api/v1/health`、`GET /`，以及上面的 auth 路由，都要已登入且已選門市。

未帶或無效 token：

| HTTP | code |
| --- | --- |
| 401 | `AUTH_REQUIRED` |
| 401 | `AUTH_SESSION_REVOKED` |
| 401 | `AUTH_SESSION_EXPIRED` |
| 401 | `AUTH_ACCOUNT_NOT_ALLOWED`（帳號已從白名單刪除） |
| 403 | `AUTH_STORE_REQUIRED` |

每次請求都會重讀白名單。角色變更下一筆請求就生效。

`admin` 與 `staff` 目前都能使用商品、會員、庫存、結帳、預購。白名單與門市清單維護只限 `admin`。

## 權限

| 端點 | 方法 | staff | admin | 狀態 |
| --- | --- | --- | --- | --- |
| `/api/v1/auth/stores` | GET | 可，含尚未選門市 | 可 | 200 門市清單 |
| `/api/v1/auth/store` | POST | 可選、可換 | 可選、可換 | 200；不存在 400 `AUTH_STORE_INVALID` |
| `/api/v1/system/stores` | GET | 不可 | 可，含尚未選門市 | staff 403 `AUTH_FORBIDDEN` |
| `/api/v1/system/stores` | POST | 不可 | 可。沒有任何門市時，尚未選門市的管理員仍可建第一間 | 201；staff 403 `AUTH_FORBIDDEN` |
| `/api/v1/system/stores/{storeName}` | PUT | 不可 | 可。改這間門市的正常貨與退貨庫存點 | 200 門市；兩個 id 都可以，也可以相同；找不到門市或庫存點 404；staff 403 `AUTH_FORBIDDEN` |
| `/api/v1/system/stores/{storeName}` | DELETE | 不可 | 可 | 200 `{ "deletedStore" }`；最後一間 409 `LAST_STORE`；找不到 404 `LOCATION_NOT_FOUND`；staff 403 `AUTH_FORBIDDEN` |

沒有設定預設門市的 API。`isDefault` 只出現在清單回應。角色每次請求都從白名單重讀，降權的下一筆管理請求就是 403。

庫存地點（`/api/v1/inventory/locations`）不是門市清單，規則不變。

若管理員刪掉店員目前的登入門市，該店員下一筆業務請求是 `403` `AUTH_STORE_REQUIRED`，要再呼叫 `POST /api/v1/auth/store` 選另一間。這不影響庫存地點。

登入與換門市請用 `/api/v1/auth/stores` 與 `/api/v1/auth/store`，不要用 `/api/v1/system/stores`。

白名單回應多了穩定 `id`：

```json
{ "id": "acct-...", "email": "person@example.com", "role": "staff", "name": "顯示名稱", "note": null }
```

建立時 `role` 只能是 `admin` 或 `staff`。`name` 可省略、null 或空白，存成沒有顯示名稱。有值會先去掉前後空白，超過 128 字拒絕。更新時沒送 `name` 表示不改；送 null 或空白表示清掉。不能刪自己、不能改自己的角色。最後一位管理員不能被刪除或降權（`409` `ACCOUNT_LAST_ADMIN` 或 `ACCOUNT_SELF_PROTECTED`）。

還沒有任何門市時，已登入但尚未選門市的管理員可以 `POST /api/v1/system/stores` 建立第一間。店員不行，即使已經選了門市也不行。

## 結帳門市與庫存

每間登入門市綁兩個庫存點。`inventoryLocationId` 是正常貨，`returnedInventoryLocationId` 是退貨品。兩個可以是同一個庫存點。換門市會改扣庫存的地點。多間門市可以綁同一個庫存點。

- 不要再依賴 body 的 `branchId`。後端會忽略它。
- 訂單的 `branchId` 與 `branchName` 都是目前 session 的門市名稱。之後改綁不會改寫舊訂單，也不會搬走已經入帳的數量。
- `cashierId` 是 `user.id`。`cashierName` 是白名單顯示名稱；該欄空白時用帳號 email。
- 銷售扣該門市的正常庫存點，數量可以變成負數，不會回 `INSUFFICIENT_STORE_INVENTORY`。
- 退貨在 `restock` 省略或為 `true` 時，數量進入該門市的退貨庫存點。`restock: false` 不改庫存。

換門市時若購物車有商品：前端顯示提示即可，不要擋住，也不要清掉數量。後端不接收購物車。下一筆成功結帳改扣新門市綁定的庫存點。

## 購物車（只在前端）

舊的、登入功能上線前的未歸屬購物車不要再問使用者要不要承接，直接清掉。範圍只有這一把：

- 刪除 `localStorage['FREDS_POS_CART']`（Zustand persist，裡面沒有帳號 id）。
- 不要清整個 `localStorage`。
- 不要清 `FREDS_POS_SESSION`、`freds-pos-theme`、`USE_MOCK`、`AUTH_TOKEN`、mock 的 `FREDS_POS_PRODUCTS` / `CUSTOMERS` / `ORDERS` / `STORES` / `STOCK_LOGS` / `LOCATIONS` / `INITIALIZED` / `SCHEMA_VERSION`。
- 不要清新的「依帳號分開」購物車。

新購物車：

- 每個白名單帳號一把，鍵請用穩定 id，例如 `localStorage['FREDS_POS_CART:' + user.id]`。
- 登出、session 過期、關分頁、關瀏覽器都留著。
- 未登入時畫面不要讀出購物車。
- 只有登入者的 `user.id` 與鍵相同才還原。別的帳號看不到。
- 後端沒有購物車 API。
