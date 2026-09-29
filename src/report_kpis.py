"""
Executive KPI report from processed star tables (metrics.md definitions).

Produces charts + JSON under output/ — usable as portfolio visuals until Power BI Desktop
is available. Does not replace Power BI; same curated tables, same metric contracts.

Usage (after pipeline):
  python -m src.report_kpis
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("MPLBACKEND", "Agg")

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from src.config import PROJECT_ROOT, get_settings


def _connect(processed: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    for name in (
        "fact_orders",
        "fact_order_items",
        "dim_customers",
        "dim_products",
        "dim_date",
    ):
        path = processed / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Missing {path}; run: python -m src.transform_star --skip-s3")
        p = path.resolve().as_posix().replace("'", "''")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{p}')")
    return con


def compute_kpis(con: duckdb.DuckDBPyConnection) -> dict:
    """Official executive defaults: order_status = delivered (docs/metrics.md)."""
    row = con.execute(
        """
        SELECT
            COUNT(*) AS orders,
            COUNT(DISTINCT customer_sk) AS unique_customers,
            SUM(gmv_items) AS gmv,
            SUM(freight_total) AS freight,
            SUM(payment_value_total) AS payment_total,
            AVG(n_items) AS items_per_order,
            AVG(review_score_avg) AS avg_review,
            SUM(CASE WHEN delivered_on_time THEN 1 ELSE 0 END) AS on_time_n,
            SUM(CASE WHEN delivered_on_time IS NOT NULL THEN 1 ELSE 0 END) AS on_time_denom
        FROM fact_orders
        WHERE order_status = 'delivered'
        """
    ).fetchone()
    orders, customers, gmv, freight, payment, items_po, avg_review, ot_n, ot_d = row
    aov = (gmv / orders) if orders else None
    on_time_rate = (ot_n / ot_d) if ot_d else None

    repeat = con.execute(
        """
        WITH cust AS (
            SELECT customer_sk, COUNT(*) AS n
            FROM fact_orders
            WHERE order_status = 'delivered'
            GROUP BY 1
        )
        SELECT
            COUNT(*) AS customers,
            SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END) AS repeat_customers
        FROM cust
        """
    ).fetchone()
    repeat_rate = (repeat[1] / repeat[0]) if repeat[0] else None

    return {
        "filter": "order_status = delivered",
        "orders": int(orders),
        "unique_customers": int(customers),
        "gmv_items": float(gmv or 0),
        "freight_total": float(freight or 0),
        "payment_total": float(payment or 0),
        "aov": float(aov) if aov is not None else None,
        "items_per_order": float(items_po) if items_po is not None else None,
        "avg_review_score": float(avg_review) if avg_review is not None else None,
        "on_time_delivery_rate": float(on_time_rate) if on_time_rate is not None else None,
        "repeat_customer_rate": float(repeat_rate) if repeat_rate is not None else None,
    }


def _save_fig(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()
    print(f"  wrote {path}")


def plot_charts(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    # Monthly orders (delivered)
    monthly = con.execute(
        """
        SELECT STRFTIME(purchase_date_sk, '%Y-%m') AS month, COUNT(*) AS orders
        FROM fact_orders
        WHERE order_status = 'delivered' AND purchase_date_sk IS NOT NULL
        GROUP BY 1
        ORDER BY 1
        """
    ).df()
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.bar(monthly["month"], monthly["orders"], color="#4C72B0")
    ax.set_title("Delivered orders per month")
    ax.set_xlabel("Month")
    ax.set_ylabel("Orders")
    plt.xticks(rotation=45, ha="right")
    _save_fig(out_dir / "kpi_orders_per_month.png")

    # Top categories by GMV
    cats = con.execute(
        """
        SELECT
            COALESCE(p.category_en, '(unknown)') AS category,
            SUM(i.price) AS gmv
        FROM fact_order_items i
        JOIN fact_orders o ON i.order_id = o.order_id
        LEFT JOIN dim_products p ON i.product_sk = p.product_sk
        WHERE o.order_status = 'delivered'
        GROUP BY 1
        ORDER BY gmv DESC
        LIMIT 12
        """
    ).df()
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(cats["category"][::-1], cats["gmv"][::-1], color="#55A868")
    ax.set_title("Top categories by GMV (delivered)")
    ax.set_xlabel("GMV (BRL)")
    _save_fig(out_dir / "kpi_gmv_by_category.png")

    # Status mix (all statuses — ops view)
    status = con.execute(
        """
        SELECT order_status, COUNT(*) AS orders
        FROM fact_orders
        GROUP BY 1
        ORDER BY orders DESC
        """
    ).df()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.barh(status["order_status"][::-1], status["orders"][::-1], color="#8172B2")
    ax.set_title("Order status mix (all orders)")
    ax.set_xlabel("Orders")
    _save_fig(out_dir / "kpi_status_mix.png")

    # Top states by GMV
    states = con.execute(
        """
        SELECT
            c.state,
            SUM(o.gmv_items) AS gmv,
            COUNT(*) AS orders
        FROM fact_orders o
        JOIN dim_customers c ON o.customer_sk = c.customer_sk
        WHERE o.order_status = 'delivered'
        GROUP BY 1
        ORDER BY gmv DESC
        LIMIT 12
        """
    ).df()
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(states["state"][::-1], states["gmv"][::-1], color="#CCB974")
    ax.set_title("Top customer states by GMV (delivered)")
    ax.set_xlabel("GMV (BRL)")
    _save_fig(out_dir / "kpi_gmv_by_state.png")


def main() -> int:
    settings = get_settings()
    processed = settings.local_processed_dir
    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== KPI report (metrics.md executive defaults) ===")
    con = _connect(processed)
    kpis = compute_kpis(con)
    summary_path = out_dir / "kpi_summary.json"
    summary_path.write_text(json.dumps(kpis, indent=2), encoding="utf-8")
    print(f"  wrote {summary_path}")
    for k, v in kpis.items():
        if k == "filter":
            print(f"  {k}: {v}")
        elif isinstance(v, float):
            print(f"  {k}: {v:,.4f}" if v < 10 else f"  {k}: {v:,.2f}")
        else:
            print(f"  {k}: {v}")

    plot_charts(con, out_dir)
    con.close()
    print("Done. Charts are under output/. Power BI can still use lake/processed/star/ later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
