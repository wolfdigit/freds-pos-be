# Products Catalog — Search Rules

Mirror FE mock [`mockProductService.searchProducts`](../../../freds-pos-fe/src/services/mock/mockProductService.ts) and [`skuNormalizer`](../../../freds-pos-fe/src/utils/skuNormalizer.ts). Backend `GET /products` must match this behavior so UI adapters do not need special cases.

## Query parameters

| Param | Source | Notes |
|-------|--------|--------|
| `keyword` | query string | Optional |
| `scale` | query | `ModelScale` or `ALL` |
| `brand` | query | Brand string or `ALL` |
| `inStockOnly` | query boolean | Default `false` |

Filters are **AND**-combined. Within the keyword filter, match conditions are **OR**.

---

## SKU normalization

Same as FE `normalizeSku`:

```text
input → toUpperCase → remove every character not in [A-Z0-9]
```

Examples:

| Input | Normalized |
|-------|------------|
| ` aa - 79121_b ` | `AA79121B` |
| `AA-79121` | `AA79121` |
| `` (empty) | `` |

Store `product.normalized_sku` using this function whenever `sku` is set or changed.

---

## Keyword filter

### Empty / missing keyword

- Treat missing or whitespace-only `keyword` as **no keyword filter** (return all rows that pass other filters).
- FE: `const keyword = params.keyword?.trim() ?? ''` then only enter keyword block if `keyword` is truthy.

### Non-empty keyword

A product matches the keyword if **any** of the following is true:

1. **Normalized SKU contains**  
   `normalizeSku(product.sku).includes(normalizeSku(keyword))`  
   (Equivalently: `product.normalized_sku` contains `normalizeSku(keyword)`.)  
   If `normalizeSku(keyword)` is empty after normalize (e.g. keyword is only symbols), FE `isSkuMatch` returns `true` for the SKU/barcode branch — prefer treating that as “SKU branch always matches” only inside `isSkuMatch`; overall keyword still also checks name/brand. Practical guidance: if normalized query is empty, rely on name/brand `includes` and barcode `includes` of trimmed query; do not exclude solely because SKU normalize emptied the query.

2. **Barcode contains** (raw, not normalized)  
   `product.barcode.includes(keyword.trim())`  
   Case-sensitive as in FE (`String.prototype.includes`).

3. **Name contains** (case-insensitive)  
   `product.name.toLowerCase().includes(keyword.toLowerCase())`

4. **Brand contains** (case-insensitive)  
   `product.brand.toLowerCase().includes(keyword.toLowerCase())`

FE composition:

```text
matchesSku = isSkuMatch(keyword, sku, barcode)
matchesName = name.toLowerCase().includes(keyword.toLowerCase())
matchesBrand = brand.toLowerCase().includes(keyword.toLowerCase())
keep if matchesSku || matchesName || matchesBrand
```

`isSkuMatch` itself:

- empty normalized query → `true`
- else normalized SKU contains normalized query → `true`
- else barcode includes trimmed query → `true`
- else `false`

**Note:** Because `barcode` is **not** unique, a barcode keyword may return **multiple** products.

---

## Scale filter

| `scale` value | Behavior |
|---------------|----------|
| missing / omitted | No filter |
| `ALL` | No filter |
| a `ModelScale` value | Keep only `product.scale === scale` |

---

## Brand filter

| `brand` value | Behavior |
|---------------|----------|
| missing / omitted | No filter |
| `ALL` | No filter |
| any other string | Keep only `product.brand === brand` (**exact** match, not substring) |

Keyword brand matching is substring/case-insensitive; the **`brand` query param** is exact equality (same as mock).

---

## In-stock filter

| `inStockOnly` | Behavior |
|---------------|----------|
| missing / `false` | No filter |
| `true` | Keep only products where `totalStock > 0` |

`totalStock` = sum of `product_stock.quantity` for that product (same as FE `stocks.reduce`).

---

## Sort

Default: **`sku ASC`**.

If `created_at` / `updated_at` exist on `product`, still prefer `sku ASC` for catalog search parity unless product later requires a different UX sort.

---

## Implementation hints (service layer)

1. Apply SQL/ORM filters for exact `scale`, exact `brand`, and optionally `inStockOnly` via `HAVING SUM(quantity) > 0` or a subquery/join aggregate.
2. Keyword is hardest to push fully into SQL if matching four fields with different transforms; acceptable approaches:
   - Load candidates with non-keyword filters then filter in Python (fine for early catalog size), or
   - SQL: `normalized_sku ILIKE %q%` OR `barcode LIKE %trim%` OR `LOWER(name) LIKE %lower%` OR `LOWER(brand) LIKE %lower%` with `q = normalizeSku(keyword)`.
3. Always return full `Product` DTOs including four `stocks` and computed totals.

---

## Out of scope for search

- Inventory transfer/adjust endpoints.
- Filtering by location-level stock (only aggregate `totalStock`).
- Full-text / trigram ranking (not in mock).
