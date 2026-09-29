"""
End-to-end pipeline: ingest → transform → DQ → (optional) S3 uploads.

Usage (project root):
  python -m src.run_pipeline --skip-s3
  python -m src.run_pipeline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import dq_checks, ingest_raw, transform_star


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run full Olist analytics pipeline")
    parser.add_argument(
        "--skip-s3",
        action="store_true",
        help="Keep data in local lake/ only; skip all S3 uploads",
    )
    args = parser.parse_args(argv)
    skip = ["--skip-s3"] if args.skip_s3 else []

    print("######## Olist ETL pipeline ########")
    code = ingest_raw.main(skip)
    if code != 0:
        return code
    code = transform_star.main(skip)
    if code != 0:
        return code
    code = dq_checks.main([])
    if code != 0:
        return code
    print("######## Pipeline complete ########")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
