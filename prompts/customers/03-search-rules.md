# Customers — Search Rules

`GET /customers` is the only list/lookup. Checkout bind uses `keyword` (phone fragment). **No** `GET /customers/by-phone/{phone}`.

All filters, sort, and paging run **in the database** (`WHERE` / `ORDER BY` / `LIMIT` / `OFFSET`). Do **not** load matching-or-all rows into Python and then filter or slice.

## Query parameters

| Param | Source | Notes |
|-------|--------|--------|
| `keyword` | query | Optional. Empty / missing = no keyword filter. Matches name, phone, or email. |
| `vipTier` | query | `VipTier` or `ALL`. Missing / `ALL` = no VIP filter. |
| `page` | query integer ≥ 1 | Default `1`. |
| `pageSize` | query integer 1–100 | Default `20`. |

AND-combined. Keyword conditions are OR.

---

## Phone canonicalize (write + keyword)

```text
input → trim → remove spaces, hyphens, parentheses
```

Keyword does **not** require a canonical typed phone: SQL matches stored canonical **non-null** `phone` against the trimmed query **and** `canonicalize(query)` when that form is non-empty (`0912-345` still hits `0912345678`). Null phones never match the phone branch.

---

## Keyword filter

### Empty / missing

No keyword predicate. Other filters and paging still apply.

### Non-empty

Keep the row if **any**:

1. `LOWER(name) LIKE %lower(trim)%`
2. `phone IS NOT NULL` **AND** (`phone LIKE %trim%` **OR** (`canonicalize(trim)` non-empty **AND** `phone LIKE %canonical%`))
3. `email IS NOT NULL AND LOWER(email) LIKE %lower(trim)%`

Null phones never match the phone branch. Null emails never match the email branch.

A **full** canonical phone typically returns one row (non-null phone is unique). Substring (`0912`) may return many — that is the bind/search UX; the client picks from `items`.

---

## VIP tier filter

| `vipTier` | Behavior |
|-----------|----------|
| missing / `ALL` | No filter |
| a `VipTier` | `customer.vip_tier = vipTier` exact |
| invalid | `422` |

---

## Paging

| Param | Default | Rules |
|-------|---------|--------|
| `page` | `1` | 1-based. `< 1` → `422`. |
| `pageSize` | `20` | 1–100. Outside range → `422`. |

```text
OFFSET (page - 1) * pageSize
LIMIT pageSize
```

`total` = `COUNT(*)` with the **same** `WHERE` (no Python `len()` on a loaded list).

Response: `{ items, page, pageSize, total }`.

---

## Sort

`ORDER BY name ASC, id ASC` in SQL, then page.

---

## Implementation (service layer)

1. Build one SQLAlchemy/`SELECT` with:
   - exact `vip_tier` when set and not `ALL`
   - keyword `OR` predicates above when keyword non-empty
2. `COUNT(*)` with that `WHERE` → `total`
3. `ORDER BY name ASC, id ASC LIMIT :pageSize OFFSET :offset` → `items`
4. Map rows to `Customer` DTOs (derived `vipTierName`)

No post-query Python filter/slice.

---

## Out of scope

- `minPoints` / `rewardPoints` (removed).
- Filter by `totalSpent`.
- Exact-phone dedicated path (removed).
- Full-text / trigram ranking.
- Nested preorder / order search.
