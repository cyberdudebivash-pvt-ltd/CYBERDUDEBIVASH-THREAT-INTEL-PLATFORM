#!/usr/bin/env python3
"""
scripts/p0_r2_stix_manifest_diagnostic.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- P0-MP.1A R2 STIX Manifest Forensic Diagnostic

READ-ONLY, BOUNDED, ONE-OFF. Answers exactly one question: what STIX
feed-manifest state currently exists in R2, and does R2 contain any
recoverable pre-collapse generation (docs/P0_FEED_MANIFEST_PERSISTENCE_INCIDENT.md)?

Reuses the existing R2 credential/endpoint model and existing verified
primitives -- does not invent a new credential path:
  - scripts/r2_upload_verifier.py   -- CF_ACCOUNT_ID/ACCESS_KEY/SECRET_KEY,
                                        R2_ENDPOINT, BUCKET_DATA, MANIFEST_KEY,
                                        _s3api_head_object() (reused unchanged)
  - scripts/r2_reports_verifier.py  -- _get_object_bytes() (reused unchanged;
                                        already the exact get-object-to-bytes
                                        primitive this diagnostic needs)
  - scripts/r2_upload.py            -- BUCKET_DATA/BUCKET_REPORTS constants
  - scripts/backup_r2.py            -- BACKUP_MANIFEST_PREFIX default
                                        ("r2-backups/") and its manifest
                                        schema (objects[].key/.sha256), reused
                                        to interpret any historical-catalog
                                        object found, not re-derived

READ-ONLY GUARANTEE: this script issues only HeadObject, GetObject,
ListObjectsV2, and ListObjectVersions calls (all read-only S3 API
operations). It contains NO PutObject, DeleteObject, CopyObject, sync-to-
remote, or any other remote-mutating call. See
tests/test_p0_r2_stix_manifest_diagnostic_read_only.py for the static proof.

Never overwrites data/stix/feed_manifest.json. Never logs secret values.

Prints one JSON object to stdout between the markers
===P0_R2_DIAGNOSTIC_JSON_START=== / ===P0_R2_DIAGNOSTIC_JSON_END=== so a
CI log capture is sufficient to retrieve the full evidence -- artifact
upload (data/quality/p0_r2_stix_manifest_diagnostic.json) is a secondary,
best-effort channel, not the only one.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import r2_upload_verifier as _verifier          # noqa: E402 -- reuse, not reimplement
import r2_reports_verifier as _reports_verifier  # noqa: E402 -- reuse _get_object_bytes
import r2_upload as _r2_upload                   # noqa: E402 -- BUCKET_DATA/BUCKET_REPORTS

OUTPUT_PATH = REPO_ROOT / "data" / "quality" / "p0_r2_stix_manifest_diagnostic.json"

# Section 5: narrow, code-evidenced search prefixes.
# "r2-backups/" and "kv-snapshots/" are the ACTUAL prefixes scripts/backup_r2.py
# and scripts/backup_kv_to_r2.py write to (confirmed by reading those scripts --
# not a guess). The rest are the mission's own candidate list, kept because no
# code path proves they are unused, only that no known writer targets them.
SEARCH_PREFIXES = [
    "intel/",
    "r2-backups/",
    "kv-snapshots/",
    "backup/",
    "backups/",
    "archive/",
    "archives/",
    "snapshots/",
    "manifest/",
    "manifests/",
]

MAX_KEYS_PER_PREFIX = 1000   # bounded listing, not an unbounded bucket dump
MAX_CANDIDATE_DOWNLOAD_BYTES = 50 * 1024 * 1024  # skip content analysis above 50MB per object
# Aggregate budget across ALL candidates combined: the per-object cap above
# bounds one download, but with 10 prefixes x up to 1000 keys each, an
# unbounded candidate LIST could still mean thousands of downloads. Bound
# both the candidate count and the cumulative bytes actually fetched, and
# record truncation explicitly rather than letting the job time out mid-scan.
MAX_CANDIDATES_DOWNLOADED = 25
MAX_TOTAL_CANDIDATE_DOWNLOAD_BYTES = 200 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Full head-object metadata: extends _verifier._s3api_head_object() (its
# full=True mode, added alongside this diagnostic) instead of duplicating
# its credential/retry/subprocess logic here. That function's default
# (full=False) return value and every existing caller are unchanged.
# ---------------------------------------------------------------------------
def _head_object_full(bucket: str, key: str) -> dict | None:
    head = _verifier._s3api_head_object(bucket, key, full=True)
    if head is None:
        # awscli path unavailable/exhausted -- fall back to the boto3 helper
        # for at least an existence/size/etag signal (no full metadata in
        # this path, same tradeoff verify_r2_object() already accepts).
        head = _verifier._boto3_head_object(bucket, key)
        if head is None:
            return None
    if head.get("status") == 404:
        return {"found": False}
    return {"found": True, **(head.get("raw") or {}), "_content_length": head.get("content_length"), "_etag": head.get("etag")}


def _list_objects_v2(bucket: str, prefix: str, max_keys: int = MAX_KEYS_PER_PREFIX) -> list[dict] | None:
    """Read-only bounded listing. Returns None on total failure (distinct from
    an empty-but-successful listing, per the mission's 'never fail-open /
    never silently absorb a failure into a negative result' posture used
    throughout this codebase's other R2 scripts)."""
    cmd = [
        "aws", "s3api", "list-objects-v2",
        "--bucket", bucket, "--prefix", prefix,
        "--max-items", str(max_keys),
        "--endpoint-url", _verifier.R2_ENDPOINT,
        "--output", "json",
    ]
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = _verifier.ACCESS_KEY
    env["AWS_SECRET_ACCESS_KEY"] = _verifier.SECRET_KEY
    env["AWS_DEFAULT_REGION"] = "auto"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=_verifier.REQUEST_TIMEOUT * 2, env=env,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return [
            {
                "key": o.get("Key"),
                "size": o.get("Size"),
                "last_modified": o.get("LastModified"),
                "etag": (o.get("ETag") or "").strip('"'),
            }
            for o in data.get("Contents", [])
        ]
    except Exception:
        return None


def _list_object_versions(bucket: str, key: str) -> dict:
    """Section 8: prove or disprove bucket versioning for the canonical key,
    rather than assuming either way. A single-key-scoped, bounded, read-only
    call."""
    cmd = [
        "aws", "s3api", "list-object-versions",
        "--bucket", bucket, "--prefix", key,
        "--endpoint-url", _verifier.R2_ENDPOINT,
        "--output", "json",
    ]
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = _verifier.ACCESS_KEY
    env["AWS_SECRET_ACCESS_KEY"] = _verifier.SECRET_KEY
    env["AWS_DEFAULT_REGION"] = "auto"
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=_verifier.REQUEST_TIMEOUT, env=env,
        )
        if result.returncode != 0:
            return {
                "checked": True, "supported": False,
                "note": "list-object-versions call failed -- bucket may not have "
                        "versioning-capable API surface enabled, or credentials "
                        "lack permission. Not proof either way.",
                "stderr_excerpt": result.stderr.strip()[:300],
            }
        data = json.loads(result.stdout)
        # --prefix matches every key that STARTS WITH `key` (e.g. it would
        # also match "intel/feed_manifest.json.backup"), not only the exact
        # canonical key -- filter to an exact match before counting, or
        # single_generation_only could describe a sibling object instead of
        # (or in addition to) the canonical one.
        versions = [v for v in data.get("Versions", []) if v.get("Key") == key]
        delete_markers = [d for d in data.get("DeleteMarkers", []) if d.get("Key") == key]
        return {
            "checked": True, "supported": True,
            "version_count": len(versions),
            "delete_marker_count": len(delete_markers),
            "versions": [
                {"version_id": v.get("VersionId"), "is_latest": v.get("IsLatest"),
                 "last_modified": v.get("LastModified"), "size": v.get("Size"),
                 "etag": (v.get("ETag") or "").strip('"')}
                for v in versions
            ],
        }
    except Exception as e:
        return {"checked": True, "supported": False, "note": f"exception: {e}"}


def _analyze_manifest_bytes(raw: bytes) -> dict:
    """Same field-name conventions scripts/r2_reports_verifier.py already
    uses for this exact schema (entry.get('id') or entry.get('stix_id');
    entry.get('processed_at') or entry.get('timestamp')) -- Single Source of
    Truth for what a STIX manifest record's identity/timestamp fields are
    named, not a re-derived guess."""
    out: dict = {"size": len(raw), "sha256": _sha256(raw)}
    try:
        data = json.loads(raw)
    except Exception as e:
        out["json_valid"] = False
        out["parse_error"] = str(e)
        return out
    out["json_valid"] = True
    items = data if isinstance(data, list) else None
    if items is None and isinstance(data, dict):
        for k in ("advisories", "items", "data", "reports"):
            if isinstance(data.get(k), list):
                items = data[k]
                break
    if items is None:
        out["schema"] = "dict-envelope" if isinstance(data, dict) else type(data).__name__
        out["looks_like_stix_manifest"] = False
        return out
    out["schema"] = "flat-list" if isinstance(data, list) else "dict-envelope"
    ids = [it.get("id") or it.get("stix_id") for it in items if isinstance(it, dict)]
    ids_present = [i for i in ids if i]
    ts = []
    for it in items:
        if isinstance(it, dict):
            t = it.get("processed_at") or it.get("timestamp") or it.get("published") or it.get("published_at")
            if t:
                ts.append(str(t))
    ts_sorted = sorted(ts)
    out.update({
        "looks_like_stix_manifest": True,
        "record_count": len(items),
        "unique_id_count": len(set(ids_present)),
        "missing_id_count": len(items) - len(ids_present),
        "duplicate_id_count": len(ids_present) - len(set(ids_present)),
        "newest_record_ts": ts_sorted[-1] if ts_sorted else None,
        "oldest_record_ts": ts_sorted[0] if ts_sorted else None,
    })
    return out


def main() -> int:
    report: dict = {
        "diagnostic": "P0-MP.1A",
        "generated_at": _utc_now(),
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "release_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "read_only": True,
        "bucket_key_mapping": {
            "bucket": _r2_upload.BUCKET_DATA,
            "canonical_key": _verifier.MANIFEST_KEY,
            "producer": "scripts/r2_upload.py main() 'Upload 1: Primary feed manifest (OVERWRITE)' "
                        "-- plain 'aws s3 cp' overwrite, once per pipeline run at STAGE 3.5, "
                        "reading data/stix/feed_manifest.json at that point in the run.",
            "worker_consumer": "workers/intel-gateway/src/index.js findItemBySlug() -- "
                                "FEED_MANIFEST_FALLBACK_KEY, the 5th/LAST-RESORT source in a "
                                "5-source waterfall (latest_pro.json, latest.json, top10.json, "
                                "apex.json, then this key), used for single-item slug resolution "
                                "in on-the-fly report synthesis and handlePublicationStatus(). "
                                "NOTE: r2_upload.py's own inline comment claims a 'handleFeedJson' "
                                "consumer -- no such function exists anywhere in workers/ as of "
                                "this diagnostic. That comment is stale; this entry reflects the "
                                "actual current code, independently verified per Section 3.",
        },
        "credentials_present": bool(_verifier.CF_ACCOUNT_ID and _verifier.ACCESS_KEY and _verifier.SECRET_KEY),
    }

    if not report["credentials_present"]:
        report["classification"] = "R2_ACCESS_FAILED"
        report["classification_reason"] = "CF_ACCOUNT_ID/AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY not present in this job's environment."
        print("===P0_R2_DIAGNOSTIC_JSON_START===")
        print(json.dumps(report, indent=2, default=str))
        print("===P0_R2_DIAGNOSTIC_JSON_END===")
        return 0

    # --- Section 4: current canonical object ------------------------------
    canonical_head = _head_object_full(_r2_upload.BUCKET_DATA, _verifier.MANIFEST_KEY)
    canonical: dict = {"head": canonical_head}
    if canonical_head and canonical_head.get("found"):
        raw = _reports_verifier._get_object_bytes(_r2_upload.BUCKET_DATA, _verifier.MANIFEST_KEY)
        if raw is not None:
            canonical["get_object_ok"] = True
            canonical["analysis"] = _analyze_manifest_bytes(raw)
        else:
            canonical["get_object_ok"] = False
    report["canonical_object"] = canonical

    # --- Section 8: version history on the canonical key -------------------
    report["canonical_key_version_history"] = _list_object_versions(_r2_upload.BUCKET_DATA, _verifier.MANIFEST_KEY)

    # --- Section 5: narrow prefix search ------------------------------------
    prefix_results: dict = {}
    for prefix in SEARCH_PREFIXES:
        listing = _list_objects_v2(_r2_upload.BUCKET_DATA, prefix)
        prefix_results[prefix] = {"listing_ok": listing is not None, "objects": listing or []}
    report["prefix_search"] = prefix_results

    # --- Candidate analysis: any object whose key contains "manifest" or
    # "feed", other than the canonical key itself, in ANY listed prefix.
    candidates = []
    seen_keys = {_verifier.MANIFEST_KEY}
    for prefix, res in prefix_results.items():
        for obj in res["objects"]:
            key = obj.get("key") or ""
            if key in seen_keys:
                continue
            lk = key.lower()
            if "manifest" in lk or "feed" in lk:
                seen_keys.add(key)
                candidates.append(obj)

    candidate_analysis = []
    candidates_downloaded = 0
    total_downloaded_bytes = 0
    candidate_scan_truncated = False
    for obj in candidates:
        key = obj["key"]
        size = obj.get("size") or 0
        entry: dict = {"key": key, "listing_metadata": obj}
        if size > MAX_CANDIDATE_DOWNLOAD_BYTES:
            entry["skipped_download"] = f"size {size} exceeds {MAX_CANDIDATE_DOWNLOAD_BYTES} byte per-object diagnostic cap"
            candidate_analysis.append(entry)
            continue
        if (candidates_downloaded >= MAX_CANDIDATES_DOWNLOADED
                or total_downloaded_bytes + size > MAX_TOTAL_CANDIDATE_DOWNLOAD_BYTES):
            entry["skipped_download"] = (
                f"aggregate diagnostic budget exhausted "
                f"({candidates_downloaded}/{MAX_CANDIDATES_DOWNLOADED} candidates, "
                f"{total_downloaded_bytes}/{MAX_TOTAL_CANDIDATE_DOWNLOAD_BYTES} bytes) -- "
                "not downloaded this run"
            )
            candidate_scan_truncated = True
            candidate_analysis.append(entry)
            continue
        candidates_downloaded += 1
        total_downloaded_bytes += size
        raw = _reports_verifier._get_object_bytes(_r2_upload.BUCKET_DATA, key)
        if raw is None:
            entry["get_object_ok"] = False
        else:
            entry["get_object_ok"] = True
            entry["analysis"] = _analyze_manifest_bytes(raw)
            # Special case: a scripts/backup_r2.py-produced catalog manifest
            # (schema: {"bucket":..., "objects":[{"key":...,"sha256":...}]})
            # -- if this IS one, pull out its nested record for the canonical
            # STIX manifest key specifically, since that is indirect historical
            # hash evidence even though the catalog itself holds no content.
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and isinstance(parsed.get("objects"), list):
                    nested = [
                        o for o in parsed["objects"]
                        if isinstance(o, dict) and o.get("key") == _verifier.MANIFEST_KEY
                    ]
                    if nested:
                        entry["nested_canonical_key_record"] = nested[0]
                    entry["is_backup_r2_catalog"] = True
            except Exception:
                pass
        candidate_analysis.append(entry)
    report["historical_candidates"] = candidate_analysis
    report["candidate_scan"] = {
        "candidates_downloaded": candidates_downloaded,
        "total_downloaded_bytes": total_downloaded_bytes,
        "truncated": candidate_scan_truncated,
        "max_candidates_downloaded": MAX_CANDIDATES_DOWNLOADED,
        "max_total_candidate_download_bytes": MAX_TOTAL_CANDIDATE_DOWNLOAD_BYTES,
    }

    # --- Section 7/8 classification ----------------------------------------
    head_found = bool(canonical_head and canonical_head.get("found"))
    version_history = report["canonical_key_version_history"]
    single_generation_only = None
    if version_history.get("supported"):
        single_generation_only = version_history.get("version_count", 0) <= 1

    if not head_found:
        classification = "R2_OBJECT_MISSING"
    elif candidate_analysis:
        # A key-name match ("manifest"/"feed" in the key) is not proof of
        # recoverable content -- it can be the current copy itself, malformed
        # JSON, or a backup_r2.py hash catalog with no manifest body at all.
        # This script never claims R2_PARTIAL_RECOVERY_AVAILABLE (one of the
        # mission's 6 final-classification values) on name-match alone; that
        # requires content-level proof (a candidate whose analysis shows
        # valid STIX-shaped records predating the current generation), which
        # only the calling document's evidence matrix can establish.
        classification = "R2_RECOVERY_CANDIDATES_FOUND"
    else:
        classification = "R2_CURRENT_ONLY_COLLAPSED"  # provisional; the calling doc compares canonical object stats against the git pre-collapse baseline to confirm

    report["classification"] = classification
    report["single_generation_only"] = single_generation_only
    report["classification_note"] = (
        "This script classifies structurally (object exists? other candidates "
        "found by key-name match?), never claiming recovery is proven just "
        "because a plausibly-named object exists. 'R2_RECOVERY_CANDIDATES_FOUND' "
        "is a preliminary signal, not one of the mission's 6 final classification "
        "values (R2_PRE_COLLAPSE_RECOVERY_AVAILABLE / R2_CURRENT_ONLY_COLLAPSED / "
        "R2_PARTIAL_RECOVERY_AVAILABLE / R2_OBJECT_MISSING / R2_ACCESS_FAILED / "
        "R2_STATE_INDETERMINATE) -- the caller "
        "(docs/P0_R2_STIX_MANIFEST_RECOVERY_DIAGNOSTIC.md) makes that final call "
        "using this report's canonical_object.analysis and each candidate's "
        "analysis (sha256/record_count/newest_record_ts/looks_like_stix_manifest) "
        "compared against the git pre-collapse baseline."
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    tmp.replace(OUTPUT_PATH)

    print("===P0_R2_DIAGNOSTIC_JSON_START===")
    print(json.dumps(report, indent=2, default=str))
    print("===P0_R2_DIAGNOSTIC_JSON_END===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        print(f"::error::p0_r2_stix_manifest_diagnostic.py unhandled exception: {e}\n{traceback.format_exc()}")
        sys.exit(1)
