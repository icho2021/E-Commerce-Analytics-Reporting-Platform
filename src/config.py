"""Project paths and AWS settings loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _path(value: str | None, default: str) -> Path:
    raw = (value or default).strip()
    p = Path(raw)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


@dataclass(frozen=True)
class Settings:
    aws_region: str
    s3_bucket: str
    aws_profile: str | None
    data_dir: Path
    local_raw_dir: Path
    local_processed_dir: Path
    s3_raw_prefix: str
    s3_processed_prefix: str

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_bucket) and self.s3_bucket != "your-unique-olist-analytics-bucket"


def get_settings() -> Settings:
    profile = os.getenv("AWS_PROFILE", "").strip() or None
    return Settings(
        aws_region=os.getenv("AWS_REGION", "us-east-1").strip(),
        s3_bucket=os.getenv("S3_BUCKET", "").strip(),
        aws_profile=profile,
        data_dir=_path(os.getenv("DATA_DIR"), "data"),
        local_raw_dir=_path(os.getenv("LOCAL_RAW_DIR"), "lake/raw/olist"),
        local_processed_dir=_path(os.getenv("LOCAL_PROCESSED_DIR"), "lake/processed/star"),
        s3_raw_prefix=os.getenv("S3_RAW_PREFIX", "raw/olist").strip().strip("/"),
        s3_processed_prefix=os.getenv("S3_PROCESSED_PREFIX", "processed/star")
        .strip()
        .strip("/"),
    )
