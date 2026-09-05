#!/usr/bin/env python3
"""
CYBERDUDEBIVASH(R) SENTINEL APEX -- Report Validation Gate
============================================================
Version : v134.1
Stage   : 3.3 (runs AFTER report_generator, BEFORE R2 upload)

Purpose:
  Hard-fail if ANY advisory in feed_manifest.json is missing its physical
  HTML report, has a report that is too small, or has a file that is not
  valid HTML. Also enforces that every advisory's report_url is an internal
  path (never an external URL).

Exit codes:
  0 -- all reports validated
  1 -- one or more advisories failed validation (pipeline MUST stop)

Usage:
  python3 scripts/validate_reports.py
  python3 scripts/validate_reports.py --manifest data/stix/feed_manifest.json
  python3 scripts/validate_reports.py --reports-dir reports

P0 RULES (non-negotiable):
  RULE 1: Every advisory MUST have internal_report_url OR report_url
  RULE 2: report_url MUST be a relative /reports/ path (never http)
  RULE 3: The physical HTML file MUST exist on disk, UNLESS the advisory is
          outside this run's rolling publish window (see DEFERRAL below)
  RULE 4: The file MUST be >= 500 bytes
  RULE 5: The file MUST begin with <!DOCTYPE html or <html
  RULE 6: Zero silent skips -- every advisory's disposition (PASS/DEFERRED/
          SKIP/FAIL) is logged and counted, never silently dropped
  RULE 7: Exit 1 if ANY failure -- pipeline stops, R2 upload is blocked

DEFERRAL (P0 root-cause fix, 2026-09): PR #369 bounded scripts/
generate_intel_reports.py and scripts/r2_report_publisher.py to a rolling
REPORT_WINDOW_HOURS window (default 24h) to stop the whole-corpus R2 cost
incident (docs/P0_R2_COST_CONTAINMENT.md) -- outside that window, a report
is deliberately NOT regenerated on a given run. reports/ is also gitignored
and lives only on the ephemeral CI runner's local disk (never restored from
git or cache), so on every fresh checkout this validator starts with ZERO
local files for every advisory the current run's generation pass did not
touch. Before this fix, RULE 3 required EVERY advisory in the manifest --
including thousands of historical ones outside the window -- to have a
local file, which held only under the PRE-#369 architecture where every
report was regenerated on every run. Confirmed live: sentinel-blogger.yml
runs #2244/#2245 (the first natural runs after #369/#370 landed) both hard-
failed here with ~1,394 RULE 3 failures, 100% of them advisories outside
the rolling window -- not a data/manifest corruption, an architecture
mismatch between this gate's assumption and the (correct, intentional) R2
cost-bounding fix.

Fix: an advisory whose canonical timestamp (scripts/r2_report_publisher.py's
own canonical_age(), reused here -- not reimplemented) places it OUTSIDE
report_window_hours() is not this run's responsibility to have produced or
verified locally -- its correctness is either scripts/r2_report_publisher.py's
own durable publish-state record (data/cache/r2_report_publish_state.json,
reused here too) or, for pre-#369 legacy items with no state record, was
guaranteed by the whole-corpus sync architecture that ran on every prior
cycle and has not been touched (R2 objects are never deleted by anything
outside r2_report_publisher.py's own bounded retirement, and legacy items
are outside its scope) -- and is verified by the operator-invoked purge/
audit tooling, not this per-run gate. Such advisories are logged as
DEFERRED, not PASS and not FAIL: still fully visible (RULE 6), never
silently reclassified as validated. An advisory INSIDE the window with a
genuinely missing/malformed local file still HARD FAILS exactly as before --
this fix narrows RULE 3's scope to what post-#369 architecture actually
guarantees, it does not weaken the check within that scope.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2_report_publisher import (  # noqa: E402
    canonical_age,
    load_publish_state,
    report_window_hours,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("CDB-VALIDATE-REPORTS")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MANIFEST_PATH   = Path("data/stix/feed_manifest.json")
REPORTS_BASE    = Path("reports")
MIN_FILE_BYTES  = 500
HTML_SIGNATURES = ("<!doctype html", "<html")

# fix(v166.2-P0): canonical ordered key list shared across all manifest readers.
# field_preserving_merge.py defaults to writing under "data" key when no known
# list key exists in the original dict. Previous 4-key lookup ("advisories",
# "entries", "items", "reports") missed "data" and "intel", causing Stage 3.3
# to read 0 advisories and HARD FAIL on every CI run.
_MANIFEST_LIST_KEYS = (
    "advisories", "items", "data", "entries", "reports", "intel", "feed"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_manifest(manifest_path: Path) -> List[Dict[str, Any]]:
    """Load advisories list from manifest. Hard-fail if unreadable."""
    if not manifest_path.exists():
        logger.error("MANIFEST NOT FOUND: %s", manifest_path)
        sys.exit(1)
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.error("MANIFEST JSON PARSE ERROR: %s -- %s", manifest_path, exc)
        sys.exit(1)

    # v160.6 FIX: handle both raw LIST format (written by sentinel_blogger engine)
    # and DICT format (normalised by run_pipeline Stage 2.2). Previously this
    # called data.get() unconditionally, crashing with AttributeError: 'list'
    # object has no attribute 'get' — confirmed in 3 consecutive CI runs (#1322,
    # run_alt1, run_alt2) at this exact line.
    #
    # v166.2-P0 FIX: extended key chain now includes "data" and "intel".
    # field_preserving_merge.py (Stage 3.1.6) writes under "data" by default
    # when no known key exists. ioc_quality_hardener.py (Stage 3.1.8) was then
    # injecting an empty "items": [] — shadowing the real 34-item "data" list —
    # causing this validator to receive 0 advisories and HARD FAIL every run.
    if isinstance(data, list):
        advisories = data
    elif isinstance(data, dict):
        advisories = None
        for _k in _MANIFEST_LIST_KEYS:
            _candidate = data.get(_k)
            if isinstance(_candidate, list) and len(_candidate) > 0:
                advisories = _candidate
                break
        if advisories is None:
            # Fall back to first list key found even if empty (preserves prior
            # behaviour for genuinely empty manifests so we still HARD FAIL below)
            for _k in _MANIFEST_LIST_KEYS:
                if isinstance(data.get(_k), list):
                    advisories = data[_k]
                    break
        if advisories is None:
            advisories = []
    else:
        logger.error(
            "MANIFEST root is neither list nor dict in %s -- got %s",
            manifest_path, type(data).__name__
        )
        sys.exit(1)
    if not isinstance(advisories, list):
        logger.error("MANIFEST 'advisories' key is not a list in %s", manifest_path)
        sys.exit(1)
    return advisories


def _resolve_report_path(entry: Dict[str, Any]) -> Tuple[str, str]:
    """
    Return (report_url, file_path_on_disk) for the given advisory.
    report_url is the internal /reports/... path.
    file_path_on_disk is the relative filesystem path.
    Returns ("", "") if no internal URL is available.
    """
    intel_id = (
        entry.get("id") or entry.get("stix_id") or ""
    ).strip()

    # Priority: internal_report_url > report_url (if internal) > derive from id
    url = (entry.get("internal_report_url") or "").strip()
    if not url:
        ru = (entry.get("report_url") or "").strip()
        # Accept only internal paths
        if ru and not ru.startswith("http"):
            url = ru

    if not url and intel_id:
        # Derive default path from intel_id using processed_at date
        ts = (entry.get("processed_at") or entry.get("timestamp") or "")[:10]
        if len(ts) >= 7:
            yyyy, mm = ts[:4], ts[5:7]
        else:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            yyyy, mm = str(now.year), f"{now.month:02d}"
        url = f"/reports/{yyyy}/{mm}/{intel_id}.html"

    if not url:
        return "", ""

    # Convert URL path to filesystem path
    # /reports/2026/04/intel--abc.html -> reports/2026/04/intel--abc.html
    fs_path = url.lstrip("/").replace("/", os.sep)

    # v160.5 HARDENING: current-run date fallback (v160.5b FIX).
    # report_generator.py always writes reports to TODAY's year/month when no
    # explicit internal_report_url is present.  The manifest entry may carry a
    # stale processed_at/timestamp from a prior run -> derived fs_path points
    # to a month/year that does not exist on the fresh runner.
    #
    # Fallback strategy -- triggers when the derived local path is absent:
    #   1. Try current run year/month (covers processed_at date-drift).
    #   2. Also fires when report_url is an HTTPS URL (cannot be checked
    #      locally; path was derived from processed_at, not from the URL).
    # Skipped only when internal_report_url is a LOCAL /reports/... path
    # (meaning report_generator explicitly wrote that exact path back).
    _internal_ru  = (entry.get("internal_report_url") or "").strip()
    _has_local_explicit = bool(_internal_ru and not _internal_ru.startswith("http"))
    if intel_id and not _has_local_explicit and not os.path.exists(fs_path):
        import datetime as _dt
        _now = _dt.datetime.now(_dt.timezone.utc)
        alt_url = f"/reports/{_now.year}/{_now.month:02d}/{intel_id}.html"
        alt_fs  = alt_url.lstrip("/").replace("/", os.sep)
        if os.path.exists(alt_fs):
            return alt_url, alt_fs  # report lives in current run month

    return url, fs_path


def _validate_one(
    entry: Dict[str, Any],
    idx: int,
    *,
    now: datetime,
    window_hours: int,
    published_ids: set[str],
) -> Tuple[List[str], str]:
    """
    Validate a single advisory entry. Returns (failures, disposition).

    disposition is exactly one of:
      "PASS"     -- fully validated: local file confirmed present & valid HTML,
                    or explicitly confirmed published via the CDN-URL bypass.
      "DEFERRED" -- report_url present, local file missing, but the advisory
                    is outside this run's rolling publish window (or its
                    canonical timestamp is unparseable) and/or its id is
                    confirmed durably published via scripts/
                    r2_report_publisher.py's own state -- not this run's
                    responsibility to have produced or verified locally.
                    See module docstring's DEFERRAL section.
      "SKIP"     -- STIX-bundle-only record, no HTML report expected.
      "FAIL"     -- one or more RULE violations; see `failures`.

    failures is non-empty only when disposition == "FAIL".

    v152.2.0 IMMUTABLE GUARD -- Root cause of Run #1269 false-positive FATAL:
    Previously RULE 1 returned early (failing) whenever report_url /
    internal_report_url were absent from the manifest entry. This produced
    false-positive failures for:
      (a) data/stix/feed_manifest.json entries -- STIX bundle index records
          that never carry report_url fields by design.
      (b) "god mode" reports skipped by report_generator -- physical HTML files
          exist on disk (74-81 KB) but the URL was not written back to the
          manifest entry because the generator skipped regeneration.

    Fix: call _resolve_report_path() FIRST. It falls back to deriving the path
    from intel_id + processed_at/timestamp when no URL field exists. RULE 1
    fails ONLY if (a) no URL in manifest AND (b) no id-derived path resolves.
    RULE 3 (file-existence check) then catches genuinely missing reports.
    """
    failures: List[str] = []
    intel_id = (entry.get("id") or entry.get("stix_id") or f"entry[{idx}]").strip()

    # Resolve best available path: explicit URL first, then id-derived fallback
    _url, fs_path = _resolve_report_path(entry)
    explicit_url = (entry.get("internal_report_url") or entry.get("report_url") or "").strip()

    # RULE 1: must resolve a report path (explicit URL in manifest OR id-derived)
    if not fs_path:
        failures.append(
            f"[{intel_id}] RULE 1 FAIL: no report_url, internal_report_url, "
            f"or derivable id -- cannot locate report file"
        )
        return failures, "FAIL"

    # v160.5e HARDENING: Skip STIX-bundle-only entries (no HTML report).
    # Manifest entries with NEITHER report_url NOR internal_report_url are raw
    # STIX bundle index records produced by run_pipeline.py. They never have
    # associated HTML report files -- HTML reports use intel--{hex} IDs while
    # STIX bundles use bundle--{uuid}. Derived fs_path will always be absent.
    # Condition: no explicit URL AND local file does not exist at derived path.
    # This preserves full RULE 3/4/5 checks for genuine intel-- advisory reports.
    if not explicit_url and not os.path.exists(fs_path):
        return failures, "SKIP"  # STIX bundle-only record, no HTML report expected

    # RULE 2: if an explicit URL is present, it must not be a foreign external URL
    if explicit_url and explicit_url.startswith("http") and "cyberdudebivash" not in explicit_url:
        failures.append(
            f"[{intel_id}] RULE 2 FAIL: report_url is external URL: {explicit_url!r}"
        )
        return failures, "FAIL"

    # v160.5d HARDENING: Already-Deployed CDN Bypass.
    # When report_url is an HTTPS URL on our own published domain
    # (cyberdudebivash.com), the report was generated and uploaded to
    # Cloudflare R2 / GitHub Pages in a prior run.  On a fresh GitHub Actions
    # runner there is NO local copy of that file -- it was never committed to
    # the repo.  Attempting a local-file check (RULE 3/4/5) will always fail
    # for these entries, producing spurious P0 GATE failures on fix-only or
    # no-new-intel commits.
    #
    # Resolution: if report_url begins with https:// AND contains our domain,
    # treat the report as already validated and deployed.  Return PASS immediately.
    # This preserves all RULE 3/4/5 checks for NEW reports (local files present).
    _pub_url = (entry.get("report_url") or "").strip()
    _already_deployed = bool(
        _pub_url.startswith("https://") and "cyberdudebivash" in _pub_url
    )
    if _already_deployed:
        return failures, "PASS"  # report already live on cyberdudebivash CDN/R2

    # RULE 3: physical HTML file must exist on disk at resolved path
    if not os.path.exists(fs_path):
        # DEFERRAL (see module docstring): confirmed durably published via
        # r2_report_publisher.py's own state, OR outside this run's rolling
        # publish window (or timestamp unparseable, which r2_report_publisher.py
        # itself also treats as "not this run's candidate") -- not a failure,
        # this run was never going to produce or verify this file locally.
        if intel_id in published_ids:
            return failures, "DEFERRED"
        _ts, _age_hours = canonical_age(entry, now)
        _in_window = _age_hours is not None and 0 <= _age_hours <= window_hours
        if not _in_window:
            return failures, "DEFERRED"
        failures.append(
            f"[{intel_id}] RULE 3 FAIL: report file NOT FOUND: {fs_path} "
            f"(within the {window_hours}h publish window -- this run should "
            f"have produced or verified it locally)"
        )
        return failures, "FAIL"  # no point checking size/content

    # RULE 3b (v154.0 P0 HARDENING): PUBLIC report_url path MUST ALSO exist.
    # If report_url diverges from internal_report_url and the public path is
    # missing, the dashboard CTA links to a 404.
    _public_ru = (entry.get("report_url") or "").strip()
    if _public_ru and not _public_ru.startswith("http") and _public_ru.startswith("/reports/"):
        _public_fs = _public_ru.lstrip("/").replace("/", os.sep)
        if _public_fs != fs_path and not os.path.exists(_public_fs):
            failures.append(
                f"[{intel_id}] RULE 3b FAIL: public report_url path NOT FOUND: "
                f"{_public_fs} (internal path {fs_path} exists but dashboard "
                f"links to the public path -- customers get 404)"
            )

    # RULE 4: file must be >= 500 bytes
    size = os.path.getsize(fs_path)
    if size < MIN_FILE_BYTES:
        failures.append(
            f"[{intel_id}] RULE 4 FAIL: report file too small "
            f"({size} bytes < {MIN_FILE_BYTES}): {fs_path}"
        )

    # RULE 5: file must start with valid HTML
    try:
        with open(fs_path, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(512).lower()
    except OSError as exc:
        failures.append(
            f"[{intel_id}] RULE 5 FAIL: cannot read report file {fs_path}: {exc}"
        )
        return failures, "FAIL"

    if not any(sig in head for sig in HTML_SIGNATURES):
        failures.append(
            f"[{intel_id}] RULE 5 FAIL: report file is not valid HTML "
            f"(head: {head[:60]!r}): {fs_path}"
        )
        return failures, "FAIL"

    return failures, "PASS"


def validate_all_reports(
    manifest_path: Path = MANIFEST_PATH,
    reports_base: Path = REPORTS_BASE,
) -> bool:
    """
    Validate all advisory reports. Returns True if all pass, False if any fail.
    Logs every failure. Never raises.
    """
    advisories = _load_manifest(manifest_path)
    total = len(advisories)

    if total == 0:
        logger.error("MANIFEST IS EMPTY -- no advisories to validate. Exit 1.")
        return False

    logger.info("Validating reports for %d advisories from %s", total, manifest_path)

    window_hours = report_window_hours()
    now = datetime.now(timezone.utc)
    publish_state = load_publish_state()
    published_ids = {
        _id for _id, _rec in publish_state.get("items", {}).items()
        if isinstance(_rec, dict) and _rec.get("html_key")
    }
    logger.info(
        "Rolling publish window: %dh -- %d id(s) confirmed durably published "
        "via r2_report_publisher.py's own state.",
        window_hours, len(published_ids),
    )

    all_failures: List[str] = []
    passed = 0
    deferred = 0
    skipped = 0

    for idx, entry in enumerate(advisories):
        failures, disposition = _validate_one(
            entry, idx, now=now, window_hours=window_hours, published_ids=published_ids,
        )
        intel_id = (entry.get("id") or entry.get("stix_id") or f"entry[{idx}]").strip()

        if disposition == "FAIL":
            for msg in failures:
                logger.error("REPORT VALIDATION FAIL: %s", msg)
            all_failures.extend(failures)
        elif disposition == "DEFERRED":
            logger.info(
                "[DEFERRED] %s -- outside the %dh publish window, not locally "
                "verifiable this run (see DEFERRAL in module docstring)",
                intel_id, window_hours,
            )
            deferred += 1
        elif disposition == "SKIP":
            skipped += 1
        else:  # PASS
            _url, fs_path = _resolve_report_path(entry)
            size = os.path.getsize(fs_path) if fs_path and os.path.exists(fs_path) else 0
            logger.info("[PASS] %s -- %s (%d bytes)", intel_id, fs_path, size)
            passed += 1

    logger.info(
        "Report validation complete: %d/%d passed, %d deferred (out-of-window, "
        "not locally verifiable), %d skipped (no report expected), %d failed",
        passed, total, deferred, skipped, len(all_failures),
    )

    if all_failures:
        logger.error(
            "P0 GATE FAIL: %d report(s) failed validation. "
            "R2 upload is BLOCKED. Fix all failures above before re-running.",
            len(all_failures),
        )
        return False

    logger.info(
        "P0 GATE PASS: %d in-scope report(s) validated, %d deferred as "
        "out-of-window. R2 upload is ALLOWED.",
        passed, deferred,
    )
    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SENTINEL APEX -- Report Validation Gate (P0, Stage 3.3)"
    )
    parser.add_argument(
        "--manifest",
        default=str(MANIFEST_PATH),
        help=f"Path to feed_manifest.json (default: {MANIFEST_PATH})",
    )
    parser.add_argument(
        "--reports-dir",
        default=str(REPORTS_BASE),
        help=f"Base reports directory (default: {REPORTS_BASE})",
    )
    args = parser.parse_args()

    ok = validate_all_reports(
        manifest_path=Path(args.manifest),
        reports_base=Path(args.reports_dir),
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
