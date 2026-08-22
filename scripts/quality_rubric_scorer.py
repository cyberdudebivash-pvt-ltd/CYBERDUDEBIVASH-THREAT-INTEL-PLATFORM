#!/usr/bin/env python3
"""
scripts/quality_rubric_scorer.py
CYBERDUDEBIVASH(R) SENTINEL APEX v185.0 -- 12-Dimension Commercial Quality
Rubric Scorer (Phase 3/4)

Reusable, deterministic, applicability-aware scorer for the 12-dimension
100-point rubric used for the representative-sample benchmark:
  1. Intelligence integrity      15
  2. Evidence / provenance       12
  3. Technical depth             12
  4. Executive usefulness         8
  5. SOC actionability           10
  6. IOC quality                  8
  7. ATT&CK quality                7
  8. Detection engineering value 10
  9. Mitigation / response        7
 10. Confidence / uncertainty     5
 11. Readability / presentation   3
 12. Machine-readable consistency 3
                          Total = 100

Applicability-aware (mandate section 20): a report type where a dimension
is NOT_APPLICABLE per report_type_contracts.py is scored out of its
reduced max and renormalised, so e.g. a NEWS item is never penalized for
lacking IOC/ATT&CK/detection content it was never expected to carry.

Reused, not duplicated: derives from validate_intelligence_content()
(Phase 4) and report_type_contracts.py rather than re-implementing content
validation. This module only adds the numeric weighting/scoring layer on
top of those existing signals.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from intelligence_content_contract import validate_intelligence_content  # noqa: E402
from report_type_contracts import contract_for_item, NOT_APPLICABLE  # noqa: E402
from p38_shared_validators import attck_eligible, is_ioc_eligible, is_detection_eligible  # noqa: E402

DIMENSION_WEIGHTS: Dict[str, int] = {
    "intelligence_integrity":      15,
    "evidence_provenance":         12,
    "technical_depth":             12,
    "executive_usefulness":         8,
    "soc_actionability":           10,
    "ioc_quality":                   8,
    "attck_quality":                 7,
    "detection_value":              10,
    "mitigation_response":           7,
    "confidence_uncertainty":        5,
    "readability_presentation":      3,
    "machine_readable_consistency":  3,
}
assert sum(DIMENSION_WEIGHTS.values()) == 100


def _word_count(item: Dict) -> int:
    return len(str(item.get("description") or "").split())


def _score_intelligence_integrity(item: Dict, vr) -> float:
    """Max points, minus deductions for hard-fail-class content violations
    (fabrication, template leakage, unsafe content) found by the content
    contract engine."""
    score = DIMENSION_WEIGHTS["intelligence_integrity"]
    hard_fail_codes = {v.code for v in vr.violations if v.severity == "HARD_FAIL"}
    deduct_per_code = {
        "PLACEHOLDER": 15, "TEMPLATE_LEAK": 15, "INTERNAL_INSTRUCTION": 15,
        "UNSAFE_HTML": 15, "MALFORMED_REFERENCE": 8, "DUPLICATE_ENTRY": 10,
        "SYNTHETIC_ACTOR": 10, "GENERATED_OPERATION": 10, "ZERO_EVIDENCE_ATTACK": 4,
        "UNSUPPORTED_ATTRIB": 3, "INVALID_IOC_CONTEXT": 6, "PSEUDO_IOC": 6, "INVALID_IOC": 4,
    }
    for code in hard_fail_codes:
        score -= deduct_per_code.get(code, 2)
    return max(0.0, min(score, DIMENSION_WEIGHTS["intelligence_integrity"]))


def _score_evidence_provenance(item: Dict) -> float:
    max_pts = DIMENSION_WEIGHTS["evidence_provenance"]
    pts = 0.0
    if item.get("source_url"):
        pts += max_pts * 0.4
    ec = item.get("evidence_chain")
    if isinstance(ec, dict):
        rc = ec.get("reliability_code", "F")
        pts += max_pts * 0.4 * {"A": 1.0, "B": 0.85, "C": 0.65, "D": 0.35, "E": 0.15, "F": 0.0}.get(rc, 0.0)
    corr = item.get("corroborating_sources") or []
    if isinstance(corr, list) and corr:
        pts += max_pts * 0.2
    return round(min(pts, max_pts), 2)


def _score_technical_depth(item: Dict, report_type: str) -> float:
    max_pts = DIMENSION_WEIGHTS["technical_depth"]
    if report_type in ("NEWS", "INDICATOR_FEED"):
        # Depth is measured differently for these types -- event/indicator
        # accuracy, not vulnerability-mechanism depth. Give full credit for
        # a factual, non-vague description; do not penalize for lacking a
        # CVE-style technical breakdown.
        wc = _word_count(item)
        return round(max_pts * (1.0 if wc >= 15 else 0.5 if wc >= 5 else 0.0), 2)
    wc = _word_count(item)
    depth_signals = sum([
        bool(item.get("cve_id") or item.get("cve_ids") or item.get("cves")),
        bool(item.get("affected_products")),
        bool(item.get("cvss_score")),
        wc >= 60,
    ])
    return round(max_pts * min(1.0, depth_signals / 4 + (0.15 if wc >= 100 else 0)), 2)


def _score_executive_usefulness(item: Dict) -> float:
    max_pts = DIMENSION_WEIGHTS["executive_usefulness"]
    pts = 0.0
    if item.get("severity"):
        pts += max_pts * 0.4
    if item.get("risk_score") is not None:
        pts += max_pts * 0.3
    wc = _word_count(item)
    if wc >= 20:
        pts += max_pts * 0.3
    return round(min(pts, max_pts), 2)


def _score_soc_actionability(item: Dict, report_type: str) -> float:
    max_pts = DIMENSION_WEIGHTS["soc_actionability"]
    if report_type == "NEWS":
        return round(max_pts * 0.5, 2)  # news is inherently lower-actionability; not a defect
    pts = 0.0
    if item.get("iocs"):
        pts += max_pts * 0.35
    if item.get("attck_technique_ids") or item.get("mitre_tactics") or item.get("ttps"):
        pts += max_pts * 0.35
    if isinstance(item.get("sigma_rule"), str) and len(item["sigma_rule"]) > 100:
        pts += max_pts * 0.30
    return round(min(pts, max_pts), 2)


def _score_ioc_quality(item: Dict, eligible: bool) -> Tuple[float, float]:
    max_pts = DIMENSION_WEIGHTS["ioc_quality"]
    if not eligible:
        return (0.0, 0.0)  # excluded from denominator, not penalized
    iocs = item.get("iocs") or []
    if not iocs:
        return (0.0, max_pts)
    pts = max_pts * 0.5
    if len(iocs) >= 3:
        pts += max_pts * 0.25
    if any(isinstance(i, dict) and "confidence" in i for i in iocs):
        pts += max_pts * 0.25
    return (round(min(pts, max_pts), 2), max_pts)


def _score_attck_quality(item: Dict, eligible: bool) -> Tuple[float, float]:
    max_pts = DIMENSION_WEIGHTS["attck_quality"]
    if not eligible:
        return (0.0, 0.0)
    current = item.get("attck_technique_ids") or item.get("attck_techniques") or []
    legacy = item.get("mitre_tactics") or item.get("ttps") or []
    if current:
        n = len(current)
        pts = max_pts * (1.0 if n >= 3 else 0.7 if n >= 2 else 0.5)
    elif legacy:
        n = len(legacy)
        pts = max_pts * 0.5 * (1.0 if n >= 3 else 0.7 if n >= 2 else 0.5)  # legacy-field discount
    else:
        pts = 0.0
    return (round(min(pts, max_pts), 2), max_pts)


def _score_detection_value(item: Dict, eligible: bool) -> Tuple[float, float]:
    max_pts = DIMENSION_WEIGHTS["detection_value"]
    if not eligible:
        return (0.0, 0.0)
    sigma = item.get("sigma_rule") or ""
    kql = item.get("kql_query") or ""
    suricata = item.get("suricata_rule") or ""
    n_present = sum(1 for x in (sigma, kql, suricata) if isinstance(x, str) and len(x) > 100)
    pts = max_pts * (n_present / 3)
    return (round(min(pts, max_pts), 2), max_pts)


def _score_mitigation_response(item: Dict, report_type: str) -> float:
    max_pts = DIMENSION_WEIGHTS["mitigation_response"]
    if report_type == "NEWS":
        return round(max_pts * 0.5, 2)
    pts = 0.0
    if item.get("recommended_sla_action"):
        pts += max_pts * 0.6
    if item.get("sla_priority"):
        pts += max_pts * 0.4
    return round(min(pts, max_pts), 2)


def _score_confidence_uncertainty(item: Dict) -> float:
    max_pts = DIMENSION_WEIGHTS["confidence_uncertainty"]
    pts = 0.0
    if item.get("confidence") is not None or item.get("confidence_label"):
        pts += max_pts * 0.6
    if item.get("confidence_rationale"):
        pts += max_pts * 0.4
    return round(min(pts, max_pts), 2)


def _score_readability(item: Dict, vr) -> float:
    max_pts = DIMENSION_WEIGHTS["readability_presentation"]
    score = max_pts
    for v in vr.violations:
        if v.code in ("BROKEN_MARKDOWN", "TRUNCATED_CONTENT", "GENERIC_FILLER"):
            score -= max_pts * 0.4
    return round(max(0.0, score), 2)


def _score_machine_readable_consistency(item: Dict) -> float:
    max_pts = DIMENSION_WEIGHTS["machine_readable_consistency"]
    score = max_pts
    ioc_count_field = item.get("ioc_count")
    real_ioc_len = len(item.get("iocs") or [])
    if ioc_count_field is not None and int(ioc_count_field or 0) != real_ioc_len:
        score -= max_pts * 0.5
    indicator_count = item.get("indicator_count")
    if indicator_count is not None and ioc_count_field is not None and int(indicator_count) != int(ioc_count_field or 0):
        score -= max_pts * 0.5
    return round(max(0.0, score), 2)


def score_item(item: Dict) -> Dict:
    """Returns {"total": float, "max_total": float, "pct": float,
    "dimensions": {name: {"score": x, "max": y}}, "report_type": str}."""
    vr = validate_intelligence_content(item)
    report_type = vr.report_type
    contract = contract_for_item(item)
    na_fields = {f.field for f in contract.fields if f.level == NOT_APPLICABLE}

    dims: Dict[str, Dict[str, float]] = {}

    dims["intelligence_integrity"] = {"score": _score_intelligence_integrity(item, vr), "max": DIMENSION_WEIGHTS["intelligence_integrity"]}
    dims["evidence_provenance"]    = {"score": _score_evidence_provenance(item), "max": DIMENSION_WEIGHTS["evidence_provenance"]}
    dims["technical_depth"]        = {"score": _score_technical_depth(item, report_type), "max": DIMENSION_WEIGHTS["technical_depth"]}
    dims["executive_usefulness"]   = {"score": _score_executive_usefulness(item), "max": DIMENSION_WEIGHTS["executive_usefulness"]}
    dims["soc_actionability"]      = {"score": _score_soc_actionability(item, report_type), "max": DIMENSION_WEIGHTS["soc_actionability"]}

    ioc_score, ioc_max = _score_ioc_quality(item, is_ioc_eligible(item) and "iocs" not in na_fields)
    dims["ioc_quality"] = {"score": ioc_score, "max": ioc_max}

    attck_score, attck_max = _score_attck_quality(item, attck_eligible(item) and "attck_technique_ids" not in na_fields)
    dims["attck_quality"] = {"score": attck_score, "max": attck_max}

    det_score, det_max = _score_detection_value(item, is_detection_eligible(item) and "detection_rules_total" not in na_fields)
    dims["detection_value"] = {"score": det_score, "max": det_max}

    dims["mitigation_response"]          = {"score": _score_mitigation_response(item, report_type), "max": DIMENSION_WEIGHTS["mitigation_response"]}
    dims["confidence_uncertainty"]       = {"score": _score_confidence_uncertainty(item), "max": DIMENSION_WEIGHTS["confidence_uncertainty"]}
    dims["readability_presentation"]     = {"score": _score_readability(item, vr), "max": DIMENSION_WEIGHTS["readability_presentation"]}
    dims["machine_readable_consistency"] = {"score": _score_machine_readable_consistency(item), "max": DIMENSION_WEIGHTS["machine_readable_consistency"]}

    total = sum(d["score"] for d in dims.values())
    max_total = sum(d["max"] for d in dims.values())
    pct = round(total / max_total * 100, 1) if max_total else 0.0

    return {
        "item_id": item.get("id"),
        "title": str(item.get("title", ""))[:80],
        "report_type": report_type,
        "total": round(total, 2),
        "max_total": round(max_total, 2),
        "pct": pct,
        "dimensions": dims,
        "content_severity": vr.severity,
    }
