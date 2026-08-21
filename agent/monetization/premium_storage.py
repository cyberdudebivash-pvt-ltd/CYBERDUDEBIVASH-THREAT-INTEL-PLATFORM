"""
CYBERDUDEBIVASH® SENTINEL APEX — Premium Artifact Storage v1.0
================================================================
Private (non-public) Cloudflare R2 storage for paid-tier products that were
previously committed straight into this public GitHub repo (api/feed.gold.json,
api/feed.silver.json, api/feed.standard.json, api/feed.executive.json, and the
paid Detection Pack artifacts under api/detections/) -- fetchable by anyone via
raw.githubusercontent.com with zero authentication, and with no route in this
codebase that ever actually checked a caller's tier before serving them.

Deliberately a SEPARATE bucket (sentinel-apex-premium) from the existing
sentinel-apex-data / sentinel-apex-reports buckets used by scripts/r2_upload.py,
which serve public dashboard/report content over a public CDN domain -- reusing
those buckets for paid content would risk the exact same public-exposure bug
this module exists to fix. This bucket should NOT have a public custom domain
or public bucket URL configured in Cloudflare; the only access path is the
CF_R2_PREMIUM_KEY_ID / CF_R2_PREMIUM_SECRET_KEY credentials used here,
server-side, by the pipeline (upload) and by api/main.py's /api/v1/premium/*
routes (fetch, after the caller's tier has already been validated).

Environment variables consumed:
  CF_ACCOUNT_ID           -- Cloudflare account ID (shared with r2_upload.py)
  CF_R2_PREMIUM_KEY_ID    -- Dedicated R2 token for sentinel-apex-premium
  CF_R2_PREMIUM_SECRET_KEY-- Dedicated R2 secret for sentinel-apex-premium

If these are not configured, upload_premium_artifact() and
fetch_premium_artifact() both return a clear failure rather than silently
falling back to a public path -- this is a security boundary, not a
best-effort convenience feature.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("CDB-PREMIUM-STORAGE")

BUCKET_PREMIUM = "sentinel-apex-premium"


def _client():
    """Build a boto3 S3-compatible client for the R2 premium bucket, or None
    if the required credentials aren't configured."""
    account_id = os.environ.get("CF_ACCOUNT_ID", "")
    key_id = os.environ.get("CF_R2_PREMIUM_KEY_ID", "")
    secret = os.environ.get("CF_R2_PREMIUM_SECRET_KEY", "")
    if not (account_id and key_id and secret):
        logger.error(
            "premium_storage: R2 premium credentials not configured "
            "(CF_ACCOUNT_ID / CF_R2_PREMIUM_KEY_ID / CF_R2_PREMIUM_SECRET_KEY)"
        )
        return None
    try:
        import boto3
        return boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
            region_name="auto",
        )
    except Exception as e:
        logger.error(f"premium_storage: failed to build R2 client: {e}")
        return None


def upload_premium_artifact(local_path: str, r2_key: str) -> bool:
    """Upload a local file to the private premium bucket. Returns True on
    success. Called by the pipeline (generate_tiered_feeds.py,
    generate_detection_pack.py) after writing paid-tier content locally."""
    client = _client()
    if client is None:
        return False
    try:
        client.upload_file(local_path, BUCKET_PREMIUM, r2_key)
        logger.info(f"premium_storage: uploaded {local_path} -> s3://{BUCKET_PREMIUM}/{r2_key}")
        return True
    except Exception as e:
        logger.error(f"premium_storage: upload failed for {r2_key}: {e}")
        return False


def fetch_premium_artifact(r2_key: str) -> Optional[bytes]:
    """Fetch a premium artifact's raw bytes from the private bucket, or None
    if unavailable. Called ONLY after the caller's tier has already been
    validated by the API route -- this function performs no entitlement
    check of its own."""
    client = _client()
    if client is None:
        return None
    try:
        obj = client.get_object(Bucket=BUCKET_PREMIUM, Key=r2_key)
        return obj["Body"].read()
    except Exception as e:
        logger.warning(f"premium_storage: fetch failed for {r2_key}: {e}")
        return None
