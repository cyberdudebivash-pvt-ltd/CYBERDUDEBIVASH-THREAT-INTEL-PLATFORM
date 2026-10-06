#!/usr/bin/env python3
"""
scripts/r2_reports_purge.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- ONE-TIME Historical Report Purge (P0)
================================================================================
Purges the pre-incident historical report corpus (~193K objects) from
sentinel-apex-reports. This is a ONE-TIME MIGRATION tool, not part of the
recurring production pipeline -- it is NEVER invoked by any scheduled
workflow. See docs/P0_R2_COST_CONTAINMENT.md for the full incident.

ORDERING REQUIREMENT (do not skip): this script must only be run AFTER the
new bounded architecture (scripts/r2_report_publisher.py) has been deployed
and has completed at least one real scheduled run. That run populates
data/cache/r2_report_publish_state.json with the exact, authoritative set
of report keys that are currently valid (<=24h old) -- this script's KEEP
set. Running this before that state file exists/is populated is refused by
default (see --i-understand-the-keep-set-is-empty below): with no keep set,
"purge >24h objects" is indistinguishable from "delete everything", and this
script will not guess.

WHY THE KEEP SET, NOT OBJECT AGE OR LastModified:
The incident this migration cleans up up was CAUSED by a whole-corpus `aws
s3 sync` re-uploading the entire historical report corpus on every pipeline
run (see scripts/r2_upload.py's former Upload-4a block, now removed) --
which means many now-historical objects' R2 LastModified timestamp reflects
recent *accidental re-uploads*, not when the underlying intelligence was
actually current. Trusting LastModified here would wrongly treat stale
reports as "recent" and fail to purge them. The R2 key path itself
(reports/YYYY/MM/...) is a more stable signal (same reasoning already
established in this codebase by scripts/report_archive_manager.py's own
REPORT_RETENTION_DAYS docstring), but only at month granularity -- too
coarse for a 24h decision. The authoritative, precise signal is instead:
"is this exact key one scripts/r2_report_publisher.py currently tracks as
live." Anything else under reports/ is, by construction, something that
script is no longer maintaining -- safe to purge. Path-derived year-month
buckets are still computed and printed in the dry-run summary purely as
human-readable context, never as the deletion criterion.

THIS SCRIPT NEVER TOUCHES sentinel-apex-data OR cyberdudebivash-scan-results.
The target bucket is hardcoded and asserted, not merely defaulted -- see
ALLOWED_BUCKET below and _assert_bucket_allowed().

Usage:
  python3 scripts/r2_reports_purge.py                                    # DRY RUN (default, always safe)
  python3 scripts/r2_reports_purge.py --execute --confirm-bucket sentinel-apex-reports
                                                                           # ACTUAL DELETION

Environment variables (same as scripts/r2_upload.py):
  CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  CF_R2_REPORTS_KEY_ID, CF_R2_REPORTS_SECRET_KEY (optional dedicated token)

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2_upload import BUCKET_DATA, BUCKET_REPORTS, get_credentials, install_awscli  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [r2-reports-purge] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.r2_reports_purge")

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "data" / "cache" / "r2_report_publish_state.json"
PURGE_REPORT_PATH = REPO_ROOT / "data" / "quality" / "r2_reports_purge_report.json"

# Hardcoded, asserted allowlist -- this script may delete from ONE bucket
# only, ever. Never sourced from an env var or CLI flag alone (the
# --confirm-bucket flag below must match this constant, not the other way
# around, so an operator cannot accidentally redirect a destructive run at
# the wrong bucket by mistyping a flag).
ALLOWED_BUCKET = BUCKET_REPORTS  # "sentinel-apex-reports"
NEVER_TOUCH_BUCKETS = {BUCKET_DATA, "cyberdudebivash-scan-results"}

DELETE_BATCH_SIZE = 1000  # aws s3api delete-objects hard max per call


def _assert_bucket_allowed(bucket: str) -> None:
    if bucket in NEVER_TOUCH_BUCKETS:
        raise SystemExit(
            f"FATAL: refusing to target {bucket!r} -- this script is hardcoded to "
            f"NEVER touch {sorted(NEVER_TOUCH_BUCKETS)}. This is not configurable."
        )
    if bucket != ALLOWED_BUCKET:
        raise SystemExit(
            f"FATAL: refusing to target {bucket!r} -- this script only ever "
            f"operates on {ALLOWED_BUCKET!r}."
        )


def load_keep_set() -> set[str]:
    """The exact, authoritative set of R2 keys scripts/r2_report_publisher.py
    currently tracks as live (<=24h window). Empty if the state file is
    missing or has never been populated -- callers MUST treat that as "no
    authoritative keep set available", never as "keep nothing"."""
    if not STATE_PATH.exists():
        return set()
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Could not parse %s (%s) -- treating keep set as unavailable.", STATE_PATH, exc)
        return set()
    items = state.get("items", {}) if isinstance(state, dict) else {}
    keep: set[str] = set()
    for entry in items.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("html_key"):
            keep.add(entry["html_key"])
        if entry.get("pdf_key"):
            keep.add(entry["pdf_key"])
    return keep


def list_all_objects(bucket: str, prefix: str, endpoint: str) -> list[dict]:
    """The ONE sanctioned full-bucket LIST in this codebase's normal-operation
    surface -- explicitly a one-time migration operation, not a recurring
    pipeline call (scripts/r2_report_publisher.py's whole architecture exists
    specifically so this never has to happen again after this migration)."""
    objects: list[dict] = []
    continuation_token: Optional[str] = None
    page = 0
    while True:
        cmd = [
            "aws", "s3api", "list-objects-v2",
            "--bucket", bucket,
            "--prefix", prefix,
            "--endpoint-url", endpoint,
            "--output", "json",
            "--max-items", "1000",
        ]
        if continuation_token:
            cmd += ["--starting-token", continuation_token]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"list-objects-v2 failed (page {page}): {result.stderr.strip()[:500]}")
        page += 1
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"list-objects-v2 returned non-JSON output (page {page}): {exc}") from exc
        for obj in payload.get("Contents", []) or []:
            objects.append({"key": obj.get("Key", ""), "size": int(obj.get("Size", 0))})
        continuation_token = (payload.get("NextToken") or "")
        if not continuation_token:
            break
    log.info("Listed %d object(s) under s3://%s/%s across %d page(s).", len(objects), bucket, prefix, page)
    return objects


def year_month_from_key(key: str) -> str:
    parts = key.split("/")
    if len(parts) >= 3 and parts[0] == "reports" and parts[1].isdigit() and parts[2].isdigit():
        return f"{parts[1]}-{parts[2]}"
    return "unknown"


def batch_delete(bucket: str, keys: list[str], endpoint: str) -> tuple[int, int]:
    """Deletes `keys` from `bucket` in batches of up to DELETE_BATCH_SIZE via
    `aws s3api delete-objects` (one API call per batch, not one per key --
    keeps even the one-time purge itself bounded in call count, not just
    bounded in scope). Returns (deleted_ok, deleted_failed)."""
    ok = 0
    failed = 0
    for i in range(0, len(keys), DELETE_BATCH_SIZE):
        batch = keys[i:i + DELETE_BATCH_SIZE]
        delete_payload = {"Objects": [{"Key": k} for k in batch], "Quiet": True}
        cmd = [
            "aws", "s3api", "delete-objects",
            "--bucket", bucket,
            "--endpoint-url", endpoint,
            "--delete", json.dumps(delete_payload),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            ok += len(batch)
            log.info("Deleted batch %d-%d/%d.", i + 1, i + len(batch), len(keys))
        else:
            failed += len(batch)
            log.error("Batch delete failed for keys %d-%d: %s", i + 1, i + len(batch), result.stderr.strip()[:500])
    return ok, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Actually delete objects. Without this, always dry-run (default).")
    parser.add_argument("--confirm-bucket", default="",
                        help=f"Must be exactly {ALLOWED_BUCKET!r} to permit --execute -- "
                             f"an explicit, unambiguous statement of intent.")
    parser.add_argument("--i-understand-the-keep-set-is-empty", action="store_true",
                        help="Required in addition to --execute if the keep set (from "
                             "scripts/r2_report_publisher.py's state file) is empty. An empty "
                             "keep set with this flag ABSENT means 'purge >24h objects' cannot "
                             "be distinguished from 'delete everything', so --execute is refused.")
    args = parser.parse_args()

    log.info("=" * 70)
    log.info("SENTINEL APEX -- ONE-TIME Historical Report Purge")
    log.info("Mode: %s", "EXECUTE (destructive)" if args.execute else "DRY-RUN (default, no changes)")
    log.info("=" * 70)

    _assert_bucket_allowed(ALLOWED_BUCKET)
    if args.execute and args.confirm_bucket != ALLOWED_BUCKET:
        log.critical(
            "FATAL: --execute requires --confirm-bucket %s exactly (got %r). "
            "Refusing to run destructively without explicit, unambiguous confirmation.",
            ALLOWED_BUCKET, args.confirm_bucket,
        )
        return 1

    keep_set = load_keep_set()
    log.info("Keep set (from %s): %d key(s) currently tracked as live by r2_report_publisher.py.",
              STATE_PATH.relative_to(REPO_ROOT), len(keep_set))
    if not keep_set and args.execute and not args.i_understand_the_keep_set_is_empty:
        log.critical(
            "FATAL: keep set is EMPTY -- scripts/r2_report_publisher.py has not yet run (or "
            "produced zero tracked reports) in this environment. Refusing --execute: with no "
            "authoritative keep set, this would delete EVERY object in %s, not just the >24h "
            "historical corpus. Deploy and run the new pipeline first (see ordering requirement "
            "in this script's module docstring), or pass --i-understand-the-keep-set-is-empty "
            "if you have independently verified this is safe.",
            ALLOWED_BUCKET,
        )
        return 1

    cf_account, _access_key, _secret_key = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    install_awscli()

    reports_key_id = os.environ.get("CF_R2_REPORTS_KEY_ID", "").strip()
    reports_secret = os.environ.get("CF_R2_REPORTS_SECRET_KEY", "").strip()
    if reports_key_id and reports_secret:
        os.environ["AWS_ACCESS_KEY_ID"] = reports_key_id
        os.environ["AWS_SECRET_ACCESS_KEY"] = reports_secret
        log.info("Using dedicated %s R2 token.", ALLOWED_BUCKET)

    all_objects = list_all_objects(ALLOWED_BUCKET, "reports/", endpoint)
    total_objects = len(all_objects)
    total_bytes = sum(o["size"] for o in all_objects)

    keep_objects = [o for o in all_objects if o["key"] in keep_set]
    delete_objects = [o for o in all_objects if o["key"] not in keep_set]
    bytes_retained = sum(o["size"] for o in keep_objects)
    bytes_eligible = sum(o["size"] for o in delete_objects)

    year_month_counts: dict[str, int] = {}
    for o in delete_objects:
        ym = year_month_from_key(o["key"])
        year_month_counts[ym] = year_month_counts.get(ym, 0) + 1

    log.info("-" * 70)
    log.info("PURGE SCOPE")
    log.info("  bucket:                %s", ALLOWED_BUCKET)
    log.info("  prefix:                reports/")
    log.info("  total objects:         %d (%.1f MB)", total_objects, total_bytes / 1e6)
    log.info("  KEEP (live, tracked):  %d (%.1f MB)", len(keep_objects), bytes_retained / 1e6)
    log.info("  DELETE (historical):   %d (%.1f MB)", len(delete_objects), bytes_eligible / 1e6)
    log.info("  historical by year-month (informational, path-derived, not the deletion criterion):")
    for ym in sorted(year_month_counts):
        log.info("    %s: %d object(s)", ym, year_month_counts[ym])
    log.info("-" * 70)

    report = {
        "bucket": ALLOWED_BUCKET,
        "prefix": "reports/",
        "dry_run": not args.execute,
        "total_objects": total_objects,
        "total_bytes": total_bytes,
        "keep_count": len(keep_objects),
        "bytes_retained": bytes_retained,
        "delete_count": len(delete_objects),
        "bytes_eligible_for_deletion": bytes_eligible,
        "delete_by_year_month": year_month_counts,
    }

    if not args.execute:
        log.warning("[DRY-RUN] No objects deleted. Re-run with --execute --confirm-bucket %s to purge.", ALLOWED_BUCKET)
        report["deleted_ok"] = 0
        report["deleted_failed"] = 0
        PURGE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        PURGE_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    if not delete_objects:
        log.info("Nothing to delete -- every object in %s is in the current keep set.", ALLOWED_BUCKET)
        report["deleted_ok"] = 0
        report["deleted_failed"] = 0
        PURGE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        PURGE_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 0

    log.warning("EXECUTING DESTRUCTIVE DELETE of %d object(s) from %s ...", len(delete_objects), ALLOWED_BUCKET)
    deleted_ok, deleted_failed = batch_delete(ALLOWED_BUCKET, [o["key"] for o in delete_objects], endpoint)
    report["deleted_ok"] = deleted_ok
    report["deleted_failed"] = deleted_failed
    PURGE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PURGE_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    log.info("PURGE COMPLETE: %d deleted, %d failed.", deleted_ok, deleted_failed)
    if deleted_failed:
        log.error("%d object(s) failed to delete -- re-run this script to retry "
                   "(it recomputes the plan fresh from the current keep set each time).", deleted_failed)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log.critical("Unhandled exception in r2_reports_purge.py:\n%s\n%s", e, traceback.format_exc())
        sys.exit(1)
