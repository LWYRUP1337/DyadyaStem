import functools
from pathlib import Path

import boto3
from botocore.config import Config

import config


@functools.lru_cache(maxsize=1)
def _client():
    scheme = "https" if config.MINIO_SECURE else "http"
    return boto3.client(
        "s3",
        endpoint_url=f"{scheme}://{config.MINIO_ENDPOINT}",
        aws_access_key_id=config.MINIO_ACCESS_KEY,
        aws_secret_access_key=config.MINIO_SECRET_KEY,
        region_name=config.S3_REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def download(key: str, dest: Path) -> None:
    _client().download_file(config.MINIO_BUCKET, key, str(dest))


def upload(path: Path, key: str) -> None:
    _client().upload_file(str(path), config.MINIO_BUCKET, key, ExtraArgs={"ContentType": "audio/mpeg"})


def delete_prefix(prefix: str) -> None:
    """Удаляет все объекты с префиксом (для идемпотентного повтора обработки)."""
    client = _client()
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=config.MINIO_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            client.delete_object(Bucket=config.MINIO_BUCKET, Key=obj["Key"])
