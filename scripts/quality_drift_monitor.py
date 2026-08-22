#!/usr/bin/env python3
"""
scripts/quality_drift_monitor.py
CYBERDUDEBIVASH(R) SENTINEL APEX v185.0 -- Quality Drift Monitor (Phase 4)
===========================================================================
Observable Everything (Principle 7): publishes PASS/WARN/HOLD trend, top
violation types, and eligible-vs-covered coverage metrics for the
canonical live feed, run over run.

Pure composition, no re-scoring:
  - intelligence_content_contract.validate_batch()  -- PASS/WARN/HOLD +
    violation-code counts (Phase 4 Checkpoint B)
  - p38_shared_validators eligibility accessors     -- eligible-vs-covered,
    never raw-vs-covered (Phase 2/Phase 4 pattern; an ineligible item
    correctly contributes 0, never counts as a miss)
  - p38_shared_validators.get_certification_feed()  -- the one canonical
    feed resolver every certification/quality script uses

Writes data/quality/quality_drift_report.json: current snapshot, delta
against the immediately preceding run's snapshot (if any), and a bounded
rolling history (last 30 runs) for trend visibility over time.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from intelligence_content_contract import validate_batch  # noqa: E402
from p38_shared_validators import (  # noqa: E402
    get_certification_feed, StaleFeedError,
    is_detection_eligible, attck_eligible, is_ioc_eligible,
    has_mitre_coverage, has_detection_rules,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [drift-monitor] %(levelname)s %(message)s")
log = logging.getLogger("quality_drift_monitor")

ENGINE_VERSION = "185.0.0"
REPO = Path(__file__).resolve().parent.parent
OUT_PATH = REPO / "data" / "quality" / "quality_drift_report.json"
MAX_HISTORY = 30


def _pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 1) if d else 0.0


def _eligible_coverage(items: List[Dict]) -> Dict[str, Any]:
    """Eligible-vs-covered, not raw-vs-covered, for each of the three
    coverage dimensions this platform already tracks eligibility for.
    An ineligible item (e.g. a NEWS item with no CVE/vuln_class) is
    correctly excluded from the denominator -- counting it as a miss is
    exactly the P21/detection-coverage defect class this phase exists to
    correct (see INTELLIGENCE-REPORT-QUALITY.md / INTELLIGENCE-DETECTION-
    ARCHITECTURE.md)."""
    attck_elig = [i for i in items if attck_eligible(i)]
    attck_cov  = [i for i in attck_elig if has_mitre_coverage(i)]

    ioc_elig = [i for i in items if is_ioc_eligible(i)]
    ioc_cov  = [i for i in ioc_elig if i.get("iocs")]

    det_elig = [i for i in items if is_detection_eligible(i)]
    det_cov  = [i for i in det_elig if has_detection_rules(i)]

    return {
        "attck": {
            "eligible": len(attck_elig), "covered": len(attck_cov),
            "pct": _pct(len(attck_cov), len(attck_elig)),
        },
        "ioc": {
            "eligible": len(ioc_elig), "covered": len(ioc_cov),
            "pct": _pct(len(ioc_cov), len(ioc_elig)),
        },
        "detection": {
            "eligible": len(det_elig), "covered": len(det_cov),
            "pct": _pct(len(det_cov), len(det_elig)),
        },
    }


def _load_previous() -> Dict[str, Any] | None:
    if not OUT_PATH.exists():
        return None
    try:
        with OUT_PATH.open(encoding="utf-8") as f:
            prior = json.load(f)
        return prior.get("current")
    except Exception as e:
        log.warning("Could not read previous report (non-fatal): %s", e)
        return None


def _compute_delta(current: Dict[str, Any], previous: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if previous is None:
        return None
    cur_sev, prev_sev = current["by_severity"], previous.get("by_severity", {})
    return {
        "pass_pct_change": round(current["by_severity_pct"].get("PASS", 0)
                                  - previous.get("by_severity_pct", {}).get("PASS", 0), 1),
        "hold_count_change": cur_sev.get("HOLD", 0) - prev_sev.get("HOLD", 0),
        "warn_count_change": cur_sev.get("WARN", 0) - prev_sev.get("WARN", 0),
        "attck_coverage_pct_change": round(
            current["eligible_coverage"]["attck"]["pct"]
            - previous.get("eligible_coverage", {}).get("attck", {}).get("pct", 0), 1),
        "ioc_coverage_pct_change": round(
            current["eligible_coverage"]["ioc"]["pct"]
            - previous.get("eligible_coverage", {}).get("ioc", {}).get("pct", 0), 1),
        "detection_coverage_pct_change": round(
            current["eligible_coverage"]["detection"]["pct"]
            - previous.get("eligible_coverage", {}).get("detection", {}).get("pct", 0), 1),
    }


def main() -> int:
    try:
        feed = get_certification_feed("live")
    except StaleFeedError as e:
        log.error("Canonical live feed unavailable: %s", e)
        return 1

    items = feed.items
    batch = validate_batch(items)

    by_severity = batch["by_severity"]
    total = batch["total_items"]
    by_severity_pct = {k: _pct(v, total) for k, v in by_severity.items()}

    top_violations = sorted(batch["violation_code_counts"].items(), key=lambda kv: -kv[1])[:15]

    current = {
        "feed_key": feed.key,
        "item_count": total,
        "feed_generated_at": feed.generated_at,
        "feed_fingerprint": feed.fingerprint,
        "by_severity": by_severity,
        "by_severity_pct": by_severity_pct,
        "by_report_type": batch["by_report_type"],
        "top_violation_types": top_violations,
        "eligible_coverage": _eligible_coverage(items),
    }

    previous = _load_previous()
    delta = _compute_delta(current, previous)

    prior_report: Dict[str, Any] = {}
    if OUT_PATH.exists():
        try:
            with OUT_PATH.open(encoding="utf-8") as f:
                prior_report = json.load(f)
        except Exception:
            prior_report = {}
    history: List[Dict[str, Any]] = prior_report.get("history", [])
    history.append({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feed_fingerprint": feed.fingerprint,
        "by_severity_pct": by_severity_pct,
        "attck_coverage_pct": current["eligible_coverage"]["attck"]["pct"],
        "ioc_coverage_pct": current["eligible_coverage"]["ioc"]["pct"],
        "detection_coverage_pct": current["eligible_coverage"]["detection"]["pct"],
    })
    history = history[-MAX_HISTORY:]

    report = {
        "engine": "quality_drift_monitor",
        "engine_version": ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current": current,
        "previous": previous,
        "delta": delta,
        "history": history,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A shared ".tmp" name lets a second concurrent run delete/overwrite the
    # first run's temp file before its own replace() -- a unique per-process
    # suffix makes the write collision-free without needing a lock, since
    # each run's own final os.replace() is still atomic.
    tmp = OUT_PATH.with_suffix(f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    tmp.replace(OUT_PATH)

    log.info(
        "Feed=%s items=%d | PASS=%d(%.1f%%) WARN=%d(%.1f%%) HOLD=%d(%.1f%%)",
        feed.key, total,
        by_severity.get("PASS", 0), by_severity_pct.get("PASS", 0),
        by_severity.get("WARN", 0), by_severity_pct.get("WARN", 0),
        by_severity.get("HOLD", 0), by_severity_pct.get("HOLD", 0),
    )
    log.info(
        "Eligible coverage: ATT&CK %.1f%% (%d/%d) | IOC %.1f%% (%d/%d) | Detection %.1f%% (%d/%d)",
        current["eligible_coverage"]["attck"]["pct"],
        current["eligible_coverage"]["attck"]["covered"], current["eligible_coverage"]["attck"]["eligible"],
        current["eligible_coverage"]["ioc"]["pct"],
        current["eligible_coverage"]["ioc"]["covered"], current["eligible_coverage"]["ioc"]["eligible"],
        current["eligible_coverage"]["detection"]["pct"],
        current["eligible_coverage"]["detection"]["covered"], current["eligible_coverage"]["detection"]["eligible"],
    )
    log.info("Top violation types: %s", top_violations[:5])
    log.info("Report written: %s", OUT_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
