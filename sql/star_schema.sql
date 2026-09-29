-- Star schema for Olist e-commerce analytics (DuckDB)
-- Grain documented in docs/schema_contract.md
-- Assumes raw CSV views/tables already registered in DuckDB:
--   raw_customers, raw_orders, raw_order_items, raw_order_payments,
--   raw_order_reviews, raw_products, raw_sellers, raw_category_translation

CREATE OR REPLACE TABLE dim_customers AS
SELECT
    c.customer_unique_id AS customer_sk,
    ANY_VALUE(c.customer_zip_code_prefix) AS zip_code_prefix,
    ANY_VALUE(c.customer_city) AS city,
    ANY_VALUE(c.customer_state) AS state,
    COUNT(DISTINCT c.customer_id) AS n_customer_ids
FROM raw_customers c
GROUP BY c.customer_unique_id;

CREATE OR REPLACE TABLE dim_products AS
SELECT
    p.product_id AS product_sk,
    p.product_category_name AS category_pt,
    t.product_category_name_english AS category_en,
    p.product_name_lenght AS product_name_length,
    p.product_description_lenght AS product_description_length,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
FROM raw_products p
LEFT JOIN raw_category_translation t
    ON p.product_category_name = t.product_category_name;

CREATE OR REPLACE TABLE dim_sellers AS
SELECT
    s.seller_id AS seller_sk,
    s.seller_zip_code_prefix AS zip_code_prefix,
    s.seller_city AS city,
    s.seller_state AS state
FROM raw_sellers s;

CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT
        MIN(CAST(order_purchase_timestamp AS DATE)) AS d_min,
        MAX(CAST(order_purchase_timestamp AS DATE)) AS d_max
    FROM raw_orders
    WHERE order_purchase_timestamp IS NOT NULL
),
spine AS (
    SELECT UNNEST(generate_series(d_min, d_max, INTERVAL 1 DAY))::DATE AS date_day
    FROM bounds
)
SELECT
    date_day AS date_sk,
    EXTRACT(year FROM date_day)::INTEGER AS year,
    EXTRACT(month FROM date_day)::INTEGER AS month,
    EXTRACT(day FROM date_day)::INTEGER AS day,
    EXTRACT(dow FROM date_day)::INTEGER AS day_of_week,
    STRFTIME(date_day, '%Y-%m') AS year_month
FROM spine;

CREATE OR REPLACE TABLE fact_order_items AS
SELECT
    i.order_id,
    i.order_item_id,
    i.product_id AS product_sk,
    i.seller_id AS seller_sk,
    CAST(i.shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
    CAST(i.price AS DOUBLE) AS price,
    CAST(i.freight_value AS DOUBLE) AS freight_value
FROM raw_order_items i;

CREATE OR REPLACE TABLE fact_orders AS
WITH pay AS (
    SELECT
        order_id,
        SUM(CAST(payment_value AS DOUBLE)) AS payment_value_total,
        COUNT(*) AS n_payment_lines,
        MAX(payment_type) AS payment_type_primary
    FROM raw_order_payments
    GROUP BY order_id
),
rev AS (
    SELECT
        order_id,
        AVG(CAST(review_score AS DOUBLE)) AS review_score_avg,
        COUNT(*) AS n_reviews
    FROM raw_order_reviews
    GROUP BY order_id
),
items_agg AS (
    SELECT
        order_id,
        SUM(price) AS gmv_items,
        SUM(freight_value) AS freight_total,
        COUNT(*) AS n_items
    FROM fact_order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.customer_unique_id AS customer_sk,
    o.order_status,
    CAST(o.order_purchase_timestamp AS TIMESTAMP) AS order_purchase_timestamp,
    CAST(o.order_purchase_timestamp AS DATE) AS purchase_date_sk,
    CAST(o.order_approved_at AS TIMESTAMP) AS order_approved_at,
    CAST(o.order_delivered_carrier_date AS TIMESTAMP) AS order_delivered_carrier_date,
    CAST(o.order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_date,
    CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS order_estimated_delivery_date,
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
             AND o.order_estimated_delivery_date IS NOT NULL
             AND CAST(o.order_delivered_customer_date AS TIMESTAMP)
                 <= CAST(o.order_estimated_delivery_date AS TIMESTAMP)
        THEN TRUE
        WHEN o.order_delivered_customer_date IS NOT NULL
             AND o.order_estimated_delivery_date IS NOT NULL
        THEN FALSE
        ELSE NULL
    END AS delivered_on_time,
    COALESCE(p.payment_value_total, 0) AS payment_value_total,
    COALESCE(p.n_payment_lines, 0) AS n_payment_lines,
    p.payment_type_primary,
    r.review_score_avg,
    COALESCE(r.n_reviews, 0) AS n_reviews,
    COALESCE(ia.gmv_items, 0) AS gmv_items,
    COALESCE(ia.freight_total, 0) AS freight_total,
    COALESCE(ia.n_items, 0) AS n_items
FROM raw_orders o
LEFT JOIN raw_customers c ON o.customer_id = c.customer_id
LEFT JOIN pay p ON o.order_id = p.order_id
LEFT JOIN rev r ON o.order_id = r.order_id
LEFT JOIN items_agg ia ON o.order_id = ia.order_id;
