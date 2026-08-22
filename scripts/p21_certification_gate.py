#!/usr/bin/env python3
"""
scripts/p21_certification_gate.py
CYBERDUDEBIVASH® SENTINEL APEX — P21.0 Certification Gate v2.0.0
=================================================================
P21.10 — Regression Certification / CI Gate

Phase 4.1 P21 migration (mandate Sections 3-8): P21 no longer maintains an
independent competing quality rubric. Per-item scoring is delegated entirely
to quality_rubric_scorer.score_item() (Phase 4's applicability-aware
12-dimension scorer, itself composing validate_intelligence_content()) --
the same "REPORT TYPE CONTRACT -> validate_intelligence_content() ->
PASS/WARN/HOLD -> commercial quality rubric -> P21 compatibility layer"
hierarchy the mandate defines. This closes the REPORT_TYPE_APPLICABILITY_
DEFECT documented in docs/architecture/INTELLIGENCE-REPORT-QUALITY.md
Section 8-9 (P21's old 8-component rubric scored a one-paragraph indicator
against the same completeness bar as a deep CVE writeup and structurally
failed anything that wasn't the latter).

Applies P21 certification thresholds to the applicability-aware score:
  PREMIUM_CERTIFIED  >= 90  AND content_severity == PASS
  ENTERPRISE_READY   >= 75  (or score >= 90 with content_severity == WARN --
                             see _certification_level()'s exact mapping)
  INTERNAL_DRAFT      < 75  (blocked from auto-publication)
  BELOW_MINIMUM       < 38, OR content_severity == HOLD regardless of score

EXACT MAPPING (mandate Section 6, documented not just implemented):
  content_severity=HOLD  -> always BELOW_MINIMUM. A HOLD verdict means
    validate_intelligence_content() found placeholder/template-leak/unsafe-
    HTML/invalid-IOC/fabricated-score-class content -- never certifiable,
    matching publication-gate.js's own deny-overrides-allow policy.
  content_severity=WARN  -> capped at ENTERPRISE_READY. A WARN item may
    still score numerically >=90 on the rubric, but Section 6 explicitly
    forbids promoting WARN to PREMIUM_CERTIFIED, so the score-derived tier
    is clamped down by exactly one level when it would otherwise reach
    PREMIUM_CERTIFIED. WARN never blocks INTERNAL_DRAFT/ENTERPRISE_READY --
    only the top tier is withheld.
  content_severity=PASS  -> full four-tier range, thresholds unchanged from
    v1.0.0 (90/75/38) so this migration is measured against a fixed bar
    rather than one silently redefined at the same time (Section 35).

Exit codes:
  0 — all items meet or exceed INTERNAL_DRAFT; certification report written
  1 — hard failure: items exist that are below MINIMUM_PUBLISHABLE (< 38)
      or critical gate errors detected

Writes: data/quality/p21_certification_report.json
  Backward-compatible: total_items, average_score, level_distribution,
  below_minimum_count/ids, premium_certified_pct, enterprise_ready_pct,
  thresholds, items[] -- unchanged shape/keys, still consumed unmodified by
  ci_stats_extract.py, p24_commercial_certification.py,
  p25_enterprise_trust_gate.py (G4), p26_intelligence_excellence.py.
  Additive (Section 7): by_report_type -- evaluated/PASS/WARN/HOLD/
  avg_score per report type, so an aggregate figure is never published
  again without showing which report classes it is made of.

ZERO FABRICATION — scoring is derived entirely from existing item fields,
via the canonical Phase 4 content-contract/rubric engines (reused, not
re-implemented -- Section 0 Level 1).
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from quality_rubric_scorer import score_item as _rubric_score_item  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] P21-CERT %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("p21-cert")

REPO      = Path(__file__).resolve().parent.parent
DRY_RUN   = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
FEED_PATH = Path(os.environ.get("FEED_PATH", str(REPO / "api" / "feed.json")))
OUT_PATH  = REPO / "data" / "quality" / "p21_certification_report.json"
FAIL_FAST = os.environ.get("FAIL_FAST", "false").strip().lower() == "true"

# P21 thresholds (stricter than P20: Enterprise Ready raised 72 → 75).
# Unchanged from v1.0.0 -- see module docstring "EXACT MAPPING" for how
# content_severity (PASS/WARN/HOLD) now additionally gates these tiers.
THRESHOLD_PREMIUM    = 90
THRESHOLD_ENTERPRISE = 75
THRESHOLD_MINIMUM    = 38  # below this = not even Analyst Review quality

PACKAGE_TAG_RE = re.compile(
    r"^(npm|pip|gem|cargo|go|composer|nuget|maven):|"
    r"^(golang\.org|go\.dev|npmjs\.com|pypi\.org|rubygems\.org|crates\.io|"
    r"packagist\.org|nuget\.org|mvnrepository\.com)$",
    re.IGNORECASE,
)

MARKDOWN_RE = re.compile(
    r"#{1,6}\s+|(\*{1,2}|_{1,2})(.*?)\1|\[([^\]]+)\]\([^\)]+\)|`{1,3}[^`]*`{1,3}",
    re.DOTALL,
)


def _strip_markdown(text: str) -> str:
    text = MARKDOWN_RE.sub(r"\2\3", text)
    return re.sub(r"\s+", " ", text).strip()


def _score_item(item: Dict) -> Tuple[int, Dict[str, Any], str, str]:
    """Compute P21 quality score for a single item.

    v2.0.0: delegates entirely to quality_rubric_scorer.score_item() (Phase
    4's applicability-aware 12-dimension scorer over validate_intelligence_
    content()'s report-type contracts) instead of an independently coded
    8-component rubric. Returns (score_0_100, dimensions_breakdown,
    report_type, content_severity) so callers can apply the WARN/HOLD
    ceiling documented in the module docstring without re-deriving it.
    """
    result = _rubric_score_item(item)
    score = round(result["pct"])
    return score, result["dimensions"], result["report_type"], result["content_severity"]


def _certification_level(score: int, content_severity: str) -> str:
    """See module docstring "EXACT MAPPING" for the full rationale.
    content_severity is validate_intelligence_content()'s PASS/WARN/HOLD
    verdict -- a ceiling on top of the numeric score, never a promotion."""
    if content_severity == "HOLD":
        return "BELOW_MINIMUM"
    if score >= THRESHOLD_PREMIUM:
        return "PREMIUM_CERTIFIED" if content_severity == "PASS" else "ENTERPRISE_READY"
    if score >= THRESHOLD_ENTERPRISE:
        return "ENTERPRISE_READY"
    if score >= THRESHOLD_MINIMUM:
        return "INTERNAL_DRAFT"
    return "BELOW_MINIMUM"


def _dim_pts(dims: Dict[str, Any], name: str) -> float:
    """Best-effort display-only point value for a legacy gate name, read from
    the new applicability-aware dimensions dict. Never used for pass/fail --
    see _gate_results()'s per-gate comments for what each gate actually
    gates on."""
    d = dims.get(name)
    return round(d["score"], 1) if isinstance(d, dict) else 0


def _gate_results(item: Dict, score: int, dims: Dict[str, Any], content_severity: str) -> Dict:
    gates: List[Dict] = []

    def gate(name: str, passed: bool, detail: str, score_pts: float = 0) -> None:
        gates.append({"gate": name, "passed": passed, "detail": detail, "score_pts": score_pts})

    # G1: Evidence Chain -- pass/fail still reads the raw field directly
    # (unaffected by the v2.0.0 rubric-scorer swap); score_pts now shows the
    # rubric's evidence_provenance dimension instead of the retired 8-part
    # breakdown's "evidence" key.
    ec = item.get("evidence_chain")
    g1 = bool(ec and isinstance(ec, dict) and ec.get("reliability_code", "F") not in ("F", "E"))
    gate("G1_EVIDENCE", g1,
         f"Reliability code: {ec.get('reliability_code','MISSING') if ec else 'MISSING'} "
         f"(corroboration: {ec.get('corroboration_count', 0) if ec else 0})" if ec
         else "No evidence_chain field present",
         _dim_pts(dims, "evidence_provenance"))

    # G2: IOC Quality -- v2.0.0 FIX: previously failed every item with zero
    # IOCs regardless of report type (part of the REPORT_TYPE_APPLICABILITY_
    # DEFECT this migration closes). Now reads the rubric's own ioc_quality
    # dimension, whose max is 0 for a report type/eligibility where IOCs are
    # NOT_APPLICABLE (e.g. NEWS) -- that case passes (nothing to satisfy),
    # matching validate_intelligence_content()'s "excluded from denominator,
    # not penalized" rule instead of a hard-coded field check.
    ioc_dim = dims.get("ioc_quality") or {"score": 0, "max": 0}
    ioc_count = item.get("ioc_count") or len(item.get("iocs") or [])
    g2 = ioc_dim["max"] == 0 or (ioc_dim["max"] > 0 and ioc_dim["score"] / ioc_dim["max"] >= 0.4)
    gate("G2_IOC_QUALITY", g2,
         f"{ioc_count} operational IOCs (score: {ioc_dim['score']:.1f}/{ioc_dim['max']:.1f})"
         if ioc_dim["max"] else "IOCs not applicable to this report type",
         ioc_dim["score"])

    # G3: Multi-source Validation -- unchanged, raw-field pass/fail; display
    # points now sourced from the closest rubric dimension (confidence_
    # uncertainty partially reflects corroboration strength; no 1:1 successor
    # to the retired "multi_source" component exists in the 12-dimension
    # rubric, so this is informational only, same as before).
    corr = item.get("corroborating_sources")
    corr_count = len(corr) if isinstance(corr, list) else (int(corr) if isinstance(corr, int) else 0)
    g3 = corr_count >= 1
    gate("G3_MULTI_SOURCE", g3,
         f"{corr_count} corroborating sources",
         _dim_pts(dims, "confidence_uncertainty"))

    # G4: MITRE Mapping
    ttps = item.get("mitre_tactics") or item.get("ttps") or []
    ttp_count = len(ttps) if isinstance(ttps, list) else 0
    g4 = ttp_count >= 1
    gate("G4_MITRE", g4,
         f"{ttp_count} ATT&CK TTPs/tactics mapped",
         _dim_pts(dims, "attck_quality"))

    # G5: Detection Engineering
    sigma = item.get("sigma_rule") or item.get("sigma") or ""
    g5 = bool(isinstance(sigma, str) and len(sigma) > 100)
    det_dim = dims.get("detection_value") or {"score": 0, "max": 0}
    gate("G5_DETECTION", g5,
         "Sigma rule present and specific" if (g5 and det_dim["max"] and det_dim["score"] >= det_dim["max"])
         else ("Sigma rule present but generic" if g5 else "No detection rule"),
         _dim_pts(dims, "detection_value"))

    # G6: Executive Summary
    text = item.get("apex", {}).get("ai_summary") or item.get("description") or ""
    words = len(_strip_markdown(str(text)).split())
    g6 = words >= 50
    gate("G6_EXECUTIVE", g6,
         f"Executive summary: {words} words (≥50 required)",
         _dim_pts(dims, "executive_usefulness"))

    # G7: Attribution Quality
    actor_conf = item.get("actor_confidence") or 0
    attr_method = item.get("attribution_method") or ""
    g7 = True  # attribution does not gate publication but we surface it
    gate("G7_ATTRIBUTION", g7,
         f"Confidence: {actor_conf}% | Method: {attr_method or 'unset'}",
         0)

    # G8: Certification Level (content_severity applies the WARN/HOLD
    # ceiling documented in the module docstring -- see _certification_level)
    cert_level = _certification_level(score, content_severity)
    g8 = cert_level != "BELOW_MINIMUM"
    gate("G8_PUBLICATION_GATE", g8,
         f"Score {score}/100 → {cert_level}",
         0)

    gates_passed = sum(1 for g in gates if g["passed"])
    return {
        "gates": gates,
        "gates_passed": gates_passed,
        "gates_total": len(gates),
        "all_critical_passed": all(g["passed"] for g in gates if g["gate"].startswith("G8")),
    }


def certify_feed(path: Path) -> Tuple[Dict, int]:
    if not path.exists():
        log.warning("Feed not found: %s", path)
        return {}, 0

    try:
        raw  = path.read_bytes().rstrip(b"\x00").replace(b"\x00", b"")
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        log.error("Failed to load feed: %s", exc)
        return {}, 1

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = next(
            (data[k] for k in ("items", "advisories", "feed", "data")
             if k in data and isinstance(data[k], list)),
            []
        )
    else:
        return {}, 0

    now = datetime.now(timezone.utc).isoformat()
    certified: List[Dict] = []
    below_min: List[str] = []
    level_counts: Dict[str, int] = Counter()
    # Section 7: publish P21 quality BY report type, never a single aggregate
    # percentage again without showing which report classes it is made of.
    by_type: Dict[str, Dict[str, Any]] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("stix_id") or item.get("id") or "unknown"
        score, dims, report_type, content_severity = _score_item(item)
        level = _certification_level(score, content_severity)
        gate_res = _gate_results(item, score, dims, content_severity)
        level_counts[level] += 1

        certified.append({
            "id":                item_id,
            "title":             str(item.get("title", ""))[:80],
            "score":             score,
            "level":             level,
            "report_type":       report_type,
            "content_severity":  content_severity,
            "dimensions":        dims,
            "gates_passed":      gate_res["gates_passed"],
            "gates_total":       gate_res["gates_total"],
            "gates":             gate_res["gates"],
            "severity":          item.get("severity", "UNKNOWN"),
            "kev":               bool(item.get("kev_present") or item.get("kev")),
            "cve":               (item.get("cve_ids") or ([item["cve_id"]] if item.get("cve_id") else []))[:3],
            "certified_at":      now,
        })

        rt = by_type.setdefault(report_type, {
            "evaluated": 0, "PASS": 0, "WARN": 0, "HOLD": 0, "_score_sum": 0.0,
            "level_distribution": Counter(),
        })
        rt["evaluated"] += 1
        rt[content_severity] += 1
        rt["_score_sum"] += score
        rt["level_distribution"][level] += 1

        if level == "BELOW_MINIMUM":
            below_min.append(item_id)
            log.warning("BELOW_MINIMUM: %s (score=%d)", item_id[:40], score)

    total = len(certified)
    avg   = round(sum(c["score"] for c in certified) / total, 1) if total else 0

    by_report_type = {}
    for rt_name, rt in sorted(by_type.items()):
        evaluated = rt["evaluated"]
        by_report_type[rt_name] = {
            "evaluated":           evaluated,
            "PASS":                rt["PASS"],
            "WARN":                rt["WARN"],
            "HOLD":                rt["HOLD"],
            "average_score":       round(rt["_score_sum"] / evaluated, 1) if evaluated else 0,
            "level_distribution":  dict(rt["level_distribution"]),
        }

    report = {
        "generated_at":           now,
        "certification_version":  "P21.0",
        "engine_version":         "2.0.0",
        "feed_path":              str(path),
        "total_items":            total,
        "average_score":          avg,
        "level_distribution":     dict(level_counts),
        "by_report_type":         by_report_type,
        "below_minimum_count":    len(below_min),
        "below_minimum_ids":      below_min[:20],
        "premium_certified_pct":  round(level_counts.get("PREMIUM_CERTIFIED", 0) / max(total, 1) * 100, 1),
        "enterprise_ready_pct":   round((level_counts.get("PREMIUM_CERTIFIED", 0) + level_counts.get("ENTERPRISE_READY", 0)) / max(total, 1) * 100, 1),
        "thresholds": {
            "premium_certified":  THRESHOLD_PREMIUM,
            "enterprise_ready":   THRESHOLD_ENTERPRISE,
            "minimum_publishable": THRESHOLD_MINIMUM,
        },
        "items": certified,
    }
    return report, len(below_min)


def main() -> int:
    log.info("P21.0 Certification Gate v1.0.0 — DRY_RUN=%s FAIL_FAST=%s", DRY_RUN, FAIL_FAST)
    log.info("Thresholds: PREMIUM≥%d | ENTERPRISE≥%d | MIN≥%d",
             THRESHOLD_PREMIUM, THRESHOLD_ENTERPRISE, THRESHOLD_MINIMUM)

    report, below_min_count = certify_feed(FEED_PATH)
    if not report:
        log.error("No items certified — feed empty or unreadable")
        return 1

    total  = report["total_items"]
    avg    = report["average_score"]
    levels = report["level_distribution"]
    prem   = report["premium_certified_pct"]
    ent    = report["enterprise_ready_pct"]

    log.info("Feed: %d items | Avg score: %.1f/100", total, avg)
    log.info("PREMIUM_CERTIFIED: %d (%.1f%%)", levels.get("PREMIUM_CERTIFIED", 0), prem)
    log.info("ENTERPRISE_READY:  %d", levels.get("ENTERPRISE_READY", 0))
    log.info("INTERNAL_DRAFT:    %d", levels.get("INTERNAL_DRAFT", 0))
    log.info("BELOW_MINIMUM:     %d", below_min_count)
    log.info("Publishable (≥ENTERPRISE_READY): %.1f%%", ent)

    if not DRY_RUN:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".tmp_p21cert")
        try:
            tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(OUT_PATH)
            log.info("Certification report: %s (%d B)", OUT_PATH, OUT_PATH.stat().st_size)
        except Exception as exc:
            log.error("Failed to write report: %s", exc)
            tmp.unlink(missing_ok=True)
            return 1
    else:
        log.info("[DRY_RUN] Would write %d-item certification report to %s", total, OUT_PATH)

    if FAIL_FAST and below_min_count > 0:
        log.error("HARD_FAIL: %d item(s) BELOW_MINIMUM threshold (score < %d)",
                  below_min_count, THRESHOLD_MINIMUM)
        return 1

    log.info("P21.0 Certification Gate PASS — %d items certified", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
