# Power BI reporting guide

**Until you have Power BI Desktop:** run `python -m src.report_kpis` for executive charts under `output/` (same metric definitions as [metrics.md](metrics.md)). Power BI remains the optional BI tool for interactive pages.

## Connect to data

**Option A — Local files (simplest)**

1. Run the pipeline at least once (`python -m src.run_pipeline --skip-s3` or full S3 run).
2. Open Power BI Desktop → **Get data** → **Folder** or **Text/CSV** / **Parquet**.
3. Point to `lake/processed/star/`.
4. Load: `fact_orders`, `fact_order_items`, `dim_customers`, `dim_products`, `dim_sellers`, `dim_date`.

**Option B — From S3**

1. Download `s3://$S3_BUCKET/processed/star/` to a local folder (AWS CLI `sync`), then use Option A.
2. Or use an S3 connector / gateway if your org provides one.

## Model relationships

| From | To | Cardinality |
|------|-----|-------------|
| fact_orders.customer_sk | dim_customers.customer_sk | Many : 1 |
| fact_orders.purchase_date_sk | dim_date.date_sk | Many : 1 |
| fact_order_items.order_id | fact_orders.order_id | Many : 1 |
| fact_order_items.product_sk | dim_products.product_sk | Many : 1 |
| fact_order_items.seller_sk | dim_sellers.seller_sk | Many : 1 |

Mark dimension keys as unique; hide surrogate technical columns from report view if desired.

## Recommended report pages

Aligned with the resume narrative:

1. **Executive KPIs** — GMV, Orders, AOV, On-time %, Avg review (filter delivered). See [metrics.md](metrics.md).
2. **Customer segmentation** — orders/GMV by state; repeat vs one-time (DAX).
3. **Product / category** — GMV by `category_en`, top products.
4. **Order operations** — status mix; delivery delay; freight vs price.

## Sample DAX (optional)

```dax
GMV Delivered =
CALCULATE(
    SUM(fact_order_items[price]),
    fact_orders[order_status] = "delivered"
)

Orders Delivered =
CALCULATE(
    DISTINCTCOUNT(fact_orders[order_id]),
    fact_orders[order_status] = "delivered"
)

AOV Delivered = DIVIDE([GMV Delivered], [Orders Delivered])

On Time Rate =
DIVIDE(
    CALCULATE(COUNTROWS(fact_orders), fact_orders[delivered_on_time] = TRUE),
    CALCULATE(COUNTROWS(fact_orders), NOT(ISBLANK(fact_orders[delivered_on_time])))
)
```

## Recurring cycle

1. Refresh raw CSVs if source updates (or re-download Kaggle).
2. `python -m src.run_pipeline` (uploads S3 + DQ).
3. Refresh Power BI dataset from the new `processed/star` files.
4. Confirm DQ report (`dq_report.json`) has zero critical failures before publishing.
