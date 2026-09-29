# Column-level metadata (processed star)

## dim_customers

| Column | Type | Description |
|--------|------|-------------|
| customer_sk | string | PK; Olist `customer_unique_id` |
| zip_code_prefix | int/string | Representative zip from any linked customer_id |
| city | string | Representative city |
| state | string | Brazilian state code |
| n_customer_ids | int | Distinct `customer_id` values mapped to this unique shopper |

## dim_products

| Column | Type | Description |
|--------|------|-------------|
| product_sk | string | PK; `product_id` |
| category_pt | string | Portuguese category name |
| category_en | string | English category (translation table) |
| product_name_length | int | Source typo retained (`lenght`) mapped to clearer name |
| product_description_length | int | |
| product_photos_qty | int | |
| product_weight_g | float | |
| product_length_cm / height_cm / width_cm | float | Package dimensions |

## dim_sellers

| Column | Type | Description |
|--------|------|-------------|
| seller_sk | string | PK; `seller_id` |
| zip_code_prefix | int/string | |
| city | string | |
| state | string | |

## dim_date

| Column | Type | Description |
|--------|------|-------------|
| date_sk | date | PK; calendar day |
| year, month, day | int | |
| day_of_week | int | DuckDB DOW |
| year_month | string | `YYYY-MM` for charts |

## fact_orders

| Column | Type | Description |
|--------|------|-------------|
| order_id | string | PK |
| customer_sk | string | FK → dim_customers |
| order_status | string | created/approved/.../delivered/canceled/... |
| order_purchase_timestamp | timestamp | |
| purchase_date_sk | date | FK → dim_date |
| order_approved_at | timestamp | nullable |
| order_delivered_carrier_date | timestamp | nullable |
| order_delivered_customer_date | timestamp | nullable |
| order_estimated_delivery_date | timestamp | |
| delivered_on_time | bool | nullable if dates missing |
| payment_value_total | float | Sum of payment lines |
| n_payment_lines | int | |
| payment_type_primary | string | MAX of payment_type (simple primary label) |
| review_score_avg | float | nullable |
| n_reviews | int | |
| gmv_items | float | Sum of item prices |
| freight_total | float | Sum of item freight |
| n_items | int | Line count |

## fact_order_items

| Column | Type | Description |
|--------|------|-------------|
| order_id | string | Part of composite PK; FK → fact_orders |
| order_item_id | int | Part of composite PK |
| product_sk | string | FK → dim_products |
| seller_sk | string | FK → dim_sellers |
| shipping_limit_date | timestamp | |
| price | float | Item price (non-negative enforced by DQ) |
| freight_value | float | Item freight (non-negative enforced by DQ) |

## pipeline_metadata.json

| Field | Description |
|-------|-------------|
| built_at_utc | Transform run timestamp |
| tables.*.rows | Row counts per star table |
| source_freshness.* | Min/max purchase timestamps and order count (DQ freshness input) |
