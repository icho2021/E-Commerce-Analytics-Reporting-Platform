"""
Build a local DuckDB file with views over processed star tables (and optional raw CSVs)
so you can preview data in the DuckDB / DBCode extension without fighting file paths.

Usage (project root, venv on):
  python -m src.create_duckdb_workspace

Then in Cursor: open lake/olist_workspace.duckdb with the DuckDB extension,
or run queries in sql/preview_star.sql.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb

from src.config import PROJECT_ROOT, get_settings

STAR_TABLES = [
    "dim_customers",
    "dim_products",
    "dim_sellers",
    "dim_date",
    "fact_orders",
    "fact_order_items",
]


def main() -> int:
    settings = get_settings()
    processed = settings.local_processed_dir
    raw = settings.local_raw_dir
    if not any(processed.glob("*.parquet")):
        print(
            f"No parquet in {processed}. Run first:\n"
            "  python -m src.transform_star --skip-s3"
        )
        return 1

    out = PROJECT_ROOT / "lake" / "olist_workspace.duckdb"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    con = duckdb.connect(str(out))

    for name in STAR_TABLES:
        parquet = processed / f"{name}.parquet"
        if not parquet.is_file():
            print(f"  skip missing {parquet.name}")
            continue
        # Use absolute path with forward slashes; DuckDB needs a quoted string literal
        p = parquet.resolve().as_posix().replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{p}')"
        )
        n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"  view {name}: {n:,} rows")

    # Optional raw sample views (if local raw exists)
    raw_files = {
        "raw_orders": "olist_orders_dataset.csv",
        "raw_order_items": "olist_order_items_dataset.csv",
        "raw_customers": "olist_customers_dataset.csv",
    }
    source_raw = raw if any(raw.glob("*.csv")) else settings.data_dir
    for view, filename in raw_files.items():
        csv_path = source_raw / filename
        if not csv_path.is_file():
            continue
        p = csv_path.resolve().as_posix().replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW {view} AS "
            f"SELECT * FROM read_csv_auto('{p}', header=true)"
        )
        print(f"  view {view}: {csv_path.name}")

    con.close()
    print(f"\nCreated: {out}")
    print("In DuckDB / DBCode: open this file, then run sql/preview_star.sql")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
