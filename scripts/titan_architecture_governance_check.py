#!/usr/bin/env python3
"""
scripts/titan_architecture_governance_check.py
Project TITAN Stage 6-8 — Architecture Governance Drift Check (advisory)

Stage 6 produced five canonical-ownership ADRs (docs/adr/0007-0011) after finding that
prior stages' discovery had real, non-hypothetical blind spots: TITAN_STAGE6_VALIDATION.md
documents a ~12,600-line parallel implementation (cyberdudebivash-blog's lib/ tree) that
existed, undetected, through two full discovery passes, plus two additional independently-
invented "has evidence" heuristics (P37, P35) neither discovery doc catalogued. The failure
mode in both cases was the same: a new confidence/evidence-shaped function or a governance
artifact went missing or was added without anyone checking it against the ownership decisions
already on record.

Stage 7 added ADR-0012/0013 to the tracked set. Stage 8 (Phase 10) added three more checks
after live production verification found that a documented route ("previously unreachable —
now wired") had drifted from its own header comment once before, and that the Phase 9 Evidence
Registry scaffolding needs a standing guard against being wired into production ahead of its
authorization. See TITAN_AR000_RESOLUTION.md and TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md.

Stage 9 Phase 1 added three more checks after graph-discovery found the true count of
graph/relationship-shaped implementations was far larger than ADR-0010 tracked (two new
same-repo implementations — R6, R7 — plus 16 long-tail files under agent/ and scripts/ that no
prior stage had catalogued at all). See TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md and
ADR-0010 Revision 3.

Stage 9 Phase 2 (architecture planning — no migration executed) added seven more checks
covering the categories that phase's own charter named: duplicate relationship generators
(a same-file inconsistency found this phase in p31-handlers.js), unused graph engines drifting
out of their confirmed-dormant status, dead graph exports changing status, the DEBT-020
"zombie pipeline" resuming or continuing, relationship-vocabulary drift against the new
canonical schema, schema-spec-document integrity, and premature/unauthorized execution of the
Migration Blueprint's feature flags. "Duplicate graph providers" (also named in that phase's
charter) is deliberately not a separate check — any duplicate implementation of the new
GraphProvider/RelationshipProvider/etc. interfaces would surface as a new file via the existing
check_for_unreviewed_graph_files() (Phase 1), so a dedicated duplicate-provider check would be
redundant with it today. See TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md,
TITAN_GRAPH_INTERFACE_SPECIFICATION.md, TITAN_GRAPH_MIGRATION_BLUEPRINT.md.

Checks, in order:

  1. Do the tracked ADRs and the discovery/governance docs they depend on still exist?
  2. Do the specific functions each ADR names as "Existing Implementations" still exist at
     their cited locations?
  3. Do any *new* top-level functions in the P-layer handlers match a confidence/evidence/
     reliability-shaped name that ISN'T already accounted for in the ADRs' inventories?
  4. Does the ownership matrix still exist and still list every tracked ADR?
  5. (Stage 8) Does index.js's own header-comment route list still match a real route
     registration in the file? (route/documentation drift — the exact failure mode
     enterprise-endpoints.js already had once, per its own "previously unreachable" comment)
  6. (Stage 8) Has the Phase 9 Evidence Registry scaffolding been wired into any production
     file, or has its feature flag been flipped on, ahead of ADR-0008 Acceptance?
  7. (Stage 8) Best-effort, network-optional: do the confirmed-live and confirmed-dead
     blog routes from the AR-000 verification still match their last-known state? Skipped
     silently (not a finding) if network access is unavailable — this check exists to catch
     regression, not to require CI to have external network access.
  8. (Stage 9 Phase 1) Do any *new* Python files under core/, agent/, scripts/, or
     sentinel-apex-api/ have a graph/relationship/correlation-shaped name that ISN'T already
     accounted for in the graph candidate matrix?
  9. (Stage 9 Phase 1) Is the traced R3 producer chain (enrichment_graph.py ->
     core/orchestrator.py's R2AIExportStage -> Cloudflare R2 storage -> api-extensions.js)
     still intact at the two reference points ADR-0010 Revision 3 cites? (Does NOT check
     whether the chain actually executes anywhere — that remains DEBT-017, open.)
  10. (Stage 9 Phase 1) Does ADR-0010 still mention every tracked graph-implementation ID
      (R1-R7)?
  11. (Stage 9 Phase 2) Does p31-handlers.js still define two internally-inconsistent
      relationship shapes (the 'rel' vs. 'relation' key drift found this phase)?
  12. (Stage 9 Phase 2) Have any of the 7 files confirmed Archive/dormant-status candidates
      gained a new importer, drifting out of that classification unreviewed?
  13. (Stage 9 Phase 2) Has api/graph/graph.json's confirmed-stale status changed?
  14. (Stage 9 Phase 2) Does data/threat_graph/ now contain the files DEBT-020 found were
      never persisted, despite two scheduled scripts targeting that path?
  15. (Stage 9 Phase 2) Does p31-handlers.js emit any relationship type outside the canonical
      vocabulary now documented in TITAN_GRAPH_INTERFACE_SPECIFICATION.md?
  16. (Stage 9 Phase 2) Is the canonical relationship schema specification document intact?
  17. (Stage 9 Phase 2) Has TITAN_GRAPH_MIGRATION_BLUEPRINT.md's Phase 1/2 been prematurely
      wired into production code ahead of its stated preconditions?

Advisory only. Exit code is informational (0 = clean, 1 = findings to review) but the CI step
invoking this script wraps it in continue-on-error / an unconditional exit 0, matching the
STAGE 4.04 schema-mirror-drift-check precedent — this is intentionally non-blocking until it
has run clean across a few real drift cycles, the same rollout pattern used for that check.
Promoting it to a blocking gate is a deliberate future decision, not a default.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
HANDLERS_DIR = ROOT / "workers" / "intel-gateway" / "src"

REQUIRED_ADRS = [
    "0007-canonical-confidence-framework.md",
    "0008-canonical-evidence-framework.md",
    "0009-source-reliability-ownership.md",
    "0010-relationship-graph-ownership.md",
    "0011-evidence-lifecycle-ownership.md",
    "0012-api-versioning-interface-governance.md",
    "0013-typescript-rc1-disposition.md",
]

REQUIRED_GOVERNANCE_DOCS = [
    "CONFIDENCE_FRAMEWORK_DISCOVERY.md",
    "EVIDENCE_ENGINE_DISCOVERY.md",
    "TITAN_OWNERSHIP_MATRIX.md",
    "TITAN_STAGE6_VALIDATION.md",
    "ARCHITECTURE_DECISIONS.md",
    "TITAN_STAGE7_VALIDATION.md",
    "TITAN_INTERFACE_REGISTRY.md",
    "TITAN_TECH_DEBT_REGISTER.md",
]

# file -> function/property names ADR-0007/0008/0009 cite as "Existing Implementations".
# Keep this list in sync with the ADRs by hand; this script does not parse the ADRs
# themselves (deliberately — parsing prose ADRs for ground truth is more fragile than a
# short, human-maintained allowlist reviewed alongside any ADR edit).
CITED_REFERENCES = {
    "p20-handlers.js": ["computeP20QualityScore", "buildEvidenceChainBlock"],
    "p18-handlers.js": ["buildEvidenceAttribution", "computeTransparentConfidence"],
    "p25-handlers.js": ["computeEnterpriseTrustScore"],
    "p23-handlers.js": [],  # gate is inline, not a named export; presence checked via keyword below
    "p30-handlers.js": [
        "buildP30VerificationBlock",
        "buildP30TimelineBlock",
        "buildP30ChangeTrackingBlock",
    ],
    "p31-handlers.js": ["buildP31RelationshipBlock"],
    "p29-handlers.js": ["_computeConfidenceGraph"],
    "p32-handlers.js": ["buildP32EvidenceTransparencyBlock"],
    "p35-handlers.js": ["handleP35Evidence"],
    "p37-handlers.js": ["_confidenceAudit", "_evidenceAudit", "_reliabilityAudit"],
}

# Names ADR-0007/0008/0009 already know about and have made an explicit ownership call on,
# reviewed by reading the function body (not just the name) before being added here — see
# TITAN_STAGE6_VALIDATION.md §4 for how the first ten of these were triaged. A new top-level
# match for the patterns below that ISN'T in this allowlist is what this script flags — it is
# not itself a defect, it's a "review this against the ADRs" signal.
KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS = {
    # Canonical sources (ADR-0007/0008/0009 Decision)
    "computeEnterpriseTrustScore",   # A1 — canonical (ADR-0007)
    "computeP20QualityScore",        # E1 support — canonical (ADR-0008)
    "computeP26Grade",               # composite grade, reads P20/P21/P23/P25 — not independently scoring
    "computeActionabilityScore",     # P23, distinct concept (actionability, not confidence) — out of scope, allowlisted to avoid false positives
    "buildEvidenceChainBlock",       # E1 renderer
    # Deprecated-pending-migration, already reviewed and decided (ADR-0007/0008/0009), not re-flag
    "buildEvidenceAttribution",      # A2/E2/S2 — Deprecated Pending Migration
    "computeTransparentConfidence",  # A9 — Deprecated Pending Migration (found via this script, §4)
    # P30 lifecycle signal (ADR-0011's L1-L4, canonical derivation source)
    "buildP30VerificationBlock",
    "buildP30TimelineBlock",
    "buildP30ChangeTrackingBlock",
    "_computeIOCLifecycle",
    "buildP30TrustTimelineBlock",    # renderer composing L1-L4 — reviewed, not a new scorer
    # P31 relationship graph (ADR-0010)
    "buildP31RelationshipBlock",
    # P32 evidence transparency (ADR-0008 item 3)
    "buildP32EvidenceTransparencyBlock",
    # Fleet-level auditors (TITAN_STAGE6_VALIDATION.md §3) — consumers/auditors, not scorers
    "_confidenceAudit",              # reuses computeEnterpriseTrustScore directly
    "_evidenceAudit",
    "_reliabilityAudit",             # false-positive name match — pipeline health, not source reliability
    "_enrichmentAudit",
    "_reliabilityMetrics",
    "handleP35Evidence",
    "buildP34ReliabilityBlock",      # false-positive name match — CI gate pass-rate, not source reliability
    # Renderers/composers reviewed and confirmed to only format already-canonical values —
    # see TITAN_STAGE6_VALIDATION.md §4 for the read-through that classified each of these
    "buildTrustIndicatorBlock",      # composes buildEvidenceAttribution + computeTransparentConfidence + quality — renderer
    "buildConfidenceExplanationBlock",  # renders computeP20QualityScore's breakdown
    "buildTrustScoreBlock",          # renders computeEnterpriseTrustScore's dims directly
    "buildP25TrustPackage",          # composes other block-builders, no independent scoring
    "buildP26TrustBadgesBlock",      # renders computeP26Grade's sub-details
    "buildP29ConfidenceGraphBlock",  # renderer for _computeConfidenceGraph (see below)
    # Tracked, not yet decided (DEBT-012) — allowlisted so the script doesn't re-flag a
    # already-logged, already-triaged item; NOT a canonical-ownership decision
    "_computeConfidenceGraph",
}

NAME_PATTERN = re.compile(
    r"function\s+(_?(?:compute|build|score|grade|rate|assess)\w*"
    r"(?:[Cc]onfidence|[Ee]vidence|[Rr]eliability|[Tt]rust)\w*)\s*\(",
)


def check_docs_exist() -> list[str]:
    findings = []
    for name in REQUIRED_ADRS:
        if not (ADR_DIR / name).exists():
            findings.append(f"MISSING ADR: docs/adr/{name} — referenced by docs/adr/README.md and TITAN_OWNERSHIP_MATRIX.md")
    for name in REQUIRED_GOVERNANCE_DOCS:
        if not (ROOT / name).exists():
            findings.append(f"MISSING GOVERNANCE DOC: {name} — cited by one or more ADRs as source material")
    return findings


def check_cited_references_exist() -> list[str]:
    findings = []
    for filename, names in CITED_REFERENCES.items():
        path = HANDLERS_DIR / filename
        if not path.exists():
            findings.append(f"MISSING FILE: {filename} — cited by an ADR's Existing Implementations table")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in names:
            if name not in text:
                findings.append(
                    f"BROKEN REFERENCE: {filename} no longer contains '{name}' — "
                    f"an ADR's Existing Implementations table cites it. Update the ADR or investigate the removal."
                )
    return findings


def check_for_unreviewed_new_scorers() -> list[str]:
    findings = []
    if not HANDLERS_DIR.exists():
        return findings
    for path in sorted(HANDLERS_DIR.glob("p*-handlers.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in NAME_PATTERN.finditer(text):
            name = match.group(1)
            if name not in KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS:
                findings.append(
                    f"POSSIBLE NEW IMPLEMENTATION: {path.name} defines '{name}', a confidence/evidence/"
                    f"reliability/trust-shaped function not in this script's known-implementations "
                    f"allowlist. Review against ADR-0007/0008/0009's ownership decisions before this "
                    f"becomes a new disagreeing scorer — see TITAN_STAGE6_VALIDATION.md §3 for why this "
                    f"category of drift matters."
                )
    return findings


def check_ownership_matrix() -> list[str]:
    findings = []
    matrix = ROOT / "TITAN_OWNERSHIP_MATRIX.md"
    if not matrix.exists():
        return findings  # already reported by check_docs_exist
    text = matrix.read_text(encoding="utf-8", errors="replace")
    for adr_num in ("0007", "0008", "0009", "0010", "0011"):
        if adr_num not in text:
            findings.append(f"OWNERSHIP MATRIX DRIFT: TITAN_OWNERSHIP_MATRIX.md does not reference ADR-{adr_num}")
    return findings


# Routes documented in index.js's own header comment (the "Routes (all v184.0 routes
# preserved):" block). Hand-maintained here for the same reason CITED_REFERENCES is
# hand-maintained: parsing the comment block itself would be more fragile than keeping
# a short list in sync, and this list changes rarely. If a route below is removed from
# the header comment, this check should be updated in the same PR — that's the point.
DOCUMENTED_CORE_ROUTES = [
    "/api/health",
    "/api/v1/ioc/lookup",
    "/api/preview",
    "/api/feed",
    "/taxii/",
    "/api/admin/health",
    "/api/admin/audit",
    "/api/admin/keys",
]


def check_route_documentation_drift() -> list[str]:
    findings = []
    index_js = HANDLERS_DIR / "index.js"
    if not index_js.exists():
        return findings
    text = index_js.read_text(encoding="utf-8", errors="replace")
    for route in DOCUMENTED_CORE_ROUTES:
        # Accept either an exact match or a startsWith-style prefix match, since some
        # routes are matched via path.startsWith(...) rather than path === "...".
        needle = route.rstrip("/")
        if needle not in text and route not in text:
            findings.append(
                f"ROUTE DOCUMENTATION DRIFT: index.js's header comment documents '{route}' "
                f"but no matching route registration string was found in the file. Either the "
                f"route was removed (update the header comment) or renamed (same). This is the "
                f"exact failure mode enterprise-endpoints.js already hit once — see its own "
                f"'previously unreachable — now wired via routeEnterpriseEndpoint' comment."
            )
    return findings


def check_evidence_registry_scaffolding_boundary() -> list[str]:
    findings = []
    scaffold_dir = HANDLERS_DIR / "evidence-registry"
    if not scaffold_dir.exists():
        return findings  # scaffolding not present yet — nothing to guard

    # 1. Nothing outside evidence-registry/ may import from it yet.
    for path in HANDLERS_DIR.rglob("*.js"):
        if scaffold_dir in path.parents or path.parent == scaffold_dir:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "evidence-registry" in text:
            findings.append(
                f"EVIDENCE REGISTRY BOUNDARY VIOLATION: {path.relative_to(ROOT)} references "
                f"'evidence-registry' — this scaffolding is authorized (Stage 8) for isolated, "
                f"unimported existence only. See TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md — "
                f"wiring it into production requires ADR-0008 Acceptance first."
            )

    # 2. The feature flag must still default to false.
    flags_file = scaffold_dir / "feature-flags.js"
    if flags_file.exists():
        flags_text = flags_file.read_text(encoding="utf-8", errors="replace")
        if "SCAFFOLDING_ENABLED: false" not in flags_text:
            findings.append(
                "EVIDENCE REGISTRY BOUNDARY VIOLATION: feature-flags.js's SCAFFOLDING_ENABLED "
                "no longer defaults to false. Flipping this ahead of ADR-0008 Acceptance is "
                "exactly what the Stage 8 authorization's Risk Assessment flagged as the "
                "scenario to guard against."
            )
    return findings


# (domain, path, expected_status_family) — a small, deliberately narrow sample from
# TITAN_STAGE8_VERIFICATION_REPORT.md's live-verification table. "family" is one of
# "not_found" (Vercel platform 404 expected) or "live" (any non-404 expected — the
# exact code may legitimately vary with auth/tier state, only 404-vs-not matters here).
AR000_REGRESSION_SAMPLE = [
    ("https://blog.cyberdudebivash.in", "/api/v1/intelligence/confidence", "not_found"),
    ("https://blog.cyberdudebivash.in", "/api/v1/newsletter", "live"),
    ("https://intel.cyberdudebivash.com", "/api/health", "live"),
]


def check_ar000_regression() -> list[str]:
    findings = []
    for domain, path, expected in AR000_REGRESSION_SAMPLE:
        url = domain + path
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "titan-governance-check/1.0"})
            try:
                resp = urllib.request.urlopen(req, timeout=8)
                status = resp.status
            except urllib.error.HTTPError as e:
                status = e.code
        except Exception:
            # Network unavailable in this CI environment, DNS blocked, timeout, etc.
            # Not a finding — this check is best-effort by design, see module docstring.
            continue

        is_not_found = (status == 404)
        if expected == "not_found" and not is_not_found:
            findings.append(
                f"AR-000 REGRESSION: {url} was confirmed NOT deployed (404) in "
                f"TITAN_STAGE8_VERIFICATION_REPORT.md but now returns HTTP {status}. If this "
                f"route has been deployed, ADR-0007/0008/0009/0010's Stage 8 Revision 2 "
                f"resolution needs re-examination — this route was the basis for un-blocking them."
            )
        elif expected == "live" and is_not_found:
            findings.append(
                f"AR-000 REGRESSION: {url} was confirmed live in "
                f"TITAN_STAGE8_VERIFICATION_REPORT.md but now returns HTTP 404. Investigate "
                f"whether this is an intentional deprecation (should be documented per the "
                f"Deprecation Instead of Deletion policy) or an unintended outage."
            )
    return findings


# ---------------------------------------------------------------------------------------
# Stage 9 Phase 1 additions — graph-implementation drift detection.
# See TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md and ADR-0010 Revision 3: graph discovery
# found the true count of graph/relationship-shaped implementations (R1-R7, plus 16 files
# under agent/ and scripts/ not previously catalogued at all) far larger than ADR-0010 tracked
# before this stage. These checks exist so the *next* one is caught at discovery time.
# ---------------------------------------------------------------------------------------

GRAPH_PYTHON_SCAN_DIRS = [
    ROOT / "core",
    ROOT / "agent",
    ROOT / "scripts",
    ROOT / "sentinel-apex-api",
]

# Every graph-related Python file known as of Stage 9 Phase 1 (ADR-0010 R6/R7 plus the
# long-tail characterized in TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md Task 1C — 9
# confirmed production, 6 confirmed dormant, 1 confirmed paused; runtime status does not
# affect allowlist membership, only *discovery* completeness does). A match below that ISN'T
# in this set is what check_for_unreviewed_graph_files() flags — mirrors
# check_for_unreviewed_new_scorers()'s existing design for the JS side. Known incomplete: the
# source file behind "ocios_campaign_correlation_engine" (evidenced only by
# data/ocios/campaign_graph.json's own self-identification) was not located as of this
# writing — deliberately NOT allowlisted, so a future scan that finds it is a useful signal,
# not a false positive to suppress.
KNOWN_GRAPH_PYTHON_FILES = {
    "core/intelligence/enrichment_graph.py",                    # R6 (ADR-0010 Revision 3)
    "core/correlation/threat_correlator.py",                    # reviewed — not a graph data structure, allowlisted to avoid false positive
    "sentinel-apex-api/app/api/v1/endpoints/intel_graph.py",    # R7 (ADR-0010 Revision 3)
    "agent/graph/graph_intel.py",                                # Dormant
    "agent/graph_operations_engine.py",                          # Dormant
    "agent/graph_integrity_validator.py",                        # Production (zombie-pipeline reader — DEBT-020)
    "agent/graph_correlation_engine.py",                         # Production (zombie-pipeline writer — DEBT-020)
    "agent/threat_graph/graph_engine.py",                        # Production
    "agent/threat_graph_engine.py",                              # Dormant
    "agent/v44_threat_graph/graph_models.py",                    # Dormant/Archived
    "agent/v44_threat_graph/threat_graph_engine.py",             # Dormant/Archived
    "scripts/adversary_graph_engine.py",                         # Production, schedule paused since 2026-07-29
    "scripts/graph_integrity_validator.py",                      # Production (distinct code from the agent/ file of the same name)
    "scripts/graph_intelligence_validator.py",                   # Dormant
    "scripts/graph_intelligence_engine.py",                      # Dormant
    "scripts/intelligence_knowledge_graph.py",                   # Production, possible silent no-op (continue-on-error, no observed output)
    "scripts/omega_ioc_graph_layer.py",                          # Production
    "scripts/persistent_campaign_graph_engine.py",               # Production
    "scripts/threat_graph_engine.py",                            # Production — feeds live /api/graph/* endpoints
    "scripts/ocios_campaign_correlation_engine.py",               # Production — imported by 3 sibling ocios_*.py scripts; was the "17th implementation" this check found on first run
}

# Deliberately NOT allowlisted: this first run of check_for_unreviewed_graph_files() also
# surfaced agent/threat_graph/correlation_engine.py, agent/v70_apex_upgrade/engines/
# correlation_engine.py, agent/v26/ioc_correlation.py, scripts/cve_correlation_engine.py, and
# scripts/adversary_correlation_engine.py — none characterized as of this writing. Leaving
# them un-allowlisted is intentional: the finding is accurate (they have not been reviewed
# against ADR-0010's candidate matrix), and allowlisting them without doing that review would
# be exactly the premature, undocumented closure this program exists to prevent. They will
# keep appearing in this check's output until someone characterizes them and either adds them
# here or records a disposition in TITAN_TECH_DEBT_REGISTER.md.

GRAPH_NAME_PATTERN = re.compile(r"graph|relationship|correlat", re.IGNORECASE)


def check_for_unreviewed_graph_files() -> list[str]:
    findings = []
    for scan_dir in GRAPH_PYTHON_SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            if "tests" in path.parts or path.name.startswith("test_") or path.name == "__init__.py":
                continue  # test files and package markers reviewed separately
            if GRAPH_NAME_PATTERN.search(path.stem):
                rel = path.relative_to(ROOT).as_posix()
                if rel not in KNOWN_GRAPH_PYTHON_FILES:
                    findings.append(
                        f"POSSIBLE NEW GRAPH IMPLEMENTATION: {rel} has a graph/relationship/"
                        f"correlation-shaped name and is not in this script's known-implementations "
                        f"allowlist. Review against ADR-0010's candidate matrix "
                        f"(TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md Task 6) before this becomes "
                        f"another uncatalogued fragmentation point."
                    )
    return findings


def check_r3_producer_chain_intact() -> list[str]:
    """Confirms the R3 producer chain traced in ADR-0010 Revision 3 (enrichment_graph.py ->
    core/orchestrator.py's R2AIExportStage -> Cloudflare R2 storage -> api-extensions.js)
    hasn't silently changed shape. Does NOT confirm the chain executes anywhere in production
    (that remains DEBT-017, open) — only that the traced code path itself is intact, so a
    future change to it is caught rather than silently invalidating the discovery report's
    trace."""
    findings = []
    orchestrator = ROOT / "core" / "orchestrator.py"
    if orchestrator.exists():
        text = orchestrator.read_text(encoding="utf-8", errors="replace")
        if "R2AIExportStage" not in text:
            findings.append(
                "GRAPH PRODUCER CHAIN DRIFT: core/orchestrator.py no longer references "
                "R2AIExportStage. TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md Task 4 and "
                "ADR-0010 Revision 3 trace R3's data through this exact reference — if it's been "
                "removed or renamed, that trace is now stale and DEBT-013/DEBT-017 need review."
            )
    api_extensions = HANDLERS_DIR / "api-extensions.js"
    if api_extensions.exists():
        text = api_extensions.read_text(encoding="utf-8", errors="replace")
        if "intel_graph.json" not in text:
            findings.append(
                "GRAPH PRODUCER CHAIN DRIFT: api-extensions.js no longer references "
                "'intel_graph.json'. R3's consumer side of the traced producer chain "
                "(ADR-0010 Revision 3) may have changed — review DEBT-013's resolution notes."
            )
    return findings


def check_adr0010_graph_ids_present() -> list[str]:
    """Confirms ADR-0010 still documents each graph-implementation ID this program has
    catalogued (R1-R8 as of Revision 4 — R8 added Stage 9 Phase 2), so a future edit that
    drops an ID isn't silently lost."""
    findings = []
    adr = ADR_DIR / "0010-relationship-graph-ownership.md"
    if not adr.exists():
        return findings  # already reported by check_docs_exist
    text = adr.read_text(encoding="utf-8", errors="replace")
    for graph_id in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        if graph_id not in text:
            findings.append(
                f"ADR-0010 DRIFT: docs/adr/0010-relationship-graph-ownership.md no longer "
                f"mentions graph-implementation ID '{graph_id}', tracked as of Stage 9 Phase 1's "
                f"candidate matrix. If this ID was intentionally retired, document why here; if "
                f"it was accidentally dropped, restore it."
            )
    return findings


# ---------------------------------------------------------------------------------------
# Stage 9 Phase 2 additions — canonical graph architecture governance (planning-only phase;
# no migration has been authorized or executed, so several of these checks are forward-
# looking sentinels with nothing to catch yet, by design — same rollout pattern as Stage 8's
# Evidence Registry boundary check, which existed before any real risk did).
# ---------------------------------------------------------------------------------------


def check_r1_internal_relationship_shape_consistency() -> list[str]:
    """TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md Task 2C found p31-handlers.js defines two
    internally-inconsistent relationship shapes in the same file: buildP31RelationshipBlock
    uses key 'rel' (UPPER_SNAKE_CASE values), _buildGraph uses key 'relation' (lowercase
    values). Not yet fixed (Phase 2 is planning-only). This keeps the finding visible rather
    than letting a one-time discovery age silently out of view."""
    findings = []
    p31 = HANDLERS_DIR / "p31-handlers.js"
    if not p31.exists():
        return findings
    text = p31.read_text(encoding="utf-8", errors="replace")
    uses_rel_key = bool(re.search(r"\brel:\s*[\"']", text))
    uses_relation_key = bool(re.search(r"\brelation:\s*\w", text))
    if uses_rel_key and uses_relation_key:
        findings.append(
            "RELATIONSHIP SHAPE DRIFT (standing finding): p31-handlers.js still defines two "
            "internally-inconsistent relationship shapes — buildP31RelationshipBlock's 'rel' "
            "key vs. _buildGraph's 'relation' key. Documented in "
            "TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md Task 2C and reconciled in "
            "TITAN_GRAPH_INTERFACE_SPECIFICATION.md's CanonicalRelationship schema, but not "
            "yet fixed in production code — no migration has been authorized. Not a "
            "regression; a tracked item this check keeps visible until Migration Blueprint "
            "Phase 1 actually lands."
        )
    return findings


# Files Stage 9 Phase 1/2 confirmed have zero importers and zero CI references (Archive
# candidates per the Phase 2 ownership recommendation). If one gains a real importer without
# review, that's a disposition-relevant change worth surfacing, not silently accepting.
CONFIRMED_DORMANT_GRAPH_FILES = [
    "agent/graph/graph_intel.py",
    "agent/graph_operations_engine.py",
    "agent/threat_graph_engine.py",
    "agent/v44_threat_graph/graph_models.py",
    "agent/v44_threat_graph/threat_graph_engine.py",
    "scripts/graph_intelligence_validator.py",
    "scripts/graph_intelligence_engine.py",
]


# Known, already-reviewed importers of a confirmed-dormant file, per
# TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md Task 1C — these do NOT change the file's
# Dormant classification (a sibling within the same unused v44 cluster; a sole caller that is
# itself unwired anywhere else in the repo) and are excluded so the check below only flags a
# genuinely NEW importer, not the ones already accounted for.
REVIEWED_DORMANT_IMPORTERS = {
    "agent/v44_threat_graph/graph_models.py": {"agent/v44_threat_graph/threat_graph_engine.py"},
    "scripts/graph_intelligence_validator.py": {"scripts/apex_sovereign_trust_orchestrator.py"},
}


def check_dormant_graph_files_still_unused() -> list[str]:
    findings = []
    for rel_path in CONFIRMED_DORMANT_GRAPH_FILES:
        target = ROOT / rel_path
        if not target.exists():
            continue
        module_stem = target.stem
        reviewed = REVIEWED_DORMANT_IMPORTERS.get(rel_path, set())
        # Must match actual Python import syntax (from ...X import / import ...X), not a bare
        # word/substring match — an earlier draft of this check used the latter and flagged
        # all 7 files as false positives (the stem names are common enough to appear in
        # unrelated comments/docstrings across a repo this large).
        import_pattern = re.compile(
            rf"(?:from\s+[\w.]*\b{re.escape(module_stem)}\b[\w.]*\s+import"
            rf"|import\s+[\w.]*\b{re.escape(module_stem)}\b)"
        )
        new_importer = None
        for scan_dir in GRAPH_PYTHON_SCAN_DIRS:
            if not scan_dir.exists() or new_importer:
                continue
            for candidate in scan_dir.rglob("*.py"):
                if candidate == target:
                    continue
                candidate_rel = candidate.relative_to(ROOT).as_posix()
                if candidate_rel in reviewed:
                    continue
                try:
                    candidate_text = candidate.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if import_pattern.search(candidate_text):
                    new_importer = candidate_rel
                    break
        if new_importer:
            findings.append(
                f"DORMANT-STATUS DRIFT: {rel_path} was confirmed to have zero *externally-"
                f"relevant* importers as of Stage 9 Phase 1/2 (an Archive candidate per "
                f"TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md Task 3), but a new reference from "
                f"{new_importer} was found beyond the ones already reviewed "
                f"(REVIEWED_DORMANT_IMPORTERS in this script). Re-review its disposition."
            )
    return findings


def check_dead_graph_export_still_stale() -> list[str]:
    """TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md Task 1C confirmed api/graph/graph.json is
    a stale, ~2-month-old static fixture, not regenerated by anything, while its sibling
    api/graph/nodes.json (R8's real output) carries a fresh generated_at. Confirms that gap
    still exists — convergence would be worth a human look (fixed? new confusion?), not a
    silent non-finding either way."""
    findings = []
    dead_export = ROOT / "api" / "graph" / "graph.json"
    live_export = ROOT / "api" / "graph" / "nodes.json"
    if not (dead_export.exists() and live_export.exists()):
        return findings
    try:
        dead_data = json.loads(dead_export.read_text(encoding="utf-8", errors="replace"))
        live_data = json.loads(live_export.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return findings
    dead_gen = dead_data.get("generated_at") or (dead_data.get("stats") or {}).get("generated_at")
    live_gen = live_data.get("generated_at")
    if dead_gen and live_gen and dead_gen == live_gen:
        findings.append(
            "DEAD GRAPH EXPORT STATUS CHANGE: api/graph/graph.json's generated_at now matches "
            "api/graph/nodes.json's. Stage 9 Phase 1 found these had diverged (graph.json "
            "frozen at 2026-05-29, nodes.json fresh). If graph.json is now being regenerated, "
            "review whether its 'dead export' classification should change; if coincidental, "
            "no action needed."
        )
    elif dead_gen is None:
        findings.append(
            "DEAD GRAPH EXPORT: api/graph/graph.json no longer has a readable generated_at "
            "field — its schema may have changed. Re-verify its stale/dead classification "
            "(TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md Task 1C) still applies."
        )
    return findings


def check_zombie_pipeline_status() -> list[str]:
    """DEBT-020: agent/graph_correlation_engine.py (writer) and agent/graph_integrity_
    validator.py (reader) are both scheduled 6x/day against data/threat_graph/, a path with
    zero git history as of Stage 9 Phase 1. Confirms that status in the current checkout —
    if the expected files now exist, the zombie-pipeline finding may have resolved (or a new
    form of it exists); either way this is worth surfacing rather than assuming unchanged."""
    findings = []
    target_dir = ROOT / "data" / "threat_graph"
    expected_files = ["graph_nodes.json", "graph_edges.json"]
    existing = [f for f in expected_files if (target_dir / f).exists()]
    if existing:
        findings.append(
            f"ZOMBIE PIPELINE STATUS CHANGE (DEBT-020): data/threat_graph/ now contains "
            f"{existing} in this checkout. Stage 9 Phase 1 found this path had zero git "
            f"history despite two scheduled scripts targeting it 6x/day each "
            f"(agent/graph_correlation_engine.py writing, agent/graph_integrity_validator.py "
            f"reading). If this data is now real, DEBT-020 may be resolvable — confirm and "
            f"update TITAN_TECH_DEBT_REGISTER.md rather than leaving its Critical severity "
            f"stale."
        )
    return findings


# Canonical relationship-type vocabulary, per TITAN_GRAPH_INTERFACE_SPECIFICATION.md Part A.3.
# Open vocabulary by design — a new type here is not inherently wrong, but should be a
# deliberate addition to that spec, not a silent one.
CANONICAL_RELATIONSHIP_TYPES = {
    "ATTRIBUTED_TO", "USES_TECHNIQUE", "REFERENCES", "RESOLVES_TO", "COMMUNICATES_WITH",
    "HOSTS", "PART_OF", "SHARES_INFRASTRUCTURE", "DROPS", "EXPLOITS", "MENTIONS", "MAPS_TO",
    "OBSERVED", "ASSOCIATED_WITH", "LINKED_TO", "CONTAINS_IOC", "MAPS_TO_TECHNIQUE", "INVOLVES",
}


def check_r1_relationship_type_vocabulary_drift() -> list[str]:
    findings = []
    p31 = HANDLERS_DIR / "p31-handlers.js"
    if not p31.exists():
        return findings
    text = p31.read_text(encoding="utf-8", errors="replace")
    literal_types = set(re.findall(r"rel:\s*[\"'](\w+)[\"']", text))
    for t in sorted(literal_types - CANONICAL_RELATIONSHIP_TYPES):
        findings.append(
            f"RELATIONSHIP VOCABULARY DRIFT: p31-handlers.js emits relationship type '{t}', "
            f"not present in TITAN_GRAPH_INTERFACE_SPECIFICATION.md Part A.3's canonical "
            f"vocabulary. That vocabulary is open by design — add it there deliberately, or "
            f"treat this as an unintentional new type worth reviewing."
        )
    return findings


def check_relationship_schema_spec_intact() -> list[str]:
    findings = []
    spec = ROOT / "TITAN_GRAPH_INTERFACE_SPECIFICATION.md"
    if not spec.exists():
        findings.append(
            "SCHEMA DRIFT: TITAN_GRAPH_INTERFACE_SPECIFICATION.md is missing — the canonical "
            "relationship schema this program is designing toward has no documented source."
        )
        return findings
    text = spec.read_text(encoding="utf-8", errors="replace")
    if "canonical-relationship.0.1-draft" not in text:
        findings.append(
            "SCHEMA DRIFT: TITAN_GRAPH_INTERFACE_SPECIFICATION.md no longer contains the "
            "expected schema_version string 'canonical-relationship.0.1-draft'. If the schema "
            "was deliberately versioned forward, update this check's expected string in the "
            "same change; if accidental, investigate."
        )
    return findings


# TITAN_GRAPH_MIGRATION_BLUEPRINT.md's Phase 1/2 flags. Neither exists in code yet — this
# migration is not authorized (ADR-0010 Acceptance with R8 added, plus DEBT-017/DEBT-020
# resolution, are still-open preconditions per that document's own Phase 0).
MIGRATION_BLUEPRINT_FLAGS = [
    "GRAPH_CANONICAL_PERSISTENCE_ENABLED",
    "GRAPH_R3_USES_CANONICAL_PROVIDER",
]


def check_migration_blueprint_not_prematurely_executed() -> list[str]:
    findings = []
    if not HANDLERS_DIR.exists():
        return findings
    for path in HANDLERS_DIR.rglob("*.js"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for flag in MIGRATION_BLUEPRINT_FLAGS:
            if flag in text:
                findings.append(
                    f"MIGRATION VIOLATION: {path.relative_to(ROOT)} references '{flag}' — "
                    f"TITAN_GRAPH_MIGRATION_BLUEPRINT.md's Phase 1/2 are NOT authorized to "
                    f"execute (ADR-0010 Acceptance with R8 added, and DEBT-017/DEBT-020 "
                    f"resolution, are still-open preconditions). If authorization has "
                    f"genuinely landed, confirm it's documented before proceeding; if "
                    f"accidental, revert."
                )
    return findings


def main() -> None:
    all_findings: list[str] = []
    all_findings += check_docs_exist()
    all_findings += check_cited_references_exist()
    all_findings += check_for_unreviewed_new_scorers()
    all_findings += check_ownership_matrix()
    all_findings += check_route_documentation_drift()
    all_findings += check_evidence_registry_scaffolding_boundary()
    all_findings += check_ar000_regression()
    all_findings += check_for_unreviewed_graph_files()
    all_findings += check_r3_producer_chain_intact()
    all_findings += check_adr0010_graph_ids_present()
    all_findings += check_r1_internal_relationship_shape_consistency()
    all_findings += check_dormant_graph_files_still_unused()
    all_findings += check_dead_graph_export_still_stale()
    all_findings += check_zombie_pipeline_status()
    all_findings += check_r1_relationship_type_vocabulary_drift()
    all_findings += check_relationship_schema_spec_intact()
    all_findings += check_migration_blueprint_not_prematurely_executed()

    print("=== Project TITAN Architecture Governance Check (advisory) ===")
    if not all_findings:
        print(f"Clean: all {len(REQUIRED_ADRS)} ADRs present, all cited references resolve, no unreviewed "
              "confidence/evidence/reliability functions found, ownership matrix in sync, "
              "documented routes still registered, Evidence Registry scaffolding boundary intact, "
              "no AR-000 regression detected (or network unavailable to check), no unreviewed "
              "graph/relationship/correlation-shaped Python files found, R3's producer chain "
              "intact, ADR-0010's tracked graph IDs (R1-R7) all present, no relationship-shape "
              "or vocabulary drift, no dormant/dead-export/zombie-pipeline status changes, "
              "Migration Blueprint not prematurely executed.")
        sys.exit(0)

    print(f"{len(all_findings)} finding(s):\n")
    for i, finding in enumerate(all_findings, 1):
        print(f"  {i}. {finding}")
    print(
        "\nNone of the above blocks this build (advisory-only stage). Review against "
        "docs/adr/ and TITAN_OWNERSHIP_MATRIX.md, and update whichever is stale — "
        "per this program's standing rule, document discrepancies rather than silently "
        "resolving them in whichever direction is convenient."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
