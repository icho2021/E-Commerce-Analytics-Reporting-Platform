"""
Stage 1 — Ingest: copy local Olist CSVs into the raw lake layer and upload to S3.

Usage (from project root):
  python -m src.ingest_raw
  python -m src.ingest_raw --skip-s3   # local lake only
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Allow `python -m src.ingest_raw` from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.s3_io import ensure_bucket_reachable, upload_dir


def copy_raw_csvs(data_dir: Path, local_raw_dir: Path) -> list[Path]:
    if not data_dir.is_dir():
        raise FileNotFoundError(f"DATA_DIR not found: {data_dir}")
    local_raw_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for src in sorted(data_dir.glob("*.csv")):
        dest = local_raw_dir / src.name
        shutil.copy2(src, dest)
        copied.append(dest)
        print(f"  local raw: {dest}")
    if not copied:
        raise FileNotFoundError(f"No CSV files in {data_dir}")
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest Olist CSVs to raw lake + S3")
    parser.add_argument(
        "--skip-s3",
        action="store_true",
        help="Only write lake/raw/olist; do not upload to S3",
    )
    args = parser.parse_args(argv)
    settings = get_settings()

    print("=== Stage 1: ingest raw ===")
    print(f"DATA_DIR = {settings.data_dir}")
    copied = copy_raw_csvs(settings.data_dir, settings.local_raw_dir)
    print(f"Copied {len(copied)} CSV files → {settings.local_raw_dir}")

    if args.skip_s3:
        print("Skipped S3 upload (--skip-s3).")
        return 0

    ensure_bucket_reachable(settings)
    print(f"Uploading to s3://{settings.s3_bucket}/{settings.s3_raw_prefix}/ ...")
    uris = upload_dir(settings, settings.local_raw_dir, settings.s3_raw_prefix, suffix=".csv")
    print(f"Uploaded {len(uris)} objects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
