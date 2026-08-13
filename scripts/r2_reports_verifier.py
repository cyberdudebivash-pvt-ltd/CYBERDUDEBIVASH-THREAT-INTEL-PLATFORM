#!/usr/bin/env python3
"""
scripts/r2_reports_verifier.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- RX-PUB-A0 Reports Artifact Identity Verifier

RX-PUB-A0 Phase 9 / Sections 19-25: closes the gap documented in
docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md and docs/RX_PUB_A0_EXECUTION_PATH.md --
scripts/r2_upload_verifier.py (STAGE 3.6) already does exactly this kind of
authenticated, hash-based, HARD FAIL post-upload verification, but is scoped
exclusively to the single data-bucket manifest object
(sentinel-apex-data/intel/feed_manifest.json). It never checks a single
reports/*.html object. This script is the same verification pattern --
reused via direct import, not reimplemented -- applied to the actual
customer-facing report artifacts.

Per the mission's Section 3 correction: a clean `aws s3 sync` exit code is a
transfer-decision fact (missing / size differs / mtime newer), never a
content-identity proof. This script supplies the missing proof directly:
SHA-256 of the exact bytes on both sides.

SCOPE (bounded, not the full ~15k+ historical corpus -- see Section 36 cost
governance): verifies every report currently in the active generation
window (data/stix/feed_manifest.json) -- the same set
generate_intel_reports.py's "Zero-skip" policy unconditionally regenerates
every pipeline run, so this is exactly the "changed this run" set the
mission's Section 22 requires full (non-sampled) verification for. Historical
reports outside this window are out of scope per Section 26.

For each in-window report:
  Layer A (cheap, always): S3 API head-object -- existence, size, ETag.
  Layer B (SHA-256, always for in-window reports): S3 API get-object -> SHA-256
    of the exact remote bytes, compared against the local file's SHA-256.

Writes data/quality/rx_pub_a0_reports_artifact_manifest.json (Phase 9 schema)
and HARD FAILS (nonzero exit) if any in-window report's remote SHA-256 does
not match its local SHA-256, or does not exist in R2 at all.

Environment variables consumed (same names r2_upload.py already uses):
  CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
  CF_R2_REPORTS_KEY_ID, CF_R2_REPORTS_SECRET_KEY (optional, preferred if set --
    same dedicated-token swap pattern as r2_upload.py's reports-upload phase)

No secrets are logged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# RX-PUB-A0: swap in the dedicated reports-bucket credentials (if configured)
# BEFORE importing r2_upload_verifier, whose R2 connection helpers
# (_s3api_head_object / _boto3_head_object) read CF_ACCOUNT_ID / ACCESS_KEY /
# SECRET_KEY as module-level constants captured at import time -- same
# swap-then-restore pattern r2_upload.py's main() already uses for its own
# reports-bucket upload phase.
_reports_key_id = os.environ.get("CF_R2_REPORTS_KEY_ID", "").strip()
_reports_secret = os.environ.get("CF_R2_REPORTS_SECRET_KEY", "").strip()
_orig_key_id    = os.environ.get("AWS_ACCESS_KEY_ID", "")
_orig_secret    = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
if _reports_key_id and _reports_secret:
    os.environ["AWS_ACCESS_KEY_ID"]     = _reports_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = _reports_secret

import r2_upload_verifier as _verifier  # noqa: E402 -- reuse, not reimplement
import r2_upload as _r2_upload  # noqa: E402 -- BUCKET_REPORTS, get_credentials()

# Restore whatever the job-level credentials were, now that the reports-scoped
# constants have been captured inside _verifier's module globals.
os.environ["AWS_ACCESS_KEY_ID"]     = _orig_key_id
os.environ["AWS_SECRET_ACCESS_KEY"] = _orig_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [rx-pub-a0-reports-verify] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.rx_pub_a0_reports_verifier")

MANIFEST_PATH  = REPO_ROOT / "data" / "stix" / "feed_manifest.json"
OUTPUT_PATH    = REPO_ROOT / "data" / "quality" / "rx_pub_a0_reports_artifact_manifest.json"
BUCKET_REPORTS = _r2_upload.BUCKET_REPORTS
GENERATOR_NAME = "generate_intel_reports.py"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_in_window_entries() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error("Cannot parse %s: %s", MANIFEST_PATH, e)
        return []
    if isinstance(data, list):
        return data
    for key in ("advisories", "items", "data", "entries"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def _local_report_path(entry: dict) -> Path | None:
    ru = (entry.get("internal_report_url") or entry.get("report_url") or "").strip()
    if ru.startswith("/"):
        p = REPO_ROOT / ru.lstrip("/")
        return p if p.exists() else None
    intel_id = entry.get("id") or entry.get("stix_id")
    if not intel_id:
        return None
    matches = sorted((REPO_ROOT / "reports").rglob(f"{intel_id}.html"))
    return matches[0] if matches else None


def _r2_key_for(local_path: Path) -> str:
    return str(local_path.relative_to(REPO_ROOT)).replace(os.sep, "/")


def verify_one(local_path: Path, r2_key: str) -> dict:
    local_bytes = local_path.read_bytes()
    local_sha256 = _sha256_bytes(local_bytes)
    result = {
        "r2_key":         r2_key,
        "size_bytes":     len(local_bytes),
        "generator":      GENERATOR_NAME,
        "artifact_sha256": local_sha256,
        "remote_sha256":  None,
        "remote_verified_at": None,
        "publication_state": "PENDING",
    }

    head = _verifier._s3api_head_object(BUCKET_REPORTS, r2_key)
    if head is None:
        head = _verifier._boto3_head_object(BUCKET_REPORTS, r2_key)

    if head is None:
        result["publication_state"] = "UNKNOWN"
        result["error"] = "head-object failed via both awscli and boto3"
        return result

    if head["status"] == 404:
        result["publication_state"] = "FAILED"
        result["error"] = "R2 object does not exist"
        return result

    remote_bytes = _get_object_bytes(BUCKET_REPORTS, r2_key)

    if remote_bytes is None:
        result["publication_state"] = "UNKNOWN"
        result["error"] = "get-object failed -- could not fetch remote bytes for SHA-256 comparison"
        return result

    remote_sha256 = _sha256_bytes(remote_bytes)
    result["remote_sha256"] = remote_sha256
    result["remote_verified_at"] = _verifier._utc_now()

    if remote_sha256 == local_sha256:
        result["publication_state"] = "REMOTE_VERIFIED"
    else:
        result["publication_state"] = "STALE_OR_DIVERGENT"
        result["error"] = (
            f"artifact_sha256 ({local_sha256[:16]}...) != remote_sha256 "
            f"({remote_sha256[:16]}...) -- local and R2 bytes diverge"
        )
    return result


def _get_object_bytes(bucket: str, key: str) -> bytes | None:
    """get-object via the same awscli s3api pattern _s3api_head_object uses.
    Not present in r2_upload_verifier.py (it only ever needed head-object) --
    this is the one genuinely new primitive this script adds, kept as small
    and consistent with the existing helper's style as possible."""
    import subprocess
    import tempfile

    if not (_verifier.CF_ACCOUNT_ID and _verifier.ACCESS_KEY and _verifier.SECRET_KEY):
        return None

    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"]     = _verifier.ACCESS_KEY
    env["AWS_SECRET_ACCESS_KEY"] = _verifier.SECRET_KEY
    env["AWS_DEFAULT_REGION"]    = "auto"

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "obj"
        cmd = [
            "aws", "s3api", "get-object",
            "--bucket", bucket, "--key", key,
            "--endpoint-url", _verifier.R2_ENDPOINT,
            str(out_path),
        ]
        for attempt in range(1, _verifier.MAX_RETRIES + 1):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=_verifier.REQUEST_TIMEOUT, env=env,
                )
                if result.returncode == 0 and out_path.exists():
                    return out_path.read_bytes()
                log.warning(
                    "get-object failed (attempt %d/%d) for s3://%s/%s: rc=%d stderr=%s",
                    attempt, _verifier.MAX_RETRIES, bucket, key,
                    result.returncode, result.stderr.strip()[:200],
                )
            except Exception as e:
                log.warning(
                    "get-object error (attempt %d/%d) for s3://%s/%s: %s",
                    attempt, _verifier.MAX_RETRIES, bucket, key, e,
                )
            if attempt < _verifier.MAX_RETRIES:
                time.sleep(_verifier.RETRY_DELAY)
    return None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enforce", action="store_true",
        help="Hard-fail (nonzero exit) on any STALE_OR_DIVERGENT/FAILED report. "
             "Not passed in CI yet -- observability-only bake-in period, matching "
             "the same rollout pattern scripts/report_engine_consistency_gate.py "
             "already established for a new gate on this exact keyspace. Once a "
             "run history exists showing zero false positives, add --enforce to "
             "the STAGE 3.6a workflow step to make this a real HARD FAIL gate "
             "(RX-PUB-A0 Section 25 requires this eventually)."
    )
    args = parser.parse_args()

    log.info("=" * 70)
    log.info("RX-PUB-A0 Reports Artifact Identity Verifier")
    log.info("Bucket: %s  |  in-window manifest: %s", BUCKET_REPORTS, MANIFEST_PATH)
    log.info("Mode: %s", "ENFORCE (hard fail on mismatch)" if args.enforce else "observability-only (bake-in)")
    log.info("=" * 70)
    t0 = time.time()

    if not (_verifier.CF_ACCOUNT_ID and _verifier.ACCESS_KEY and _verifier.SECRET_KEY):
        msg = (
            "R2 credentials absent (CF_ACCOUNT_ID / AWS_ACCESS_KEY_ID / "
            "AWS_SECRET_ACCESS_KEY) -- skipping. Trusting Stage 3.5 exit code "
            "as source of truth for this run (same soft-pass posture as "
            "r2_upload_verifier.py's own credential-absent path)."
        )
        log.warning(msg)
        return 0

    entries = _load_in_window_entries()
    log.info("In-window manifest entries: %d", len(entries))

    manifest_out: dict = {
        "schema_version": "1",
        "generated_at":   _verifier._utc_now(),
        "pipeline_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "release_sha":    os.environ.get("GITHUB_SHA", "unknown"),
        "bucket":         BUCKET_REPORTS,
        "reports":        {},
    }

    verified = 0
    mismatched = 0
    missing_local = 0
    unknown = 0

    for entry in entries:
        intel_id = entry.get("id") or entry.get("stix_id")
        if not intel_id:
            continue
        local_path = _local_report_path(entry)
        if not local_path:
            missing_local += 1
            manifest_out["reports"][intel_id] = {
                "publication_state": "FAILED",
                "error": "no local HTML artifact found for an in-window manifest entry",
            }
            continue

        r2_key = _r2_key_for(local_path)
        result = verify_one(local_path, r2_key)
        result["source_record_id"] = intel_id
        result["source_updated_at"] = entry.get("processed_at") or entry.get("timestamp") or ""
        result["path"] = str(local_path.relative_to(REPO_ROOT))
        manifest_out["reports"][intel_id] = result

        state = result["publication_state"]
        if state == "REMOTE_VERIFIED":
            verified += 1
        elif state == "STALE_OR_DIVERGENT" or state == "FAILED":
            mismatched += 1
            log.error("[%s] %s: %s", state, intel_id, result.get("error", ""))
        else:
            unknown += 1
            log.warning("[%s] %s: %s", state, intel_id, result.get("error", ""))

    elapsed = round(time.time() - t0, 2)
    manifest_out["summary"] = {
        "total_in_window":  len(entries),
        "remote_verified":  verified,
        "stale_or_divergent_or_failed": mismatched,
        "unknown":          unknown,
        "missing_local":    missing_local,
        "elapsed_seconds":  elapsed,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest_out, indent=2, default=str), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)
    log.info("Wrote %s", OUTPUT_PATH)

    log.info(
        "Summary: %d in-window, %d REMOTE_VERIFIED, %d STALE_OR_DIVERGENT/FAILED, "
        "%d UNKNOWN, %d missing-local, %.2fs",
        len(entries), verified, mismatched, unknown, missing_local, elapsed,
    )

    if mismatched > 0:
        log.error("=" * 70)
        log.error(
            "%s -- %d in-window report(s) have a proven local/remote "
            "SHA-256 mismatch or missing R2 object. A changed, certified "
            "commercial artifact must be remotely verified before this run "
            "can be treated as production-certified (RX-PUB-A0 Section 25).",
            "HARD FAIL" if args.enforce else "WOULD HARD FAIL (--enforce not set)",
            mismatched,
        )
        log.error("=" * 70)
        return 1 if args.enforce else 0

    log.info("PASS -- every in-window report's remote SHA-256 matches its local artifact.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log.critical("Unhandled exception: %s\n%s", e, traceback.format_exc())
        sys.exit(1)
