#!/usr/bin/env python3
"""
scripts/p40_production_certification.py
P40.0 Production Certification — Global Intelligence Source Fabric

Chains from p38_certification_report.json (P39 is deliberately unwired/
internal-only per its own file header and has no certification report to
chain from — this mirrors how P34 chained from P33 when an intermediate
layer's report was unavailable).

22 gates covering:
  G01-G03: Certification chain (P38)
  G04-G07: Source registry integrity (existence, honesty-contract validation,
           scale, domain breadth)
  G08-G11: Source health observability
  G12-G13: Live pipeline extension (new adapters + verified URLhaus fix present)
  G14-G18: Worker handler layer + wiring + R2 bridge
  G19:     MITRE ATT&CK reference sync sanity
  G20:     Documentation completeness
  G21:     Licensing governance coherence (permanent regression guard for the
           commercial_use_allowed bug found and fixed during this change)
  G22:     Source health dashboard existence

Reuses scripts/p38_shared_validators.py:gate()/load_json_safe() (its own
docstring: "New P-layer cert scripts MUST call this function") and
scripts/source_registry.py:load_registry()/validate_registry()/
licensing_summary() — zero gate logic re-implemented from scratch that
already exists elsewhere.

Result written to data/quality/p40_certification_report.json.
"""
from __future__ import annotations
import datetime
import json
import pathlib
import sys

ROOT   = pathlib.Path(__file__).resolve().parent.parent
DATA_Q = ROOT / "data" / "quality"
SRC_P  = ROOT / "workers" / "intel-gateway" / "src"

sys.path.insert(0, str(ROOT / "scripts"))

try:
    from p38_shared_validators import gate as _gate, load_json_safe
    _SHARED_IMPORT_OK = True
    _SHARED_IMPORT_ERROR = ""
except ImportError as _e:
    _SHARED_IMPORT_OK = False
    _SHARED_IMPORT_ERROR = str(_e)

    def _gate(gate_id, label, severity, status, detail):
        return {
            "gate_id": gate_id, "label": label, "severity": severity,
            "status": "PASS" if status else ("FAIL_BLOCKER" if severity == "BLOCKER" else "FAIL_WARNING"),
            "detail": detail,
        }

    def load_json_safe(path):
        try:
            return json.loads(path.read_bytes())
        except Exception:
            return None

try:
    from source_registry import load_registry, validate_registry, licensing_summary
    _REGISTRY_IMPORT_OK = True
    _REGISTRY_IMPORT_ERROR = ""
except ImportError as _e:
    _REGISTRY_IMPORT_OK = False
    _REGISTRY_IMPORT_ERROR = str(_e)


def run_certification() -> dict:
    gates: list = []

    # ── G01-G03: Certification chain ─────────────────────────────────────────
    p38 = load_json_safe(DATA_Q / "p38_certification_report.json")
    g01 = p38 is not None and isinstance(p38, dict)
    gates.append(_gate("G01", "P38 certification report present", "BLOCKER", g01,
                        f"tier={p38.get('release_tier','?')} blockers={p38.get('blocker_count','?')}" if g01 else "NOT FOUND"))

    p38_tier_ok = g01 and p38.get("release_tier") == "WORLDWIDE_RELEASE"
    gates.append(_gate("G02", "P38 release tier = WORLDWIDE_RELEASE", "BLOCKER", p38_tier_ok,
                        p38.get("release_tier", "?") if g01 else "N/A"))

    p38_blockers_ok = g01 and p38.get("blocker_count", 1) == 0
    gates.append(_gate("G03", "P38 has zero blockers", "BLOCKER", p38_blockers_ok,
                        f"blockers={p38.get('blocker_count','?')}" if g01 else "N/A"))

    # ── G04-G07: Source registry integrity ───────────────────────────────────
    g04 = _REGISTRY_IMPORT_OK
    gates.append(_gate("G04", "scripts/source_registry.py imports successfully", "BLOCKER", g04,
                        "OK" if g04 else f"IMPORT ERROR: {_REGISTRY_IMPORT_ERROR}"))

    registry = None
    if g04:
        try:
            registry = load_registry(force_reload=True)
        except FileNotFoundError as e:
            registry = None
            g04_load_error = str(e)
    g04b = registry is not None
    gates.append(_gate("G04B", "data/registry/source_registry.json loads", "BLOCKER", g04b,
                        f"total_sources={registry.get('total_sources')}" if g04b else "NOT FOUND — run scripts/build_source_registry.py"))

    validation_errors = validate_registry(registry) if (g04 and registry) else ["registry unavailable"]
    g05 = len(validation_errors) == 0
    gates.append(_gate(
        "G05", "Source registry passes honesty-contract + integrity validation", "BLOCKER", g05,
        "0 errors" if g05 else f"{len(validation_errors)} error(s): {validation_errors[:5]}",
    ))

    total_sources = registry.get("total_sources", 0) if registry else 0
    g06 = total_sources >= 90
    gates.append(_gate("G06", "Source registry covers >= 90 sources (global taxonomy breadth)", "BLOCKER", g06,
                        f"total_sources={total_sources}"))

    waves_present = set(registry.get("wave_breakdown", {}).keys()) if registry else set()
    g07 = waves_present == {"1", "2", "3", "4", "5"}
    gates.append(_gate("G07", "All 5 mission waves represented in registry", "BLOCKER", g07,
                        f"waves_present={sorted(waves_present)}"))

    active_count = (registry.get("status_breakdown", {}).get("ACTIVE", 0)) if registry else 0
    g07b = active_count >= 1
    gates.append(_gate("G07B", "At least 1 source is genuinely ACTIVE (not all scaffolding)", "BLOCKER", g07b,
                        f"active_count={active_count}"))

    # ── G08-G11: Source health observability ─────────────────────────────────
    health = load_json_safe(DATA_Q / "source_fabric_health.json")
    g08 = health is not None
    gates.append(_gate("G08", "data/quality/source_fabric_health.json present", "BLOCKER", g08,
                        f"sources={health.get('total_sources')}" if g08 else "NOT FOUND — run scripts/source_fabric_health.py"))

    g09 = g08 and g04b and health.get("total_sources") == registry.get("total_sources")
    gates.append(_gate("G09", "Health report source count matches registry (not stale)", "BLOCKER", g09,
                        f"health={health.get('total_sources') if g08 else '?'} registry={total_sources}"))

    healthy_count = health.get("health_breakdown", {}).get("HEALTHY", 0) if g08 else 0
    g10 = healthy_count >= 1
    gates.append(_gate("G10", "At least 1 source reports HEALTHY (pipeline genuinely alive)", "BLOCKER", g10,
                        f"healthy_count={healthy_count}"))

    no_data_count = health.get("health_breakdown", {}).get("NO_DATA", 0) if g08 else 0
    g11 = no_data_count <= 3
    gates.append(_gate(
        "G11", "ACTIVE sources with zero observed output stay bounded (<=3)", "WARNING", g11,
        f"no_data_count={no_data_count} — expected to include openphish/first_epss until the next "
        f"scheduled multi-source-intel.yml run persists their first real output",
    ))

    # ── G12-G13: Live pipeline extension ─────────────────────────────────────
    ingestor_path = ROOT / "scripts" / "true_intel_ingestor.py"
    g12 = ingestor_path.exists()
    ingestor_src = ingestor_path.read_text(encoding="utf-8") if g12 else ""
    required_fns = ["def ingest_openphish(", "def enrich_with_epss(", "def sync_mitre_attack("]
    missing_fns = [f for f in required_fns if f not in ingestor_src]
    g12b = g12 and not missing_fns
    gates.append(_gate("G12", "true_intel_ingestor.py has all 3 new P40 source functions", "BLOCKER", g12b,
                        "OK" if g12b else f"MISSING: {missing_fns}"))

    g13 = "ABUSECH_AUTH_KEY" in ingestor_src and '"Auth-Key": ABUSECH_AUTH_KEY' in ingestor_src
    gates.append(_gate("G13", "Verified URLhaus Auth-Key regression fix present", "BLOCKER", g13,
                        "OK — Auth-Key header wired from ABUSECH_AUTH_KEY" if g13 else "FIX NOT FOUND in source"))

    # ── G14-G18: Worker handler layer + wiring + R2 bridge ───────────────────
    handler_path = SRC_P / "p40-handlers.js"
    g14 = handler_path.exists()
    gates.append(_gate("G14", "p40-handlers.js exists", "BLOCKER", g14, "found" if g14 else "NOT FOUND"))

    required_exports = [
        "handleP40SourceRegistry", "handleP40SourceDetail", "handleP40SourceHealth",
        "handleP40Licensing", "handleP40Coverage", "handleP40Waves",
        "handleP40Certification", "handleP40Metrics", "handleP40Dashboard",
        "handleP40Observability",
    ]
    if g14:
        handler_src = handler_path.read_text(encoding="utf-8")
        missing_exports = [e for e in required_exports if f"export async function {e}" not in handler_src]
        g15 = len(missing_exports) == 0
        gates.append(_gate("G15", "p40-handlers.js has all 10 required exports", "BLOCKER", g15,
                            "OK" if g15 else f"MISSING: {missing_exports}"))
    else:
        gates.append(_gate("G15", "p40-handlers.js has all 10 required exports", "BLOCKER", False, "handler file missing"))

    index_path = SRC_P / "index.js"
    g16 = index_path.exists()
    index_src = index_path.read_text(encoding="utf-8") if g16 else ""
    g16b = g16 and "from './p40-handlers.js'" in index_src
    gates.append(_gate("G16", "index.js imports p40-handlers.js", "BLOCKER", g16b,
                        "OK" if g16b else "import not found in index.js"))

    required_routes = [f'"/api/v1/p40/{r}"' for r in
                        ["source-registry", "source-detail", "source-health", "licensing",
                         "coverage", "waves", "certification", "metrics", "dashboard", "observability"]]
    missing_routes = [r for r in required_routes if r not in index_src]
    g17 = g16 and not missing_routes
    gates.append(_gate("G17", "index.js registers all 10 P40 routes", "BLOCKER", g17,
                        "OK" if g17 else f"MISSING: {missing_routes}"))

    r2_path = ROOT / "scripts" / "r2_upload.py"
    r2_src = r2_path.read_text(encoding="utf-8") if r2_path.exists() else ""
    g18 = all(k in r2_src for k in ["intel/source_registry.json", "intel/source_fabric_health.json", "intel/p40_certification_report.json"])
    gates.append(_gate("G18", "r2_upload.py bridges all 3 P40 artifacts to R2", "BLOCKER", g18,
                        "OK" if g18 else "one or more P40 R2 keys missing from r2_upload.py"))

    # ── G19: MITRE ATT&CK reference sync sanity ──────────────────────────────
    attck = load_json_safe(ROOT / "data" / "attck" / "enterprise-attack.json")
    g19 = attck is not None and attck.get("counts", {}).get("techniques", 0) >= 500
    gates.append(_gate("G19", "MITRE ATT&CK reference sync has >= 500 techniques", "WARNING", g19,
                        f"techniques={attck.get('counts',{}).get('techniques',0) if attck else 0}"))

    # ── G20: Documentation completeness ──────────────────────────────────────
    doc_files = [
        ROOT / "docs" / "SOURCE_FABRIC_ARCHITECTURE.md",
        ROOT / "docs" / "SOURCE_REGISTRY.md",
        ROOT / "docs" / "SOURCE_ADAPTER_ONBOARDING_GUIDE.md",
        ROOT / "docs" / "SOURCE_LICENSING_MODEL.md",
    ]
    missing_docs = [str(p.relative_to(ROOT)) for p in doc_files if not p.exists()]
    g20 = len(missing_docs) == 0
    gates.append(_gate("G20", "P40 documentation set complete (4 docs)", "WARNING", g20,
                        "OK" if g20 else f"MISSING: {missing_docs}"))

    # ── G21: Licensing governance coherence (permanent regression guard) ────
    g21 = False
    licensing_detail = "registry unavailable"
    if _REGISTRY_IMPORT_OK and registry:
        try:
            lic = licensing_summary()
            free_noncommercial_and_licensed = 0
            for s in registry.get("sources", []):
                if s.get("licensing_class") in ("FREE_NONCOMMERCIAL", "INTERNAL_USE_ONLY") and s.get("commercial_use_allowed"):
                    free_noncommercial_and_licensed += 1
            g21 = free_noncommercial_and_licensed == 0
            licensing_detail = (f"violations={free_noncommercial_and_licensed} "
                                 f"commercial_use_allowed={lic['commercial_use_allowed']}/{lic['total']}")
        except Exception as e:
            licensing_detail = f"error computing licensing_summary: {e}"
    gates.append(_gate(
        "G21", "Zero FREE_NONCOMMERCIAL/INTERNAL_USE_ONLY sources flagged commercially usable",
        "BLOCKER", g21, licensing_detail,
    ))

    # ── G22: Source health dashboard existence ───────────────────────────────
    dashboard_path = ROOT / "dashboard" / "source_fabric_dashboard.html"
    g22 = dashboard_path.exists()
    gates.append(_gate("G22", "Source Fabric Health Dashboard exists", "WARNING", g22,
                        "found" if g22 else "NOT FOUND"))

    # ── Tally ─────────────────────────────────────────────────────────────────
    blockers = sum(1 for g in gates if g["status"] == "FAIL_BLOCKER")
    warnings = sum(1 for g in gates if g["status"] == "FAIL_WARNING")
    passed   = sum(1 for g in gates if g["status"] == "PASS")
    total    = len(gates)
    tier     = "WORLDWIDE_RELEASE" if blockers == 0 else "BLOCKED"

    report = {
        "schema_version":    "p40.0",
        "generated_at":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "layer":             "P40",
        "scope":             "global_intelligence_source_fabric",
        "release_tier":      tier,
        "passed_count":      passed,
        "blocker_count":     blockers,
        "warning_count":     warnings,
        "total_gates":       total,
        "p38_tier":          p38.get("release_tier", "UNKNOWN") if p38 else "UNKNOWN",
        "shared_validators_import_ok": _SHARED_IMPORT_OK,
        "registry_import_ok":          _REGISTRY_IMPORT_OK,
        "source_registry": {
            "total_sources":    total_sources,
            "status_breakdown": registry.get("status_breakdown") if registry else None,
            "wave_breakdown":   registry.get("wave_breakdown") if registry else None,
        },
        "source_health": {
            "health_breakdown": health.get("health_breakdown") if health else None,
        },
        "governance_deliverables": {
            "canonical_source_registry": "data/registry/source_registry.json",
            "registry_generator":        "scripts/build_source_registry.py",
            "registry_loader":           "scripts/source_registry.py",
            "health_aggregator":         "scripts/source_fabric_health.py",
            "handler_js":                "workers/intel-gateway/src/p40-handlers.js",
            "executive_dashboard":       "/api/v1/p40/dashboard",
        },
        "adr": [
            {
                "id": "ADR-P40-001",
                "decision": "Extend scripts/true_intel_ingestor.py (live, scheduled, proven-resilient) "
                            "rather than activate core/ingestion's dormant BaseSource adapter engine "
                            "(mounted but never .start()'d — verified during reconnaissance) or build a "
                            "third parallel ingestion path.",
                "rationale": "Activating a previously-never-run background scheduler inside the shared "
                             "Railway web dyno is a real architectural/operational-risk event (Architecture "
                             "Preservation Rule) with no blast-radius sign-off in this change. The existing "
                             "batch pipeline already has checkpointing, dedup, and atomic-write resilience "
                             "matching mission Section 20's requirements.",
                "approach": "Additive — 0 lines changed in the 6 existing source functions' logic "
                            "(URLhaus's Auth-Key fix is the one evidence-based exception, HTTP 401 verified "
                            "live). 3 new functions appended, registry-driven where new.",
                "risk": "LOW",
            },
            {
                "id": "ADR-P40-002",
                "decision": "EPSS integrated as ENRICHMENT over already-collected CVE IDs, not a "
                            "standalone ingest_* event-stream source.",
                "rationale": "FIRST.org publishes a score for the entire ~280k-CVE corpus daily; treating "
                              "that as a firehose of 'new items' would misrepresent a daily re-score as "
                              "280k new intelligence events.",
                "approach": "New enrich_with_epss(items) function, mirrors the same technique already used "
                            "by core/ingestion/sources/nvd_source.py._enrich_with_epss().",
                "risk": "LOW",
            },
            {
                "id": "ADR-P40-003",
                "decision": "MITRE ATT&CK ingested as REFERENCE_SYNC to data/attck/enterprise-attack.json, "
                            "never merged into feed_manifest.json.",
                "rationale": "ATT&CK techniques/groups/software/mitigations are taxonomy data, not discrete "
                             "threat events — the manifest represents 'new intelligence happened', not "
                             "'this reference dataset was revised'. Original STIX object IDs preserved "
                             "verbatim per mission Section 8.",
                "approach": "New module-level function, content-hash gated against re-sync churn, "
                            "dry_run-aware (no disk writes under --dry-run, matching the other 6 sources' "
                            "no-persisted-side-effects contract).",
                "risk": "LOW",
            },
        ],
        "gates": gates,
    }

    out_path = DATA_Q / "p40_certification_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nP40.0 Production Certification — Global Intelligence Source Fabric")
    print(f"{'='*62}")
    print(f"Release tier    : {tier}")
    print(f"Gates           : {passed}/{total} PASS | {blockers} blockers | {warnings} warnings")
    print(f"Source registry : {total_sources} sources across {len(waves_present)} waves")
    print(f"Source health   : {health.get('health_breakdown') if health else 'N/A'}")
    print(f"Report          : {out_path}")
    for g in gates:
        prefix = "  [PASS]" if g["status"] == "PASS" else "  [WARN]" if g["status"] == "FAIL_WARNING" else "  [FAIL]"
        print(f"{prefix} {g['gate_id']}: {g['label']} — {g['detail']}")

    return report


if __name__ == "__main__":
    report = run_certification()
    sys.exit(0 if report["blocker_count"] == 0 else 1)
