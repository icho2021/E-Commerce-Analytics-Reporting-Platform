# Schema contract — Olist star schema

## Layers

| Layer | Location | Contents |
|-------|----------|----------|
| Source | `data/*.csv` | Immutable Kaggle extract (do not mutate in place) |
| Raw | `lake/raw/olist/` and `s3://$S3_BUCKET/raw/olist/` | Byte-copy of source CSVs |
| Processed | `lake/processed/star/` and `s3://$S3_BUCKET/processed/star/` | Analytics-ready star tables (Parquet + CSV) |

## Table grain

| Table | Grain (one row =) | Primary key |
|-------|-------------------|-------------|
| `dim_customers` | One unique shopper (`customer_unique_id`) | `customer_sk` (= `customer_unique_id`) |
| `dim_products` | One product | `product_sk` (= `product_id`) |
| `dim_sellers` | One seller | `seller_sk` (= `seller_id`) |
| `dim_date` | One calendar day in the order purchase range | `date_sk` (DATE) |
| `fact_orders` | One marketplace order | `order_id` |
| `fact_order_items` | One line item on an order | (`order_id`, `order_item_id`) |

## Relationships (Power BI / SQL joins)

```
fact_orders.customer_sk          → dim_customers.customer_sk
fact_orders.purchase_date_sk     → dim_date.date_sk
fact_order_items.order_id        → fact_orders.order_id
fact_order_items.product_sk      → dim_products.product_sk
fact_order_items.seller_sk       → dim_sellers.seller_sk
```

## Design notes

- **Customer key:** facts use `customer_unique_id` (not session `customer_id`) so segmentation and LTV are at shopper grain. `dim_customers.n_customer_ids` records how many order-session ids map to that unique shopper.
- **Reviews:** multiple reviews per order are averaged into `fact_orders.review_score_avg`.
- **Payments:** multiple payment lines are summed into `fact_orders.payment_value_total`.
- **On-time flag:** `delivered_on_time` is true when delivery timestamp ≤ estimated delivery; null if either date is missing.

## Contract change process

Any grain or key change must update this file, `docs/column_metadata.md`, `docs/metrics.md`, and re-run DQ before publishing a new Power BI cycle.
