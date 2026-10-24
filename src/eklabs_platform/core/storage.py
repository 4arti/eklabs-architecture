import asyncio
import functools
import os

import boto3
from botocore.client import BaseClient
from botocore.config import Config

# Supabase Storage, used as a plain S3-compatible bucket (CLAUDE.md's stack
# line: "Files: S3 (supabase)") — any S3 SDK works against it, so this stays
# boto3 rather than a Supabase-specific client, in case storage ever moves.


@functools.lru_cache(maxsize=1)
def _client() -> BaseClient:
    endpoint = os.environ.get("S3_ENDPOINT")
    access_key = os.environ.get("S3_ACCESS_KEY_ID")
    secret_key = os.environ.get("S3_SECRET_ACCESS_KEY")
    region = os.environ.get("S3_REGION")
    if not (endpoint and access_key and secret_key and region):
        raise RuntimeError(
            "S3_ENDPOINT, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY and S3_REGION must all be "
            "set — Supabase project settings -> Storage -> S3 Connection. The region is "
            "required: SigV4 signs requests with it, and a mismatch between what boto3 signs "
            "with and what Supabase expects fails auth, not just a cosmetic setting."
        )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(s3={"addressing_style": "path"}),
    )


def _bucket() -> str:
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        raise RuntimeError("S3_BUCKET is not set.")
    return bucket


async def upload_bytes(key: str, data: bytes, *, content_type: str) -> None:
    """Uploads under `key` exactly as given — callers (documents.py) are
    responsible for prefixing it with the owning tenant_id, so that even at
    the storage layer, not just via RLS, one tenant's files sit under their
    own prefix (spec §13: "files under per-client S3 prefixes").

    `_client()` is resolved lazily (cached after the first real call), not
    at module import time — boto3 construction itself does no network I/O,
    but it does require S3_* env vars that aren't configured everywhere
    this module gets imported from (e.g. documents.py, pulled in by tests
    that never touch storage at all). An eager singleton would break
    collection for the whole suite the moment those vars are unset, the
    same failure mode an unset APP_DATABASE_URL has — except that one is a
    genuine whole-app prerequisite and this isn't, for most tests.
    """
    await asyncio.to_thread(
        _client().put_object,
        Bucket=_bucket(),
        Key=key,
        Body=data,
        ContentType=content_type,
    )


async def download_bytes(key: str) -> bytes:
    response = await asyncio.to_thread(_client().get_object, Bucket=_bucket(), Key=key)
    body: bytes = await asyncio.to_thread(response["Body"].read)
    return body
