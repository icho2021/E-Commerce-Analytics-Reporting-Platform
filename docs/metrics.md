# Metric definitions

Freeze these definitions for recurring Power BI reporting. Do not redefine ad hoc in visuals without updating this file.

## Core commerce

| Metric | Definition | Grain | Filter / notes |
|--------|------------|-------|----------------|
| **GMV (items)** | `SUM(fact_order_items.price)` | line item or rolled to order via `fact_orders.gmv_items` | Default executive filter: `fact_orders.order_status = 'delivered'`. Document if you include all statuses. |
| **Freight** | `SUM(fact_order_items.freight_value)` | line / order (`freight_total`) | Same status filter as GMV. |
| **Payment total** | `SUM(fact_orders.payment_value_total)` | order | May differ slightly from GMV due to fees/installments; use GMV for product mix, payment total for cash collection views. |
| **Orders** | `COUNT(DISTINCT fact_orders.order_id)` or `COUNTROWS` on fact_orders | order | Apply status filter consistently. |
| **AOV** | GMV ÷ Orders | order set | Same filter as GMV and Orders. |
| **Items per order** | `AVG(fact_orders.n_items)` or GMV items count ÷ Orders | order | |

## Customer

| Metric | Definition | Notes |
|--------|------------|-------|
| **Unique customers** | `COUNTDISTINCT(fact_orders.customer_sk)` | Uses unique shopper id. |
| **Orders per customer** | Orders ÷ Unique customers | |
| **Repeat rate** | Share of `customer_sk` with ≥ 2 orders | Build as calculated measure or DAX. |

## Operations & experience

| Metric | Definition | Notes |
|--------|------------|-------|
| **On-time delivery rate** | `COUNT` where `delivered_on_time = TRUE` ÷ `COUNT` where `delivered_on_time IS NOT NULL` | Only among delivered with both dates. |
| **Avg review score** | `AVERAGE(fact_orders.review_score_avg)` | Orders without reviews are blank (exclude blanks or use COALESCE—pick one in the report and stick to it). |
| **Status mix** | Orders by `order_status` | Ops monitoring page. |

## Category / product

| Metric | Definition | Notes |
|--------|------------|-------|
| **GMV by category** | Sum of item `price` grouped by `dim_products.category_en` | Join items → products. Prefer English category. |
| **Top N categories** | Rank GMV by category | |

## Official default for “executive KPI” page

Unless a stakeholder requests otherwise:

1. Filter **`order_status = delivered`**.
2. Report **GMV (items)**, **Orders**, **AOV**, **On-time delivery rate**, **Avg review score**.

These defaults are implemented in `python -m src.report_kpis` (writes `output/kpi_summary.json` and charts). Power BI should use the same filters when you build the Desktop report later.
