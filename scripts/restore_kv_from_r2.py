#!/usr/bin/env python3
"""
scripts/restore_kv_from_r2.py
CYBERDUDEBIVASH(R) SENTINEL APEX - Cloudflare KV Namespace Restore from R2

Restores a KV namespace from a daily snapshot JSON file previously written by
scripts/backup_kv_to_r2.py (key schema: kv-snapshots/{YYYY-MM-DD}/{namespace_name}.json).
Companion to that script, which has no restore counterpart.

Env vars required:
  CF_API_TOKEN            - CF token with KV:Write permission
  CF_ACCOUNT_ID           - Cloudflare account ID
  CF_R2_ACCESS_KEY_ID     - R2 S3-compatible access key
  CF_R2_SECRET_ACCESS_KEY - R2 S3-compatible secret key
  CF_R2_ENDPOINT          - https://<account_id>.r2.cloudflarestorage.com
  CF_R2_BUCKET            - source bucket (default: sentinel-apex-data)

Usage:
  python3 scripts/restore_kv_from_r2.py --namespace API_KEYS_KV --date 2026-07-28 [--dry-run]
"""
import os
import sys
import json
import time
import hashlib
import argparse
import urllib.request
import urllib.error
import urllib.parse

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("FATAL: boto3 is required. Run: pip install boto3")
    sys.exit(1)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "")
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "")
CF_R2_ACCESS_KEY = os.environ.get("CF_R2_ACCESS_KEY_ID", "")
CF_R2_SECRET_KEY = os.environ.get("CF_R2_SECRET_ACCESS_KEY", "")
CF_R2_ENDPOINT = os.environ.get("CF_R2_ENDPOINT", "")
CF_R2_BUCKET = os.environ.get("CF_R2_BUCKET", "sentinel-apex-data")

KV_NAMESPACES = {
    "API_KEYS_KV":      "ca786702c6df47b7a95d9777536c7cfb",
    "RATE_LIMIT_KV":    "647efdda28dc4a2db91378931cfa02dc",
    "ANALYTICS_KV":     "baa66e510f7247d4b268af943bfb7213",
    "SECURITY_HUB_KV":  "95faae90943f43afa26d552b8385d339",
}


def cf_put(path, body_bytes):
    url = f"{CF_API_BASE}{path}"
    req = urllib.request.Request(
        url,
        data=body_bytes,
        method="PUT",
        headers={"Authorization": f"Bearer {CF_API_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CF API {path} -> HTTP {e.code}: {body[:200]}")


def put_kv_value(ns_id, key, value):
    path = f"/accounts/{CF_ACCOUNT_ID}/storage/kv/namespaces/{ns_id}/values/{urllib.parse.quote(key, safe='')}"
    return cf_put(path, value.encode("utf-8"))


def download_snapshot(ns_name, date):
    if not all([CF_R2_ACCESS_KEY, CF_R2_SECRET_KEY, CF_R2_ENDPOINT]):
        raise RuntimeError("R2 credentials not configured -- cannot download snapshot")
    s3 = boto3.client(
        "s3",
        endpoint_url=CF_R2_ENDPOINT,
        aws_access_key_id=CF_R2_ACCESS_KEY,
        aws_secret_access_key=CF_R2_SECRET_KEY,
        region_name="auto",
    )
    key = f"kv-snapshots/{date}/{ns_name}.json"
    try:
        obj = s3.get_object(Bucket=CF_R2_BUCKET, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except ClientError as e:
        raise RuntimeError(f"Could not fetch snapshot {key}: {e}")


def verify_checksum(snapshot):
    entries = snapshot.get("entries", {})
    expected = snapshot.get("checksum_sha256", "")
    actual = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    return actual == expected, expected, actual


def restore_namespace(ns_name, ns_id, snapshot, dry_run):
    entries = snapshot.get("entries", {})
    print(f"  Snapshot exported_at={snapshot.get('exported_at')} count={snapshot.get('count')}")

    ok_checksum, expected, actual = verify_checksum(snapshot)
    if not ok_checksum:
        print(f"  FATAL: checksum mismatch -- expected {expected}, got {actual}. Refusing to restore a snapshot that may be corrupted or tampered with.")
        return False

    restored, errors = 0, 0
    for i, (key, value) in enumerate(entries.items()):
        if value is None:
            continue
        if dry_run:
            restored += 1
            continue
        try:
            put_kv_value(ns_id, key, value)
            restored += 1
        except Exception as e:
            print(f"    WARN: could not restore key {key!r}: {e}")
            errors += 1
        if i > 0 and i % 100 == 0:
            print(f"    Progress: {i}/{len(entries)} keys restored...")
            time.sleep(0.05)

    verb = "Would restore" if dry_run else "Restored"
    print(f"  [{'DRY RUN' if dry_run else 'LIVE'}] {verb} {restored} keys ({errors} errors) to {ns_name}")
    return errors == 0


def main():
    parser = argparse.ArgumentParser(description="Restore a Cloudflare KV namespace from an R2 backup snapshot")
    parser.add_argument("--namespace", required=True, choices=sorted(KV_NAMESPACES), help="KV namespace to restore")
    parser.add_argument("--date", required=True, help="Snapshot date, YYYY-MM-DD (must match a date backup_kv_to_r2.py already ran for)")
    parser.add_argument("--dry-run", action="store_true", help="Verify and report only -- write nothing to KV")
    args = parser.parse_args()

    if not args.dry_run and not CF_API_TOKEN:
        print("FATAL: CF_API_TOKEN not set")
        sys.exit(1)
    if not args.dry_run and not CF_ACCOUNT_ID:
        print("FATAL: CF_ACCOUNT_ID not set")
        sys.exit(1)

    ns_id = KV_NAMESPACES[args.namespace]
    print(f"=== SENTINEL APEX KV Restore <- R2 | Namespace: {args.namespace} | Date: {args.date} | dry_run={args.dry_run} ===")

    snapshot = download_snapshot(args.namespace, args.date)
    success = restore_namespace(args.namespace, ns_id, snapshot, args.dry_run)

    if not success:
        print("\nFATAL: restore completed with errors -- see warnings above.")
        sys.exit(1)

    print("\n=== KV restore complete. ===")


if __name__ == "__main__":
    main()
