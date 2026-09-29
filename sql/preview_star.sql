-- Preview star schema in DuckDB / DBCode
-- 1) In terminal (project root):  python -m src.create_duckdb_workspace
-- 2) Open lake/olist_workspace.duckdb in the DuckDB extension
-- 3) Run the queries below (no file paths needed)

-- List how many rows in each fact/dim
SELECT 'fact_orders' AS table_name, COUNT(*) AS n FROM fact_orders
UNION ALL SELECT 'fact_order_items', COUNT(*) FROM fact_order_items
UNION ALL SELECT 'dim_customers', COUNT(*) FROM dim_customers
UNION ALL SELECT 'dim_products', COUNT(*) FROM dim_products
UNION ALL SELECT 'dim_sellers', COUNT(*) FROM dim_sellers
UNION ALL SELECT 'dim_date', COUNT(*) FROM dim_date;

-- Peek at orders
SELECT *
FROM fact_orders
LIMIT 20;

-- Order status mix
SELECT order_status, COUNT(*) AS orders
FROM fact_orders
GROUP BY 1
ORDER BY 2 DESC;

-- Join fact → customer dim (star schema in action)
SELECT
    c.state,
    COUNT(*) AS orders,
    ROUND(SUM(f.gmv_items), 2) AS gmv
FROM fact_orders f
JOIN dim_customers c ON f.customer_sk = c.customer_sk
WHERE f.order_status = 'delivered'
GROUP BY 1
ORDER BY gmv DESC
LIMIT 15;
