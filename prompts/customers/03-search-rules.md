# Customers — Search Rules

Mirror FE mock [`mockCustomerService.searchCustomers`](../../../freds-pos-fe/src/services/mock/mockCustomerService.ts) for keyword behavior, plus VIP / points query filters aligned with product search (`scale` / `inStockOnly` style). Backend `GET /customers` must match this so UI adapters do not need special cases once FE sends the extra params.

Today’s FE HTTP adapter uses `q`; the contract is **`keyword`** (same as products). VIP/points UI does not exist yet — FE must extend `searchCustomers` (see [`05-fe-changes.md`](./05-fe-changes.md)).

## Query parameters

| Param | Source | Notes |
|-------|--------|--------|
| `keyword` | query string | Optional. Same name as `GET /products`. Empty / missing = no keyword filter. |
| `vipTier` | query | `VipTier` or `ALL`. Missing / `ALL` = no VIP filter. |
| `minPoints` | query integer ≥ 0 | Missing = no points filter. When set, `rewardPoints >= minPoints`. |

Filters are **AND**-combined. Within the keyword filter, match conditions are **OR**.

---

## Phone canonicalize (lookup + write)

Used on create/update **and** on `GET /customers/by-phone/{phone}`:

```text
input → trim → remove spaces, hyphens, parentheses
```

Examples: see [`02-data-model.md`](./02-data-model.md).

Keyword search does **not** require the user to type a canonical phone: substring match runs against the **stored** canonical `phone` using the trimmed query (and, if the query contains separators, also against `canonicalize(q)` so `0912-345` still hits `0912345678`).

---

## Keyword filter (`keyword`)

### Empty / missing keyword

- Treat missing or whitespace-only `keyword` as **no keyword filter** (other filters still apply).
- FE mock: `const q = query.trim().toLowerCase(); if (!q) return customers;`
- Member list (`useCustomerSearch`) starts with empty keyword and expects the full list when no VIP/points filters are set.

### Non-empty keyword

A customer matches if **any** of the following is true:

1. **Name contains** (case-insensitive)  
   `customer.name.toLowerCase().includes(q.toLowerCase())`  
   FE mock: `c.name.toLowerCase().includes(q)` after `q = query.trim().toLowerCase()`.

2. **Phone contains**  
   - Stored canonical phone contains trimmed query: `customer.phone.includes(query.trim())`  
   - **Or** stored phone contains `canonicalize(query)` when that canonical form is non-empty.  
   FE mock today only does `c.phone.includes(q)` with `q` already lowercased; digits are unaffected.

3. **Email contains** (case-insensitive) — **extension vs mock**  
   Stored `email` contains (case-insensitive)  
   `customer.email.toLowerCase().includes(q.toLowerCase())`.  
   Email is always present (required unique).  
   FE mock currently **does not** search email; update mock for parity (see [`05-fe-changes.md`](./05-fe-changes.md)).

Composition:

```text
keyword = trim(query)
keep if name_contains_ci(keyword) || phone_contains(keyword) || email_contains_ci(keyword)
```

Empty `keyword` → skip this block.

**Note:** `email` and `phone` are **unique**, so a **full** canonical phone or **full** lowercased email typically returns one row. Substring queries (`0912`, `@example.com`) may still return many.

---

## VIP tier filter

Same idea as product `scale` / `ALL`:

| `vipTier` value | Behavior |
|-----------------|----------|
| missing / omitted | No filter |
| `ALL` | No filter |
| a `VipTier` value (`regular` \| `silver` \| `gold` \| `platinum`) | Keep only `customer.vipTier === vipTier` (**exact**) |

Invalid enum → `422`.

---

## Points filter

| `minPoints` value | Behavior |
|-------------------|----------|
| missing / omitted | No filter |
| integer `N` ≥ 0 | Keep only members with `rewardPoints >= N` |
| negative | `422` |

This is a **minimum balance**, not “has any points” (`> 0`) and not a max/range (decision 19).

`minPoints: 0` is equivalent to no filter (every stored balance is ≥ 0).

---

## Exact phone lookup (not search)

`GET /customers/by-phone/{phone}` is **exact equality** on canonical phone, not substring. It does **not** accept `vipTier` / `minPoints`.

| Path `phone` | Behavior |
|--------------|----------|
| canonicalizes to stored `phone` | `200` that member |
| no row | `404` `CUSTOMER_NOT_FOUND` |

Do not fall back to name/email on this path.

---

## Sort

Default: **`name ASC`**.

If `created_at` / `updated_at` exist on `customer`, still prefer `name ASC` for member-list parity unless product later requires a different UX sort (e.g. newest-first). Tie-break: `id ASC` is acceptable.

---

## Implementation hints (service layer)

1. Apply SQL/ORM filters for exact `vipTier` and `reward_points >= minPoints` first.
2. Empty `keyword`: those filters only, `ORDER BY name ASC`.
3. Non-empty `keyword`: plus  
   `LOWER(name) LIKE %lower%`  
   OR `phone LIKE %trim%`  
   OR (`canonicalize(q)` non-empty AND `phone LIKE %canonical%`)  
   OR `LOWER(email) LIKE %lower%`.
4. Always return full `Customer` DTOs including derived `vipTierName`.
5. For early member-table size, filtering in Python after load is acceptable (same note as product keyword search).

---

## Out of scope for search

- Filter by `totalSpent`.
- `maxPoints` / points range (only `minPoints` in this phase).
- Pagination / cursor (not in mock).
- Full-text / trigram ranking (not in mock).
- Nested preorder / order search (preorder and checkout modules).
