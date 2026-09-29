"""Thin S3 helpers (upload / download / list)."""

from __future__ import annotations

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from src.config import Settings


def s3_client(settings: Settings):
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_profile:
        session = boto3.Session(profile_name=settings.aws_profile)
        return session.client("s3", **kwargs)
    return boto3.client("s3", **kwargs)


def upload_file(settings: Settings, local_path: Path, s3_key: str) -> str:
    client = s3_client(settings)
    key = s3_key.lstrip("/")
    client.upload_file(str(local_path), settings.s3_bucket, key)
    uri = f"s3://{settings.s3_bucket}/{key}"
    print(f"  uploaded {local_path.name} → {uri}")
    return uri


def download_file(settings: Settings, s3_key: str, local_path: Path) -> Path:
    client = s3_client(settings)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    client.download_file(settings.s3_bucket, s3_key.lstrip("/"), str(local_path))
    return local_path


def upload_dir(settings: Settings, local_dir: Path, s3_prefix: str, suffix: str = "") -> list[str]:
    """Upload files under local_dir to s3://bucket/prefix/ (optional name suffix filter)."""
    if not settings.s3_configured:
        raise RuntimeError(
            "S3_BUCKET is not set. Copy .env.example → .env and set a real bucket name. "
            "See docs/aws_setup.md."
        )
    uris: list[str] = []
    prefix = s3_prefix.strip("/")
    paths = sorted(local_dir.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        if suffix and not path.name.endswith(suffix):
            continue
        rel = path.relative_to(local_dir).as_posix()
        key = f"{prefix}/{rel}"
        uris.append(upload_file(settings, path, key))
    return uris


def ensure_bucket_reachable(settings: Settings) -> None:
    if not settings.s3_configured:
        raise RuntimeError("S3_BUCKET not configured. See docs/aws_setup.md and .env.example.")
    client = s3_client(settings)
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        raise RuntimeError(
            f"Cannot access bucket '{settings.s3_bucket}' in {settings.aws_region}: {exc}"
        ) from exc
