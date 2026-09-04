#!/usr/bin/env python3
"""
scripts/r2_upload.py
CYBERDUDEBIVASH(R) SENTINEL APEX v200.0 -- Cloudflare R2 Upload Engine
=========================================================================
P0 FIX: Replaces the inline PYEOF/unquoted-heredoc R2 upload block from
sentinel-blogger.yml.  Zero inline Python in YAML.

P0 R2 COST INCIDENT FIX (2026-09): this script no longer touches the
sentinel-apex-reports bucket at all. It used to run `aws s3 sync reports/
-> s3://sentinel-apex-reports/reports/` (whole-prefix LIST + full content
comparison, no bound) on every scheduled run -- confirmed root cause of a
3,004,147-Class-A-operation billing cycle (docs/P0_R2_COST_CONTAINMENT.md).
That sync, and its reports/pdf/ counterpart, have been removed entirely --
not flag-gated. scripts/r2_report_publisher.py is now the sole writer/
retirer for both keyspaces: deterministic keys, sha256-diffed against its
own state file (zero R2 LIST), bounded to a rolling 24h window, fail-closed
operation budget before any mutation. Run it as its own pipeline stage
immediately after this script.

Responsibilities (bounded to sentinel-apex-data only):
  1.  Validate R2 credentials (CF_ACCOUNT_ID, AWS_ACCESS_KEY_ID,
      AWS_SECRET_ACCESS_KEY).  Exit 1 if any missing.
  2.  Install awscli if not present.
  3.  Configure awscli for high-throughput parallel uploads.
  4.  Upload feed_manifest.json and enriched manifests.
  5.  Upload apex_v2 API endpoint files.
  6.  Upload AI intelligence data files.
  7.  Write and upload sync_meta.json with advisory count + run metadata.

Report/PDF publishing to sentinel-apex-reports and reports/pdf/ moved to
scripts/r2_report_publisher.py -- see that script's module docstring.

Environment variables consumed (set at job level in workflow):
  CF_ACCOUNT_ID            -- Cloudflare account ID
  AWS_ACCESS_KEY_ID        -- R2 access key
  AWS_SECRET_ACCESS_KEY    -- R2 secret key
  CF_R2_REPORTS_KEY_ID     -- Dedicated token for sentinel-apex-reports bucket
  CF_R2_REPORTS_SECRET_KEY -- Dedicated secret for sentinel-apex-reports bucket
  PIPELINE_VERSION         -- e.g. 143.0.0
  GITHUB_RUN_ID            -- GitHub run ID
  REPORT_COUNT             -- set by run_pipeline.py

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [r2_upload] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.r2_upload")

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_VERSION = os.environ.get("PIPELINE_VERSION", "200.0")
BUCKET_DATA = "sentinel-apex-data"
BUCKET_REPORTS = "sentinel-apex-reports"  # written/retired only by scripts/r2_report_publisher.py now


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_github_env(key: str, value: str) -> None:
    gh_env = os.environ.get("GITHUB_ENV", "/dev/null")
    try:
        with open(gh_env, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")
    except Exception:
        pass


def get_credentials() -> tuple[str, str, str]:
    """Return (cf_account_id, access_key, secret_key). Exit 1 if missing."""
    cf_account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    access_key  = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key  = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()

    if not cf_account or not access_key:
        log.error("FATAL: CF_ACCOUNT_ID or AWS_ACCESS_KEY_ID not set.")
        log.error("Add secrets per SETUP_GITHUB_SECRETS.md -- R2 upload is MANDATORY.")
        sys.exit(1)
    return cf_account, access_key, secret_key


def install_awscli() -> None:
    """Install awscli if aws command is not available."""
    result = subprocess.run(["aws", "--version"], capture_output=True)
    if result.returncode == 0:
        log.info("awscli already installed.")
        return
    log.info("Installing awscli...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "awscli", "--quiet"],
        check=False,
    )


def configure_awscli_performance() -> None:
    """
    Configure awscli for high-throughput R2 uploads.

    Root cause of the 36-minute stall: default awscli uses only 10 concurrent
    requests and computes MD5 checksums for every file before uploading.
    For 18k+ HTML reports this takes 35+ minutes, exceeding the old 60-minute
    job timeout.

    Fix:
      - max_concurrent_requests = 50  (5x throughput increase)
      - multipart_chunksize = 16MB    (fewer round trips per file)
      - max_queue_size = 10000        (larger in-flight queue)
      - multipart_threshold = 64MB   (single-part for small HTML files)

    The --size-only flag on s3 sync handles the checksum problem separately.
    """
    settings = [
        ("default.s3.max_concurrent_requests", "50"),
        ("default.s3.multipart_chunksize", "16MB"),
        ("default.s3.max_queue_size", "10000"),
        ("default.s3.multipart_threshold", "64MB"),
    ]
    for key, value in settings:
        subprocess.run(
            ["aws", "configure", "set", key, value],
            capture_output=True, check=False,
        )
    log.info(
        "OK: awscli performance profile set -- "
        "50 concurrent requests, 16MB chunks, size-only comparison."
    )


def s3_cp(
    src: str,
    dst_bucket: str,
    dst_key: str,
    endpoint: str,
    content_type: str = "application/json",
    cache_control: str = "no-cache, no-store, must-revalidate",
    only_show_errors: bool = True,
) -> bool:
    """Upload a single file to R2. Returns True on success."""
    cmd = [
        "aws", "s3", "cp", src, f"s3://{dst_bucket}/{dst_key}",
        "--endpoint-url", endpoint,
        "--content-type", content_type,
        "--cache-control", cache_control,
    ]
    if only_show_errors:
        cmd.append("--only-show-errors")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("OK: Uploaded %s -> s3://%s/%s", src, dst_bucket, dst_key)
        return True
    log.warning(
        "WARN: Upload failed (%d): %s %s",
        result.returncode, result.stdout.strip(), result.stderr.strip(),
    )
    return False


def s3_get(
    dst_local: str,
    src_bucket: str,
    src_key: str,
    endpoint: str,
) -> str:
    """
    Download a single object from R2 to a local path.

    Returns one of three distinct outcomes -- callers that need bootstrap
    semantics (missing object is fine, transient errors are not) MUST branch
    on this three-way result rather than treating any failure alike:
      "OK"        -- downloaded successfully, dst_local now holds the object.
      "NOT_FOUND" -- the object genuinely does not exist yet in R2 (a brand
                     new key, e.g. before this migration's first successful
                     upload). Safe to fall back to a bootstrap source.
      "ERROR"     -- anything else (network, auth, R2 outage, malformed
                     response, or -- CodeRabbit review finding on this
                     migration, verified: AWS's actual NoSuchBucket message
                     is "The specified bucket does not exist", which the
                     naive "does not exist" substring check below used to
                     also match, misclassifying a wrong/misconfigured bucket
                     name as "object not created yet" -- checked first and
                     explicitly excluded). NOT safe to treat any of these as
                     "start fresh": doing so for a dedup/incremental-state
                     object could silently discard real history and
                     reintroduce duplicates, or mask a bucket misconfig
                     behind what looks like a normal first-run bootstrap.
    """
    cmd = [
        "aws", "s3", "cp", f"s3://{src_bucket}/{src_key}", dst_local,
        "--endpoint-url", endpoint,
        "--only-show-errors",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("OK: Downloaded s3://%s/%s -> %s", src_bucket, src_key, dst_local)
        return "OK"

    combined = f"{result.stdout}\n{result.stderr}".lower()
    if "nosuchbucket" in combined:
        log.error(
            "ERROR: Download failed for s3://%s/%s (%d): bucket does not "
            "exist or is misconfigured -- NOT the same as the object simply "
            "not being created yet. %s %s",
            src_bucket, src_key, result.returncode,
            result.stdout.strip(), result.stderr.strip(),
        )
        return "ERROR"
    if "404" in combined or "not found" in combined or "nosuchkey" in combined or "does not exist" in combined:
        log.info(
            "NOT_FOUND: s3://%s/%s does not exist yet (expected on first run "
            "after a state-object migration).", src_bucket, src_key,
        )
        return "NOT_FOUND"

    log.error(
        "ERROR: Download failed for s3://%s/%s (%d): %s %s",
        src_bucket, src_key, result.returncode,
        result.stdout.strip(), result.stderr.strip(),
    )
    return "ERROR"


def s3_delete(
    bucket: str,
    key: str,
    endpoint: str,
) -> bool:
    """Delete a single object from R2. Returns True on success (including
    the case where the object is already absent -- `aws s3 rm` on a
    nonexistent key exits 0, which is the correct outcome for a caller
    retiring an object it believes exists: idempotent, not an error).

    Cloudflare R2 does not bill DeleteObject as a Class A operation (see
    scripts/r2_cost_guard.py's module docstring) -- this helper exists for
    bounded, deterministic-key retirement (scripts/r2_report_publisher.py's
    24h rolling-window cleanup), not as a cost optimization in itself. Callers
    remain responsible for keeping the total delete count bounded and
    tracked through r2_cost_guard -- unbounded blast radius, not billing, is
    the risk this helper does not protect against on its own.
    """
    cmd = [
        "aws", "s3", "rm", f"s3://{bucket}/{key}",
        "--endpoint-url", endpoint,
        "--only-show-errors",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("OK: Deleted s3://%s/%s", bucket, key)
        return True
    log.warning(
        "WARN: Delete failed (%d): %s %s",
        result.returncode, result.stdout.strip(), result.stderr.strip(),
    )
    return False


def s3_sync(
    src_dir: str,
    dst_bucket: str,
    dst_prefix: str,
    endpoint: str,
    content_type: str = "text/html; charset=utf-8",
    cache_control: str = "public, max-age=300",
    size_only: bool = False,
    timeout_seconds: int | None = None,
) -> bool:
    """
    Sync a directory to R2. Returns True on success.

    Args:
        size_only:       Use --size-only instead of full MD5 checksum comparison.
                         Dramatically faster for large directories where most files
                         are already in R2 and unchanged.
        timeout_seconds: Hard subprocess timeout in seconds. On expiry, logs a WARN
                         and returns False (non-fatal). Prevents job-level timeout
                         kill from leaving the pipeline in an unknown state.
    """
    cmd = [
        "aws", "s3", "sync", src_dir, f"s3://{dst_bucket}/{dst_prefix}",
        "--endpoint-url", endpoint,
        "--content-type", content_type,
        "--cache-control", cache_control,
        "--only-show-errors",
    ]
    if size_only:
        cmd.append("--size-only")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "WARN: s3 sync timed out after %ds (non-fatal). "
            "Partial upload may have occurred -- existing R2 files remain valid. "
            "Remaining files will sync on the next pipeline run.",
            timeout_seconds,
        )
        return False

    if result.returncode == 0:
        log.info("OK: Synced %s -> s3://%s/%s", src_dir, dst_bucket, dst_prefix)
        return True
    log.warning(
        "WARN: Sync had errors (%d): %s",
        result.returncode, result.stderr.strip()[:400],
    )
    return False


def s3_sync_download(
    dst_dir: str,
    src_bucket: str,
    src_prefix: str,
    endpoint: str,
    timeout_seconds: int | None = None,
) -> bool:
    """
    Download counterpart to s3_sync(): pulls src_bucket/src_prefix down to
    dst_dir. Returns True on success (including the trivial case where the
    prefix has no objects yet -- `aws s3 sync` from an empty/nonexistent
    prefix is a legitimate no-op, not an error, unlike s3_get()'s single-
    object OK/NOT_FOUND/ERROR contract which a directory sync doesn't need:
    without --delete, sync only adds/updates -- it never removes files
    already present in dst_dir, so a git-checkout copy of dst_dir is safe to
    sync onto (bootstrap-safe by construction, no special-casing required).
    """
    cmd = [
        "aws", "s3", "sync", f"s3://{src_bucket}/{src_prefix}", dst_dir,
        "--endpoint-url", endpoint,
        "--only-show-errors",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        log.warning(
            "WARN: s3 sync download timed out after %ds (non-fatal) -- "
            "existing local copy of %s is left untouched.",
            timeout_seconds, dst_dir,
        )
        return False

    if result.returncode == 0:
        log.info("OK: Synced s3://%s/%s -> %s", src_bucket, src_prefix, dst_dir)
        return True
    log.warning(
        "WARN: Sync download had errors (%d): %s",
        result.returncode, result.stderr.strip()[:400],
    )
    return False


def upload_p40_artifacts(endpoint: str) -> int:
    """
    Upload the 3 P40 Global Intelligence Source Fabric artifacts to R2.

    Extracted from main()'s inline "Upload 2b" block so it can also be
    invoked standalone (--p40-only) late in sentinel-blogger.yml, after
    STAGE 5.9.5 regenerates these files. Without this, main()'s single
    upload pass at STAGE 3.5 runs BEFORE STAGE 5.9.5 in the same pipeline
    execution, so the freshly-regenerated certification/health reports were
    never uploaded until the *next* pipeline run — R2 was permanently one
    full pipeline cycle (~8h) behind what was actually on disk/in git.
    Returns the count of artifacts uploaded (0-3).
    """
    p40_source_fabric_files = [
        ("data/registry/source_registry.json",           "intel/source_registry.json"),
        ("data/quality/source_fabric_health.json",        "intel/source_fabric_health.json"),
        ("data/quality/p40_certification_report.json",    "intel/p40_certification_report.json"),
    ]
    uploaded_p40 = 0
    for src, dst_key in p40_source_fabric_files:
        if Path(src).exists():
            s3_cp(src, BUCKET_DATA, dst_key, endpoint)
            uploaded_p40 += 1
        else:
            log.warning("SKIP: %s not found (P40 endpoint will 503 until it is generated)", src)
    log.info("OK: P40 source fabric artifacts uploaded (%d/%d)",
             uploaded_p40, len(p40_source_fabric_files))
    return uploaded_p40


def main_p40_only() -> None:
    """Late-pipeline sync of just the P40 artifacts (see upload_p40_artifacts)."""
    log.info("=" * 60)
    log.info("SENTINEL APEX v%s -- R2 Upload Engine (P40-only late sync)", PIPELINE_VERSION)
    log.info("=" * 60)
    os.chdir(REPO_ROOT)
    cf_account, _access_key, _secret_key = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    install_awscli()
    upload_p40_artifacts(endpoint)
    log.info("P40-only R2 sync complete.")


def count_manifest() -> int:
    """Count advisory entries in feed_manifest.json."""
    path = REPO_ROOT / "data" / "stix" / "feed_manifest.json"
    if not path.exists():
        return 0
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return len(d)
        if isinstance(d, dict):
            for key in ("advisories", "reports", "items"):
                if key in d and isinstance(d[key], list):
                    return len(d[key])
    except Exception:
        pass
    return 0


def main() -> None:
    log.info("=" * 60)
    log.info("SENTINEL APEX v%s -- R2 Upload Engine", PIPELINE_VERSION)
    log.info("=" * 60)

    os.chdir(REPO_ROOT)

    cf_account, access_key, secret_key = get_credentials()
    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"

    install_awscli()

    # Configure awscli for high-throughput parallel uploads BEFORE any transfer.
    # This is the primary fix for the 36-minute stall / job-timeout cancellation.
    configure_awscli_performance()

    item_count = count_manifest()
    log.info("Uploading %d advisories to R2...", item_count)

    # --- Upload 1: Primary feed manifest (OVERWRITE) ---
    s3_cp(
        "data/stix/feed_manifest.json",
        BUCKET_DATA, "intel/feed_manifest.json",
        endpoint,
    )
    log.info("OK: feed_manifest.json uploaded (%d items)", item_count)

    # --- Upload 2: Enriched manifests ---
    enriched_files = [
        ("data/apex_enriched_manifest.json",    "intel/apex_enriched_manifest.json"),
        ("data/apex_v2_manifest.json",          "intel/apex_v2_manifest.json"),
        ("data/apex_v2_strategic_report.json",  "intel/apex_v2_strategic_report.json"),
        ("data/validated_manifest.json",        "intel/validated_manifest.json"),
    ]
    for src, dst_key in enriched_files:
        if Path(src).exists():
            s3_cp(src, BUCKET_DATA, dst_key, endpoint)

    # --- Upload 2b: P40 Global Intelligence Source Fabric artifacts ---
    # Bridges scripts/build_source_registry.py, scripts/source_fabric_health.py,
    # and scripts/p40_production_certification.py output into R2 so
    # workers/intel-gateway/src/p40-handlers.js (env.INTEL_R2.get(...)) can
    # actually serve real data instead of a permanent 503. Same
    # additive-tuple-list pattern as "Upload 2" above -- no existing upload
    # touched. This early-pipeline upload is superseded later in the same
    # run by STAGE 5.9.5's `r2_upload.py --p40-only` call once the
    # certification/health reports are regenerated fresh -- see
    # upload_p40_artifacts()'s docstring for why that late call exists.
    upload_p40_artifacts(endpoint)

    # --- Upload 3: apex_v2 API endpoint files ---
    apex_v2_dir = REPO_ROOT / "api" / "apex_v2"
    if apex_v2_dir.is_dir():
        for f in apex_v2_dir.glob("*.json"):
            s3_cp(str(f), BUCKET_DATA, f"apex_v2/{f.name}", endpoint)
        log.info("OK: apex_v2/ uploaded")

    # --- Upload 3a: Immutable public intel manifests (v150.1 API-first) ---
    # Served by Cloudflare Worker via servePublicIntelManifest() using
    # r2Key = pathname.slice(1), e.g. "api/v1/intel/latest.json".
    # Uploading here guarantees Worker hits R2 (primary, ~1ms) instead of
    # GitHub raw fallback (~150-300ms, rate-limited).
    #
    # v184.0 FIX: api/feed.json is now EXPLICITLY uploaded to R2.
    # ROOT CAUSE: handleFeedJson in the Worker reads intel/feed_manifest.json
    # (STIX format -- only ~54 items survive normaliseManifestData filtering)
    # while api/feed.json has ALL pipeline items (71+ items, plain array).
    # Uploading api/feed.json as R2 key "api/feed.json" lets the Worker serve
    # the full authoritative feed without schema-loss normalisation.
    intel_v1_manifests = [
        ("api/feed.json",                 "api/feed.json"),                # v184.0 CRITICAL FIX
        ("api/v1/intel/latest.json",      "api/v1/intel/latest.json"),
        ("api/v1/intel/latest_pro.json",  "api/v1/intel/latest_pro.json"),  # PRO/ENTERPRISE tier manifest (includes report_url)
        ("api/v1/intel/top10.json",       "api/v1/intel/top10.json"),
        ("api/v1/intel/apex.json",        "api/v1/intel/apex.json"),
        ("api/v1/intel/manifest.json",    "api/v1/intel/manifest.json"),
        ("api/v1/intel/ai_summary.json",  "api/v1/intel/ai_summary.json"),  # AI Cyber Brain endpoint (v147.0)
        # v161.3: Reports index files -- public (dashboard REPORTS tab via Worker)
        # Written by build_reports_index.py (Stage 3.3.7). Must be in R2 so the
        # Worker can serve them without auth to the public dashboard.
        ("api/reports/latest.json",       "api/reports/latest.json"),    # top-50 for dashboard REPORTS tab
        ("api/reports/index.json",        "api/reports/index.json"),     # full 500-entry index
        ("api/reports/stats.json",        "api/reports/stats.json"),     # severity breakdown + totals
    ]
    uploaded_manifests = 0
    for src, dst_key in intel_v1_manifests:
        src_path = REPO_ROOT / src
        if src_path.exists():
            s3_cp(str(src_path), BUCKET_DATA, dst_key, endpoint)
            uploaded_manifests += 1
        else:
            log.warning("SKIP: %s not found (will fallback to GitHub raw)", src)
    log.info(
        "OK: api/v1/intel/ manifests uploaded (%d/%d)",
        uploaded_manifests, len(intel_v1_manifests),
    )

    # --- Upload 3b: AI Tracker endpoint files (v148.1.0 FIX - MANDATORY) ---
    # ROOT CAUSE FIX: api/ai/tracker.json, health.json, executive-brief.json
    # were not being explicitly tracked. This block ensures all four AI Tracker
    # files are explicitly uploaded each pipeline run (the ai_dirs loop in
    # Upload 4b also covers these, but this explicit block provides auditability
    # and fail-safe coverage even if generate_ai_endpoints.py step is skipped).
    ai_tracker_files = [
        ("api/ai/tracker.json",          "ai/tracker.json"),
        ("api/ai/health.json",           "ai/health.json"),
        ("api/ai/executive-brief.json",  "ai/executive-brief.json"),
        ("api/ai/monetization.json",     "ai/monetization.json"),
    ]
    uploaded_ai_tracker = 0
    for src, dst_key in ai_tracker_files:
        src_path = REPO_ROOT / src
        if src_path.exists():
            s3_cp(str(src_path), BUCKET_DATA, dst_key, endpoint)
            uploaded_ai_tracker += 1
        else:
            log.warning("SKIP (AI tracker): %s not found -- run generate-and-sync workflow first", src)
    log.info("OK: AI Tracker files uploaded to R2 (%d/%d)", uploaded_ai_tracker, len(ai_tracker_files))

    # --- Upload 3c: AI Index + Detection Rule Manifest (Stage 4 P0) ---
    # Same fix as Upload 3b above, extended to the two files backing
    # index.html's per-card "AI Record" / "Detection Rules" annotations
    # (_cdbGetAIRecord() / _cdbGetDetectionRules()), which previously had
    # no R2 copy at all -- the Worker's new intel-gateway proxy route
    # (INTEL_STATIC_PROXY) checks R2 first, so these need to land here for
    # that proxy to serve fresh content instead of always falling through
    # to its gh-pages fallback.
    ai_index_files = [
        ("data/ai_intelligence/ai_index.json",                     "intelligence/ai_index.json"),
        ("data/intelligence/detection_rules/rule_manifest.json",   "intelligence/detection_rules_manifest.json"),
    ]
    uploaded_ai_index = 0
    for src, dst_key in ai_index_files:
        src_path = REPO_ROOT / src
        if src_path.exists():
            s3_cp(str(src_path), BUCKET_DATA, dst_key, endpoint)
            uploaded_ai_index += 1
        else:
            log.warning("SKIP (AI index): %s not found", src)
    log.info("OK: AI index/detection-rules files uploaded to R2 (%d/%d)", uploaded_ai_index, len(ai_index_files))

    # --- Upload 4a / 4a-PDF: REMOVED (P0 R2 COST INCIDENT, 2026-09) ---
    # ROOT CAUSE: this block used to run `aws s3 sync reports/ ->
    # s3://sentinel-apex-reports/reports/` (size_only=False, full content/
    # mtime comparison, no bound) plus a second `aws s3 sync` for
    # reports/pdf/ -- on EVERY scheduled pipeline run. Because
    # generate_intel_reports.py's default (non---only-missing) mode
    # regenerates a report for every item in the manifest -- not just new/
    # changed ones -- and every regenerated file embeds a fresh minute-
    # granularity timestamp into its SIGMA/YARA/KQL/SPL blocks, the entire
    # local reports/ tree looked "changed" to `aws s3 sync` on every single
    # run. `aws s3 sync` also unconditionally LISTs the entire destination
    # prefix to build its comparison map regardless of how much actually
    # changed. Against a ~193K-object bucket, this produced the 3,004,147
    # billable R2 Class A operations in one billing cycle documented in
    # docs/P0_R2_COST_CONTAINMENT.md.
    #
    # FIX: whole-corpus sync does not exist in this codebase anymore -- not
    # flag-gated, structurally removed. scripts/r2_report_publisher.py is
    # now the sole normal-operation writer/retirer for both the HTML
    # reports keyspace (sentinel-apex-reports) and reports/pdf/ (sentinel-
    # apex-data). It works from deterministic keys derived from the
    # CURRENT manifest, publishes only genuinely new/changed content (sha256
    # -diffed against its own local state file, never a bucket LIST), is
    # bounded to the rolling REPORT_WINDOW_HOURS (default 24h) window, and
    # enforces a fail-closed operation budget (scripts/r2_cost_guard.py)
    # before issuing a single R2 call. Invoked as its own pipeline stage
    # (see sentinel-blogger.yml) immediately after this script, not from
    # inside main() -- keeping this script's own responsibility limited to
    # the bounded sentinel-apex-data manifest/endpoint uploads below, which
    # were never the cost driver.
    #
    # R2_REPORT_PUBLISHING_ENABLED=false (env var, read by
    # r2_report_publisher.py) remains the emergency kill switch if report
    # publishing itself ever needs to be paused without a code change.

    # --- Upload 4b: AI intelligence data ---
    # First generate AI endpoints from current manifest
    result = subprocess.run(
        [sys.executable, "scripts/generate_ai_endpoints.py"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        log.warning(
            "WARN: AI endpoint generation failed (non-fatal): %s",
            result.stderr.strip()[:200],
        )

    ai_dirs = [REPO_ROOT / "data" / "ai_intelligence", REPO_ROOT / "api" / "ai"]
    for ai_dir in ai_dirs:
        if ai_dir.is_dir():
            for f in ai_dir.glob("*.json"):
                s3_cp(str(f), BUCKET_DATA, f"ai/{f.name}", endpoint)
    log.info("OK: AI intelligence data uploaded")

    # --- Upload 5: Sync metadata ---
    meta = {
        "synced_at":        utc_now(),
        "advisory_count":   item_count,
        "source":           "sentinel-blogger",
        "pipeline_version": PIPELINE_VERSION,
        "run_id":           os.environ.get("GITHUB_RUN_ID", "local"),
        "p0_fix":           "v184.2 -- r2_timeout_fix, awscli_perf, full_content_sync",
    }
    sync_meta_path = "/tmp/sync_meta.json"
    with open(sync_meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    s3_cp(sync_meta_path, BUCKET_DATA, "intel/_sync_meta.json", endpoint)
    log.info("OK: Sync metadata written (%d advisories synced to R2)", item_count)

    write_github_env("R2_UPLOAD_COUNT", str(item_count))
    log.info("R2 upload complete.")


if __name__ == "__main__":
    try:
        if "--p40-only" in sys.argv:
            main_p40_only()
        else:
            main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        log.critical(
            "Unhandled exception in r2_upload.py:\n%s\n%s", e, traceback.format_exc(),
        )
        sys.exit(1)
