"""
Stage 2 — Transform: load raw CSVs into DuckDB, build star schema, export Parquet/CSV,
optionally upload processed layer to S3.

Usage:
  python -m src.transform_star
  python -m src.transform_star --skip-s3
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb

from src.config import PROJECT_ROOT, get_settings
from src.s3_io import ensure_bucket_reachable, upload_dir

STAR_TABLES = [
    "dim_customers",
    "dim_products",
    "dim_sellers",
    "dim_date",
    "fact_orders",
    "fact_order_items",
]

RAW_MAP = {
    "raw_customers": "olist_customers_dataset.csv",
    "raw_orders": "olist_orders_dataset.csv",
    "raw_order_items": "olist_order_items_dataset.csv",
    "raw_order_payments": "olist_order_payments_dataset.csv",
    "raw_order_reviews": "olist_order_reviews_dataset.csv",
    "raw_products": "olist_products_dataset.csv",
    "raw_sellers": "olist_sellers_dataset.csv",
    "raw_category_translation": "product_category_name_translation.csv",
}


def _register_raw(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    for view, filename in RAW_MAP.items():
        path = raw_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing raw file: {path}")
        # DuckDB read_csv_auto; quote path for spaces
        con.execute(
            f"CREATE OR REPLACE VIEW {view} AS "
            f"SELECT * FROM read_csv_auto('{path.as_posix()}', header=true)"
        )


def build_star(raw_dir: Path, out_dir: Path) -> dict:
    sql_path = PROJECT_ROOT / "sql" / "star_schema.sql"
    sql_text = sql_path.read_text(encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(database=":memory:")
    _register_raw(con, raw_dir)
    con.execute(sql_text)

    meta: dict = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "tables": {},
    }

    for table in STAR_TABLES:
        parquet_path = out_dir / f"{table}.parquet"
        csv_path = out_dir / f"{table}.csv"
        con.execute(f"COPY {table} TO '{parquet_path.as_posix()}' (FORMAT PARQUET)")
        con.execute(f"COPY {table} TO '{csv_path.as_posix()}' (HEADER, DELIMITER ',')")
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        meta["tables"][table] = {"rows": int(n), "parquet": parquet_path.name, "csv": csv_path.name}
        print(f"  wrote {table}: {n:,} rows → {parquet_path.name}, {csv_path.name}")

    # Source freshness stamp from fact_orders
    row = con.execute(
        """
        SELECT
            MIN(order_purchase_timestamp) AS min_purchase,
            MAX(order_purchase_timestamp) AS max_purchase,
            COUNT(*) AS n_orders
        FROM fact_orders
        """
    ).fetchone()
    meta["source_freshness"] = {
        "min_order_purchase_timestamp": str(row[0]),
        "max_order_purchase_timestamp": str(row[1]),
        "n_orders": int(row[2]),
    }

    meta_path = out_dir / "pipeline_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  wrote {meta_path.name}")
    con.close()
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build star schema and export processed layer")
    parser.add_argument("--skip-s3", action="store_true", help="Do not upload processed files to S3")
    args = parser.parse_args(argv)
    settings = get_settings()

    print("=== Stage 2: transform star schema ===")
    raw_dir = settings.local_raw_dir
    if not any(raw_dir.glob("*.csv")):
        # Fall back to source data/ if ingest not run yet
        print(f"No CSVs in {raw_dir}; using DATA_DIR={settings.data_dir}")
        raw_dir = settings.data_dir

    meta = build_star(raw_dir, settings.local_processed_dir)
    print(
        "Freshness:",
        meta["source_freshness"]["min_order_purchase_timestamp"],
        "→",
        meta["source_freshness"]["max_order_purchase_timestamp"],
    )

    if args.skip_s3:
        print("Skipped S3 upload (--skip-s3).")
        return 0

    ensure_bucket_reachable(settings)
    print(f"Uploading to s3://{settings.s3_bucket}/{settings.s3_processed_prefix}/ ...")
    upload_dir(settings, settings.local_processed_dir, settings.s3_processed_prefix)
    print("Processed upload complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
