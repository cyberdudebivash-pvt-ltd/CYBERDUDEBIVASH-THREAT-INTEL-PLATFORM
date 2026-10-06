#!/usr/bin/env python3
"""
scripts/commercial_quality_orchestrator.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Commercial Quality Orchestrator (Python composition layer)
Project TITAN Stage 20A -- Enterprise Commercial Quality Orchestrator
=====================================================================

Approved by: COMMERCIAL_QUALITY_GOVERNANCE_AUDIT.md +
             COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md (PR #131, merged to main)

ARCHITECTURE NOTE -- independent of the JS-side orchestrator:
  This script is the Python-runtime half of the two-runtime Commercial
  Quality Orchestrator design (architecture doc Sec 0 point 5). It shares
  ZERO code with workers/intel-gateway/src/p39-handlers.js -- the platform's
  confirmed, pre-existing zero-shared-code boundary between the live JS
  Cloudflare Worker and the batch Python CI pipeline is preserved exactly,
  not bridged. Each runtime reads only its own runtime's already-computed
  outputs.

DESIGN PRINCIPLE (architecture doc Sec 0): this script COMPOSES. It never
computes what an existing engine already computes, and it NEVER modifies
scripts/commercial_readiness_governor.py or agent/dossier_quality_engine.py
-- both are read-only inputs, their own already-written report files loaded
and cited verbatim. The only genuinely new computation in this file is
compute_commercial_applicability() (architecture doc Sec 5).

Reads (read-only, never mutated by this script):
  api/feed.json                                          -- governed feed (commercial_readiness_governor.py output)
  data/health/commercial_readiness_governor_report.json  -- feed-level GO-LIVE / commercial_readiness_score
  data/quality/dossier_quality_report.json               -- feed-level dossier quality grades (if present)
  data/quality/p33_certification_report.json             -- platform release-gate tier (context only, not counted -- Sec 2)

Writes:
  data/quality/commercial_quality_orchestrator_report.json

7 exported composition functions (the 7 components the approved architecture
authorizes -- mirrors p39-handlers.js's export list exactly, independent code):
  compute_commercial_applicability      - Applicability Engine (Sec 5; the one new computation)
  build_commercial_quality_view         - Commercial Quality Orchestrator (Sec 1-2)
  build_commercial_readiness_summary    - Commercial Readiness Summary
  build_commercial_publication_decision - Commercial Publication Decision (Sec 3; cites only, never decides)
  build_commercial_explanation          - Commercial Explanation Engine (Sec 6)
  build_commercial_recommendation_layer - Commercial Recommendation Layer (Sec 7)
  build_commercial_release_decision     - Commercial Release Decision (final packaged view)

Never raises on malformed input; never fabricates evidence -- fields this
script cannot obtain from an existing engine's real output are reported as
UNKNOWN / not available, never defaulted to a value that looks like a real
citation.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT   = Path(__file__).resolve().parent.parent
_DATA   = _ROOT / "data"
_API    = _ROOT / "api"
_QUAL   = _DATA / "quality"
_HEALTH = _DATA / "health"

_FEED_PATH       = _API / "feed.json"
_GOVERNOR_REPORT = _HEALTH / "commercial_readiness_governor_report.json"
_DOSSIER_REPORT  = _QUAL / "dossier_quality_report.json"
_P33_CERT_REPORT = _QUAL / "p33_certification_report.json"
_OUT_REPORT      = _QUAL / "commercial_quality_orchestrator_report.json"

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

DETECTION_FORMATS = {
    "sigma": "sigma_rule", "kql": "kql_query", "spl": "spl_query",
    "suricata": "suricata_rule", "yara": "yara_rule",
    "elastic": "elastic_rule", "snort": "snort_rule",
}


def _load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _has_cve(item: Dict) -> bool:
    if item.get("cve_id"):
        return True
    cve_ids = item.get("cve_ids")
    if isinstance(cve_ids, list) and cve_ids:
        return True
    return bool(re.match(r"^CVE-", str(item.get("id", "")), re.IGNORECASE))


def _has_behavioral_evidence(item: Dict) -> bool:
    """Signals that this item describes observed/inferred adversary BEHAVIOR,
    not a bare vulnerability disclosure (architecture doc Sec 5.2)."""
    if str(item.get("actor_tag", "")).strip():
        return True
    if item.get("active_exploit") or item.get("exploit_maturity"):
        return True
    if item.get("kev_present") or item.get("kev"):
        return True
    if isinstance(item.get("exploit_refs"), list) and item.get("exploit_refs"):
        return True
    try:
        if int(item.get("poc_github_count") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    if item.get("metasploit_available"):
        return True
    if isinstance(item.get("kill_chain_phases"), list) and item.get("kill_chain_phases"):
        return True
    threat_type = item.get("threat_type")
    if threat_type and not re.match(r"^(vulnerability|patch|advisory)$", str(threat_type), re.IGNORECASE):
        return True
    return False


def _days_since(date_str: Optional[str]) -> Optional[float]:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Commercial Applicability Engine (Sec 5) -- the one genuinely new computation
# ---------------------------------------------------------------------------

def compute_commercial_applicability(item: Dict) -> Dict:
    """
    Applicability Engine (architecture doc Sec 5) -- independent Python
    implementation, zero shared code with p39-handlers.js's JS version.
    Same four-state model (APPLICABLE / NOT_APPLICABLE / UNKNOWN / whole-item
    EXCLUDED), same five named dimensions from Sec 5.2's worked-example
    table, same Sec 5.3 denominator rule: NOT_APPLICABLE dimensions are
    excluded from both numerator and denominator, never scored as a failure.
    """
    if not isinstance(item, dict) or not item.get("id"):
        return {
            "excluded": True,
            "reason": "Unsupported report type -- item missing minimum identity fields (id).",
            "dimensions": {},
            "summary": {"applicable": 0, "not_applicable": 0, "unknown": 0, "passed": 0, "failed": 0},
        }

    has_cve = _has_cve(item)
    has_behavior = _has_behavioral_evidence(item)
    dims: Dict[str, Any] = {}

    # --- MITRE ATT&CK mapping ---
    # Requires a non-empty LIST specifically (matching p39-handlers.js's
    # Array.isArray(...) && .length > 0 check) -- a bare truthy check would
    # let a malformed scalar/string value pass here in Python while the same
    # item fails this check in JS, breaking the "same conceptual model,
    # independently coded" guarantee both runtimes are supposed to honor.
    has_mitre = any(
        isinstance(item.get(field), list) and len(item.get(field)) > 0
        for field in ("mitre_tactics", "ttps", "attck_technique_ids")
    )
    if not has_behavior:
        dims["mitre_attack"] = {
            "status": "NOT_APPLICABLE",
            "rationale": "No observed/inferred adversary behavior signal (no actor_tag, exploit, KEV, or kill-chain data) -- reads as a bare vulnerability disclosure, which has no technique to map.",
        }
    elif has_mitre:
        dims["mitre_attack"] = {"status": "APPLICABLE", "result": "PASS", "rationale": "Behavioral evidence present and MITRE ATT&CK mapping populated."}
    else:
        dims["mitre_attack"] = {"status": "APPLICABLE", "result": "FAIL", "rationale": "Behavioral evidence present (actor/exploit/KEV/kill-chain) but no MITRE ATT&CK mapping recorded -- a real gap, not inapplicable."}

    # --- EPSS score ---
    if not has_cve:
        dims["epss"] = {"status": "NOT_APPLICABLE", "rationale": "Item carries no CVE identifier -- EPSS is CVE-scoped and cannot apply."}
    else:
        epss_val = item.get("epss_score")
        has_epss = epss_val is not None and epss_val != ""
        if has_epss:
            dims["epss"] = {"status": "APPLICABLE", "result": "PASS", "rationale": f"EPSS score present ({epss_val})."}
        else:
            age = _days_since(item.get("nvd_disclosure") or item.get("published_at") or item.get("timestamp"))
            if age is not None and age < 3:
                dims["epss"] = {"status": "UNKNOWN", "rationale": f"CVE disclosed {age:.1f}d ago -- EPSS has a real publication lag; too early to call this a gap (Sec 5.2)."}
            else:
                dims["epss"] = {"status": "APPLICABLE", "result": "FAIL", "rationale": "CVE-bearing item with no EPSS score and sufficient age for one to plausibly exist."}

    # --- KEV listing -- "should almost never be NOT_APPLICABLE" (Sec 5.2) ---
    if not has_cve:
        dims["kev"] = {"status": "NOT_APPLICABLE", "rationale": "Item carries no CVE identifier -- KEV is CVE-scoped."}
    else:
        kev_val = bool(item.get("kev_present") or item.get("kev"))
        dims["kev"] = {
            "status": "APPLICABLE", "result": "PASS",
            "rationale": "Listed on CISA KEV." if kev_val else "Not on CISA KEV -- itself a meaningful, scoreable signal per Sec 5.2, not a gap.",
        }

    # --- IOC presence ---
    threat_type = item.get("threat_type")
    policy_only = bool(threat_type) and bool(re.match(r"^(policy|compliance|advisory-only)$", str(threat_type), re.IGNORECASE))
    if policy_only:
        dims["ioc_presence"] = {"status": "NOT_APPLICABLE", "rationale": "Pure policy/compliance advisory -- not the kind of item that plausibly carries IOCs."}
    else:
        iocs = item.get("iocs")
        raw_cnt = item.get("ioc_count") or (len(iocs) if isinstance(iocs, list) else 0) or 0
        try:
            # A malformed feed value (non-numeric string, dict, list) must
            # never raise here -- this function's contract (see module
            # docstring) is "never raises on malformed input," and one bad
            # item must not abort an entire run_orchestration() batch.
            ioc_cnt = int(float(raw_cnt))
        except (TypeError, ValueError):
            ioc_cnt = 0
        if ioc_cnt > 0:
            dims["ioc_presence"] = {"status": "APPLICABLE", "result": "PASS", "rationale": f"{ioc_cnt} IOC(s) present."}
        else:
            dims["ioc_presence"] = {"status": "APPLICABLE", "result": "FAIL", "rationale": "Item type plausibly carries IOCs but none are present."}

    # --- Detection rule coverage, per format ---
    # Absence alone does not prove inapplicability (Sec 5.2). Without confirmed
    # producing-pipeline metadata on the item itself, an absent format is
    # honestly UNKNOWN -- never a guessed NOT_APPLICABLE and never a false FAIL.
    coverage: Dict[str, Any] = {}
    for fmt, field in DETECTION_FORMATS.items():
        if item.get(field):
            coverage[fmt] = {"status": "APPLICABLE", "result": "PASS", "rationale": f"{field} present."}
        else:
            coverage[fmt] = {"status": "UNKNOWN", "rationale": f"{field} absent; producing pipeline's by-design format set is not determinable from this item alone (Sec 5.5)."}
    dims["detection_coverage"] = coverage

    flat: List[Dict] = []
    for key, val in dims.items():
        if key == "detection_coverage":
            flat.extend(val.values())
        else:
            flat.append(val)

    summary = {
        "applicable":     sum(1 for d in flat if d["status"] == "APPLICABLE"),
        "not_applicable": sum(1 for d in flat if d["status"] == "NOT_APPLICABLE"),
        "unknown":        sum(1 for d in flat if d["status"] == "UNKNOWN"),
        "passed":         sum(1 for d in flat if d["status"] == "APPLICABLE" and d.get("result") == "PASS"),
        "failed":         sum(1 for d in flat if d["status"] == "APPLICABLE" and d.get("result") == "FAIL"),
    }
    return {"excluded": False, "dimensions": dims, "summary": summary}


def _applicability_adjusted_composite(applicability: Dict) -> Optional[int]:
    """Sec 5.3: composite = (sum of scores for applicable D) / (count of
    applicable D) -- NOT_APPLICABLE dimensions never enter numerator or
    denominator."""
    if not applicability or applicability.get("excluded"):
        return None
    numerator = 0
    denominator = 0
    for key, val in applicability.get("dimensions", {}).items():
        entries = val.values() if key == "detection_coverage" else [val]
        for d in entries:
            if d["status"] == "APPLICABLE":
                denominator += 1
                if d.get("result") == "PASS":
                    numerator += 1
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100)


# ---------------------------------------------------------------------------
# Commercial Quality Orchestrator (Sec 1-2) -- reads existing outputs only
# ---------------------------------------------------------------------------

def build_commercial_quality_view(item: Dict, context: Optional[Dict] = None) -> Dict:
    """
    Commercial Quality Orchestrator. Composes commercial_readiness_governor.py's
    and dossier_quality_engine.py's already-written outputs (read from their
    own report files, never recomputed) plus the Applicability Model.
    `context` (optional) carries pre-loaded feed-level report dicts -- see
    load_composition_context(). Never fabricates a citation this script
    cannot actually source.
    """
    context = context or {}
    applicability = compute_commercial_applicability(item)
    inputs_cited: List[Dict] = []

    governor_report = context.get("governor_report")
    if governor_report:
        go_live = governor_report.get("go_live", governor_report)
        inputs_cited.append({
            "source": "commercial_readiness_governor.py (data/health/commercial_readiness_governor_report.json)",
            "value": f"commercial_readiness_score={go_live.get('commercial_readiness_score')}, dashboard_status={go_live.get('dashboard_status')}",
            "kind": "feed_level_go_live",
        })
    else:
        inputs_cited.append({"source": "commercial_readiness_governor.py", "error": "report not found -- governor has not been run on this snapshot"})

    dossier_report = context.get("dossier_report")
    if dossier_report:
        inputs_cited.append({
            "source": "agent/dossier_quality_engine.py (data/quality/dossier_quality_report.json)",
            "value": f"platform_quality_tier={dossier_report.get('platform_quality_tier')}, grade_dist=A:{dossier_report.get('grade_a')} B:{dossier_report.get('grade_b')} C:{dossier_report.get('grade_c')} F:{dossier_report.get('grade_f')}",
            "kind": "feed_level_dossier_quality",
        })
    else:
        inputs_cited.append({"source": "agent/dossier_quality_engine.py", "error": "report not found -- dossier_quality_report.json not present in this snapshot (informational engine; not every pipeline run persists a feed-level report)"})

    p33_report = context.get("p33_report")
    if p33_report:
        inputs_cited.append({
            "source": "scripts/p33_production_certification.py (data/quality/p33_certification_report.json)",
            "value": f"release_tier={p33_report.get('release_tier')}",
            "kind": "platform_wide_gate_context_only",
            "note": "A different kind of signal (platform-wide release gate, not item-level commercial quality) -- shown for context, never counted toward the applicability-adjusted composite (Architecture Sec 2).",
        })

    publication_decision = item.get("publication_decision")
    inputs_cited.append({
        "source": "commercial_readiness_governor.py (item field)",
        "value": publication_decision if publication_decision else None,
        "kind": "item_publication_decision",
        "status": "CITED" if publication_decision else "UNKNOWN -- field not present on this item; never fabricated.",
    })

    applicability_composite = _applicability_adjusted_composite(applicability)

    positive_signals: List[str] = []
    if governor_report:
        go_live = governor_report.get("go_live", governor_report)
        if go_live.get("dashboard_status") == "GO":
            positive_signals.append("commercial_readiness_governor")
    if applicability_composite is not None and applicability_composite >= 75:
        positive_signals.append("Applicability Model")
    if publication_decision in ("ALLOW", "ALLOW_WITH_WARNING"):
        positive_signals.append("publication_decision")

    return {
        "schema_version": "commercial_quality_orchestrator.1",
        "item_id": item.get("id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs_cited": inputs_cited,
        "applicability": applicability,
        "applicability_adjusted_composite": applicability_composite,
        "agreement_summary": {
            "systems_evaluated": sum(1 for c in inputs_cited if "error" not in c),
            "positive_signals": positive_signals,
            "agreement_count": len(positive_signals),
            "note": "Full citation, not arbitration -- disagreement between systems is surfaced, never resolved by this layer (Architecture Sec 2).",
        },
        "engines_reused": ["commercial_readiness_governor.py", "agent/dossier_quality_engine.py", "scripts/p33_production_certification.py"],
    }


# ---------------------------------------------------------------------------
# Commercial Readiness Summary
# ---------------------------------------------------------------------------

def build_commercial_readiness_summary(view: Dict) -> Dict:
    applicability = view.get("applicability", {})
    summary = applicability.get("summary", {})
    missing_evidence: List[str] = []
    for key, val in applicability.get("dimensions", {}).items():
        entries = val.items() if key == "detection_coverage" else [(key, val)]
        for name, d in entries:
            if d.get("status") == "UNKNOWN":
                missing_evidence.append(f"detection_coverage.{name}" if key == "detection_coverage" else name)
    return {
        "schema_version": "commercial_quality_orchestrator.1",
        "item_id": view.get("item_id"),
        "applicable_gates": summary.get("applicable", 0),
        "non_applicable_gates": summary.get("not_applicable", 0),
        "unknown_gates": summary.get("unknown", 0),
        "passed_applicable_gates": summary.get("passed", 0),
        "failed_applicable_gates": summary.get("failed", 0),
        "applicability_adjusted_composite": view.get("applicability_adjusted_composite"),
        "zero_applicable_failures": summary.get("failed", 0) == 0 and summary.get("applicable", 0) > 0,
        "missing_evidence": missing_evidence,
    }


# ---------------------------------------------------------------------------
# Commercial Publication Decision -- cites only, never decides (Sec 3)
# ---------------------------------------------------------------------------

def build_commercial_publication_decision(item: Dict, view: Optional[Dict] = None) -> Dict:
    """
    Publication BLOCK/QUARANTINE/PUBLISH is owned exclusively by
    enforce_publication_decision() in commercial_readiness_governor.py. This
    function never decides -- it cites that engine's own item-level field
    verbatim, and is honest (UNKNOWN) when the field is absent.
    """
    decision = item.get("publication_decision")
    return {
        "schema_version": "commercial_quality_orchestrator.1",
        "item_id": (view.get("item_id") if view else item.get("id")),
        "publication_decision_citation": decision,
        "source": "commercial_readiness_governor.py:enforce_publication_decision() (cited verbatim)" if decision else None,
        "status": "CITED" if decision else "UNKNOWN -- not present on this item; never fabricated.",
        "governance_note": "This function is a downstream reader only. It never overrides or re-decides publication (Architecture Sec 3).",
    }


# ---------------------------------------------------------------------------
# Commercial Explanation Engine (Sec 6 -- Explainability Flow)
# ---------------------------------------------------------------------------

def build_commercial_explanation(view: Dict) -> Dict:
    readiness = build_commercial_readiness_summary(view)
    agreement = view.get("agreement_summary", {})
    lines = [f"{agreement.get('systems_evaluated', 0)} system(s) evaluated this item."]
    if agreement.get("positive_signals"):
        lines.append(f"{len(agreement['positive_signals'])} agree on a positive commercial signal: {', '.join(agreement['positive_signals'])}.")
    lines.append(
        f"{readiness['applicable_gates']} applicable gate(s); {readiness['non_applicable_gates']} not applicable "
        f"for this item type (excluded from scoring, not penalized); {readiness['unknown_gates']} unknown/pending."
    )
    lines.append(f"{readiness['failed_applicable_gates']} applicable gate(s) failed.")
    if view.get("applicability_adjusted_composite") is not None:
        lines.append(f"Applicability-adjusted composite: {view['applicability_adjusted_composite']}/100.")
    return {
        "schema_version": "commercial_quality_orchestrator.1",
        "item_id": view.get("item_id"),
        "narrative": " ".join(lines),
        "citations": view.get("inputs_cited", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Commercial Recommendation Layer (Sec 7 -- presentation-only 9th tier)
# ---------------------------------------------------------------------------

_RECOMMENDATION_TIERS = [
    (98, "PREMIUM_INTELLIGENCE", "Premium Intelligence"),
    (90, "COMMERCIAL_CERTIFIED", "Commercial Certified"),
    (75, "ENTERPRISE_READY", "Enterprise Ready"),
    (60, "ANALYST_REVIEW", "Analyst Review"),
    (0,  "INTERNAL_DRAFT", "Internal Draft"),
]


def build_commercial_recommendation_layer(view: Dict) -> Dict:
    readiness = build_commercial_readiness_summary(view)
    composite = view.get("applicability_adjusted_composite")
    tier_id, tier_label = "INTERNAL_DRAFT", "Internal Draft"
    if composite is not None:
        for threshold, tid, tlabel in _RECOMMENDATION_TIERS:
            if composite >= threshold:
                tier_id, tier_label = tid, tlabel
                break
    # Premium Intelligence additionally requires zero applicable failures
    # (Architecture Sec 7's qualifying language, structurally satisfied by
    # the Applicability Model rather than any extra logic).
    if tier_id == "PREMIUM_INTELLIGENCE" and not readiness["zero_applicable_failures"]:
        tier_id, tier_label = "COMMERCIAL_CERTIFIED", "Commercial Certified"
    return {
        "schema_version": "commercial_quality_orchestrator.1",
        "item_id": view.get("item_id"),
        "tier": tier_id,
        "tier_label": tier_label,
        "composite_used": composite,
        "presentation_only": True,
        "non_authoritative_note": "A 9th, clearly-labeled, presentation-only tier -- never replaces or outranks existing tier outputs (Architecture Sec 7).",
        "explainability_trace": build_commercial_explanation(view),
    }


# ---------------------------------------------------------------------------
# Commercial Release Decision -- final packaged view
# ---------------------------------------------------------------------------

def build_commercial_release_decision(view: Dict, publication: Optional[Dict] = None) -> Dict:
    recommendation = build_commercial_recommendation_layer(view)
    return {
        "schema_version": "commercial_quality_orchestrator.1",
        "item_id": view.get("item_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recommendation_tier": recommendation["tier"],
        "recommendation_label": recommendation["tier_label"],
        "publication_decision": publication,
        "readiness_summary": build_commercial_readiness_summary(view),
        "explanation": recommendation["explainability_trace"],
        "governance_note": "Composed view only. Never overrides commercial_readiness_governor.py, dossier_quality_engine.py, or p33_production_certification.py (Architecture Sec 0-3).",
    }


# ---------------------------------------------------------------------------
# Feed-wide orchestration run
# ---------------------------------------------------------------------------

def load_composition_context() -> Dict:
    """Loads the already-written report files this orchestrator composes
    from. Missing files are reported as None, never fabricated."""
    return {
        "governor_report": _load_json(_GOVERNOR_REPORT),
        "dossier_report":  _load_json(_DOSSIER_REPORT),
        "p33_report":      _load_json(_P33_CERT_REPORT),
    }


def run_orchestration(items: Optional[List[Dict]] = None) -> Dict:
    """Feed-wide orchestration run. Loads api/feed.json (the governed,
    commercial-relevant feed) unless items are supplied, composes a view per
    item, and aggregates into a feed-level Commercial Quality Summary."""
    context = load_composition_context()
    if items is None:
        items = _load_json(_FEED_PATH) or []

    per_item_views = []
    for item in items:
        if not isinstance(item, dict):
            continue
        view = build_commercial_quality_view(item, context)
        readiness = build_commercial_readiness_summary(view)
        recommendation = build_commercial_recommendation_layer(view)
        per_item_views.append({
            "item_id": view["item_id"],
            "applicability_adjusted_composite": view["applicability_adjusted_composite"],
            "zero_applicable_failures": readiness["zero_applicable_failures"],
            "recommendation_tier": recommendation["tier"],
        })

    n = len(per_item_views)
    tier_dist: Dict[str, int] = {}
    for v in per_item_views:
        tier_dist[v["recommendation_tier"]] = tier_dist.get(v["recommendation_tier"], 0) + 1
    composites = [v["applicability_adjusted_composite"] for v in per_item_views if v["applicability_adjusted_composite"] is not None]
    avg_composite = round(sum(composites) / len(composites), 1) if composites else None

    report = {
        "schema_version": "commercial_quality_orchestrator.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "orchestrator_version": "1.0.0",
        "runtime": "python",
        "governance_note": "Read-only composition layer. Never modifies commercial_readiness_governor.py, agent/dossier_quality_engine.py, scripts/p33_production_certification.py, or any P20-P37 JS engine. Zero shared code with workers/intel-gateway/src/p39-handlers.js (the JS-runtime counterpart).",
        "feed_items_evaluated": n,
        "average_applicability_adjusted_composite": avg_composite,
        "recommendation_tier_distribution": tier_dist,
        "items_with_zero_applicable_failures": sum(1 for v in per_item_views if v["zero_applicable_failures"]),
        "context_sources": {
            "governor_report_available": context["governor_report"] is not None,
            "dossier_report_available": context["dossier_report"] is not None,
            "p33_report_available": context["p33_report"] is not None,
        },
        "per_item_summary": per_item_views[:200],
    }

    if not DRY_RUN:
        _QUAL.mkdir(parents=True, exist_ok=True)
        _OUT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> int:
    print("=" * 70)
    print("CYBERDUDEBIVASH(R) SENTINEL APEX -- Commercial Quality Orchestrator")
    print("Project TITAN Stage 20A (Python composition layer)")
    print("=" * 70)

    report = run_orchestration()

    print(f"  Feed items evaluated       : {report['feed_items_evaluated']}")
    print(f"  Avg applicability composite: {report['average_applicability_adjusted_composite']}")
    print(f"  Recommendation tiers       : {report['recommendation_tier_distribution']}")
    print(f"  Zero-applicable-failure    : {report['items_with_zero_applicable_failures']}/{report['feed_items_evaluated']}")
    print(f"  Governor report available  : {report['context_sources']['governor_report_available']}")
    print(f"  Dossier report available   : {report['context_sources']['dossier_report_available']}")
    print(f"  P33 report available       : {report['context_sources']['p33_report_available']}")
    print()
    if not DRY_RUN:
        print(f"  Report: {_OUT_REPORT}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
