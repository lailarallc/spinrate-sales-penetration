# Spin Rate — Client Data Input Specification

Spin Rate measures **SPPD** (sales per point of distribution) and projects
**dollarized expansion upside** — what each SKU would add if it reached peer
distribution levels. It consumes the shared POS contract (`lailara_engagement.pos`):
weekly **scans**, the **authorization** log, the **store** dimension, plus a
Spin-Rate-specific **products** file that carries the **wholesale price** upside
is valued at.

The one rule this tool exists to enforce: **upside is valued at wholesale;
current revenue is retail scan.** Both bases are declared and printed — never
mixed. Column names are canonical; map your headers in `engagement.yml`.

## §Scans — weekly POS scan movement (required)
| Column | Type | Required | Used for |
|---|---|---|---|
| `store_id` | identifier (text) | **required** | door counts |
| `sku` | identifier (text) | **required** | per-SKU SPPD |
| `week_ending` | date | **required** | window + days-in-period |
| `units_sold` | number ≥ 0 | **required** | SPPD numerator |
| `dollars_sold` | number ≥ 0 | **required** | current **retail-scan** revenue (the other basis) |

## §Authorizations — the distribution log (required)
`sku`, `store_id`, `authorized_date` (**required**), `deauthorized_date` (optional).
Active pairs are the current distribution footprint.

## §Stores — the store dimension (required)
`store_id` (**unique**), `retailer_id`, `chain_name`, `region`, `state`,
`volume_tier` — the tier drives ACV weighting.

## §Products — item master (required for Spin Rate)
| Column | Type | Required | Used for |
|---|---|---|---|
| `sku` | identifier (text) | **required** | join key |
| `product_line` | string | **required** | peer benchmarks (median / 75th / leader doors) |
| `wholesale_price` | number ≥ 0 | **required** | values the projected upside (WHOLESALE, not scan) |

## Required declarations (`basis:`)
- **`week_convention`** — validates every `week_ending` weekday (see the shared
  contract).
- **`scan_basis`** — `retail_scan` | `wholesale`; the basis of **current revenue**
  (`dollars_sold`). Upside is always wholesale, and both bases are printed side
  by side. Carried into the provenance footer.

Scans grain `(store_id, sku, week_ending)` is validated unique;
`deauthorized_date >= authorized_date` is validated.

## Column mapping (`engagement.yml`)
```yaml
client: {name: Your Brand}
engagement: {id: YB-2026-08}
as_of_date: 2026-06-27
basis:
  week_convention: week_ending_saturday
  scan_basis: retail_scan
inputs:
  scans: client-data/scans.csv
  authorizations: client-data/auth.csv
  stores: client-data/stores.csv
  products: client-data/products.csv
columns:
  store_id: "Store #"
  sku: "Item Code"
  week_ending: "Week Ending"
  units_sold: "Scan Units"
  dollars_sold: "Scan $"
  wholesale_price: "Case Cost / Units per Case"
```
