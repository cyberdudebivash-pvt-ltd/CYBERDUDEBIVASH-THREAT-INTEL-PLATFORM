#!/usr/bin/env python3
"""
scripts/intel_state_r2_sync.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Intel Ingestion State R2 Runtime-Authority Bridge

ARCHITECTURE NOTE: multi-source-intel.yml's true_intel_ingestor.py tracks
cross-run incremental-ingestion state in 3 files:
    data/cache/feed_state.json     -- per-source last-seen timestamps
    data/processed_intel.json      -- dedup fingerprint store
    data/stix/feed_manifest.json   -- the intel manifest itself (this
                                       pipeline's additive output, and
                                       run_pipeline.py / sentinel-blogger.yml's
                                       own Single Source of Truth input)

That workflow used to persist these files by committing + pushing directly
to main on a schedule (every ~4h). Confirmed live (GitHub Actions run
history, 2026-09-02): every run that finds new items has that push
rejected by this repository's branch-protection ruleset (GH013, "changes
must be made through a pull request"), and a prior fix made that
rejection loud (hard-fail) instead of silent -- but the underlying
architecture was unchanged: newly-ingested intelligence was still
discarded every time, because there was nowhere else for it to go.

Per the explicitly approved direction (no branch-protection bypass, no
automation exception, no recurring auto-merge data PRs, no weakening of
the ruleset): this migrates runtime authority for these 3 files from
"committed to protected main" to the same R2 bucket (sentinel-apex-data)
the rest of this platform's runtime data already lives in -- reusing the
exact aws-cli-via-R2-endpoint upload pattern scripts/r2_resync_manifests.py
and scripts/r2_upload.py already established (Reuse Before Build /
Single Source of Truth for the upload primitive), in both directions:

  --download : pull the current R2 copies into their local paths before
               true_intel_ingestor.py runs, so this run's incremental
               dedup/state tracking picks up from wherever the last
               successful run actually left off -- not from whatever
               stale copy happens to be in this checkout's git history,
               which (per the failure above) can be arbitrarily far
               behind. Non-fatal by design: a missing R2 object is the
               expected first-run/bootstrap case, not an error -- falls
               through to whatever this checkout already has, identical
               to this script not existing at all.

  --upload   : push the freshly-updated local copies to R2 after
               true_intel_ingestor.py runs, making them immediately
               readable by sentinel-blogger.yml's own R2 bootstrap step
               (see that workflow's "Pull intel ingestion state from R2"
               step) and by any Worker handler that reads them directly --
               without a git commit, without a PR, and without waiting
               for a deploy. An actual upload failure is loud (exit 1),
               matching this repository's existing convention for R2
               upload failures (r2_resync_manifests.py); a local file
               that does not exist yet is skipped, not an error.

This script never touches git and never re-implements the R2 upload
mechanics (aws-cli via a Cloudflare R2 S3-compatible endpoint) --
it calls the same `aws s3 cp` shape r2_resync_manifests.py already uses.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [intel-state-r2-sync] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.intel_state_r2_sync")

REPO_ROOT   = Path(__file__).resolve().parent.parent
BUCKET_DATA = "sentinel-apex-data"

# (local path, R2 key) -- same bucket, "intel/ingestion/" prefix keeps this
# runtime-authority state cleanly separated from the customer-facing
# api/v1/intel/*.json keys r2_resync_manifests.py manages.
STATE_FILES = [
    (REPO_ROOT / "data" / "cache" / "feed_state.json",   "intel/ingestion/feed_state.json"),
    (REPO_ROOT / "data" / "processed_intel.json",        "intel/ingestion/processed_intel.json"),
    (REPO_ROOT / "data" / "stix" / "feed_manifest.json", "intel/ingestion/feed_manifest.json"),
]


def get_credentials() -> tuple[str, str, str]:
    cf_account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    if not cf_account or not access_key or not secret_key:
        log.error("FATAL: CF_ACCOUNT_ID / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set.")
        sys.exit(1)
    return cf_account, access_key, secret_key


def s3_cp(src: str, dst: str, endpoint: str) -> subprocess.CompletedProcess:
    cmd = [
        "aws", "s3", "cp", src, dst,
        "--endpoint-url", endpoint,
        "--content-type", "application/json",
        "--only-show-errors",
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def download(endpoint: str) -> int:
    """Pull current R2 copies into their local paths. A missing R2 object
    is the expected bootstrap/first-run case, not a failure -- falls
    through to this checkout's own copy, same as before this script
    existed."""
    pulled = 0
    for local_path, r2_key in STATE_FILES:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        src = f"s3://{BUCKET_DATA}/{r2_key}"
        result = subprocess.run(
            ["aws", "s3", "cp", src, str(local_path), "--endpoint-url", endpoint, "--only-show-errors"],
            capture_output=True, text=True,
        )
        rel = local_path.relative_to(REPO_ROOT)
        if result.returncode == 0:
            log.info("OK: pulled %s <- %s", rel, src)
            pulled += 1
        else:
            log.info("SKIP: no R2 object at %s yet -- using this checkout's copy of %s", src, rel)
    log.info("Download complete: %d/%d pulled from R2.", pulled, len(STATE_FILES))
    return pulled


def upload(endpoint: str) -> bool:
    """Push local copies to R2. A local file that does not exist is
    skipped (nothing new to upload); an actual upload failure is loud."""
    uploaded = 0
    skipped = 0
    failed = 0
    for local_path, r2_key in STATE_FILES:
        rel = local_path.relative_to(REPO_ROOT)
        if not local_path.exists():
            log.warning("SKIP: %s does not exist locally -- nothing to upload for %s", rel, r2_key)
            skipped += 1
            continue
        dst = f"s3://{BUCKET_DATA}/{r2_key}"
        result = s3_cp(str(local_path), dst, endpoint)
        if result.returncode == 0:
            log.info("OK: %s -> %s", rel, dst)
            uploaded += 1
        else:
            log.warning(
                "WARN: %s -> %s failed (%d): %s %s",
                rel, dst, result.returncode,
                result.stdout.strip()[:200], result.stderr.strip()[:200],
            )
            failed += 1
    log.info("Upload complete: %d uploaded, %d skipped, %d failed.", uploaded, skipped, failed)
    if failed > 0:
        print(
            f"::error::intel_state_r2_sync --upload: {failed} file(s) failed to upload to R2. "
            "This run's freshly-ingested intel state was NOT persisted -- the next scheduled run "
            "will start from stale state again. Check CF_ACCOUNT_ID/CF_R2_ACCESS_KEY_ID/"
            "CF_R2_SECRET_ACCESS_KEY secrets and bucket 'sentinel-apex-data' policy.",
            flush=True,
        )
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--download", action="store_true", help="Pull current R2 state before ingestion runs.")
    mode.add_argument("--upload", action="store_true", help="Push updated state to R2 after ingestion runs.")
    args = parser.parse_args()

    cf_account, _, _ = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"

    log.info("=" * 64)
    log.info("SENTINEL APEX -- Intel Ingestion State R2 Runtime-Authority Bridge")
    log.info("Mode: %s", "download" if args.download else "upload")
    log.info("=" * 64)

    if args.download:
        download(endpoint)
        return 0  # never fatal -- see download()'s own docstring
    return 0 if upload(endpoint) else 1


if __name__ == "__main__":
    sys.exit(main())
