"""
Stage 3 — Data quality checks on the local processed star schema (Parquet).

Critical failures exit with code 1.

Usage:
  python -m src.dq_checks
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb

from src.config import get_settings


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    critical: bool = True


def _con_from_processed(processed_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(database=":memory:")
    for name in (
        "dim_customers",
        "dim_products",
        "dim_sellers",
        "dim_date",
        "fact_orders",
        "fact_order_items",
    ):
        path = processed_dir / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Missing processed table: {path}")
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{path.as_posix()}')"
        )
    return con


def run_checks(processed_dir: Path) -> list[CheckResult]:
    con = _con_from_processed(processed_dir)
    results: list[CheckResult] = []

    def q(sql: str):
        return con.execute(sql).fetchone()[0]

    # --- Null constraints ---
    null_orders = q("SELECT COUNT(*) FROM fact_orders WHERE order_id IS NULL OR customer_sk IS NULL")
    results.append(
        CheckResult(
            "fact_orders_required_not_null",
            null_orders == 0,
            f"rows with null order_id or customer_sk: {null_orders}",
        )
    )
    null_items = q(
        "SELECT COUNT(*) FROM fact_order_items "
        "WHERE order_id IS NULL OR order_item_id IS NULL OR product_sk IS NULL "
        "OR seller_sk IS NULL OR price IS NULL"
    )
    results.append(
        CheckResult(
            "fact_order_items_required_not_null",
            null_items == 0,
            f"rows with null keys/price: {null_items}",
        )
    )

    # --- PK uniqueness ---
    dup_orders = q(
        "SELECT COUNT(*) FROM ("
        " SELECT order_id FROM fact_orders GROUP BY order_id HAVING COUNT(*) > 1"
        ")"
    )
    results.append(
        CheckResult(
            "fact_orders_pk_unique",
            dup_orders == 0,
            f"duplicate order_id groups: {dup_orders}",
        )
    )
    dup_items = q(
        "SELECT COUNT(*) FROM ("
        " SELECT order_id, order_item_id FROM fact_order_items "
        " GROUP BY 1, 2 HAVING COUNT(*) > 1"
        ")"
    )
    results.append(
        CheckResult(
            "fact_order_items_composite_pk_unique",
            dup_items == 0,
            f"duplicate (order_id, order_item_id) groups: {dup_items}",
        )
    )
    for dim, sk in (
        ("dim_customers", "customer_sk"),
        ("dim_products", "product_sk"),
        ("dim_sellers", "seller_sk"),
        ("dim_date", "date_sk"),
    ):
        dups = q(
            f"SELECT COUNT(*) FROM (SELECT {sk} FROM {dim} GROUP BY 1 HAVING COUNT(*) > 1)"
        )
        results.append(
            CheckResult(
                f"{dim}_pk_unique",
                dups == 0,
                f"duplicate {sk} groups: {dups}",
            )
        )

    # --- Non-negative financials ---
    neg_price = q("SELECT COUNT(*) FROM fact_order_items WHERE price < 0 OR freight_value < 0")
    results.append(
        CheckResult(
            "fact_order_items_non_negative_money",
            neg_price == 0,
            f"rows with negative price/freight: {neg_price}",
        )
    )
    neg_pay = q("SELECT COUNT(*) FROM fact_orders WHERE payment_value_total < 0 OR gmv_items < 0")
    results.append(
        CheckResult(
            "fact_orders_non_negative_money",
            neg_pay == 0,
            f"rows with negative payment/gmv: {neg_pay}",
        )
    )

    # --- Source freshness (historical public dataset window) ---
    meta_path = processed_dir / "pipeline_metadata.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        max_ts = meta.get("source_freshness", {}).get("max_order_purchase_timestamp")
        min_ts = meta.get("source_freshness", {}).get("min_order_purchase_timestamp")
        ok = bool(max_ts) and bool(min_ts)
        # Olist public data is ~2016–2018; fail if missing or empty
        detail = f"min={min_ts}, max={max_ts}"
        if ok:
            try:
                # Accept ISO-like timestamps from DuckDB stringification
                max_year = datetime.fromisoformat(str(max_ts).replace(" ", "T")).year
                ok = 2016 <= max_year <= 2019
                detail += f", max_year={max_year} (expected 2016–2019 for public Olist)"
            except ValueError:
                ok = False
                detail += " (could not parse max timestamp)"
        results.append(
            CheckResult("source_freshness_validation", ok, detail, critical=True)
        )
    else:
        results.append(
            CheckResult(
                "source_freshness_validation",
                False,
                "pipeline_metadata.json missing",
                critical=True,
            )
        )

    # Orphan item → order (informational / critical)
    orphan_items = q(
        "SELECT COUNT(*) FROM fact_order_items i "
        "LEFT JOIN fact_orders o ON i.order_id = o.order_id WHERE o.order_id IS NULL"
    )
    results.append(
        CheckResult(
            "fact_order_items_fk_order",
            orphan_items == 0,
            f"item rows without matching fact_orders: {orphan_items}",
        )
    )

    con.close()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run star-schema data quality checks")
    parser.add_argument(
        "--report",
        type=str,
        default="",
        help="Optional path to write JSON report (default: lake/processed/star/dq_report.json)",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    processed = settings.local_processed_dir

    print("=== Stage 3: data quality ===")
    print(f"Processed dir: {processed}")
    results = run_checks(processed)

    failed_critical = [r for r in results if r.critical and not r.passed]
    for r in results:
        flag = "PASS" if r.passed else ("FAIL" if r.critical else "WARN")
        print(f"  [{flag}] {r.name}: {r.detail}")

    report_path = Path(args.report) if args.report else processed / "dq_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "checked_at_utc": datetime.utcnow().isoformat() + "Z",
        "results": [asdict(r) for r in results],
        "critical_failures": len(failed_critical),
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")

    if failed_critical:
        print(f"DQ FAILED: {len(failed_critical)} critical check(s).")
        return 1
    print("DQ PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
