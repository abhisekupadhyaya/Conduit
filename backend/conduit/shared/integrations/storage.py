"""Object storage — S3 in prod, MinIO locally (verified S3-compatible).

The same boto3 client speaks to AWS S3 or the docker-compose MinIO; only the
endpoint/credentials differ (env). Path-style addressing is required for
MinIO. v1 app is text-only so usage is minimal (artifacts/backups), but the
abstraction keeps prod↔local parity.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from conduit.core.config import get_settings


@lru_cache
def s3_client() -> Any:
    import boto3
    from botocore.config import Config

    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=Config(
            s3={"addressing_style": "path" if s.s3_force_path_style else "auto"}
        ),
    )
