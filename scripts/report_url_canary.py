#!/usr/bin/env python3
"""
scripts/report_url_canary.py
CYBERDUDEBIVASH(R) SENTINEL APEX v174.1 -- Report URL Canary (Existence + Body)
====================================================================
Two-phase, fail-closed verification that customer-facing report_url values
actually resolve to a REAL report -- not a soft-404 stub, and not a stale
historical sample.

  --local  (PRE/POST-DEPLOY, fail-closed, no network):
           For EVERY report_url in the CURRENT run's feed, verify the on-disk
           artifact exists (in reports/ OR dist/reports/), is readable, and
           carries a valid report body (size + <html> + no soft-404 marker).
           Exit 1 on ANY missing/invalid. Blocks publish-before-persist.

           Pipeline lifecycle on CI:
             Stage 5.4.6  : reports/ -> dist/reports/  (copy)
             Stage 5.4.6b : rm -rf reports/             (disk governance)
             Stage 5.8.1b : THIS gate                   (dist/reports/ present)

           The gate checks BOTH locations so it works correctly at any stage
           position -- before OR after Stage 5.4.6b cleanup.

  --live / (default, POST-DEPLOY HTTP probe):
           GET each CURRENT-run report URL from the live site and validate the
           BODY (not just the status code), so a 200-with-"report_not_found"
           body FAILS. Retries for CDN propagation. 401/403 = auth-gated = PASS.

ROOT CAUSES FIXED (v174.0):
  1. v156 loader required `not ru.startswith("http")` -> silently DROPPED every
     fully-qualified https://intel.cyberdudebivash.com/reports/... URL, so the
     canary probed NOTHING from the current run (structurally blind).
  2. HEAD + status-only -> a soft-404 (HTTP 200 with report_not_found body)
     passed. Now GET + body validation.
  3. Sampled historical manifest first -> never the new current-run reports.
     Now the CURRENT feed is the authoritative source.
  4. No pre-deploy existence gate -> URLs were published before artifacts were
     persisted. --local now fails closed before publish.

ROOT CAUSE FIXED (v174.1):
  5. --local checked ONLY reports/ directory. Stage 5.4.6b deletes reports/
     for disk governance BEFORE Stage 5.8.1b runs this gate. All 11 artifacts
     appeared missing even though they were present in dist/reports/.
     Fix: _resolve_artifact() checks reports/ first, then dist/reports/.

ROOT CAUSE FIXED (P0 2026-09-05):
  6. Same architectural mismatch already fixed in scripts/validate_reports.py
     (STAGE 3.3) and scripts/report_existence_validator.py (STAGE 5.4.1) --
     confirmed live (run #2250) hard-failing THIS gate instead, one stage
     later, against the exact same api/feed.json: PR #369 bounded report
     (re)generation to a rolling REPORT_WINDOW_HOURS window, and reports/ is
     gitignored (never persisted across CI runs), so a fresh runner has zero
     local file for a CURRENT-feed report_url whose id was rendered/published
     in an EARLIER run and is still legitimately current (in-window, or
     already durably published to R2 per r2_report_publisher.py's own
     state) but wasn't re-rendered THIS run. --local now applies the exact
     same deferral rule report_existence_validator.py already established
     (reused via r2_report_publisher.py's own canonical_age()/
     load_publish_state()/report_window_hours() helpers, not reimplemented)
     before treating a missing on-disk artifact as a real P0 defect. A
     report_url sourced from the deployment_manifest.json fallback (used
     only when the feed itself is empty) carries no id/timestamp to defer
     with, so it is conservatively never deferred -- unchanged fail-closed
     behavior for that path.

Env: PAGES_BASE_URL CANARY_WAIT_SECS CANARY_RETRY_COUNT CANARY_RETRY_WAIT
     CANARY_MAX_PROBES CANARY_TIMEOUT
(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CDB-REPORT-CANARY] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("sentinel.report_url_canary")

REPO_ROOT          = Path(__file__).resolve().parent.parent

# v187.0 P0 FIX: reuse the SAME authoritative publication-status query this
# repo already has (deployment_convergence_validator.py, STAGE 5.8.1c) rather
# than re-implementing publication-gate awareness here. Before this fix, a
# 404 on a report the publication gate correctly rejected (P21_BELOW_MINIMUM
# / P26_REJECTED / etc.) was indistinguishable from a genuine deployment
# failure, so this canary logged "P0 DEPLOYMENT FAILURE" for expected,
# by-design rejections. Import failure degrades to "always unknown" (fail
# closed -- never silently treated as a pass) rather than crashing the gate.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
try:
    from deployment_convergence_validator import query_publication_status
except Exception as _import_exc:  # pragma: no cover - defensive only
    def query_publication_status(report_id: str) -> Optional[dict]:  # type: ignore
        return None

# P0 2026-09-05 FIX: reuse the SAME rolling-window/publish-state helpers
# scripts/report_existence_validator.py already reuses from this module
# (not reimplemented) so --local can distinguish a genuinely missing
# artifact from one that is legitimately absent on THIS run's fresh
# runner -- see the "ROOT CAUSE FIXED (P0 2026-09-05)" module docstring
# section above.
from r2_report_publisher import (  # noqa: E402
    canonical_age,
    load_publish_state,
    report_window_hours,
)
REPORTS_DIR        = REPO_ROOT / "reports"
DIST_REPORTS_DIR   = REPO_ROOT / "dist" / "reports"
PAGES_BASE_URL     = os.environ.get("PAGES_BASE_URL", "https://intel.cyberdudebivash.com").rstrip("/")
CANARY_WAIT        = int(os.environ.get("CANARY_WAIT_SECS", "120"))
RETRY_COUNT        = int(os.environ.get("CANARY_RETRY_COUNT", "3"))
RETRY_WAIT         = int(os.environ.get("CANARY_RETRY_WAIT", "60"))
MAX_PROBES         = int(os.environ.get("CANARY_MAX_PROBES", "10"))
HTTP_TIMEOUT       = int(os.environ.get("CANARY_TIMEOUT", "15"))

MANIFEST_PATH = REPO_ROOT / "dist" / "deployment_manifest.json"
FEED_PATHS = [REPO_ROOT / "api" / "feed.json", REPO_ROOT / "feed.json"]

# Body-validation calibration (real reports observed at ~100KB valid HTML).
MIN_REPORT_BYTES = 512
SOFT_404_MARKERS = (
    "report_not_found", "report not found", "page not found",
    "404 not found", "this report could not be found", "no report found",
)

_PASS_CODES = frozenset([200, 301, 302, 304])
_AUTH_GATED_CODES = frozenset([401, 403])


def _parse_feed_safe(feed_path: Path) -> List:
    try:
        raw = feed_path.read_bytes().rstrip(b"\x00").replace(b"\x00", b"")
        data = json.loads(raw.decode("utf-8", errors="replace"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.warning("Could not parse %s: %s", feed_path.name, exc)
        return []


def _report_path(ru: Optional[str]) -> Optional[str]:
    """Normalize a report_url (full https URL OR relative) to '/reports/....html'."""
    ru = (ru or "").strip()
    if not ru:
        return None
    p = urlparse(ru).path if ru.lower().startswith("http") else ru
    if "/reports/" in p and p.lower().endswith(".html"):
        return p[p.index("/reports/"):]
    return None


def load_current_report_paths(max_count: int) -> List[str]:
    """Authoritative source = the CURRENT run's feed (reports being published now).

    Handles BOTH fully-qualified https URLs and relative paths (v174 fix).
    Falls back to dist/deployment_manifest.json only if no feed paths exist.
    """
    for feed_path in FEED_PATHS:
        if not feed_path.exists():
            continue
        items = _parse_feed_safe(feed_path)
        paths: List[str] = []
        seen = set()
        for item in items:
            for key in ("report_url", "internal_report_url"):
                rp = _report_path(item.get(key))
                if rp and rp not in seen:
                    seen.add(rp)
                    paths.append(rp)
        if paths:
            log.info("Loaded %d CURRENT-run report path(s) from %s", len(paths), feed_path.name)
            return paths[:max_count] if max_count and max_count > 0 else paths
    if MANIFEST_PATH.exists():
        try:
            manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            rep = [f"/{k}" for k in manifest.get("files", {})
                   if k.startswith("reports/") and k.endswith(".html")]
            if rep:
                log.warning("Feed empty -- falling back to %d manifest path(s)", len(rep))
                return rep[:max_count] if max_count and max_count > 0 else rep
        except Exception as exc:
            log.warning("Could not read deployment_manifest.json: %s", exc)
    log.warning("No report URLs found to probe.")
    return []


def load_current_feed_items() -> List[dict]:
    """Same feed source/precedence as load_current_report_paths(), returning
    the raw CURRENT-run feed items (not just normalized paths) so --local can
    look up each report_url's id/canonical timestamp for rolling-window
    deferral. Returns [] when the feed is empty/absent -- the
    deployment_manifest.json fallback path has no item metadata, so paths
    sourced from it are never deferred (see local_artifact_check())."""
    for feed_path in FEED_PATHS:
        if not feed_path.exists():
            continue
        items = _parse_feed_safe(feed_path)
        if items:
            return items
    return []


def build_path_to_item(items: List[dict]) -> Dict[str, dict]:
    """Maps each normalized '/reports/....html' path back to its source feed
    item (first match wins, mirroring load_current_report_paths()'s own
    dedup-by-first-seen) so local_artifact_check() need not re-parse the feed
    per path."""
    mapping: Dict[str, dict] = {}
    for item in items:
        for key in ("report_url", "internal_report_url"):
            rp = _report_path(item.get(key))
            if rp and rp not in mapping:
                mapping[rp] = item
    return mapping


def validate_body(body: str) -> Tuple[bool, str]:
    """A real report = sufficient size + html shell + no soft-404 marker."""
    if body is None:
        return False, "no body"
    low = body.lower()
    if len(body) < MIN_REPORT_BYTES:
        return False, f"body too small ({len(body)}B < {MIN_REPORT_BYTES}B)"
    for mk in SOFT_404_MARKERS:
        if mk in low:
            return False, f"soft-404 marker present: {mk!r}"
    if "<html" not in low and "<!doctype" not in low:
        return False, "missing <html>/<!doctype> -- not a rendered report"
    return True, "ok"


def _resolve_artifact(rel: str) -> Optional[Path]:
    """Return the first on-disk path that holds the artifact, checking both
    the working-tree reports/ directory (pre-cleanup) and dist/reports/ (post-
    Stage-5.4.6b cleanup, where the dist artifact is always present until
    the gh-pages upload completes).  Returns None when neither location has
    the file.

    Pipeline lifecycle on CI:
      Stage 5.4.6  : reports/ -> dist/reports/  (copy)
      Stage 5.4.6b : rm -rf reports/             (disk governance)
      Stage 5.8.1b : THIS gate                   (dist/reports/ still present)

    On local dev both directories may coexist; reports/ is checked first.
    """
    for base in (REPORTS_DIR, DIST_REPORTS_DIR):
        candidate = base / rel
        if candidate.exists():
            return candidate
    return None


def local_artifact_check(
    paths: List[str],
    path_to_item: Dict[str, dict],
    now: datetime,
    window_hours: int,
    published_ids: set,
) -> int:
    """PRE/POST-DEPLOY fail-closed: every current report_url must resolve to a
    valid on-disk artifact in reports/ OR dist/reports/, UNLESS it is
    confirmed durably published already or legitimately outside this run's
    rolling regeneration window.  Exit 1 on any genuinely missing artifact or
    on any invalid (report_not_found) body -- body validation is never
    deferred, since a file that exists but fails validation is a real defect
    regardless of age.

    Root cause fix v174.1: Stage 5.4.6b deletes reports/ before Stage 5.8.1b
    runs this gate. dist/reports/ is the authoritative fallback because
    Stage 5.4.6 copies all reports there and nothing deletes dist/ before
    Stage 5.8.1b executes.

    Root cause fix P0 2026-09-05: a report_url whose id is not in
    path_to_item (deployment_manifest.json fallback -- no item metadata) is
    never deferred, same fail-closed behavior as before. Otherwise, reuses
    the exact same deferral rule report_existence_validator.py already
    established -- see the module docstring's "ROOT CAUSE FIXED (P0
    2026-09-05)" section.
    """
    reports_present  = REPORTS_DIR.exists()
    dist_present     = DIST_REPORTS_DIR.exists()
    log.info("LOCAL pre-deploy artifact gate: %d current report_url(s)", len(paths))
    log.info("Artifact search: reports/=%s  dist/reports/=%s",
             "EXISTS" if reports_present else "ABSENT",
             "EXISTS" if dist_present    else "ABSENT")
    if not paths:
        log.info("No report_url values in current feed -- nothing to publish, gate PASS (exit 0).")
        return 0
    missing: List[str] = []
    deferred: List[str] = []
    invalid: List[Tuple[str, str]] = []
    ok = 0
    for rp in paths:
        rel = rp.split("/reports/", 1)[1]
        disk = _resolve_artifact(rel)
        if disk is None:
            item = path_to_item.get(rp)
            intel_id = (item.get("id") or "").strip() if item else ""
            if intel_id and intel_id in published_ids:
                deferred.append(rp)
                log.info("[DEFERRED:published] %s  (confirmed durably published via "
                         "r2_report_publisher.py state)", rp)
                continue
            if item is not None:
                _ts, _age_hours = canonical_age(item, now)
                if _age_hours is None or not (0 <= _age_hours <= window_hours):
                    deferred.append(rp)
                    log.info("[DEFERRED:out-of-window] %s  (not this run's %dh rolling-window "
                             "regeneration candidate)", rp, window_hours)
                    continue
            missing.append(rp)
            log.error("[MISSING] %s  (checked reports/ and dist/reports/)", rp)
            continue
        try:
            body = disk.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            invalid.append((rp, f"unreadable: {exc}"))
            log.error("[UNREADABLE] %s (%s)", rp, exc)
            continue
        valid, why = validate_body(body)
        if valid:
            ok += 1
            log.info("[OK] %s  [from %s] (%dB)", rp, disk.parent.parent.name, len(body))
        else:
            invalid.append((rp, why))
            log.error("[INVALID] %s -- %s", rp, why)
    log.info("=" * 70)
    log.info("LOCAL GATE: %d ok / %d missing / %d invalid / %d deferred (of %d)",
             ok, len(missing), len(invalid), len(deferred), len(paths))
    log.info("=" * 70)
    if missing or invalid:
        log.error("P0 FAIL-CLOSED: %d report_url(s) would publish without a valid artifact.",
                  len(missing) + len(invalid))
        return 1
    log.info("ALL current report_url artifacts exist on disk and carry valid bodies "
              "(%d deferred as out-of-window/already-published).", len(deferred))
    return 0


def probe_url(report_path: str) -> Tuple[str, int, str, str]:
    """GET (not HEAD) so we can validate the BODY. Returns (url, status, body, err)."""
    full_url = f"{PAGES_BASE_URL}{report_path}"
    try:
        req = urllib.request.Request(full_url, method="GET")
        req.add_header("User-Agent", "CDB-Sentinel-Canary/174.1")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read(131072).decode("utf-8", errors="replace")
            return full_url, resp.status, body, ""
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(8192).decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return full_url, exc.code, body, str(exc.reason)
    except Exception as exc:
        return full_url, 0, "", str(exc)


def probe_round(report_paths: List[str]) -> Tuple[List[str], List[Tuple[str, int, str]]]:
    passed: List[str] = []
    failed: List[Tuple[str, int, str]] = []
    for rp in report_paths:
        full_url, status, body, err = probe_url(rp)
        if status in _PASS_CODES:
            valid, why = validate_body(body)
            if valid:
                log.info("[PASS] HTTP %d (valid body) -- %s", status, full_url)
                passed.append(full_url)
            else:
                log.error("[FAIL] HTTP %d but SOFT-404 body -- %s (%s)", status, full_url, why)
                failed.append((full_url, status, f"soft-404: {why}"))
        elif status in _AUTH_GATED_CODES:
            log.info("[AUTH-GATED] HTTP %d -- %s (CDN-delivered, auth required -- PASS)", status, full_url)
            passed.append(full_url)
        else:
            log.error("[FAIL] HTTP %d -- %s (%s)", status, full_url, err or "no detail")
            failed.append((full_url, status, err))
    return passed, failed


# -- v187.0 P0 FIX: publication-gate-aware failure classification ------------
# A 404 on a report_url is not, by itself, evidence of a deployment failure.
# It must be classified against the SAME authoritative source the live
# Worker gates /reports/** on (see query_publication_status() import above):
#
#   PUBLISHED (customer_ready=true)  + still 404/invalid -> real P0 failure
#   REJECTED/BLOCKED (customer_ready=false)              -> expected, non-public
#   status undeterminable (network/parse error, or the
#   item cannot be resolved at all)                      -> unknown, fail closed
#
# "Pending/still generating" is not modelled as a separate state here: the
# authoritative publication-status endpoint does not currently expose one
# (see workers/intel-gateway/src/index.js:handlePublicationStatus -- an
# unresolvable item returns state="UNKNOWN", not a distinct pending state),
# and inventing one here would duplicate/guess at publication-gate logic
# this script must not own. The existing CDN-propagation retry loop above
# is what actually covers "still generating" -- a URL that is genuinely
# still propagating will typically succeed on one of those retries before
# ever reaching this classification step.
CLASS_PUBLISHED_HTTP_FAILURE = "PUBLISHED_REPORT_HTTP_FAILURE"
CLASS_EXPECTED_REJECTION     = "EXPECTED_PUBLICATION_REJECTION"
CLASS_STATUS_UNKNOWN         = "REPORT_STATUS_UNKNOWN"


def _extract_report_id(report_path: str) -> Optional[str]:
    """'/reports/2026/08/intel--<id>.html' -> 'intel--<id>' (matches the id
    form the publication-status endpoint expects, same as the incoming path
    param it strips '.html' from)."""
    name = report_path.rsplit("/", 1)[-1]
    for suffix in (".html", ".htm"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name if name.startswith("intel--") else None


def classify_and_summarize(
    report_paths: List[str],
    passed_urls: List[str],
    failed_tuples: List[Tuple[str, int, str]],
) -> Dict:
    """Classifies every probed report URL (not only the failures) against the
    authoritative publication-status endpoint, producing the structured
    breakdown required for observability. Never overrides the HTTP pass/fail
    verdict already computed by probe_round()/run_live() -- purely adds the
    "why" behind a failure so real deployment failures are never buried
    inside an "expected rejection" bucket, and expected rejections never get
    reported as P0 alarms.
    """
    passed_paths = {u.replace(PAGES_BASE_URL, "") for u in passed_urls}
    failed_paths = {u.replace(PAGES_BASE_URL, ""): (code, err) for u, code, err in failed_tuples}

    published_passed = 0
    published_failed: List[Tuple[str, int, str]] = []
    expected_rejections: List[str] = []
    unknown: List[str] = []

    for rp in report_paths:
        report_id = _extract_report_id(rp)
        data = query_publication_status(report_id) if report_id else None
        if data is None:
            unknown.append(rp)
            continue
        customer_ready = data.get("customer_ready")
        if customer_ready is True:
            if rp in passed_paths:
                published_passed += 1
            else:
                code, err = failed_paths.get(rp, (0, "unknown"))
                published_failed.append((rp, code, err))
        elif customer_ready is False:
            expected_rejections.append(rp)
        else:
            unknown.append(rp)

    return {
        "published_checked": published_passed + len(published_failed),
        "published_passed": published_passed,
        "published_failed": published_failed,
        "expected_rejections": expected_rejections,
        "pending": [],  # not distinguishable from unknown via the authoritative endpoint today
        "unknown": unknown,
    }


def run_live(report_paths: List[str]) -> int:
    if CANARY_WAIT > 0:
        log.info("Waiting %ds for GitHub Pages CDN propagation...", CANARY_WAIT)
        time.sleep(CANARY_WAIT)
    log.info("Probing %d CURRENT-run report URL(s) with body validation...", len(report_paths))
    passed, failed = probe_round(report_paths)
    for retry in range(1, RETRY_COUNT + 1):
        if not failed:
            break
        still = [u for u, _, _ in failed]
        log.info("Retry %d/%d: %d still failing. Waiting %ds...", retry, RETRY_COUNT, len(still), RETRY_WAIT)
        time.sleep(RETRY_WAIT)
        retry_paths = [u.replace(PAGES_BASE_URL, "") for u in still]
        passed_retry, failed = probe_round(retry_paths)
        passed.extend(passed_retry)
    log.info("=" * 70)
    log.info("LIVE CANARY: probed=%d passed=%d failed=%d", len(report_paths), len(passed), len(failed))
    log.info("=" * 70)

    if not failed:
        log.info("ALL current report URLs GREEN with valid bodies.")
        return 0

    # v187.0 P0 FIX: classify every remaining HTTP failure against the
    # authoritative publication-status endpoint before deciding whether it's
    # a real deployment failure -- see the classification block above.
    summary = classify_and_summarize(report_paths, passed, failed)
    log.info("=" * 70)
    log.info("PUBLICATION-STATUS CLASSIFICATION:")
    log.info("  published_checked   = %d", summary["published_checked"])
    log.info("  published_passed    = %d", summary["published_passed"])
    log.info("  published_failed    = %d", len(summary["published_failed"]))
    log.info("  expected_rejections = %d", len(summary["expected_rejections"]))
    log.info("  pending             = %d", len(summary["pending"]))
    log.info("  unknown             = %d", len(summary["unknown"]))
    log.info("=" * 70)

    if summary["expected_rejections"]:
        log.info(
            "%s (%d): 404 because the publication gate correctly rejected these "
            "reports -- NOT a deployment failure:",
            CLASS_EXPECTED_REJECTION, len(summary["expected_rejections"]),
        )
        for rp in summary["expected_rejections"]:
            log.info("  %s%s", PAGES_BASE_URL, rp)

    real_failures = summary["published_failed"]
    unknown_failures = summary["unknown"]

    if not real_failures and not unknown_failures:
        log.info("No genuine deployment failures -- all remaining 404s are expected publication-gate rejections.")
        return 0

    if real_failures:
        log.error(
            "%s (%d): CUSTOMER_READY per the publication gate but returning "
            "non-200/soft-404 -- genuine P0 deployment failure:",
            CLASS_PUBLISHED_HTTP_FAILURE, len(real_failures),
        )
        for rp, code, err in real_failures:
            log.error("  HTTP %s: %s%s (%s)", code, PAGES_BASE_URL, rp, err or "no detail")
    if unknown_failures:
        log.error(
            "%s (%d): publication-status could not be determined -- failing closed:",
            CLASS_STATUS_UNKNOWN, len(unknown_failures),
        )
        for rp in unknown_failures:
            log.error("  %s%s", PAGES_BASE_URL, rp)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="SENTINEL APEX Report URL Canary v174.1")
    ap.add_argument("--local", action="store_true",
                    help="Pre/post-deploy fail-closed on-disk existence+body gate (no network)")
    ap.add_argument("--live", action="store_true",
                    help="Post-deploy live HTTP probe with body validation")
    args = ap.parse_args()

    log.info("=" * 70)
    log.info("SENTINEL APEX -- Report URL Canary v174.1")
    log.info("Mode: %s | Pages base: %s", "LOCAL" if args.local else "LIVE", PAGES_BASE_URL)
    log.info("=" * 70)

    if args.local:
        paths = load_current_report_paths(0)   # ALL current paths
        path_to_item = build_path_to_item(load_current_feed_items())
        window_hours = report_window_hours()
        now = datetime.now(timezone.utc)
        publish_state = load_publish_state()
        published_ids = {
            _id for _id, _rec in publish_state.get("items", {}).items()
            if isinstance(_rec, dict) and _rec.get("html_key")
        }
        log.info(
            "Rolling publish window: %dh -- %d id(s) confirmed durably published via "
            "r2_report_publisher.py's own state.", window_hours, len(published_ids),
        )
        return local_artifact_check(paths, path_to_item, now, window_hours, published_ids)

    report_paths = load_current_report_paths(MAX_PROBES)
    if not report_paths:
        log.info("No report URLs to probe -- canary exits 0 (nothing to validate).")
        return 0
    return run_live(report_paths)


if __name__ == "__main__":
    sys.exit(main())
