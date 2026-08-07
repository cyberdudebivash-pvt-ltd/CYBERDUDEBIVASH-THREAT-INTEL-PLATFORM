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

Stage 10 added the Canonical Evidence Core (CEC) — a second canonical domain-model type
(CanonicalEvidence, entity.js) alongside the CanonicalRelationship schema Stage 9 Phase 2
already governs above — plus eight checks covering the categories that stage's own Phase 10
charter named: duplicate evidence models, schema drift, version conflicts (specifically a
version:0 falsy-zero bug this stage found and fixed in createCanonicalEvidence), missing
validation, adapter regressions, feature-flag violations, serialization drift, and architecture
violations (required-file-set integrity). All Stage 10 code lives inside
workers/intel-gateway/src/evidence-registry/, already covered by
check_evidence_registry_scaffolding_boundary()'s Stage 8 boundary checks above — these eight are
additive, narrower checks specific to the CEC's own internal consistency, not a replacement for
that boundary check. See TITAN_STAGE10_ENGINEERING_SPECIFICATION.md.

Stage 11 activated the CEC with a working internal registry service (registry-service.js),
repository (in-memory-repository.js), lifecycle engine (lifecycle.js), version manager
(versioning.js), and indexes (indexes.js) — still fully inert. Nine more checks cover that
stage's own Phase 8 charter: duplicate registry entries, version conflicts, lifecycle
violations, evidence duplication, broken references, missing relationships, invalid
supersession, orphaned evidence, and architecture violations. Several of these are regression
guards for specific mechanisms Stage 11's own test suite proved matter (index staleness after
an edit, version-conflict masking) rather than static shape checks — there is no persisted
registry data file to inspect, since nothing is wired live. See
TITAN_STAGE11_REGISTRY_ARCHITECTURE.md.

Stage 12 built the Enterprise Evidence Service Platform (EESP) on top of Stage 11's registry:
seven named services, a twelve-dimension query engine, a six-lineage provenance engine, a
deliberately-scoped relationship resolution contract (no concrete P31 import — ADR-0010 is not
Accepted), five versioned internal contracts, and service-layer observability — still fully
inert. Seven more checks cover that stage's own Phase 7 charter: duplicate services, duplicate
contracts, version drift, registry bypass, relationship bypass, validation bypass, and
architecture violations. See TITAN_STAGE12_SERVICE_ARCHITECTURE.md.

Stage 14 built the Enterprise Intelligence Gateway (EIG) on top of Stage 13's Enterprise
Intelligence Platform Services (EIPS) — a facade (EnterpriseGateway), a capability registry, a
dispatcher with a composable middleware pipeline, in-process capability authorization, and its
own gateway-layer metrics view sharing the one ServicePlatformMetrics instance the whole
platform already threads through — the exact "no duplicate metrics instance" property this
stage's own brief names as a bug class to guard against by name. Twelve checks below cover this
stage's own Phase 1 charter: architecture violations, duplicate engines, reuse bypass, contract
version drift, duplicate contracts, registry bypass, ADR-0010 governance, validation bypass,
duplicate metrics instance, circular dependency, capability-authorization presence, and
network-auth scope creep (the last two have no Stage 12/13 precedent — this stage introduces
both concepts for the first time). See TITAN_STAGE14_SERVICE_ARCHITECTURE.md. (Note: Stage
13/EIPS's own check functions, added by PR #119, were never correspondingly added to this
docstring's narrative or numbered list below — a pre-existing documentation gap, not introduced
or corrected by this stage's own additions, flagged here rather than silently left unremarked.)

Stage 14 Phase 2 audited the merged Phase 1 Gateway (composition boundaries, registry, dispatcher,
lifecycle, middleware, metrics, authorization) and found it already satisfied nearly every audited
dimension by construction or by pre-existing reuse (see TITAN_STAGE14_PHASE2_COMPLETION_REPORT.md
for the full per-dimension findings) — the one genuine, evidence-backed gap was GatewayRegistry.get()
exposing its full internal entry, including the raw handler function, with no safe metadata-only
accessor. One check below (#54) guards the fix: GatewayRegistry.describe()/.describeAll().

Stage 15 inventoried every internal consumer of the Stage 8-14 lineage repo-wide (not just
scripts/) and found exactly two: scripts/enterprise_gateway_snapshot.mjs (already Gateway-backed,
Stage 14) and scripts/intelligence_platform_snapshot.mjs (direct composition, pre-dates the
Gateway). The P16-P38 handler stack and ~100 Python quality/trust/correlation scripts were
confirmed architecturally separate (different runtime or different data model, zero shared code)
-- not migration candidates without a translation layer, itself unauthorized future work; see
TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md Sec 2-4. The one real direct-composition consumer was
deprecated in place (its replacement already existed and is a strict superset), not rewritten or
deleted, per this program's Deprecation Instead of Deletion policy. One check below (#55) detects
any NEW bypass beyond that one tracked exception; adoption metrics (informational, not a
pass/fail gate) are printed separately by main().

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
  18. (Stage 10) Does any file outside evidence-registry/entity.js define its own
      createCanonicalEvidence or CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION (duplicate evidence
      domain model)?
  19. (Stage 10) Does schema.js's SCHEMA_VERSION_HISTORY still record both the Stage 8 and
      Stage 10 schema version strings, in sync with entity.js's own constant?
  20. (Stage 10) Has the version:0 falsy-zero bug in createCanonicalEvidence (found and fixed
      this stage) regressed?
  21. (Stage 10) Is the validation pipeline (validateCanonicalEvidence/validateEvidenceBatch)
      still exported, still composed by interfaces.js, and still called by serialization.js's
      DefaultEvidenceImporter before accepting an import?
  22. (Stage 10) Do all four Phase 7 migration adapters still exist, and does
      migration-adapters.js still avoid importing a live pNN-handlers.js file?
  23. (Stage 10) Does feature-flags.js's CEC_FLAGS still default canary/production to disabled,
      and has SCAFFOLDING_ENABLED stayed false?
  24. (Stage 10) Does serialization.js's getSerializer() still refuse 'stix'/'api' as named
      future capabilities rather than silently serializing them?
  25. (Stage 10) Does the full Stage 10 CEC file set still exist under evidence-registry/?
  26. (Stage 11) Does any file outside registry-service.js define its own `class
      EvidenceRegistry` (duplicate registry)?
  27. (Stage 11) Does in-memory-repository.js's version-bump arithmetic still avoid the
      version:0 falsy-zero pattern?
  28. (Stage 11) Do ARCHIVED/REJECTED remain terminal lifecycle states, and does
      registry-service.js still enforce transitions through lifecycle.js?
  29. (Stage 11) Does registerEvidence() still perform a content-hash reuse check before
      creating a new record?
  30. (Stage 11) Do updateEvidence()/supersedeEvidence() still reindex after a mutation?
  31. (Stage 11) Does every EVIDENCE_RELATIONSHIP_FIELDS entry have a corresponding index
      dimension in indexes.js?
  32. (Stage 11) Does supersede() still stamp superseded_at on the outgoing historical version?
  33. (Stage 11) Does registerEvidence() still index every record it creates?
  34. (Stage 11) Does the full Stage 11 EER file set exist, and does none of it import a live
      pNN-handlers.js/index.js file?

  35. (Stage 12) Does any file outside evidence-service.js define its own `class
      EvidenceService` (duplicate service)?
  36. (Stage 12) Does any file outside service-contracts.js export its own copy of the five
      named contract constants (duplicate contracts)?
  37. (Stage 12) Does each of the five contracts' declared `version` still match its own
      `history` array's last entry (version drift)?
  38. (Stage 12) Do any Stage 12 files reach into EvidenceRegistry's private fields directly
      instead of calling its public API (registry bypass)?
  39. (Stage 12) Does relationship-resolution.js still avoid importing p31-handlers.js (or any
      live handler/index.js file), and does it still throw rather than silently return empty
      data when no provider is injected (relationship bypass  -  ADR-0010 is not Accepted)?
  40. (Stage 12) Does EvidenceValidationService still delegate to registry.validateEvidence()
      and validation.js's validateEvidenceBatch() rather than reimplementing either
      (validation bypass)?
  41. (Stage 12) Does the full Stage 12 EESP file set still exist, and does none of it import
      a live pNN-handlers.js/index.js file (architecture violations)?

  42. (Stage 14) Does the full Stage 14 EIG file set still exist, and does none of it import a
      live pNN-handlers.js/index.js file (architecture violations)?
  43. (Stage 14) Does any file outside its own canonical file define its own copy of
      EnterpriseGateway/GatewayContext/GatewayRegistry/GatewayDispatcher/GatewayLifecycle/
      GatewayMetrics (duplicate engines)?
  44. (Stage 14) Do gateway-service.js's 8 pre-registered capabilities still delegate to
      IntelligenceService's own public properties rather than reimplementing any of their
      logic (reuse bypass)?
  45. (Stage 14) Does each of the 4 EIG contracts' declared `version` still match its own
      `history` array's last entry (version drift)?
  46. (Stage 14) Does any file outside service-contracts.js export its own copy of the 4 named
      EIG contract constants (duplicate contracts)?
  47. (Stage 14) Do any EIG files reach into GatewayRegistry's/GatewayMetrics's private fields
      directly instead of calling their public API (registry bypass)?
  48. (Stage 14) Does the evidence.relationships capability still target
      RelationshipResolutionService's pass-through-only surface, and does gateway-service.js
      still document the ADR-0010 gate (ADR-0010 governance — ADR-0010 is not Accepted)?
  49. (Stage 14) Does the intelligence.validation capability still target
      IntelligenceValidationService, and has gateway-middleware.js's own validation stage
      avoided growing evidence/intelligence DATA-validation-shaped logic of its own
      (validation bypass)?
  50. (Stage 14) Does EnterpriseGateway's constructor still resolve _platform first, derive
      serviceMetrics from its sharedServiceMetrics rather than constructing a fresh
      ServicePlatformMetrics, guard a mismatched explicit deps.serviceMetrics, and thread that
      one instance into both GatewayMetrics and GatewayDispatcher (duplicate metrics instance
      — the exact bug class this stage's own brief names)?
  51. (Stage 14) Does any intelligence-platform/ or evidence-registry/ PRODUCTION file
      reference enterprise-gateway/ (circular dependency)?
  52. (Stage 14) Does GatewayDispatcher still perform a real capability-authorization check
      before invoking a handler (governance expansion — no Stage 12/13 precedent)?
  53. (Stage 14) Has any EIG file started reaching for network-auth-shaped primitives (a live
      fetch handler, Request/Response construction, ADMIN_SECRET, a JWT library) — scope
      creep against this stage's own documented in-process/DI-only boundary (no Stage 12/13
      precedent)?
  54. (Stage 14 Phase 2) Do GatewayRegistry.describe()/.describeAll() — the read-only capability
      metadata accessors added for registry-maturity introspection — still exist in the
      expected shape and still omit the raw handler function from their return value?
  55. (Stage 15) Does any scripts/ consumer import intelligence-platform/ directly
      (createIntelligencePlatform) without also composing through enterprise-gateway/, beyond
      the one tracked, already-deprecated Stage 13 exception (Gateway bypass)?
  56. (Stage 17) Do correlation-policy.js and explainability-engine.js still exist and still
      avoid importing a live pNN-handlers.js/index.js file directly?
  57. (Stage 17) Does any file outside intelligence-platform/ define its own
      'class IntelligenceExplainabilityService' (duplicate engine)?
  58. (Stage 17) Do correlation-policy.js/explainability-engine.js still avoid defining a new
      compute*/score*/weight*/rank*Confidence* function — the ADR-0007 boundary (Proposed, not
      Accepted) made mechanically enforceable?
  59. (Stage 17) Does index.js still have zero references to explainability-engine.js,
      correlation-policy.js, or IntelligenceExplainabilityService (still unwired)?
  60. (Stage 17) Does correlation-policy.js still export CORRELATION_POLICY_VERSION and
      describePolicy() (policies must be versioned and auditable)?
  61. (Stage 18) Does the full Stage 18 knowledge-platform/ file set still exist, and does none
      of it import a live pNN-handlers.js/index.js file (architecture violations)?
  62. (Stage 18) Does any file outside its own canonical file define its own copy of
      KnowledgeObjectService/KnowledgeNavigationService/AnalystViewService/ExecutiveViewService/
      KnowledgeQualityService/KnowledgePlatform (duplicate engines)?
  63. (Stage 18) Do knowledge-platform/ files still avoid defining a new compute*/score*/weight*/
      rank*Confidence* function -- the same ADR-0007 boundary (Proposed, not Accepted) Stage 17's
      check #58 enforces on intelligence-platform/, mechanically enforced here too?
  64. (Stage 18) Does index.js, gateway-service.js, and intelligence-service.js still have zero
      references to "knowledge-platform"/"KnowledgePlatform" (still unwired)?
  65. (Stage 19) Does the full Stage 19 product-platform/ file set still exist, and does none of
      it import a live pNN-handlers.js/index.js file (architecture violations)?
  66. (Stage 19) Does any file outside its own canonical file define its own copy of
      ProductEngineService/ProductProfileService/ProductPackagingService/ProductQualityService/
      ProductPlatform (duplicate engines)?
  67. (Stage 19) Do product-platform/ files still avoid defining a new compute*/score*/weight*/
      rank*Confidence* function -- the same ADR-0007 boundary (Proposed, not Accepted) Stage
      17/18's checks #58/#63 enforce, mechanically enforced here too?
  68. (Stage 19) Does index.js, gateway-service.js, intelligence-service.js, and
      knowledge-platform.js still have zero references to "product-platform"/"ProductPlatform"
      (still unwired)?
  69. (Stage 19) Does any product-platform/ production file reference the Python dossier/report
      pipeline (report_generator.py, dynamic_dossier_engine.py, dossier_quality_engine.py,
      generate_intel_reports.py) by name -- the re-verified architectural boundary from
      TITAN_STAGE19_READINESS_REPORT.md Sec 2.3, made mechanically enforceable?

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

    # Stage 13: intelligence-platform/ is the first explicitly-authorized consumer of this
    # scaffolding (its own brief requires composing EvidenceService/EvidenceQueryEngine/
    # EvidenceProvenanceEngine/RelationshipResolutionService — see
    # TITAN_STAGE13_SERVICE_ARCHITECTURE.md). This does not weaken what check 1 below actually
    # protects: evidence-registry/ still must not be reachable from index.js or any
    # pNN-handlers.js file — see check_eips_files_present_and_isolated() and
    # check_no_circular_dependency_intelligence_evidence_registry() below, plus
    # intelligence-platform/__tests__/zero-blast-radius.test.js's independent Node-side
    # verification of the same property. Exempting this one named, documented directory --
    # rather than relaxing the check generally -- keeps it able to catch any OTHER,
    # unauthorized reference. Mirrors the identical, symmetric fix already applied to
    # evidence-registry/__tests__/zero-blast-radius.test.js.
    #
    # Stage 14: enterprise-gateway/ is added for the same test-fixture-construction reason its
    # Node-side counterpart (evidence-registry/__tests__/zero-blast-radius.test.js's own
    # AUTHORIZED_CONSUMER_DIRS) was updated for — its PRODUCTION code composes only
    # intelligence-platform/'s IntelligenceService, one hop up (see its own
    # TITAN_STAGE14_SERVICE_ARCHITECTURE.md and independent zero-blast-radius test); what trips
    # this sweep is enterprise-gateway/__tests__/test-helpers.js importing
    # evidence-registry/entity.js to build fixtures, identical to intelligence-platform's own
    # test-helpers.js one directory up. This Python check and the Node test above are two
    # independently-maintained mechanisms for the same property (a pre-existing duplication,
    # not introduced here) — kept in sync by hand, same as this addition does.
    #
    # Stage 16: relationship-framework/ is added because ADR-0010 (a DIFFERENT ADR from the
    # ADR-0008 this check's own finding message names) is now Accepted. Its production code
    # imports exactly one evidence-registry/ file, relationship-resolution.js's
    # RelationshipProviderInterface (relationship-provider.js's P31RelationshipProvider
    # implements it) — the same single-file shape intelligence-service.js itself already uses.
    # This exemption does not touch what this check's finding message still correctly warns
    # about: wiring evidence-registry/ itself into a live pNN-handlers.js/index.js route still
    # requires ADR-0008 (separately, already Accepted, but not yet exercised for production
    # wiring by any stage including this one).
    #
    # Stage 18: knowledge-platform/ is added for the same test-fixture-construction reason as
    # intelligence-platform/enterprise-gateway above — its own __tests__/test-helpers.js imports
    # evidence-registry/entity.js to build CanonicalEvidence fixtures. Its PRODUCTION code does
    # not import evidence-registry/ at all (it composes only intelligence-platform/'s
    # IntelligenceService properties, one hop up, per TITAN_STAGE18_READINESS_REPORT.md and its
    # own independent zero-blast-radius test); what trips this sweep is JSDoc @param/@returns
    # type references to evidence-registry/entity.js's CanonicalEvidence and
    # evidence-registry/service-metrics.js's ServicePlatformMetrics types (comments only, not
    # runtime imports) plus this directory's own zero-blast-radius.test.js/test-helpers.js
    # naming "evidence-registry" for the identical boundary-documentation reason already
    # exempted for the other three consumers.
    #
    # Stage 19: product-platform/ is added for the identical JSDoc-comment reason as
    # knowledge-platform above — its own production files' @param/@returns type comments cite
    # evidence-registry/service-metrics.js's ServicePlatformMetrics type. Its PRODUCTION code
    # does not import evidence-registry/ at all (it composes only knowledge-platform/'s
    # KnowledgePlatform properties, one hop up, per TITAN_STAGE19_READINESS_REPORT.md and its
    # own independent zero-blast-radius test).
    authorized_consumer_dirs = [
        HANDLERS_DIR / "intelligence-platform",
        HANDLERS_DIR / "enterprise-gateway",
        HANDLERS_DIR / "relationship-framework",
        HANDLERS_DIR / "knowledge-platform",
        HANDLERS_DIR / "product-platform",
    ]

    # 1. Nothing outside evidence-registry/ (or an authorized consumer) may import from it.
    for path in HANDLERS_DIR.rglob("*.js"):
        if scaffold_dir in path.parents or path.parent == scaffold_dir:
            continue
        if any(consumer_dir in path.parents or path.parent == consumer_dir for consumer_dir in authorized_consumer_dirs):
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


# ---------------------------------------------------------------------------------------
# Stage 10 additions — Canonical Evidence Core (CEC) governance. Stage 10 Phases 1-9 added a
# second canonical domain-model type (CanonicalEvidence, entity.js) alongside the
# CanonicalRelationship schema Stage 9 Phase 2 already governs above. Same rationale as every
# prior stage's additions: a domain model this young accumulates duplicate/drifted
# implementations fastest before its discipline is habitual, so these checks exist before
# evidence of a real violation, not after. All Stage 10 code lives inside
# workers/intel-gateway/src/evidence-registry/, already covered by
# check_evidence_registry_scaffolding_boundary()'s two boundary checks (Stage 8) above — these
# eight checks are additive, narrower checks specific to the CEC's own internal consistency, not
# a replacement for that boundary check. See TITAN_STAGE10_ENGINEERING_SPECIFICATION.md.
# ---------------------------------------------------------------------------------------

EVIDENCE_REGISTRY_DIR = HANDLERS_DIR / "evidence-registry"

CEC_CORE_FILES = [
    "entity.js",
    "identifiers.js",
    "validation.js",
    "interfaces.js",
    "serialization.js",
    "migration-adapters.js",
    "schema.js",
    "feature-flags.js",
    "repository-interface.js",
]


def check_no_duplicate_evidence_domain_model() -> list[str]:
    """Duplicate evidence models: confirms entity.js remains the SOLE definer of
    createCanonicalEvidence/CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION — the same "one canonical
    source per capability" property check_for_unreviewed_new_scorers() already enforces for
    confidence/evidence *functions* on the P-layer side, applied here to the CEC's own *domain
    model*. A second definition anywhere else in workers/intel-gateway/src would mean two
    authoritative shapes for the same concept, which Single Source of Truth (Principle 3)
    forbids."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for path in HANDLERS_DIR.rglob("*.js"):
        if path.parent == EVIDENCE_REGISTRY_DIR and path.name == "entity.js":
            continue  # the one authorized definition
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"\bfunction\s+createCanonicalEvidence\s*\(", text) or re.search(
            r"\bCANONICAL_EVIDENCE_CORE_SCHEMA_VERSION\s*=", text
        ):
            findings.append(
                f"DUPLICATE EVIDENCE MODEL: {path.relative_to(ROOT)} defines its own "
                f"createCanonicalEvidence / CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION — "
                f"evidence-registry/entity.js is the sole authorized definition (Stage 10 "
                f"Phase 1). Import from there instead of re-implementing."
            )
    return findings


def check_cec_schema_version_intact() -> list[str]:
    """Schema drift: confirms schema.js's SCHEMA_VERSION_HISTORY still references both the
    Stage 8 and Stage 10 schema version constants by name, and that entity.js still defines
    CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION as a string literal. schema.js imports these
    constants from entity.js rather than re-typing their string values (Single Source of
    Truth), so this check looks for the imported symbol names being referenced, not for the
    literal string values to appear a second time — mirrors
    check_relationship_schema_spec_intact()'s pattern for the relationship schema."""
    findings = []
    entity_js = EVIDENCE_REGISTRY_DIR / "entity.js"
    schema_js = EVIDENCE_REGISTRY_DIR / "schema.js"
    if not (entity_js.exists() and schema_js.exists()):
        return findings
    entity_text = entity_js.read_text(encoding="utf-8", errors="replace")
    schema_text = schema_js.read_text(encoding="utf-8", errors="replace")

    if not re.search(r'CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION\s*=\s*"[^"]+"', entity_text):
        findings.append(
            "SCHEMA DRIFT: entity.js no longer defines CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION "
            "as a string literal — schema.js's generated documentation depends on importing it."
        )
    for symbol in ("EVIDENCE_ENTITY_SCHEMA_VERSION", "CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION"):
        if symbol not in schema_text:
            findings.append(
                f"SCHEMA DRIFT: schema.js's SCHEMA_VERSION_HISTORY no longer references "
                f"{symbol} — history entries are additive-only (Deprecation Instead of "
                f"Deletion applies to schema history too); every schema version bump must add "
                f"a new history entry, not replace an earlier one."
            )
    return findings


def check_version_field_falsy_zero_regression() -> list[str]:
    """Version conflicts: guards against regression of a real bug this stage found and fixed —
    createCanonicalEvidence() originally used `extension.version || 1`, which incorrectly
    treats an explicit `version: 0` as absent and silently substitutes 1, which would mask a
    real version conflict a caller passed (validateEvidenceBatch's whole job is detecting
    exactly that). Fixed to `extension.version !== undefined ? extension.version : 1`. This
    check exists so a future edit doesn't reintroduce the `||` form, the same rationale as
    check_r1_internal_relationship_shape_consistency's standing-finding pattern above."""
    findings = []
    entity_js = EVIDENCE_REGISTRY_DIR / "entity.js"
    if not entity_js.exists():
        return findings
    text = entity_js.read_text(encoding="utf-8", errors="replace")
    if re.search(r"version:\s*extension\.version\s*\|\|\s*1\b", text):
        findings.append(
            "VERSION CONFLICT RISK: entity.js's createCanonicalEvidence() uses "
            "`extension.version || 1` again — this treats an explicit `version: 0` as absent "
            "(JS falsy-zero), silently masking what should be a detectable version conflict. "
            "Use `extension.version !== undefined ? extension.version : 1` instead."
        )
    return findings


def check_evidence_validation_pipeline_present() -> list[str]:
    """Missing validation: confirms the validation pipeline Phases 3/4 built is still actually
    composed, not silently bypassed — interfaces.js's EvidenceValidatorInterface must still
    delegate to validation.js's functions, and serialization.js's DefaultEvidenceImporter must
    still validate before accepting an import (Phase 5's own stated contract: "deserialize then
    validate"). A regression here would mean invalid evidence could be imported without any
    validation ever running."""
    findings = []
    interfaces_js = EVIDENCE_REGISTRY_DIR / "interfaces.js"
    serialization_js = EVIDENCE_REGISTRY_DIR / "serialization.js"
    validation_js = EVIDENCE_REGISTRY_DIR / "validation.js"
    if not (interfaces_js.exists() and serialization_js.exists() and validation_js.exists()):
        return findings

    validation_text = validation_js.read_text(encoding="utf-8", errors="replace")
    for fn in ("validateCanonicalEvidence", "validateEvidenceBatch"):
        if f"export function {fn}" not in validation_text:
            findings.append(
                f"MISSING VALIDATION: validation.js no longer exports {fn}() — Stage 10 "
                f"Phase 4's validation engine requires it."
            )

    interfaces_text = interfaces_js.read_text(encoding="utf-8", errors="replace")
    if "validateCanonicalEvidence" not in interfaces_text or "validateEvidenceBatch" not in interfaces_text:
        findings.append(
            "MISSING VALIDATION: interfaces.js's EvidenceValidatorInterface no longer "
            "references validation.js's functions — the interface must delegate to the "
            "canonical validators (Reuse Before Build), not silently no-op."
        )

    serialization_text = serialization_js.read_text(encoding="utf-8", errors="replace")
    if "validateCanonicalEvidence" not in serialization_text:
        findings.append(
            "MISSING VALIDATION: serialization.js's DefaultEvidenceImporter no longer "
            "references validateCanonicalEvidence — Phase 5's contract is 'deserialize then "
            "validate'; an importer that skips validation would accept structurally invalid "
            "evidence."
        )
    return findings


def check_migration_adapters_intact() -> list[str]:
    """Adapter regressions: confirms all four Phase 7 migration adapters still exist AND still
    avoid importing a live pNN-handlers.js/index.js file — the latter is the specific "zero
    blast radius regardless of adapter sophistication" design property migration-adapters.js's
    own file-level docstring claims (also smoke-tested from the Node side by
    internal-integration-smoke.test.js; this is the authoritative CI-side check, since CI runs
    this Python script on every build, not necessarily `node --test`)."""
    findings = []
    adapters_js = EVIDENCE_REGISTRY_DIR / "migration-adapters.js"
    if not adapters_js.exists():
        return findings
    text = adapters_js.read_text(encoding="utf-8", errors="replace")

    for adapter_class in (
        "P20EvidenceChainAdapter",
        "CanonicalRelationshipAdapter",
        "P25ConfidenceAdapter",
        "ReportItemAdapter",
    ):
        if f"class {adapter_class}" not in text:
            findings.append(
                f"ADAPTER REGRESSION: migration-adapters.js no longer defines {adapter_class} "
                f"— Stage 10 Phase 7 requires all four named migration adapters (Legacy "
                f"Evidence Objects, Existing Report Structures, Existing Graph/Relationship "
                f"Structures, Existing Confidence Objects)."
            )

    if re.search(r'(?:from|require\()\s*["\'][^"\']*-handlers(?:\.js)?["\']', text):
        findings.append(
            "ADAPTER REGRESSION: migration-adapters.js now imports a pNN-handlers.js file "
            "directly — this breaks the documented design property that these adapters "
            "operate on data shapes only, never on a live handler import, which is what keeps "
            "adopting them a zero-blast-radius change regardless of adapter complexity."
        )
    return findings


def check_cec_feature_flags_disabled() -> list[str]:
    """Feature-flag violations: confirms Stage 10 Phase 6's CEC_FLAGS still default the
    canary/production environments to disabled, and that EVIDENCE_REGISTRY_FLAGS (Stage 8,
    still the only flag that gates real production wiring) hasn't drifted. Mirrors
    check_evidence_registry_scaffolding_boundary()'s existing SCAFFOLDING_ENABLED check,
    extended to the two new CEC_FLAGS environments that actually matter for a rollback
    scenario."""
    findings = []
    flags_js = EVIDENCE_REGISTRY_DIR / "feature-flags.js"
    if not flags_js.exists():
        return findings
    text = flags_js.read_text(encoding="utf-8", errors="replace")

    if "SCAFFOLDING_ENABLED: false" not in text:
        findings.append(
            "FEATURE-FLAG VIOLATION: feature-flags.js's SCAFFOLDING_ENABLED no longer defaults "
            "to false (also checked by check_evidence_registry_scaffolding_boundary() above; "
            "flagged here too since Stage 10 specifically extends this same file)."
        )

    canary_match = re.search(r"canary:\s*Object\.freeze\(\{\s*CEC_ENABLED:\s*(\w+)", text)
    production_match = re.search(r"production:\s*Object\.freeze\(\{\s*CEC_ENABLED:\s*(\w+)", text)
    if canary_match and canary_match.group(1) != "false":
        findings.append(
            "FEATURE-FLAG VIOLATION: feature-flags.js's CEC_FLAGS.canary.CEC_ENABLED is not "
            "'false' — canary must stay disabled until a separately-authorized rollout stage "
            "(Stage 10 Phase 6: Canary/Production tiers are 'all disabled by default')."
        )
    if production_match and production_match.group(1) != "false":
        findings.append(
            "FEATURE-FLAG VIOLATION: feature-flags.js's CEC_FLAGS.production.CEC_ENABLED is "
            "not 'false' — production must stay disabled until a separately-authorized "
            "rollout stage."
        )
    return findings


def check_serialization_future_formats_still_stubbed() -> list[str]:
    """Serialization drift: confirms getSerializer() still refuses to silently succeed for
    'stix'/'api' — Phase 5's explicit instruction was "Future STIX compatibility, Future API
    compatibility... Do not expose public APIs yet." A regression where either format silently
    returns a working serializer instead of throwing would mean this stage started exposing a
    public-API-shaped capability without the separate authorization Phase 5 deferred it
    behind."""
    findings = []
    serialization_js = EVIDENCE_REGISTRY_DIR / "serialization.js"
    if not serialization_js.exists():
        return findings
    text = serialization_js.read_text(encoding="utf-8", errors="replace")

    if not re.search(r'case\s+"stix"\s*:\s*\n\s*case\s+"api"\s*:\s*\n\s*throw', text):
        findings.append(
            "SERIALIZATION DRIFT: serialization.js's getSerializer() no longer throws for "
            "'stix'/'api' as named-future-capability stubs — verify neither format now returns "
            "a working serializer ahead of its separate authorization (Phase 5's own scope "
            "boundary: 'Do not expose public APIs yet')."
        )
    for fmt in ("json", "markdown", "dto"):
        if f'"{fmt}"' not in text:
            findings.append(
                f"SERIALIZATION DRIFT: serialization.js no longer references the '{fmt}' "
                f"format — Phase 5 requires JSON, Markdown, and internal DTO support."
            )
    return findings


def check_cec_files_present() -> list[str]:
    """Architecture violations: confirms every Stage 10 CEC file Phases 1-7 introduced still
    exists — no silent deletion (Deprecation Instead of Deletion applies here too). A coarse
    safety net alongside the more targeted symbol-level checks above, since those check specific
    exports/classes but not whole-file presence for files like schema.js or
    repository-interface.js that no other check here inspects directly."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for filename in CEC_CORE_FILES:
        if not (EVIDENCE_REGISTRY_DIR / filename).exists():
            findings.append(
                f"ARCHITECTURE VIOLATION: evidence-registry/{filename} is missing — Stage 10 "
                f"requires it (see TITAN_STAGE10_ENGINEERING_SPECIFICATION.md). If "
                f"intentionally removed, that is a breaking change requiring the Deprecation "
                f"Instead of Deletion protocol, not silent removal."
            )
    return findings


# ---------------------------------------------------------------------------------------
# Stage 11 additions — Enterprise Evidence Registry (EER) governance. Stage 11 Phases 1-7
# activated the Canonical Evidence Core (Stage 10) with a working internal registry service
# (registry-service.js), repository (in-memory-repository.js), lifecycle engine (lifecycle.js),
# version manager (versioning.js), and indexes (indexes.js) — all still inert (zero imports
# from index.js or any pNN-handlers.js). These nine checks cover the categories Phase 8's own
# charter named: duplicate registry entries, version conflicts, lifecycle violations, evidence
# duplication, broken references, missing relationships, invalid supersession, orphaned
# evidence, architecture violations. Unlike Stage 10's checks (which mostly guarded static
# domain-model shape), several of these are regression guards for specific MECHANISMS this
# stage's own test suite proved matter (e.g. index staleness after an edit, version-conflict
# masking) — the same "guard the exact bug class this stage found" pattern
# check_r1_internal_relationship_shape_consistency and
# check_version_field_falsy_zero_regression established above. There is no persisted registry
# data file to inspect (nothing is wired live; the reference repository is in-memory only), so
# these checks are necessarily source-level, mirroring every other check in this script.
# See TITAN_STAGE11_REGISTRY_ARCHITECTURE.md.
# ---------------------------------------------------------------------------------------

EER_CORE_FILES = [
    "registry-repository-interface.js",
    "in-memory-repository.js",
    "lifecycle.js",
    "versioning.js",
    "indexes.js",
    "registry-metrics.js",
    "registry-service.js",
]


def check_no_duplicate_evidence_registry() -> list[str]:
    """Duplicate registry entries: confirms registry-service.js remains the SOLE definer of
    `class EvidenceRegistry` — the same "one canonical source per capability" property
    check_no_duplicate_evidence_domain_model() already enforces for the CEC domain model,
    applied here to the registry SERVICE ("One Evidence Registry")."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for path in HANDLERS_DIR.rglob("*.js"):
        if path.parent == EVIDENCE_REGISTRY_DIR and path.name == "registry-service.js":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"\bclass\s+EvidenceRegistry\b", text):
            findings.append(
                f"DUPLICATE REGISTRY: {path.relative_to(ROOT)} defines its own "
                f"'class EvidenceRegistry' — evidence-registry/registry-service.js is the sole "
                f"authorized definition (Stage 11 Phase 1, 'One Evidence Registry')."
            )
    return findings


def check_registry_version_arithmetic_safe() -> list[str]:
    """Version conflicts: guards against the same class of bug check_version_field_falsy_zero_
    regression() guards against in entity.js, this time in in-memory-repository.js's version-
    bump arithmetic (nextVersion() / computeNextVersion()). `current.version || 1` would
    silently treat version 0 as absent and mask a real version conflict."""
    findings = []
    repo_js = EVIDENCE_REGISTRY_DIR / "in-memory-repository.js"
    if not repo_js.exists():
        return findings
    text = repo_js.read_text(encoding="utf-8", errors="replace")
    if re.search(r"current\.version\s*\|\|\s*1\b", text):
        findings.append(
            "VERSION CONFLICT RISK: in-memory-repository.js's version-bump arithmetic uses "
            "`current.version || 1` — this treats an explicit `version: 0` as absent (JS "
            "falsy-zero), silently masking what should be a detectable version conflict. Use "
            '`typeof current.version === "number" ? current.version : 1` instead.'
        )
    return findings


def check_lifecycle_terminal_states_intact() -> list[str]:
    """Lifecycle violations: confirms ARCHIVED and REJECTED remain terminal (zero legal
    outgoing transitions) in lifecycle.js, and that registry-service.js still enforces
    transitions through lifecycle.js's assertValidTransition rather than mutating lifecycle
    state directly — "Every transition must be validated... Illegal transitions must fail" only
    holds if the one enforcement point is actually on the call path."""
    findings = []
    lifecycle_js = EVIDENCE_REGISTRY_DIR / "lifecycle.js"
    registry_js = EVIDENCE_REGISTRY_DIR / "registry-service.js"
    if not (lifecycle_js.exists() and registry_js.exists()):
        return findings
    lifecycle_text = lifecycle_js.read_text(encoding="utf-8", errors="replace")
    for terminal in ("ARCHIVED", "REJECTED"):
        if not re.search(rf"{terminal}:\s*Object\.freeze\(\[\]\)", lifecycle_text):
            findings.append(
                f"LIFECYCLE VIOLATION: lifecycle.js's {terminal} state no longer has zero "
                f"legal outgoing transitions — Phase 3 requires ARCHIVED and REJECTED to be "
                f"terminal."
            )
    registry_text = registry_js.read_text(encoding="utf-8", errors="replace")
    if "assertValidTransition" not in registry_text:
        findings.append(
            "LIFECYCLE VIOLATION: registry-service.js no longer references "
            "assertValidTransition — a mutation path that changes lifecycle state without "
            "going through lifecycle.js's validated transition graph would let illegal "
            "transitions succeed silently."
        )
    return findings


def check_evidence_duplication_guard_intact() -> list[str]:
    """Evidence duplication: confirms registerEvidence()'s cross-report reuse check (Phase 7 —
    content-hash lookup before create) is still present in registry-service.js. Without it,
    registering the same substantive evidence twice would silently create two records instead
    of returning the existing one."""
    findings = []
    registry_js = EVIDENCE_REGISTRY_DIR / "registry-service.js"
    if not registry_js.exists():
        return findings
    text = registry_js.read_text(encoding="utf-8", errors="replace")
    if "findByContentHash" not in text:
        findings.append(
            "EVIDENCE DUPLICATION RISK: registry-service.js's registerEvidence() no longer "
            "calls findByContentHash — the cross-report reuse check (Phase 7, 'No "
            "duplication') would be silently bypassed, allowing duplicate registration of the "
            "same substantive evidence under different evidence_uuids."
        )
    return findings


def check_index_reindexing_on_mutation_intact() -> list[str]:
    """Broken references: confirms updateEvidence() and supersedeEvidence() still call
    indexes.reindex() after a content-changing mutation. Without it, an edit that removes a
    relationship (e.g. a corrected CVE reference) would leave the OLD reference findable via
    findByCVE() pointing at evidence that no longer actually references it — a broken/stale
    reference, exactly the regression indexes.test.js's reindex() test guards against at the
    unit level."""
    findings = []
    registry_js = EVIDENCE_REGISTRY_DIR / "registry-service.js"
    if not registry_js.exists():
        return findings
    text = registry_js.read_text(encoding="utf-8", errors="replace")
    if text.count("_indexes.reindex(") < 2:
        findings.append(
            "BROKEN REFERENCE RISK: registry-service.js calls `_indexes.reindex(` fewer than "
            "2 times — Phase 1's updateEvidence() and supersedeEvidence() must each reindex "
            "after mutating evidence content, or stale related_* associations will linger in "
            "the registry's indexes after an edit."
        )
    return findings


def check_relationship_fields_and_indexes_in_sync() -> list[str]:
    """Missing relationships: confirms every field in entity.js's EVIDENCE_RELATIONSHIP_FIELDS
    has a corresponding index dimension in indexes.js. If a future stage adds an 8th related_*
    field to the CEC domain model without adding its index, that field becomes silently
    unqueryable through the registry's named finders — this check catches that drift at the
    point it's introduced, the same rationale as every other "N and M must stay in sync" check
    in this script."""
    findings = []
    entity_js = EVIDENCE_REGISTRY_DIR / "entity.js"
    indexes_js = EVIDENCE_REGISTRY_DIR / "indexes.js"
    if not (entity_js.exists() and indexes_js.exists()):
        return findings
    entity_text = entity_js.read_text(encoding="utf-8", errors="replace")
    indexes_text = indexes_js.read_text(encoding="utf-8", errors="replace")

    match = re.search(r"EVIDENCE_RELATIONSHIP_FIELDS\s*=\s*Object\.freeze\(\[(.*?)\]\)", entity_text, re.DOTALL)
    if not match:
        findings.append(
            "MISSING RELATIONSHIPS: entity.js no longer defines EVIDENCE_RELATIONSHIP_FIELDS "
            "in the expected shape — indexes.js's sync with it cannot be verified."
        )
        return findings
    fields = re.findall(r'"(related_\w+)"', match.group(1))
    for field in fields:
        if field not in indexes_text:
            findings.append(
                f"MISSING RELATIONSHIP INDEX: entity.js's EVIDENCE_RELATIONSHIP_FIELDS "
                f"includes '{field}' but indexes.js has no reference to it — Stage 11 Phase 5 "
                f"requires every relationship field to have a corresponding registry index "
                f"dimension."
            )
    return findings


def check_supersession_stamps_superseded_at() -> list[str]:
    """Invalid supersession: confirms in-memory-repository.js's supersede() still stamps a
    superseded_at timestamp on the outgoing historical version. Without it, a superseded
    version would be indistinguishable from a plain updated version in the lineage — the exact
    distinction getSupersededVersions() (versioning.js) depends on to exist."""
    findings = []
    repo_js = EVIDENCE_REGISTRY_DIR / "in-memory-repository.js"
    if not repo_js.exists():
        return findings
    text = repo_js.read_text(encoding="utf-8", errors="replace")
    if "superseded_at" not in text:
        findings.append(
            "INVALID SUPERSESSION: in-memory-repository.js no longer references "
            "'superseded_at' — supersede() must stamp the outgoing historical version with it "
            "so getSupersededVersions() can distinguish a supersession from a plain update."
        )
    return findings


def check_registration_always_indexes_evidence() -> list[str]:
    """Orphaned evidence: confirms registerEvidence() still calls indexes.index() on the record
    it just created. Evidence stored via the repository but never indexed would be retrievable
    only by exact evidence_uuid (getEvidence()) — orphaned from every named finder
    (findByCVE/findByThreatActor/etc.), silently invisible to any relationship-based query."""
    findings = []
    registry_js = EVIDENCE_REGISTRY_DIR / "registry-service.js"
    if not registry_js.exists():
        return findings
    text = registry_js.read_text(encoding="utf-8", errors="replace")
    if "_indexes.index(stored)" not in text:
        findings.append(
            "ORPHANED EVIDENCE RISK: registry-service.js's registerEvidence() no longer calls "
            "`_indexes.index(stored)` — newly registered evidence would be unreachable from "
            "every named finder (findByCVE, findByThreatActor, etc.), retrievable only by "
            "exact evidence_uuid."
        )
    return findings


def check_eer_files_present_and_isolated() -> list[str]:
    """Architecture violations: confirms every Stage 11 EER file still exists (Deprecation
    Instead of Deletion — no silent removal) and that none of them imports a live
    pNN-handlers.js/index.js file — the same zero-blast-radius property
    check_migration_adapters_intact() enforces for Stage 10's migration adapters, extended to
    the full Stage 11 file set."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for filename in EER_CORE_FILES:
        path = EVIDENCE_REGISTRY_DIR / filename
        if not path.exists():
            findings.append(
                f"ARCHITECTURE VIOLATION: evidence-registry/{filename} is missing — Stage 11 "
                f"requires it (see TITAN_STAGE11_REGISTRY_ARCHITECTURE.md). If intentionally "
                f"removed, that is a breaking change requiring the Deprecation Instead of "
                f"Deletion protocol, not silent removal."
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'(?:from|require\()\s*["\'][^"\']*(?:-handlers(?:\.js)?|/index\.js)["\']', text):
            findings.append(
                f"ARCHITECTURE VIOLATION: evidence-registry/{filename} imports a pNN-handlers.js "
                f"or index.js file directly — this breaks the zero-blast-radius property every "
                f"file in this directory is required to maintain."
            )
    return findings


# ---------------------------------------------------------------------------------------
# Stage 12 additions — Enterprise Evidence Service Platform (EESP) governance. Stage 12
# Phases 1-6 built a service layer on top of Stage 11's registry: seven named services
# (evidence-service.js), a twelve-dimension query engine (query-engine.js), a six-lineage
# provenance engine (provenance-engine.js), a deliberately-scoped relationship resolution
# contract (relationship-resolution.js — no concrete P31 import, since ADR-0010 is not
# Accepted), five versioned internal contracts (service-contracts.js), and service-layer
# observability (service-metrics.js) — still fully inert (zero imports from index.js or any
# pNN-handlers.js). These seven checks cover the categories Phase 7's own charter named:
# duplicate services, duplicate contracts, version drift, registry bypass, relationship
# bypass, validation bypass, architecture drift. "Registry bypass" and "relationship bypass"
# are new categories this script has not needed before Stage 12 — Stage 8-11 only had one
# thing to avoid bypassing (the eventual live route); Stage 12 introduces a second, internal
# kind of bypass (reaching around EvidenceRegistry's public API into its private fields, or
# around relationship-resolution.js's contract into a direct P31 import) that matters even
# though nothing here is wired live yet. See TITAN_STAGE12_SERVICE_ARCHITECTURE.md.
# ---------------------------------------------------------------------------------------

EESP_CORE_FILES = [
    "evidence-service.js",
    "query-engine.js",
    "provenance-engine.js",
    "relationship-resolution.js",
    "service-contracts.js",
    "service-metrics.js",
]

# Private fields only EvidenceRegistry (registry-service.js) itself may access. Any other
# file under evidence-registry/ referencing these by name is reaching around the registry's
# public API — Stage 12's own services are built specifically to avoid this (see
# evidence-service.js's module docstring), so a new file doing it would be a real regression.
REGISTRY_PRIVATE_FIELDS = ["_repository", "_versionManager", "_indexes", "_metrics", "_lifecycleStates", "_lifecycleAuditTrail"]


def check_no_duplicate_evidence_service() -> list[str]:
    """Duplicate services: confirms evidence-service.js remains the SOLE definer of
    `class EvidenceService` — the same "one canonical source per capability" property
    check_no_duplicate_evidence_registry() enforces for the registry, applied here to the
    service layer ("One Evidence Service")."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for path in HANDLERS_DIR.rglob("*.js"):
        if path.parent == EVIDENCE_REGISTRY_DIR and path.name == "evidence-service.js":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"\bclass\s+EvidenceService\b", text):
            findings.append(
                f"DUPLICATE SERVICE: {path.relative_to(ROOT)} defines its own "
                f"'class EvidenceService' — evidence-registry/evidence-service.js is the sole "
                f"authorized definition (Stage 12 Phase 1, 'One Evidence Service')."
            )
    return findings


def check_no_duplicate_service_contracts() -> list[str]:
    """Duplicate contracts: confirms service-contracts.js remains the SOLE definer of each of
    the five named contract constants — "One Service Layer" implies one contract registry,
    not five scattered re-declarations."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    contract_names = ["EvidenceServiceContract", "RelationshipContract", "ProvenanceContract", "ValidationContract", "MetricsContract"]
    for path in HANDLERS_DIR.rglob("*.js"):
        if path.parent == EVIDENCE_REGISTRY_DIR and path.name == "service-contracts.js":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in contract_names:
            if re.search(rf"\bexport\s+const\s+{name}\b", text):
                findings.append(
                    f"DUPLICATE CONTRACT: {path.relative_to(ROOT)} exports its own "
                    f"'{name}' — evidence-registry/service-contracts.js is the sole authorized "
                    f"definition."
                )
    return findings


def check_contract_version_drift() -> list[str]:
    """Version drift: confirms each of the five contracts' declared `version` field matches
    the last entry in its own `history` array — the same kind of "declared version must match
    the version history's own last entry" property check_cec_schema_version_intact() verifies
    for the Evidence schema, applied here to Stage 12's five service contracts."""
    findings = []
    contracts_js = EVIDENCE_REGISTRY_DIR / "service-contracts.js"
    if not contracts_js.exists():
        return findings
    text = contracts_js.read_text(encoding="utf-8", errors="replace")
    # Each contract block: name: "X", version: "1.0.0", ... history: Object.freeze([ ... ]),
    for match in re.finditer(
        r'name:\s*"([^"]+)",\s*version:\s*"([^"]+)"'
        r'(?:(?!\}\);).)*?'
        r'history:\s*Object\.freeze\(\[(.*?)\]\),\s*\}\);',
        text,
        re.DOTALL,
    ):
        contract_name, declared_version, history_block = match.groups()
        history_versions = re.findall(r'version:\s*"([^"]+)"', history_block)
        if not history_versions:
            findings.append(f"VERSION DRIFT: {contract_name}'s history block has no parseable version entries.")
            continue
        if history_versions[-1] != declared_version:
            findings.append(
                f"VERSION DRIFT: {contract_name}'s declared version \"{declared_version}\" does not "
                f"match its own history array's last entry \"{history_versions[-1]}\"."
            )
    return findings


def check_no_registry_private_field_bypass() -> list[str]:
    """Registry bypass: confirms none of Stage 12's new files reach into EvidenceRegistry's
    private fields (_repository, _versionManager, _indexes, _metrics, _lifecycleStates,
    _lifecycleAuditTrail) directly. Every Stage 12 service is designed to call only
    EvidenceRegistry's public methods (see evidence-service.js's module docstring) — reaching
    around that public API would risk exactly the kind of divergent-state bug two separate
    EvidenceVersionManager instances over two different repository instances would produce."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for filename in EESP_CORE_FILES:
        path = EVIDENCE_REGISTRY_DIR / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for field in REGISTRY_PRIVATE_FIELDS:
            if re.search(rf"registry\.{field}\b", text) or re.search(rf"_registry\.{field}\b", text):
                findings.append(
                    f"REGISTRY BYPASS: {filename} references EvidenceRegistry's private field "
                    f"'{field}' directly — Stage 12 services must call only EvidenceRegistry's "
                    f"public methods, per this stage's own design discipline."
                )
    return findings


def check_relationship_resolution_still_unwired() -> list[str]:
    """Architecture boundary (renamed in spirit, not in name, by Stage 16 -- see
    check_relationship_framework_provider_wiring_intact() for the now-Accepted-ADR-0010 positive
    check): confirms relationship-resolution.js still does not import p31-handlers.js (or any
    pNN-handlers.js/index.js file) directly, and still has an explicit NullRelationshipProvider
    default. This invariant is intentionally independent of ADR-0010's acceptance status (now
    Accepted, Stage 16) -- it protects two separate properties that remain true regardless:
    (1) the zero-blast-radius architecture boundary check_eer_files_present_and_isolated()
    enforces for the full EER file set, and (2) good DI hygiene (an unconfigured instance should
    fail loudly, not silently). Concrete wiring now happens by INJECTING a provider
    (relationship-framework/'s P31RelationshipProvider) at a composition root, never by adding an
    import to this file -- this check keeps verifying that stays true."""
    findings = []
    path = EVIDENCE_REGISTRY_DIR / "relationship-resolution.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r'(?:from|require\()\s*["\'][^"\']*(?:p31-handlers|-handlers(?:\.js)?|/index\.js)["\']', text):
        findings.append(
            "RELATIONSHIP BYPASS: relationship-resolution.js imports a pNN-handlers.js or "
            "index.js file directly — ADR-0010 (Relationship Graph Ownership) is not Accepted; "
            "this file must remain a consumption contract only until it is. See "
            "TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md."
        )
    if "NullRelationshipProvider" not in text or "NOT_WIRED" not in text:
        findings.append(
            "RELATIONSHIP BYPASS: relationship-resolution.js no longer has an explicit "
            "unwired-by-default provider that throws rather than silently returning empty "
            "data — this was the specific safeguard against ADR-0010's Proposed status being "
            "worked around by accident."
        )
    return findings


def check_validation_service_delegates_not_reimplements() -> list[str]:
    """Validation bypass: confirms EvidenceValidationService still calls through to
    registry.validateEvidence() and validation.js's validateEvidenceBatch() rather than
    reimplementing any check inline — "One Validation Pipeline" (Stage 12's own architectural
    principle) means Stage 10's validation.js remains the only place validation rules live."""
    findings = []
    service_js = EVIDENCE_REGISTRY_DIR / "evidence-service.js"
    if not service_js.exists():
        return findings
    text = service_js.read_text(encoding="utf-8", errors="replace")
    if "this._registry.validateEvidence" not in text:
        findings.append(
            "VALIDATION BYPASS: evidence-service.js's EvidenceValidationService no longer "
            "delegates to registry.validateEvidence() — it may be reimplementing validation "
            "logic inline, violating 'One Validation Pipeline'."
        )
    if "validateEvidenceBatch" not in text:
        findings.append(
            "VALIDATION BYPASS: evidence-service.js no longer references validation.js's "
            "validateEvidenceBatch — EvidenceValidationService.validateBatch() must delegate "
            "to it, not reimplement duplicate-identifier/version-conflict checking."
        )
    return findings


def check_eesp_files_present_and_isolated() -> list[str]:
    """Architecture violations: confirms every Stage 12 EESP file still exists (Deprecation
    Instead of Deletion) and that none of them imports a live pNN-handlers.js/index.js file —
    the same zero-blast-radius property check_eer_files_present_and_isolated() enforces for
    Stage 11, extended to the full Stage 12 file set."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists():
        return findings
    for filename in EESP_CORE_FILES:
        path = EVIDENCE_REGISTRY_DIR / filename
        if not path.exists():
            findings.append(
                f"ARCHITECTURE VIOLATION: evidence-registry/{filename} is missing — Stage 12 "
                f"requires it (see TITAN_STAGE12_SERVICE_ARCHITECTURE.md). If intentionally "
                f"removed, that is a breaking change requiring the Deprecation Instead of "
                f"Deletion protocol, not silent removal."
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'(?:from|require\()\s*["\'][^"\']*(?:-handlers(?:\.js)?|/index\.js)["\']', text):
            findings.append(
                f"ARCHITECTURE VIOLATION: evidence-registry/{filename} imports a pNN-handlers.js "
                f"or index.js file directly — this breaks the zero-blast-radius property every "
                f"file in this directory is required to maintain."
            )
    return findings


# ---------------------------------------------------------------------------------------
# Stage 13 additions — Enterprise Intelligence Platform Services (EIPS) governance. Stage 13
# Phases 1-7 built workers/intel-gateway/src/intelligence-platform/, an orchestration layer
# composing Stage 12's EESP (evidence-registry/evidence-service.js, query-engine.js,
# provenance-engine.js, relationship-resolution.js) — still fully inert (zero imports from
# index.js or any pNN-handlers.js). Ten checks cover this stage's own Phase 8 charter: duplicate
# services/orchestration, duplicate query logic, registry bypass, validation bypass, contract
# drift, circular dependencies, architecture drift, plus a dedicated regression guard for the
# single-shared-ServicePlatformMetrics-instance property — the specific "metrics propagation
# bug" the interrupted prior attempt at this stage found (see the resume brief's Task 4) before
# losing the fix along with everything else uncommitted when it hit a usage limit. Codifying
# that exact bug class as a standing check, the same way check_version_field_falsy_zero_
# regression() guards Stage 10's own found-and-fixed bug, is cheap insurance against
# reintroducing it. See TITAN_STAGE13_SERVICE_ARCHITECTURE.md.
# ---------------------------------------------------------------------------------------

INTELLIGENCE_PLATFORM_DIR = HANDLERS_DIR / "intelligence-platform"

EIPS_CORE_FILES = [
    "intelligence-service.js",
    "query-service.js",
    "correlation-engine.js",
    "platform.js",
    "service-contracts.js",
    "feature-flags.js",
]


def check_eips_files_present_and_isolated() -> list[str]:
    """Architecture violations: confirms every Stage 13 EIPS file still exists (Deprecation
    Instead of Deletion — no silent removal) and that none of them imports a live
    pNN-handlers.js/index.js file directly — the same zero-blast-radius property
    check_eesp_files_present_and_isolated() enforces for Stage 12, extended to Stage 13's file
    set. (Independently re-verified from the Node side by
    intelligence-platform/__tests__/zero-blast-radius.test.js, so this property is checkable
    from either toolchain without depending on the other.)"""
    findings = []
    if not INTELLIGENCE_PLATFORM_DIR.exists():
        return findings
    for filename in EIPS_CORE_FILES:
        path = INTELLIGENCE_PLATFORM_DIR / filename
        if not path.exists():
            findings.append(
                f"ARCHITECTURE VIOLATION: intelligence-platform/{filename} is missing — Stage 13 "
                f"requires it (see TITAN_STAGE13_SERVICE_ARCHITECTURE.md). If intentionally "
                f"removed, that is a breaking change requiring the Deprecation Instead of "
                f"Deletion protocol, not silent removal."
            )
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'(?:from|require\()\s*["\'][^"\']*(?:-handlers(?:\.js)?|/index\.js)["\']', text):
            findings.append(
                f"ARCHITECTURE VIOLATION: intelligence-platform/{filename} imports a "
                f"pNN-handlers.js or index.js file directly — this breaks the zero-blast-radius "
                f"property every file in this directory is required to maintain."
            )
    return findings


def check_no_duplicate_intelligence_service() -> list[str]:
    """Duplicate services / duplicate orchestration: confirms intelligence-service.js remains
    the SOLE definer of `class IntelligenceService` (the Phase 1 facade) and
    `class ThreatIntelligenceService` — mirrors check_no_duplicate_evidence_service() one layer
    up."""
    findings = []
    if not INTELLIGENCE_PLATFORM_DIR.exists():
        return findings
    for path in HANDLERS_DIR.rglob("*.js"):
        if path.parent == INTELLIGENCE_PLATFORM_DIR and path.name == "intelligence-service.js":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for class_name in ("IntelligenceService", "ThreatIntelligenceService"):
            if re.search(rf"\bclass\s+{class_name}\b", text):
                findings.append(
                    f"DUPLICATE SERVICE: {path.relative_to(ROOT)} defines its own "
                    f"'class {class_name}' — intelligence-platform/intelligence-service.js is "
                    f"the sole authorized definition (Stage 13 Phase 1)."
                )
    return findings


def check_no_duplicate_query_logic() -> list[str]:
    """Duplicate query logic / query bypass: confirms query-service.js remains the SOLE definer
    of `class EnterpriseQueryService`, AND that its nine covered-dimension methods still
    delegate to `this._queryEngine.lookupBy*` rather than reimplementing a lookup inline —
    "One Query Engine" (Stage 12's own principle) applies transitively: Stage 13 must compose
    EvidenceQueryEngine, not grow a second query implementation next to it."""
    findings = []
    query_service_js = INTELLIGENCE_PLATFORM_DIR / "query-service.js"
    if not query_service_js.exists():
        return findings
    text = query_service_js.read_text(encoding="utf-8", errors="replace")

    for path in HANDLERS_DIR.rglob("*.js"):
        if path == query_service_js:
            continue
        try:
            other_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if re.search(r"\bclass\s+EnterpriseQueryService\b", other_text):
            findings.append(
                f"DUPLICATE SERVICE: {path.relative_to(ROOT)} defines its own "
                f"'class EnterpriseQueryService' — intelligence-platform/query-service.js is "
                f"the sole authorized definition (Stage 13 Phase 2)."
            )

    covered_dimension_calls = [
        "this._queryEngine.lookupByUuid", "this._queryEngine.lookupByReport",
        "this._queryEngine.lookupByCve", "this._queryEngine.lookupByThreatActor",
        "this._queryEngine.lookupByCampaign", "this._queryEngine.lookupByIoc",
        "this._queryEngine.lookupByConfidence", "this._queryEngine.lookupBySource",
        "this._queryEngine.lookupByAttackTechnique",
    ]
    for call in covered_dimension_calls:
        if call not in text:
            findings.append(
                f"QUERY BYPASS: query-service.js no longer calls '{call}' — EnterpriseQueryService's "
                f"covered dimensions must delegate to EvidenceQueryEngine, not reimplement lookup logic."
            )
    return findings


def check_eips_contract_version_drift() -> list[str]:
    """Contract drift: confirms each of Stage 13's six contracts' declared `version` field
    matches the last entry in its own `history` array — mirrors
    check_contract_version_drift() (Stage 12), same regex/algorithm, different file."""
    findings = []
    contracts_js = INTELLIGENCE_PLATFORM_DIR / "service-contracts.js"
    if not contracts_js.exists():
        return findings
    text = contracts_js.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(
        r'name:\s*"([^"]+)",\s*version:\s*"([^"]+)"'
        r'(?:(?!\}\);).)*?'
        r'history:\s*Object\.freeze\(\[(.*?)\]\),\s*\}\);',
        text,
        re.DOTALL,
    ):
        contract_name, declared_version, history_block = match.groups()
        history_versions = re.findall(r'version:\s*"([^"]+)"', history_block)
        if not history_versions:
            findings.append(f"VERSION DRIFT: {contract_name}'s history block has no parseable version entries.")
            continue
        if history_versions[-1] != declared_version:
            findings.append(
                f"VERSION DRIFT: {contract_name}'s declared version \"{declared_version}\" does not "
                f"match its own history array's last entry \"{history_versions[-1]}\"."
            )
    return findings


def check_no_duplicate_eips_contracts() -> list[str]:
    """Duplicate contracts: confirms intelligence-platform/service-contracts.js remains the SOLE
    `const`-definer of each of Stage 13's five genuinely-new contract constants.
    ProvenanceContract is deliberately excluded from this name list: Stage 13 imports and
    re-exports Stage 12's ProvenanceContract UNCHANGED (`export { ProvenanceContract } from
    "../evidence-registry/service-contracts.js"`, not `export const`) rather than defining a
    second one, so it correctly never matches this check's `export\\s+const` pattern in either
    file — see service-contracts.js's own module docstring for why. The other two Stage 12
    names this would otherwise collide with (ValidationContract, MetricsContract) were
    deliberately renamed to IntelligenceValidationContract/IntelligenceMetricsContract for
    exactly this reason."""
    findings = []
    if not INTELLIGENCE_PLATFORM_DIR.exists():
        return findings
    contract_names = ["IntelligenceServiceContract", "QueryContract", "CorrelationContract", "IntelligenceValidationContract", "IntelligenceMetricsContract"]
    for path in HANDLERS_DIR.rglob("*.js"):
        if path.parent == INTELLIGENCE_PLATFORM_DIR and path.name == "service-contracts.js":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name in contract_names:
            if re.search(rf"\bexport\s+const\s+{name}\b", text):
                findings.append(
                    f"DUPLICATE CONTRACT: {path.relative_to(ROOT)} exports its own '{name}' — "
                    f"intelligence-platform/service-contracts.js is the sole authorized definition."
                )
    return findings


def check_no_eips_registry_private_field_bypass() -> list[str]:
    """Registry bypass: confirms none of Stage 13's files reach into EvidenceRegistry's private
    fields directly — same REGISTRY_PRIVATE_FIELDS list check_no_registry_private_field_bypass()
    (Stage 12) already governs for evidence-registry/'s own files, extended here to Stage 13's
    directory since Stage 13 also holds registry references (via EvidenceService.registry)."""
    findings = []
    if not INTELLIGENCE_PLATFORM_DIR.exists():
        return findings
    for filename in EIPS_CORE_FILES:
        path = INTELLIGENCE_PLATFORM_DIR / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for field in REGISTRY_PRIVATE_FIELDS:
            if re.search(rf"registry\.{field}\b", text) or re.search(rf"_registry\.{field}\b", text) or re.search(rf"_evidenceService\.{field}\b", text):
                findings.append(
                    f"REGISTRY BYPASS: {filename} references EvidenceRegistry's private field "
                    f"'{field}' directly — Stage 13 services must call only EvidenceRegistry's "
                    f"and EvidenceService's public methods."
                )
    return findings


def check_intelligence_relationship_still_unwired() -> list[str]:
    """Dependency violation / relationship bypass: confirms correlation-engine.js still does not
    import p31-handlers.js (or any pNN-handlers.js/index.js file) directly, and still has no
    hardcoded relationship-graph logic of its own — mirrors
    check_relationship_resolution_still_unwired() (Stage 12) one layer up. Independent of
    ADR-0010's acceptance status (now Accepted, Stage 16): correlateByRelationship() should
    remain a pure pass-through to Stage 12's RelationshipResolutionService regardless, per
    Single Source of Truth -- this file must never grow a second relationship-resolution path
    even now that a real provider exists upstream."""
    findings = []
    path = INTELLIGENCE_PLATFORM_DIR / "correlation-engine.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r'(?:from|require\()\s*["\'][^"\']*(?:p31-handlers|-handlers(?:\.js)?|/index\.js)["\']', text):
        findings.append(
            "RELATIONSHIP BYPASS: correlation-engine.js imports a pNN-handlers.js or index.js "
            "file directly — ADR-0010 (Relationship Graph Ownership) is not Accepted; "
            "correlateByRelationship() must remain a pass-through to Stage 12's "
            "RelationshipResolutionService until it is. See TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md."
        )
    if "ADR-0010" not in text or "resolveRelationships" not in text:
        findings.append(
            "RELATIONSHIP BYPASS: correlation-engine.js no longer references ADR-0010's gating "
            "status or RelationshipResolutionService.resolveRelationships() — it may have grown "
            "independent relationship logic."
        )
    return findings


def check_intelligence_validation_delegates_not_reimplements() -> list[str]:
    """Validation bypass: confirms IntelligenceValidationService still calls through to
    EvidenceValidationService's validateEvidence()/validateBatch() rather than reimplementing
    any check inline — mirrors check_validation_service_delegates_not_reimplements() (Stage 12)
    one layer up."""
    findings = []
    service_js = INTELLIGENCE_PLATFORM_DIR / "intelligence-service.js"
    if not service_js.exists():
        return findings
    text = service_js.read_text(encoding="utf-8", errors="replace")
    if "this._evidenceValidation.validateEvidence" not in text:
        findings.append(
            "VALIDATION BYPASS: intelligence-service.js's IntelligenceValidationService no "
            "longer delegates to EvidenceValidationService.validateEvidence() — it may be "
            "reimplementing validation logic inline."
        )
    if "this._evidenceValidation.validateBatch" not in text:
        findings.append(
            "VALIDATION BYPASS: intelligence-service.js's IntelligenceValidationService no "
            "longer delegates to EvidenceValidationService.validateBatch()."
        )
    return findings


def check_eips_metrics_no_duplicate_instance() -> list[str]:
    """Service drift / duplicate metrics instance: confirms IntelligenceService's constructor
    still builds exactly ONE ServicePlatformMetrics instance and threads it into every Stage 12
    component it constructs (EvidenceService, EvidenceQueryEngine, EvidenceProvenanceEngine,
    RelationshipResolutionService) rather than letting any of them default their own — this is
    the specific bug class the prior, interrupted attempt at this stage found ("the metrics
    instance recording the flag check never actually reaches the returned service") and lost
    before committing a fix. Also confirms IntelligenceMetricsService itself defines no second
    counter object (e.g. `this._callCounts`) — it must remain a passthrough view, per
    intelligence-service.js's own module docstring. (Independently re-verified behaviorally, by
    instance identity, in intelligence-platform/__tests__/metrics-sharing.test.js.)"""
    findings = []
    service_js = INTELLIGENCE_PLATFORM_DIR / "intelligence-service.js"
    if not service_js.exists():
        return findings
    text = service_js.read_text(encoding="utf-8", errors="replace")

    # Whitespace-tolerant: exact substring matching here would produce false
    # DUPLICATE METRICS INSTANCE findings on a pure formatting change (brace spacing, wrapped
    # argument lists) — a formatter run should never fail this advisory check.
    # this._evidenceService must be resolved BEFORE serviceMetrics: an injected
    # deps.evidenceService already owns its own metrics instance, so serviceMetrics must be
    # DERIVED from it (or from the newly-constructed default), never built independently first —
    # that ordering bug is exactly what this check exists to catch (see the fix's own commit).
    if not re.search(
        r"this\._evidenceService\s*=\s*deps\.evidenceService\s*\|\|\s*new\s+EvidenceService\(\s*\{\s*"
        r"serviceMetrics:\s*deps\.serviceMetrics\s*\|\|\s*new\s+ServicePlatformMetrics\(\)\s*,?\s*\}\s*\)",
        text,
    ):
        findings.append(
            "DUPLICATE METRICS INSTANCE: intelligence-service.js's IntelligenceService "
            "constructor no longer resolves _evidenceService first, deriving its default "
            "metrics instance from deps.serviceMetrics -- an injected deps.evidenceService must "
            "own whichever ServicePlatformMetrics instance the rest of the constructor shares."
        )
    if not re.search(
        r"const\s+serviceMetrics\s*=\s*deps\.serviceMetrics\s*\|\|\s*this\._evidenceService\.metrics\.serviceMetrics",
        text,
    ):
        findings.append(
            "DUPLICATE METRICS INSTANCE: intelligence-service.js no longer derives the shared "
            "serviceMetrics from this._evidenceService.metrics.serviceMetrics -- an injected "
            "evidenceService's own metrics instance may no longer be honored, silently splitting "
            "observability in two."
        )
    if not re.search(r"this\._evidenceService\.metrics\.serviceMetrics\s*!==\s*serviceMetrics", text):
        findings.append(
            "DUPLICATE METRICS INSTANCE: intelligence-service.js no longer guards against a "
            "mismatched explicit deps.serviceMetrics + deps.evidenceService combination -- that "
            "caller error must fail loudly, not silently pick one instance over the other."
        )
    for constructor_call, pattern in [
        (
            "new EvidenceQueryEngine(this._evidenceService.registry, serviceMetrics)",
            r"new\s+EvidenceQueryEngine\(\s*this\._evidenceService\.registry\s*,\s*serviceMetrics\s*,?\s*\)",
        ),
        (
            "new EvidenceProvenanceEngine(this._evidenceService.registry, serviceMetrics)",
            r"new\s+EvidenceProvenanceEngine\(\s*this\._evidenceService\.registry\s*,\s*serviceMetrics\s*,?\s*\)",
        ),
        (
            "new RelationshipResolutionService({ metrics: serviceMetrics })",
            r"new\s+RelationshipResolutionService\(\s*\{\s*metrics:\s*serviceMetrics\s*,?\s*\}\s*\)",
        ),
    ]:
        if not re.search(pattern, text):
            findings.append(
                f"DUPLICATE METRICS INSTANCE: intelligence-service.js no longer contains "
                f"'{constructor_call}' — a component may be defaulting its own "
                f"ServicePlatformMetrics instance instead of sharing the one IntelligenceService "
                f"already built, silently splitting observability in two."
            )
    if re.search(r"class\s+IntelligenceMetricsService\b[\s\S]*?_callCounts", text):
        findings.append(
            "DUPLICATE METRICS INSTANCE: IntelligenceMetricsService appears to define its own "
            "counter state (_callCounts) — it must remain a passthrough over the shared "
            "ServicePlatformMetrics instance's own snapshot(), not a second counter set."
        )
    return findings


def check_no_circular_dependency_intelligence_evidence_registry() -> list[str]:
    """Circular dependency: confirms the one-directional import rule holds — intelligence-
    platform/ may import FROM evidence-registry/, but no evidence-registry/ PRODUCTION file
    (i.e. excluding its own __tests__, which legitimately documents Stage 13 by name in its
    authorized-exception comment — see that file) may import FROM intelligence-platform/. Same
    direction P-layers themselves are required to import in (lower layers never import higher
    ones)."""
    findings = []
    if not EVIDENCE_REGISTRY_DIR.exists() or not INTELLIGENCE_PLATFORM_DIR.exists():
        return findings
    for path in EVIDENCE_REGISTRY_DIR.rglob("*.js"):
        if path.parent.name == "__tests__":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "intelligence-platform" in text:
            findings.append(
                f"CIRCULAR DEPENDENCY: {path.relative_to(ROOT)} references intelligence-platform/ "
                f"— evidence-registry/ production files must not import from their own consumer; "
                f"this is a one-directional relationship."
            )
    return findings


def _display_path(path: Path) -> str:
    """Repo-relative path for a finding message when `path` is really under ROOT (the normal,
    non-test case); falls back to the absolute path otherwise so the check_eig_* functions stay
    safely callable against a temp-directory fixture (scripts/test_titan_stage14_governance_checks.py)
    without raising ValueError on `.relative_to(ROOT)`."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


ENTERPRISE_GATEWAY_DIR = HANDLERS_DIR / "enterprise-gateway"

EIG_CORE_FILES = [
    "gateway-context.js",
    "gateway-lifecycle.js",
    "gateway-registry.js",
    "gateway-middleware.js",
    "gateway-metrics.js",
    "gateway-dispatcher.js",
    "gateway-service.js",
    "platform.js",
    "feature-flags.js",
    "service-contracts.js",
]


def check_eig_files_present_and_isolated(gateway_dir: Path | None = None) -> list[str]:
    """Architecture violations: confirms every Stage 14 EIG file still exists (Deprecation
    Instead of Deletion — no silent removal) and that none of them imports a live
    pNN-handlers.js/index.js file directly — the same zero-blast-radius property
    enterprise-gateway/__tests__/zero-blast-radius.test.js verifies independently in Node.
    `gateway_dir` is overridable so scripts/test_titan_stage14_governance_checks.py can exercise
    this against temp-directory good/bad fixtures; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    if not gateway_dir.exists():
        return findings
    for name in EIG_CORE_FILES:
        path = gateway_dir / name
        if not path.exists():
            findings.append(f"MISSING EIG FILE: enterprise-gateway/{name} — Stage 14 file set is incomplete")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'from\s+["\'].*p\d+-handlers\.js["\']', text) or re.search(r'from\s+["\'].*/index\.js["\']', text):
            findings.append(f"ARCHITECTURE VIOLATION: enterprise-gateway/{name} imports a live pNN-handlers.js/index.js file")
    return findings


def check_no_duplicate_enterprise_gateway(handlers_dir: Path | None = None, gateway_dir: Path | None = None) -> list[str]:
    """Duplicate engines: confirms no file outside enterprise-gateway/ defines its own copy of
    any of this stage's six core classes (duplicate gateway/context/registry/dispatcher/
    lifecycle/metrics). `handlers_dir`/`gateway_dir` are overridable for fixture testing; main()
    always calls with the defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    if not gateway_dir.exists():
        return findings
    class_to_file = {
        "EnterpriseGateway": "gateway-service.js",
        "GatewayContext": "gateway-context.js",
        "GatewayRegistry": "gateway-registry.js",
        "GatewayDispatcher": "gateway-dispatcher.js",
        "GatewayLifecycle": "gateway-lifecycle.js",
        "GatewayMetrics": "gateway-metrics.js",
    }
    for class_name, canonical_file in class_to_file.items():
        pattern = re.compile(rf"\bclass\s+{class_name}\b")
        for path in handlers_dir.rglob("*.js"):
            if path.parent == gateway_dir and path.name == canonical_file:
                continue
            if path.parent.name == "__tests__":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                findings.append(
                    f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'class {class_name}' — "
                    f"the canonical implementation is enterprise-gateway/{canonical_file}"
                )
    return findings


def check_gateway_capabilities_delegate_not_reimplement(gateway_dir: Path | None = None) -> list[str]:
    """Reuse bypass: confirms gateway-service.js's 9 pre-registered capabilities (8 from Stage 14,
    plus Stage 17's intelligence.explainability) still delegate to IntelligenceService's own
    public properties (platform.lookup, .enterpriseQuery, .correlation, .validation,
    .threatIntelligence, .provenance, .relationshipResolution, .metrics, .explainability) rather
    than reimplementing any of their logic. `gateway_dir` is overridable for fixture testing;
    main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    path = gateway_dir / "gateway-service.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    required_targets = [
        "platform.lookup", "platform.enterpriseQuery", "platform.correlation",
        "platform.validation", "platform.threatIntelligence", "platform.provenance",
        "platform.relationshipResolution", "platform.metrics", "platform.explainability",
    ]
    for target in required_targets:
        if target not in text:
            findings.append(
                f"REUSE BYPASS: gateway-service.js no longer references '{target}' — a pre-registered "
                f"capability may have stopped delegating to IntelligenceService's own public surface."
            )
    return findings


def check_eig_contract_version_drift(gateway_dir: Path | None = None) -> list[str]:
    """Version drift: confirms each of the 4 EIG contracts' declared `version` still matches its
    own `history` array's last entry, mirroring check_eips_contract_version_drift().
    `gateway_dir` is overridable for fixture testing; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    path = gateway_dir / "service-contracts.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    for contract_name in ["GatewayServiceContract", "MiddlewareContract", "CapabilityRegistryContract", "GatewayMetricsContract"]:
        block_match = re.search(rf"export const {contract_name} = Object\.freeze\(\{{([\s\S]*?)\n\}}\);", text)
        if not block_match:
            findings.append(f"CONTRACT VERSION DRIFT: {contract_name} not found in service-contracts.js in the expected shape")
            continue
        versions_in_block = re.findall(r'version:\s*"([\d.]+)"', block_match.group(1))
        if len(versions_in_block) < 2 or versions_in_block[0] != versions_in_block[-1]:
            findings.append(f"CONTRACT VERSION DRIFT: {contract_name}'s declared version does not match its own history's last entry")
    return findings


def check_no_duplicate_eig_contracts(handlers_dir: Path | None = None, gateway_dir: Path | None = None) -> list[str]:
    """Duplicate contracts: confirms no file outside service-contracts.js exports its own copy of
    the 4 EIG contract constants. `handlers_dir`/`gateway_dir` are overridable for fixture
    testing; main() always calls with the defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    if not gateway_dir.exists():
        return findings
    canonical = gateway_dir / "service-contracts.js"
    for contract_name in ["GatewayServiceContract", "MiddlewareContract", "CapabilityRegistryContract", "GatewayMetricsContract"]:
        pattern = re.compile(rf"\bexport\s+const\s+{contract_name}\b")
        for path in handlers_dir.rglob("*.js"):
            if path == canonical or path.parent.name == "__tests__":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                findings.append(f"DUPLICATE CONTRACT: {_display_path(path)} exports its own '{contract_name}'")
    return findings


def check_no_eig_registry_private_field_bypass(gateway_dir: Path | None = None) -> list[str]:
    """Registry bypass: confirms no EIG file reaches into GatewayRegistry's/GatewayMetrics's
    private fields directly (this._entries, this._featureFlagEvaluations, etc.) from outside
    their own canonical files, instead of calling their public API. `gateway_dir` is overridable
    for fixture testing; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    if not gateway_dir.exists():
        return findings
    private_fields = [
        "_entries", "_featureFlagEvaluations", "_capabilityAuthorizationDenials",
        "_middlewareValidationFailures", "_auditEntries",
    ]
    for path in gateway_dir.rglob("*.js"):
        if path.parent.name == "__tests__" or path.name in ("gateway-registry.js", "gateway-metrics.js"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for field in private_fields:
            if re.search(rf"\.{field}\b", text):
                findings.append(
                    f"REGISTRY BYPASS: {_display_path(path)} references '{field}' directly — "
                    f"private state must only be touched inside its own canonical class."
                )
    return findings


def check_gateway_relationship_capability_still_passthrough(gateway_dir: Path | None = None) -> list[str]:
    """ADR-0010 governance: confirms the evidence.relationships capability still targets
    RelationshipResolutionService's surface (platform.relationshipResolution) and that
    gateway-service.js still documents the ADR-0010 gate (now Accepted, Stage 16 — the
    substring check only requires "ADR-0010" appear, not a specific status, so this check's
    logic is unchanged by the acceptance; only its rationale is: the Gateway must keep routing
    this capability through the same single surface regardless of whether that surface is wired
    to a real provider or still NullRelationshipProvider-backed). Mirrors
    check_intelligence_relationship_still_unwired(). `gateway_dir` is overridable for fixture
    testing; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    path = gateway_dir / "gateway-service.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    if "platform.relationshipResolution" not in text:
        findings.append(
            "ADR-0010 GOVERNANCE: gateway-service.js no longer registers evidence.relationships "
            "against platform.relationshipResolution"
        )
    if "ADR-0010" not in text:
        findings.append("ADR-0010 GOVERNANCE: gateway-service.js no longer documents the ADR-0010 gate on its relationship capability")
    return findings


def check_gateway_validation_middleware_delegates_not_reimplements(gateway_dir: Path | None = None) -> list[str]:
    """Validation bypass: confirms the intelligence.validation capability still targets
    IntelligenceValidationService (platform.validation) and that gateway-middleware.js's own
    validation stage has not grown evidence/intelligence DATA-validation-shaped logic of its
    own (a reimplementation smell), which would duplicate what IntelligenceValidationService
    already does. `gateway_dir` is overridable for fixture testing; main() always calls with
    the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    service_path = gateway_dir / "gateway-service.js"
    middleware_path = gateway_dir / "gateway-middleware.js"
    if not service_path.exists() or not middleware_path.exists():
        return findings
    service_text = service_path.read_text(encoding="utf-8", errors="replace")
    if "platform.validation" not in service_text:
        findings.append("VALIDATION BYPASS: gateway-service.js no longer registers intelligence.validation against platform.validation")
    middleware_text = middleware_path.read_text(encoding="utf-8", errors="replace")
    for smell in ["reliability_code", "evidence_uuid", "canonical_confidence_object", "related_cves"]:
        if smell in middleware_text:
            findings.append(
                f"VALIDATION BYPASS: gateway-middleware.js references '{smell}' — this looks like "
                f"evidence/intelligence DATA validation logic, which belongs in "
                f"IntelligenceValidationService, not gateway-request-shape validation."
            )
    return findings


def check_eig_metrics_no_duplicate_instance(gateway_dir: Path | None = None) -> list[str]:
    """Service drift / duplicate metrics instance: confirms EnterpriseGateway's constructor
    still resolves _platform first, derives serviceMetrics from
    this._platform.metrics.sharedServiceMetrics (never constructs a fresh ServicePlatformMetrics
    independently), guards a mismatched explicit deps.serviceMetrics, and threads that one
    instance into both GatewayMetrics and GatewayDispatcher — the exact bug class the prior,
    interrupted attempt at this stage found in EIPS ("the metrics instance recording the flag
    check never actually reaches the returned service") and this stage's own brief names by
    name. Also confirms GatewayMetrics itself defines no ServicePlatformMetrics-owned private
    field (no second counter set for anything ServicePlatformMetrics already tracks).
    (Independently re-verified behaviorally, by instance identity, in
    enterprise-gateway/__tests__/metrics-sharing.test.js.) `gateway_dir` is overridable for
    fixture testing; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    service_js = gateway_dir / "gateway-service.js"
    if not service_js.exists():
        return findings
    text = service_js.read_text(encoding="utf-8", errors="replace")

    if not re.search(r"this\._platform\s*=\s*deps\.platform\s*;", text):
        findings.append(
            "DUPLICATE METRICS INSTANCE: gateway-service.js's EnterpriseGateway constructor no "
            "longer resolves this._platform from deps.platform first."
        )
    if not re.search(
        r"const\s+serviceMetrics\s*=\s*deps\.serviceMetrics\s*\|\|\s*this\._platform\.metrics\.sharedServiceMetrics",
        text,
    ):
        findings.append(
            "DUPLICATE METRICS INSTANCE: gateway-service.js no longer derives the shared "
            "serviceMetrics from this._platform.metrics.sharedServiceMetrics -- an injected "
            "platform's own metrics instance may no longer be honored, silently splitting "
            "observability in two."
        )
    if not re.search(r"this\._platform\.metrics\.sharedServiceMetrics\s*!==\s*serviceMetrics", text):
        findings.append(
            "DUPLICATE METRICS INSTANCE: gateway-service.js no longer guards against a mismatched "
            "explicit deps.serviceMetrics + deps.platform combination -- that caller error must "
            "fail loudly, not silently pick one instance over the other."
        )
    if not re.search(r"new\s+GatewayMetrics\(\s*this\._platform\.metrics\s*\)", text):
        findings.append(
            "DUPLICATE METRICS INSTANCE: gateway-service.js no longer constructs "
            "'new GatewayMetrics(this._platform.metrics)' -- GatewayMetrics may be losing access "
            "to the shared instance."
        )
    if not re.search(r"serviceMetrics\s*,\s*gatewayMetrics:\s*this\.metrics", text):
        findings.append(
            "DUPLICATE METRICS INSTANCE: gateway-service.js's GatewayDispatcher construction no "
            "longer threads the shared serviceMetrics through -- a component may be defaulting "
            "its own instance instead."
        )

    metrics_js = gateway_dir / "gateway-metrics.js"
    if metrics_js.exists():
        metrics_text = metrics_js.read_text(encoding="utf-8", errors="replace")
        for field in [
            "_callCounts", "_callLatenciesMs", "_queryCounts", "_relationshipResolutions",
            "_provenanceLookups", "_validationFailures", "_contractVersionMismatches",
        ]:
            if re.search(rf"this\.{re.escape(field)}\b", metrics_text):
                findings.append(
                    f"DUPLICATE METRICS INSTANCE: gateway-metrics.js's GatewayMetrics defines "
                    f"'{field}' -- already owned by ServicePlatformMetrics."
                )
    return findings


def check_no_circular_dependency_gateway_intelligence_platform(
    gateway_dir: Path | None = None,
    intelligence_platform_dir: Path | None = None,
    evidence_registry_dir: Path | None = None,
) -> list[str]:
    """Circular dependency: confirms the one-directional import rule holds — enterprise-gateway/
    may import FROM intelligence-platform/ and evidence-registry/, but no intelligence-platform/
    or evidence-registry/ PRODUCTION file (excluding their own __tests__, which legitimately
    document Stage 14 by name in their authorized-exception comments — see those files) may
    import FROM enterprise-gateway/. Directory params are overridable for fixture testing;
    main() always calls with the defaults."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    intelligence_platform_dir = intelligence_platform_dir or INTELLIGENCE_PLATFORM_DIR
    evidence_registry_dir = evidence_registry_dir or EVIDENCE_REGISTRY_DIR
    findings = []
    if not gateway_dir.exists():
        return findings
    for base_dir in [intelligence_platform_dir, evidence_registry_dir]:
        if not base_dir.exists():
            continue
        for path in base_dir.rglob("*.js"):
            if path.parent.name == "__tests__":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "enterprise-gateway" in text:
                findings.append(
                    f"CIRCULAR DEPENDENCY: {_display_path(path)} references enterprise-gateway/ "
                    f"— {base_dir.name}/ production files must not import from their own consumer; "
                    f"this is a one-directional relationship."
                )
    return findings


def check_gateway_capability_authorization_present(gateway_dir: Path | None = None) -> list[str]:
    """Governance expansion: confirms GatewayDispatcher still performs a real capability-
    authorization check (requiredCapabilities vs. grantedCapabilities) before invoking a
    handler, and still has a dedicated CapabilityAuthorizationError — rather than routing every
    request unconditionally. No Stage 12/13 precedent for this check: authorization is a
    capability this stage introduces for the first time. `gateway_dir` is overridable for
    fixture testing; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    path = gateway_dir / "gateway-dispatcher.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    for marker in ["requiredCapabilities", "grantedCapabilities", "CapabilityAuthorizationError"]:
        if marker not in text:
            findings.append(
                f"GOVERNANCE: gateway-dispatcher.js no longer references '{marker}' -- capability "
                f"authorization may have been removed or bypassed"
            )
    return findings


def check_gateway_no_network_auth_scope_creep(gateway_dir: Path | None = None) -> list[str]:
    """Architecture Preservation Rule: confirms this stage's own explicit scope boundary holds —
    'internal authentication' stays in-process/DI-only (GatewayContext-carried capabilities), not
    a real network-facing service-identity system, which this stage's own design doc names as a
    separate, future, explicitly-authorized architectural event. Flags any EIG file that starts
    reaching for network-auth-shaped primitives (a live fetch handler, Request/Response
    construction, the existing blunt ADMIN_SECRET shared-secret pattern, or a JWT library) —
    any of which would be exactly the kind of quiet scope creep this program's Architecture
    Preservation Rule exists to catch. No Stage 12/13 precedent: this concept doesn't apply to
    directories that were never even candidates for a network surface. `gateway_dir` is
    overridable for fixture testing; main() always calls with the default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    if not gateway_dir.exists():
        return findings
    forbidden_patterns = {
        r"addEventListener\(\s*[\"']fetch[\"']": "a live 'fetch' event handler (this stage has no HTTP surface)",
        r"\bnew\s+Response\(": "constructing a Response (this stage has no HTTP surface)",
        r"\bnew\s+Request\(": "constructing a Request (this stage has no HTTP surface)",
        r"\bADMIN_SECRET\b": "the existing blunt shared-secret admin pattern (a separate, future architectural decision, not this stage's)",
        r"\bjsonwebtoken\b": "a JWT library (network-facing auth is explicitly out of Phase 1 scope)",
    }
    for path in gateway_dir.rglob("*.js"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, description in forbidden_patterns.items():
            if re.search(pattern, text):
                findings.append(
                    f"SCOPE CREEP: {_display_path(path)} references {description} -- this "
                    f"stage is documented as in-process/DI-only, no network-facing auth."
                )
    return findings


def check_gateway_registry_describe_omits_handler(gateway_dir: Path | None = None) -> list[str]:
    """Registry maturity (Stage 14 Phase 2): confirms GatewayRegistry.describe()/.describeAll() --
    the safe, read-only capability-metadata accessors added so a diagnostic caller can introspect
    registered capabilities without get()'s full internal entry (which includes the raw handler
    function) -- still exist in the expected shape and their bodies never reference `handler` or
    spread the unfiltered internal entry, which would silently reopen the exact leak they exist
    to close. `gateway_dir` is overridable for fixture testing; main() always calls with the
    default."""
    gateway_dir = gateway_dir or ENTERPRISE_GATEWAY_DIR
    findings = []
    path = gateway_dir / "gateway-registry.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    for method_name in ["describe", "describeAll"]:
        match = re.search(rf"\n  {re.escape(method_name)}\(.*?\)\s*\{{([\s\S]*?)\n  \}}\n", text)
        if not match:
            findings.append(
                f"GOVERNANCE: gateway-registry.js no longer defines '{method_name}()' in the "
                f"expected shape -- registry metadata introspection may have been removed"
            )
            continue
        body = match.group(1)
        if re.search(r"\bhandler\b", body) or re.search(r"\.\.\.entry\b", body):
            findings.append(
                f"REGISTRY BYPASS: gateway-registry.js's {method_name}() body references 'handler' "
                f"or spreads the full entry -- it must return handler-free metadata only"
            )
    return findings


# Stage 15: scripts/intelligence_platform_snapshot.mjs (Stage 13) is a KNOWN, tracked,
# already-deprecated direct-composition consumer -- see its own @deprecated header comment and
# TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md Sec 1. Matched by filename, not full path, so this
# allowlist is exercised correctly against both the real repo and a fixture temp directory.
# Exempting this one named, documented file -- rather than relaxing the check generally --
# mirrors check_evidence_registry_scaffolding_boundary()'s established idiom for the same kind
# of "one authorized exception, not a general loophole" property.
AUTHORIZED_LEGACY_GATEWAY_BYPASS_CONSUMER_NAMES = frozenset({"intelligence_platform_snapshot.mjs"})


def _classify_scripts_gateway_consumers(
    scripts_dir: Path | None = None, handlers_dir: Path | None = None
) -> list[tuple[Path, str]]:
    """Stage 15 shared helper: scans scripts_dir's .mjs/.js files and classifies each as
    'gateway_backed' (imports enterprise-gateway/) or 'direct_composition' (imports
    intelligence-platform/ directly, without also going through enterprise-gateway/). Files that
    reference neither are not consumers of this lineage at all and are omitted. Single source of
    truth for both check_gateway_bypass_new_direct_composition_consumers() (pass/fail findings)
    and compute_gateway_adoption_metrics() (informational counts) -- Principle 3/4: one scan, two
    views, not two independently-drifting implementations. `scripts_dir`/`handlers_dir` are
    overridable for fixture testing; both check functions below always call with the defaults."""
    scripts_dir = scripts_dir or (ROOT / "scripts")
    handlers_dir = handlers_dir or HANDLERS_DIR
    consumers: list[tuple[Path, str]] = []
    if not scripts_dir.exists() or not (handlers_dir / "intelligence-platform").exists():
        return consumers
    for path in sorted(list(scripts_dir.rglob("*.mjs")) + list(scripts_dir.rglob("*.js"))):
        text = path.read_text(encoding="utf-8", errors="replace")
        imports_gateway = "enterprise-gateway/platform.js" in text or "createEnterpriseGateway" in text
        imports_platform_directly = "intelligence-platform/platform.js" in text or "createIntelligencePlatform" in text
        if imports_gateway:
            consumers.append((path, "gateway_backed"))
        elif imports_platform_directly:
            consumers.append((path, "direct_composition"))
    return consumers


def check_gateway_bypass_new_direct_composition_consumers(
    scripts_dir: Path | None = None, handlers_dir: Path | None = None
) -> list[str]:
    """Governance expansion (Stage 15): flags any scripts/ consumer that imports
    intelligence-platform/ directly (bypassing enterprise-gateway/) and is NOT the one
    already-tracked, already-deprecated legacy exception -- i.e., a genuinely NEW bypass, not a
    restatement of the known one. `scripts_dir`/`handlers_dir` are overridable for fixture
    testing; main() always calls with the defaults."""
    findings = []
    for path, classification in _classify_scripts_gateway_consumers(scripts_dir, handlers_dir):
        if classification == "direct_composition" and path.name not in AUTHORIZED_LEGACY_GATEWAY_BYPASS_CONSUMER_NAMES:
            findings.append(
                f"GATEWAY BYPASS: {_display_path(path)} imports intelligence-platform/ directly "
                f"(createIntelligencePlatform) without composing through enterprise-gateway/ -- "
                f"new internal consumers should route through the Gateway per Stage 15's "
                f"migration policy. See TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md."
            )
    return findings


def compute_gateway_adoption_metrics(scripts_dir: Path | None = None, handlers_dir: Path | None = None) -> dict:
    """Stage 15 Phase 6 -- Gateway adoption metrics. Reuses
    _classify_scripts_gateway_consumers(), the same scan check_gateway_bypass_new_direct_
    composition_consumers() uses, rather than a second independent implementation (Principle 3/4:
    Reuse Before Build). Returns counts, not findings -- main() prints this as a separate,
    informational section, never folded into the pass/fail governance finding count.
    `scripts_dir`/`handlers_dir` are overridable for fixture testing; main() always calls with
    the defaults."""
    consumers = _classify_scripts_gateway_consumers(scripts_dir, handlers_dir)
    gateway_backed = sum(1 for _, c in consumers if c == "gateway_backed")
    direct_composition = sum(1 for _, c in consumers if c == "direct_composition")
    total = gateway_backed + direct_composition
    return {
        "total_known_consumers": total,
        "gateway_backed": gateway_backed,
        "direct_composition_legacy": direct_composition,
        "adoption_percentage": round(gateway_backed / total * 100, 1) if total else None,
        "consumers": [{"file": _display_path(p), "classification": c} for p, c in consumers],
    }


RELATIONSHIP_FRAMEWORK_DIR = HANDLERS_DIR / "relationship-framework"

RELATIONSHIP_FRAMEWORK_CORE_FILES = [
    "relationship-types.js",
    "relationship-registry.js",
    "edge-repository-interface.js",
    "in-memory-edge-repository.js",
    "p31-edge-adapter.js",
    "relationship-provider.js",
    "relationship-traversal.js",
    "relationship-validation.js",
    "relationship-metrics.js",
    "relationship-lookup.js",
    "relationship-service.js",
    "service-contracts.js",
]


def check_relationship_framework_files_present_and_isolated(rf_dir: Path | None = None) -> list[str]:
    """Stage 16: confirms every Relationship Framework file still exists (Deprecation Instead of
    Deletion — no silent removal) and that none of them imports a live pNN-handlers.js/index.js
    file directly — the same zero-blast-radius property every prior TITAN-stage scaffolding
    directory (evidence-registry/, intelligence-platform/, enterprise-gateway/) enforces,
    mirroring check_eig_files_present_and_isolated()/check_eesp_files_present_and_isolated()
    exactly. This is the property that makes ADR-0010's Acceptance safe: real relationship data
    now flows through this directory, but only via documented-shape adapters (p31-edge-adapter.js),
    never via a direct handler import. `rf_dir` is overridable for fixture testing; main() always
    calls with the default."""
    rf_dir = rf_dir or RELATIONSHIP_FRAMEWORK_DIR
    findings = []
    if not rf_dir.exists():
        return findings
    for name in RELATIONSHIP_FRAMEWORK_CORE_FILES:
        path = rf_dir / name
        if not path.exists():
            findings.append(f"MISSING RELATIONSHIP FRAMEWORK FILE: relationship-framework/{name} — Stage 16 file set is incomplete")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'from\s+["\'].*p\d+-handlers\.js["\']', text) or re.search(r'from\s+["\'].*/index\.js["\']', text):
            findings.append(f"ARCHITECTURE VIOLATION: relationship-framework/{name} imports a live pNN-handlers.js/index.js file")
    return findings


def check_no_duplicate_relationship_engine(handlers_dir: Path | None = None, rf_dir: Path | None = None) -> list[str]:
    """Duplicate engines (Stage 16's own NON-GOALS: "No duplicate graph engines... No duplicate
    traversal engine"): confirms no file outside relationship-framework/ defines its own copy of
    this stage's core classes. Mirrors check_no_duplicate_enterprise_gateway()'s exact pattern.
    `handlers_dir`/`rf_dir` are overridable for fixture testing; main() always calls with the
    defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    rf_dir = rf_dir or RELATIONSHIP_FRAMEWORK_DIR
    findings = []
    if not rf_dir.exists():
        return findings
    class_to_file = {
        "RelationshipService": "relationship-service.js",
        "RelationshipRegistry": "relationship-registry.js",
        "RelationshipTraversalService": "relationship-traversal.js",
        "RelationshipValidationService": "relationship-validation.js",
        "RelationshipMetricsService": "relationship-metrics.js",
        "RelationshipLookupService": "relationship-lookup.js",
        "P31RelationshipProvider": "relationship-provider.js",
        "InMemoryRelationshipEdgeRepository": "in-memory-edge-repository.js",
    }
    for class_name, canonical_file in class_to_file.items():
        pattern = re.compile(rf"\bclass\s+{class_name}\b")
        for path in handlers_dir.rglob("*.js"):
            if path.parent == rf_dir and path.name == canonical_file:
                continue
            if path.parent.name == "__tests__":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                findings.append(
                    f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'class {class_name}' — "
                    f"the canonical implementation is relationship-framework/{canonical_file}"
                )
    return findings


def check_relationship_framework_provider_wiring_intact(rf_dir: Path | None = None) -> list[str]:
    """Stage 16 positive-state check (architecture drift, both directions): confirms
    relationship-service.js still constructs Stage 12's RelationshipResolutionService WITH a real
    `provider` (P31RelationshipProvider), not left on the NullRelationshipProvider default — i.e.
    that the ADR-0010 Acceptance this stage exercised has not silently regressed back to unwired.
    Equally, confirms relationship-provider.js still does not import p31-handlers.js directly
    (the P31RelationshipProvider must stay adapter-based, per p31-edge-adapter.js, even though a
    real import would no longer violate ADR-0010's gate — it would still violate the
    zero-blast-radius boundary check_relationship_framework_files_present_and_isolated() enforces).
    `rf_dir` is overridable for fixture testing; main() always calls with the default."""
    rf_dir = rf_dir or RELATIONSHIP_FRAMEWORK_DIR
    findings = []
    service_path = rf_dir / "relationship-service.js"
    if not service_path.exists():
        return findings
    service_text = service_path.read_text(encoding="utf-8", errors="replace")
    if "new RelationshipResolutionService({ provider:" not in service_text and "new RelationshipResolutionService({provider:" not in service_text:
        findings.append(
            "RELATIONSHIP WIRING DRIFT: relationship-service.js no longer constructs "
            "RelationshipResolutionService with an explicit `provider` — ADR-0010 was Accepted "
            "specifically so this wiring could happen; regressing to the unwired default silently "
            "defeats that Acceptance. See TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md."
        )
    if "P31RelationshipProvider" not in service_text:
        findings.append(
            "RELATIONSHIP WIRING DRIFT: relationship-service.js no longer references "
            "P31RelationshipProvider — the concrete provider this stage built may have been bypassed."
        )

    provider_path = rf_dir / "relationship-provider.js"
    if provider_path.exists():
        provider_text = provider_path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'from\s+["\'].*p\d+-handlers\.js["\']', provider_text):
            findings.append(
                "ARCHITECTURE VIOLATION: relationship-provider.js imports a pNN-handlers.js file "
                "directly — it must stay adapter-based via p31-edge-adapter.js's documented data "
                "shape, per this directory's zero-blast-radius rule."
            )
    return findings


STAGE17_CORE_FILES = [
    "correlation-policy.js",
    "explainability-engine.js",
]


def check_stage17_files_present_and_isolated(platform_dir: Path | None = None) -> list[str]:
    """Stage 17: confirms both Track A files (correlation-policy.js, explainability-engine.js)
    still exist (Deprecation Instead of Deletion — no silent removal) and that neither imports a
    live pNN-handlers.js/index.js file directly — the same zero-blast-radius property every prior
    TITAN-stage scaffolding file in this directory enforces, mirroring
    check_eips_files_present_and_isolated()/check_relationship_framework_files_present_and_isolated()
    exactly. `platform_dir` is overridable for fixture testing; main() always calls with the
    default."""
    platform_dir = platform_dir or INTELLIGENCE_PLATFORM_DIR
    findings = []
    if not platform_dir.exists():
        return findings
    for name in STAGE17_CORE_FILES:
        path = platform_dir / name
        if not path.exists():
            findings.append(f"MISSING STAGE 17 FILE: intelligence-platform/{name} — Track A file set is incomplete")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'from\s+["\'].*p\d+-handlers\.js["\']', text) or re.search(r'from\s+["\'].*/index\.js["\']', text):
            findings.append(f"ARCHITECTURE VIOLATION: intelligence-platform/{name} imports a live pNN-handlers.js/index.js file")
    return findings


def check_no_duplicate_explainability_engine(handlers_dir: Path | None = None, platform_dir: Path | None = None) -> list[str]:
    """Duplicate engines (Stage 17's own NON-GOALS, inherited from every prior stage's "no
    duplicate engines" rule): confirms no file outside intelligence-platform/ defines its own copy
    of IntelligenceExplainabilityService. Mirrors check_no_duplicate_relationship_engine()'s exact
    pattern. `handlers_dir`/`platform_dir` are overridable for fixture testing; main() always
    calls with the defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    platform_dir = platform_dir or INTELLIGENCE_PLATFORM_DIR
    findings = []
    if not platform_dir.exists():
        return findings
    pattern = re.compile(r"\bclass\s+IntelligenceExplainabilityService\b")
    for path in handlers_dir.rglob("*.js"):
        if path.parent == platform_dir and path.name == "explainability-engine.js":
            continue
        if path.parent.name == "__tests__":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            findings.append(
                f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'class IntelligenceExplainabilityService' — "
                f"the canonical implementation is intelligence-platform/explainability-engine.js"
            )
    return findings


# Function-name shapes that would signal Stage 17 quietly computing/weighting/ranking a
# confidence value itself, rather than surfacing canonical_confidence_object verbatim -- the
# exact boundary TITAN_STAGE17_READINESS_REPORT.md Sec 4 documents as gated on ADR-0007
# (Proposed, not Accepted). Deliberately narrow (matches this script's existing
# KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS idiom): named function/method DEFINITIONS only, not every
# occurrence of the word "confidence" (both files legitimately mention it in comments/field names).
_STAGE17_CONFIDENCE_COMPUTATION_PATTERN = re.compile(
    r"\b(?:function|async\s+function)\s+(?:compute|score|weight|rank)\w*[Cc]onfidence\w*\s*\("
)


def check_no_confidence_computation_introduced_stage17(platform_dir: Path | None = None) -> list[str]:
    """Stage 17's own ADR-0007 boundary, made mechanically enforceable rather than only
    documented in prose: confirms neither Track A file (correlation-policy.js,
    explainability-engine.js) defines a new compute*/score*/weight*/rank*Confidence* function --
    the shape a confidence-computing, -weighting, or -ranking function would take, mirroring this
    script's existing KNOWN_CONFIDENCE_EVIDENCE_FUNCTIONS/NAME_PATTERN idiom used for the P16-P38
    handler stack. Both files are permitted (and expected) to reference
    `canonical_confidence_object`/`verification_status`/`evidence_weight` verbatim -- this check
    only fires on a new function DEFINITION whose name claims to compute/score/weight/rank
    confidence, which the module docstrings of both files say should never happen while ADR-0007
    (docs/adr/0007-canonical-confidence-framework.md) remains Proposed. `platform_dir` is
    overridable for fixture testing; main() always calls with the default."""
    platform_dir = platform_dir or INTELLIGENCE_PLATFORM_DIR
    findings = []
    for name in STAGE17_CORE_FILES:
        path = platform_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _STAGE17_CONFIDENCE_COMPUTATION_PATTERN.search(text):
            findings.append(
                f"ADR-0007 BOUNDARY VIOLATION: intelligence-platform/{name} appears to define a "
                f"confidence-computing/weighting/ranking function — ADR-0007 (Canonical Confidence "
                f"Framework) is Proposed, not Accepted. Confidence fields must be surfaced verbatim "
                f"only until it is. See TITAN_STAGE17_READINESS_REPORT.md Sec 4."
            )
    return findings


def check_explainability_still_unwired(handlers_dir: Path | None = None) -> list[str]:
    """Architecture boundary: confirms index.js has zero references to explainability-engine.js,
    correlation-policy.js, or IntelligenceExplainabilityService -- Stage 17's Track A output stays
    an internal Gateway capability only, not a live index.js route, matching the unbroken Stage
    8-16 precedent this lineage has kept for every one of its files (see
    TITAN_STAGE17_READINESS_REPORT.md Sec 3). Mirrors check_relationship_resolution_still_unwired()'s
    exact pattern. `handlers_dir` is overridable for fixture testing; main() always calls with the
    default."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    findings = []
    index_path = handlers_dir / "index.js"
    if not index_path.exists():
        return findings
    text = index_path.read_text(encoding="utf-8", errors="replace")
    for needle in ("explainability-engine", "correlation-policy.js", "IntelligenceExplainabilityService"):
        if needle in text:
            findings.append(
                f"STAGE 17 BYPASS: index.js references '{needle}' — Stage 17's Track A output is "
                f"authorized as an internal Gateway capability only; wiring it into a live "
                f"production route requires its own separate authorization, not granted by this "
                f"stage (see TITAN_STAGE17_READINESS_REPORT.md Sec 3)."
            )
    return findings


def check_correlation_policy_versioned(platform_dir: Path | None = None) -> list[str]:
    """Phase 4's own auditability requirement ("policies must be auditable and versioned"), made
    mechanically enforceable: confirms correlation-policy.js still exports
    CORRELATION_POLICY_VERSION and a describePolicy() introspection function. `platform_dir` is
    overridable for fixture testing; main() always calls with the default."""
    platform_dir = platform_dir or INTELLIGENCE_PLATFORM_DIR
    findings = []
    path = platform_dir / "correlation-policy.js"
    if not path.exists():
        return findings
    text = path.read_text(encoding="utf-8", errors="replace")
    if "export const CORRELATION_POLICY_VERSION" not in text:
        findings.append(
            "POLICY GOVERNANCE: correlation-policy.js no longer exports CORRELATION_POLICY_VERSION "
            "— Phase 4 requires correlation policies to be versioned."
        )
    if "export function describePolicy" not in text:
        findings.append(
            "POLICY GOVERNANCE: correlation-policy.js no longer exports describePolicy() — Phase 4 "
            "requires correlation policies to be auditable/introspectable."
        )
    return findings


KNOWLEDGE_PLATFORM_DIR = HANDLERS_DIR / "knowledge-platform"

STAGE18_CORE_FILES = [
    "feature-flags.js",
    "service-contracts.js",
    "knowledge-object.js",
    "knowledge-navigation.js",
    "analyst-views.js",
    "executive-views.js",
    "knowledge-quality.js",
    "knowledge-platform.js",
    "platform.js",
]

STAGE18_CLASS_TO_FILE = {
    "KnowledgeObjectService": "knowledge-object.js",
    "KnowledgeNavigationService": "knowledge-navigation.js",
    "AnalystViewService": "analyst-views.js",
    "ExecutiveViewService": "executive-views.js",
    "KnowledgeQualityService": "knowledge-quality.js",
    "KnowledgePlatform": "knowledge-platform.js",
}


def check_stage18_files_present_and_isolated(kp_dir: Path | None = None) -> list[str]:
    """Stage 18: confirms every knowledge-platform/ production file still exists (Deprecation
    Instead of Deletion -- no silent removal) and that none of them imports a live
    pNN-handlers.js/index.js file directly -- the same zero-blast-radius property every prior
    TITAN-stage scaffolding directory in this lineage enforces, mirroring
    check_stage17_files_present_and_isolated()/check_relationship_framework_files_present_and_isolated()
    exactly. `kp_dir` is overridable for fixture testing; main() always calls with the default."""
    kp_dir = kp_dir or KNOWLEDGE_PLATFORM_DIR
    findings = []
    if not kp_dir.exists():
        return findings
    for name in STAGE18_CORE_FILES:
        path = kp_dir / name
        if not path.exists():
            findings.append(f"MISSING STAGE 18 FILE: knowledge-platform/{name} -- file set is incomplete")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'from\s+["\'].*p\d+-handlers\.js["\']', text) or re.search(r'from\s+["\'].*/index\.js["\']', text):
            findings.append(f"ARCHITECTURE VIOLATION: knowledge-platform/{name} imports a live pNN-handlers.js/index.js file")
    return findings


def check_no_duplicate_knowledge_platform_engines(handlers_dir: Path | None = None, kp_dir: Path | None = None) -> list[str]:
    """Duplicate engines (Stage 18's own NON-GOALS, inherited from every prior stage's "no
    duplicate engines" rule): confirms no file outside knowledge-platform/ defines its own copy
    of any of the six Stage 18 classes. Mirrors check_no_duplicate_explainability_engine()'s
    exact pattern. `handlers_dir`/`kp_dir` are overridable for fixture testing; main() always
    calls with the defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    kp_dir = kp_dir or KNOWLEDGE_PLATFORM_DIR
    findings = []
    if not kp_dir.exists():
        return findings
    for class_name, canonical_file in STAGE18_CLASS_TO_FILE.items():
        pattern = re.compile(rf"\bclass\s+{class_name}\b")
        for path in handlers_dir.rglob("*.js"):
            if path.parent == kp_dir and path.name == canonical_file:
                continue
            if path.parent.name == "__tests__":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                findings.append(
                    f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'class {class_name}' -- "
                    f"the canonical implementation is knowledge-platform/{canonical_file}"
                )
    return findings


_STAGE18_CONFIDENCE_COMPUTATION_PATTERN = re.compile(
    r"\b(?:function|async\s+function)\s+(?:compute|score|weight|rank)\w*[Cc]onfidence\w*\s*\("
)


def check_no_confidence_computation_introduced_stage18(kp_dir: Path | None = None) -> list[str]:
    """Stage 18's own ADR-0007 boundary, made mechanically enforceable rather than only
    documented in prose -- mirrors check_no_confidence_computation_introduced_stage17() exactly.
    Confirms no Stage 18 file defines a new compute*/score*/weight*/rank*Confidence* function.
    `analyst-views.js`'s confidenceContext() and `knowledge-object.js`'s confidenceAsRecorded
    passthrough are permitted (and expected) to reference canonical_confidence_object/
    verification_status/evidence_weight verbatim -- this check only fires on a new function
    DEFINITION whose name claims to compute/score/weight/rank confidence, which every Stage 18
    file's own module docstring says should never happen while ADR-0007
    (docs/adr/0007-canonical-confidence-framework.md) remains Proposed. `kp_dir` is overridable
    for fixture testing; main() always calls with the default."""
    kp_dir = kp_dir or KNOWLEDGE_PLATFORM_DIR
    findings = []
    for name in STAGE18_CORE_FILES:
        path = kp_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _STAGE18_CONFIDENCE_COMPUTATION_PATTERN.search(text):
            findings.append(
                f"ADR-0007 BOUNDARY VIOLATION: knowledge-platform/{name} appears to define a "
                f"confidence-computing/weighting/ranking function -- ADR-0007 (Canonical Confidence "
                f"Framework) is Proposed, not Accepted. Confidence fields must be surfaced verbatim "
                f"only until it is. See TITAN_STAGE18_READINESS_REPORT.md."
            )
    return findings


def check_knowledge_platform_still_unwired(handlers_dir: Path | None = None) -> list[str]:
    """Architecture boundary: confirms index.js, gateway-service.js, and intelligence-service.js
    all have zero references to any knowledge-platform/ file or its exported class names --
    Stage 18's output stays an internal, externally-composed Gateway capability only (wired via
    registerCapability() from a composition script, per TITAN_STAGE18_READINESS_REPORT.md Sec 3),
    never a live index.js route and never a property baked onto IntelligenceService or
    EnterpriseGateway themselves (which would create a circular import through
    correlation-policy.js -- see the same section). Mirrors
    check_explainability_still_unwired()'s exact pattern. `handlers_dir` is overridable for
    fixture testing; main() always calls with the default."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    findings = []
    targets = {
        "index.js": handlers_dir / "index.js",
        "enterprise-gateway/gateway-service.js": handlers_dir / "enterprise-gateway" / "gateway-service.js",
        "intelligence-platform/intelligence-service.js": handlers_dir / "intelligence-platform" / "intelligence-service.js",
    }
    for label, path in targets.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "knowledge-platform" in text or "KnowledgePlatform" in text:
            findings.append(
                f"STAGE 18 BYPASS: {label} references knowledge-platform/ or KnowledgePlatform -- "
                f"Stage 18's output is authorized as an externally-composed Gateway capability "
                f"only; wiring it directly into {label} requires its own separate authorization, "
                f"not granted by this stage (see TITAN_STAGE18_READINESS_REPORT.md Sec 3)."
            )
    return findings


PRODUCT_PLATFORM_DIR = HANDLERS_DIR / "product-platform"

STAGE19_CORE_FILES = [
    "feature-flags.js",
    "service-contracts.js",
    "product-engine.js",
    "product-profiles.js",
    "product-packaging.js",
    "product-quality.js",
    "product-platform.js",
    "platform.js",
]

STAGE19_CLASS_TO_FILE = {
    "ProductEngineService": "product-engine.js",
    "ProductProfileService": "product-profiles.js",
    "ProductPackagingService": "product-packaging.js",
    "ProductQualityService": "product-quality.js",
    "ProductPlatform": "product-platform.js",
}

# The four canonical Python dossier/report pipeline files, per TITAN_STAGE19_READINESS_REPORT.md
# Sec 2.3's fresh re-verification: CI-wired, independent, unmodified, uncoupled from the JS
# lineage. Named here (not imported/executed) purely so check_product_platform_no_python_pipeline_coupling()
# below can detect an accidental future reference.
STAGE19_PYTHON_PIPELINE_MARKERS = [
    "report_generator.py",
    "dynamic_dossier_engine.py",
    "dossier_quality_engine.py",
    "generate_intel_reports.py",
]


def check_stage19_files_present_and_isolated(pp_dir: Path | None = None) -> list[str]:
    """Stage 19: confirms every product-platform/ production file still exists (Deprecation
    Instead of Deletion -- no silent removal) and that none of them imports a live
    pNN-handlers.js/index.js file directly -- the same zero-blast-radius property every prior
    TITAN-stage scaffolding directory in this lineage enforces, mirroring
    check_stage18_files_present_and_isolated()/check_stage17_files_present_and_isolated() exactly.
    `pp_dir` is overridable for fixture testing; main() always calls with the default."""
    pp_dir = pp_dir or PRODUCT_PLATFORM_DIR
    findings = []
    if not pp_dir.exists():
        return findings
    for name in STAGE19_CORE_FILES:
        path = pp_dir / name
        if not path.exists():
            findings.append(f"MISSING STAGE 19 FILE: product-platform/{name} -- file set is incomplete")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r'from\s+["\'].*p\d+-handlers\.js["\']', text) or re.search(r'from\s+["\'].*/index\.js["\']', text):
            findings.append(f"ARCHITECTURE VIOLATION: product-platform/{name} imports a live pNN-handlers.js/index.js file")
    return findings


def check_no_duplicate_product_platform_engines(handlers_dir: Path | None = None, pp_dir: Path | None = None) -> list[str]:
    """Duplicate engines (Stage 19's own NON-GOALS, inherited from every prior stage's "no
    duplicate engines" rule): confirms no file outside product-platform/ defines its own copy of
    any of the five Stage 19 classes. Mirrors check_no_duplicate_knowledge_platform_engines()'s
    exact pattern. `handlers_dir`/`pp_dir` are overridable for fixture testing; main() always
    calls with the defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    pp_dir = pp_dir or PRODUCT_PLATFORM_DIR
    findings = []
    if not pp_dir.exists():
        return findings
    for class_name, canonical_file in STAGE19_CLASS_TO_FILE.items():
        pattern = re.compile(rf"\bclass\s+{class_name}\b")
        for path in handlers_dir.rglob("*.js"):
            if path.parent == pp_dir and path.name == canonical_file:
                continue
            if path.parent.name == "__tests__":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if pattern.search(text):
                findings.append(
                    f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'class {class_name}' -- "
                    f"the canonical implementation is product-platform/{canonical_file}"
                )
    return findings


_STAGE19_CONFIDENCE_COMPUTATION_PATTERN = re.compile(
    r"\b(?:function|async\s+function)\s+(?:compute|score|weight|rank)\w*[Cc]onfidence\w*\s*\("
)


def check_no_confidence_computation_introduced_stage19(pp_dir: Path | None = None) -> list[str]:
    """Stage 19's own ADR-0007 boundary, made mechanically enforceable rather than only
    documented in prose -- mirrors check_no_confidence_computation_introduced_stage18() exactly.
    Confirms no Stage 19 file defines a new compute*/score*/weight*/rank*Confidence* function.
    `confidenceAsRecorded` passthrough (read from an assembled Knowledge Object, unchanged) is
    permitted and expected -- this check only fires on a new function DEFINITION whose name
    claims to compute/score/weight/rank confidence, which every Stage 19 file's own module
    docstring says should never happen while ADR-0007
    (docs/adr/0007-canonical-confidence-framework.md) remains Proposed. `pp_dir` is overridable
    for fixture testing; main() always calls with the default."""
    pp_dir = pp_dir or PRODUCT_PLATFORM_DIR
    findings = []
    for name in STAGE19_CORE_FILES:
        path = pp_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _STAGE19_CONFIDENCE_COMPUTATION_PATTERN.search(text):
            findings.append(
                f"ADR-0007 BOUNDARY VIOLATION: product-platform/{name} appears to define a "
                f"confidence-computing/weighting/ranking function -- ADR-0007 (Canonical Confidence "
                f"Framework) is Proposed, not Accepted. Confidence fields must be surfaced verbatim "
                f"only until it is. See TITAN_STAGE19_READINESS_REPORT.md."
            )
    return findings


def check_product_platform_still_unwired(handlers_dir: Path | None = None) -> list[str]:
    """Architecture boundary: confirms index.js, gateway-service.js, intelligence-service.js, and
    knowledge-platform.js all have zero references to any product-platform/ file or its exported
    class names -- Stage 19's output stays an internal, externally-composed Gateway capability
    only (wired via registerCapability() from a composition script, per
    TITAN_STAGE19_READINESS_REPORT.md Sec 3.2), never a live index.js route and never a property
    baked onto KnowledgePlatform, IntelligenceService, or EnterpriseGateway themselves (which
    would create a circular import). Mirrors check_knowledge_platform_still_unwired()'s exact
    pattern, extended with knowledge-platform.js since that is this stage's own one authorized
    upstream hop. `handlers_dir` is overridable for fixture testing; main() always calls with the
    default."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    findings = []
    targets = {
        "index.js": handlers_dir / "index.js",
        "enterprise-gateway/gateway-service.js": handlers_dir / "enterprise-gateway" / "gateway-service.js",
        "intelligence-platform/intelligence-service.js": handlers_dir / "intelligence-platform" / "intelligence-service.js",
        "knowledge-platform/knowledge-platform.js": handlers_dir / "knowledge-platform" / "knowledge-platform.js",
    }
    for label, path in targets.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "product-platform" in text or "ProductPlatform" in text:
            findings.append(
                f"STAGE 19 BYPASS: {label} references product-platform/ or ProductPlatform -- "
                f"Stage 19's output is authorized as an externally-composed Gateway capability "
                f"only; wiring it directly into {label} requires its own separate authorization, "
                f"not granted by this stage (see TITAN_STAGE19_READINESS_REPORT.md Sec 3.2)."
            )
    return findings


def check_product_platform_no_python_pipeline_coupling(pp_dir: Path | None = None) -> list[str]:
    """Stage 19's own re-verified architectural decision (TITAN_STAGE19_READINESS_REPORT.md Sec
    2.3), made mechanically enforceable: confirms no product-platform/ production file references
    the Python dossier/report pipeline (report_generator.py, dynamic_dossier_engine.py,
    dossier_quality_engine.py, generate_intel_reports.py) by name. The two systems are
    independent, unmodified, and uncoupled -- product-platform/'s "tactical_dossier" package type
    is a structured JSON envelope over Knowledge Platform output, not the Python pipeline's HTML
    output, and this check guards against the two architectures ever being silently merged.
    `pp_dir` is overridable for fixture testing; main() always calls with the default."""
    pp_dir = pp_dir or PRODUCT_PLATFORM_DIR
    findings = []
    for name in STAGE19_CORE_FILES:
        path = pp_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in STAGE19_PYTHON_PIPELINE_MARKERS:
            if marker in text:
                findings.append(
                    f"PYTHON PIPELINE COUPLING: product-platform/{name} references '{marker}' -- "
                    f"the Python dossier/report pipeline must remain independent, unmodified, and "
                    f"uncoupled from the JS Evidence Registry/Intelligence Platform/Gateway/"
                    f"Knowledge Platform/Product Platform lineage (see "
                    f"TITAN_STAGE19_READINESS_REPORT.md Sec 2.3)."
                )
    return findings


# =============================================================================
# Stage 20A -- Commercial Quality Orchestrator governance checks
# =============================================================================
# Project TITAN Stage 20A built a read-only composition layer over existing
# quality/trust/certification engines (COMMERCIAL_QUALITY_GOVERNANCE_AUDIT.md
# + COMMERCIAL_QUALITY_ORCHESTRATOR_ARCHITECTURE.md, PR #131). Its own charter
# is explicit: never modify P20/P21/P25/P26/P29/P35/P36/P37, never modify
# commercial_readiness_governor.py or dossier_quality_engine.py, never
# duplicate quality/certification/confidence/publication engines, and stay
# internal-only (never wired into index.js). Five checks cover that charter,
# mirroring check_stage19_files_present_and_isolated() /
# check_no_duplicate_product_platform_engines() /
# check_no_confidence_computation_introduced_stage19() /
# check_product_platform_still_unwired()'s exact patterns, extended one step
# further with a protected-engine-signature check since Stage 20A (unlike
# Stage 19) composes directly from live P20/P21/P25/P26 exports by name.

COMMERCIAL_ORCHESTRATOR_JS = HANDLERS_DIR / "p39-handlers.js"
COMMERCIAL_ORCHESTRATOR_PY = ROOT / "scripts" / "commercial_quality_orchestrator.py"

COMMERCIAL_ORCHESTRATOR_JS_FUNCTIONS = [
    "computeCommercialApplicability",
    "buildCommercialQualityView",
    "buildCommercialReadinessSummary",
    "buildCommercialPublicationDecision",
    "buildCommercialExplanation",
    "buildCommercialRecommendationLayer",
    "buildCommercialReleaseDecision",
]

COMMERCIAL_ORCHESTRATOR_PY_FUNCTIONS = [
    "compute_commercial_applicability",
    "build_commercial_quality_view",
    "build_commercial_readiness_summary",
    "build_commercial_publication_decision",
    "build_commercial_explanation",
    "build_commercial_recommendation_layer",
    "build_commercial_release_decision",
]

# Protected engines Stage 20A's charter forbids modifying (governance audit +
# architecture doc Sec 0). This does not diff file contents against a stored
# baseline -- it confirms the specific function/class names those engines are
# known to own are still defined at their canonical location, the same
# structural guarantee every duplicate-engine check in this file provides in
# the opposite direction.
COMMERCIAL_ORCHESTRATOR_PROTECTED_JS = {
    "computeP20QualityScore": "p20-handlers.js",
    "getP21CertificationLevel": "p21-handlers.js",
    "computeEnterpriseTrustScore": "p25-handlers.js",
    "computeP26Grade": "p26-handlers.js",
}
COMMERCIAL_ORCHESTRATOR_PROTECTED_PY = {
    "def enforce_publication_decision": ROOT / "scripts" / "commercial_readiness_governor.py",
    "class DossierQualityEngine": ROOT / "agent" / "dossier_quality_engine.py",
}


def check_commercial_orchestrator_files_present() -> list[str]:
    """Stage 20A: confirms both runtime halves of the Commercial Quality
    Orchestrator still exist (Deprecation Instead of Deletion -- no silent
    removal), mirroring check_stage19_files_present_and_isolated()'s pattern
    for a two-file (not multi-file-directory) deliverable."""
    findings = []
    for label, path in [("p39-handlers.js", COMMERCIAL_ORCHESTRATOR_JS),
                         ("commercial_quality_orchestrator.py", COMMERCIAL_ORCHESTRATOR_PY)]:
        if not path.exists():
            findings.append(
                f"MISSING STAGE 20A FILE: {_display_path(path)} -- {label} is required by the approved "
                f"architecture (PR #131) and must not be silently removed."
            )
    return findings


def check_no_duplicate_commercial_orchestrator_functions(handlers_dir: Path | None = None, scripts_dir: Path | None = None) -> list[str]:
    """Stage 20A's own NON-GOAL (inherited from every prior stage's "no
    duplicate engines" rule): confirms no file other than p39-handlers.js
    defines any of its 7 exported composition functions, and no file other
    than commercial_quality_orchestrator.py defines any of its 7. Mirrors
    check_no_duplicate_product_platform_engines()'s exact pattern.
    `handlers_dir`/`scripts_dir` are overridable for fixture testing; main()
    always calls with the defaults."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    scripts_dir = scripts_dir or (ROOT / "scripts")
    findings = []

    if COMMERCIAL_ORCHESTRATOR_JS.exists() and handlers_dir.exists():
        for fn in COMMERCIAL_ORCHESTRATOR_JS_FUNCTIONS:
            pattern = re.compile(rf"\bfunction\s+{fn}\b")
            for path in handlers_dir.rglob("*.js"):
                if path == COMMERCIAL_ORCHESTRATOR_JS or path.parent.name == "__tests__":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if pattern.search(text):
                    findings.append(
                        f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'function {fn}' -- the "
                        f"canonical implementation is workers/intel-gateway/src/p39-handlers.js"
                    )

    if COMMERCIAL_ORCHESTRATOR_PY.exists() and scripts_dir.exists():
        for fn in COMMERCIAL_ORCHESTRATOR_PY_FUNCTIONS:
            pattern = re.compile(rf"^def\s+{fn}\b", re.MULTILINE)
            for path in scripts_dir.rglob("*.py"):
                if path == COMMERCIAL_ORCHESTRATOR_PY:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if pattern.search(text):
                    findings.append(
                        f"DUPLICATE ENGINE: {_display_path(path)} defines its own 'def {fn}' -- the canonical "
                        f"implementation is scripts/commercial_quality_orchestrator.py"
                    )
    return findings


def check_commercial_orchestrator_protected_engines_intact(handlers_dir: Path | None = None) -> list[str]:
    """Stage 20A's charter explicitly forbids modifying P20/P21/P25/P26 (JS)
    or commercial_readiness_governor.py/dossier_quality_engine.py (Python).
    Confirms the specific function/class signatures those engines are known
    to export are still present at their canonical file -- see the module
    comment above COMMERCIAL_ORCHESTRATOR_PROTECTED_JS for what this can and
    cannot detect. `handlers_dir` is overridable for fixture testing; main()
    always calls with the default."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    findings = []
    for fn, filename in COMMERCIAL_ORCHESTRATOR_PROTECTED_JS.items():
        path = handlers_dir / filename
        if not path.exists():
            findings.append(f"PROTECTED ENGINE MISSING: {filename} -- Stage 20A composes this engine and must not cause its removal.")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not re.search(rf"\bfunction\s+{fn}\b", text):
            findings.append(
                f"PROTECTED ENGINE SIGNATURE MISSING: {filename} no longer defines 'function {fn}' -- Stage 20A's "
                f"composition layer depends on this exact export remaining unchanged."
            )
    for needle, path in COMMERCIAL_ORCHESTRATOR_PROTECTED_PY.items():
        if not path.exists():
            findings.append(f"PROTECTED ENGINE MISSING: {_display_path(path)} -- Stage 20A composes this engine and must not cause its removal.")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle not in text:
            findings.append(
                f"PROTECTED ENGINE SIGNATURE MISSING: {_display_path(path)} no longer defines '{needle}' -- Stage "
                f"20A's composition layer depends on this exact export remaining unchanged."
            )
    return findings


_COMMERCIAL_ORCHESTRATOR_NEW_SCORER_PATTERN = re.compile(
    r"\b(?:function|async\s+function|def)\s+(?:compute|score|weight|rank)\w*(?:Confidence|Trust|Quality|Certification)\w*\s*\("
)


def check_commercial_orchestrator_no_new_scorer() -> list[str]:
    """ADR-0007's boundary and the governance audit's own mandate ("no new
    independent scorer"), made mechanically enforceable -- mirrors
    check_no_confidence_computation_introduced_stage19() exactly, extended to
    also catch a new *Quality*/*Certification* computation, not just
    *Confidence*/*Trust*. computeCommercialApplicability()/compute_commercial_
    applicability() are exempt by construction -- they classify APPLICABLE/
    NOT_APPLICABLE/UNKNOWN, not compute/score/weight/rank a number, so neither
    matches this pattern."""
    findings = []
    for path in [COMMERCIAL_ORCHESTRATOR_JS, COMMERCIAL_ORCHESTRATOR_PY]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _COMMERCIAL_ORCHESTRATOR_NEW_SCORER_PATTERN.finditer(text):
            findings.append(
                f"ADR-0007 / GOVERNANCE AUDIT BOUNDARY VIOLATION: {_display_path(path)} appears to define a new "
                f"confidence/trust/quality/certification-computing function ('{match.group(0).strip()}') -- Stage "
                f"20A's charter and ADR-0007 both forbid a new independent scorer. Composed values must be cited "
                f"verbatim from an existing engine only."
            )
    return findings


def check_commercial_orchestrator_still_unwired(handlers_dir: Path | None = None) -> list[str]:
    """Architecture boundary: confirms index.js has zero references to
    p39-handlers.js or its exported function names -- Stage 20A's explicit
    implementation directive ("Integrate with Gateway composition layer only.
    Never expose publicly. Remain internal.") means this file, unlike every
    P16-P38 handler, is never imported and never routed. Mirrors
    check_product_platform_still_unwired()'s exact pattern. `handlers_dir` is
    overridable for fixture testing; main() always calls with the default."""
    handlers_dir = handlers_dir or HANDLERS_DIR
    findings = []
    index_path = handlers_dir / "index.js"
    if not index_path.exists():
        return findings
    text = index_path.read_text(encoding="utf-8", errors="replace")
    if "p39-handlers" in text:
        findings.append(
            "STAGE 20A BYPASS: index.js references p39-handlers.js -- the Commercial Quality Orchestrator's JS "
            "composition layer is authorized as internal-only per its explicit implementation directive; wiring "
            "it into index.js requires its own separate authorization, not granted by this stage."
        )
    for fn in COMMERCIAL_ORCHESTRATOR_JS_FUNCTIONS:
        if fn in text:
            findings.append(
                f"STAGE 20A BYPASS: index.js references '{fn}' -- the Commercial Quality Orchestrator must remain "
                f"unrouted (see p39-handlers.js file header)."
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
    all_findings += check_no_duplicate_evidence_domain_model()
    all_findings += check_cec_schema_version_intact()
    all_findings += check_version_field_falsy_zero_regression()
    all_findings += check_evidence_validation_pipeline_present()
    all_findings += check_migration_adapters_intact()
    all_findings += check_cec_feature_flags_disabled()
    all_findings += check_serialization_future_formats_still_stubbed()
    all_findings += check_cec_files_present()
    all_findings += check_no_duplicate_evidence_registry()
    all_findings += check_registry_version_arithmetic_safe()
    all_findings += check_lifecycle_terminal_states_intact()
    all_findings += check_evidence_duplication_guard_intact()
    all_findings += check_index_reindexing_on_mutation_intact()
    all_findings += check_relationship_fields_and_indexes_in_sync()
    all_findings += check_supersession_stamps_superseded_at()
    all_findings += check_registration_always_indexes_evidence()
    all_findings += check_eer_files_present_and_isolated()
    all_findings += check_no_duplicate_evidence_service()
    all_findings += check_no_duplicate_service_contracts()
    all_findings += check_contract_version_drift()
    all_findings += check_no_registry_private_field_bypass()
    all_findings += check_relationship_resolution_still_unwired()
    all_findings += check_validation_service_delegates_not_reimplements()
    all_findings += check_eesp_files_present_and_isolated()
    all_findings += check_eips_files_present_and_isolated()
    all_findings += check_no_duplicate_intelligence_service()
    all_findings += check_no_duplicate_query_logic()
    all_findings += check_eips_contract_version_drift()
    all_findings += check_no_duplicate_eips_contracts()
    all_findings += check_no_eips_registry_private_field_bypass()
    all_findings += check_intelligence_relationship_still_unwired()
    all_findings += check_intelligence_validation_delegates_not_reimplements()
    all_findings += check_eips_metrics_no_duplicate_instance()
    all_findings += check_no_circular_dependency_intelligence_evidence_registry()
    all_findings += check_eig_files_present_and_isolated()
    all_findings += check_no_duplicate_enterprise_gateway()
    all_findings += check_gateway_capabilities_delegate_not_reimplement()
    all_findings += check_eig_contract_version_drift()
    all_findings += check_no_duplicate_eig_contracts()
    all_findings += check_no_eig_registry_private_field_bypass()
    all_findings += check_gateway_relationship_capability_still_passthrough()
    all_findings += check_gateway_validation_middleware_delegates_not_reimplements()
    all_findings += check_eig_metrics_no_duplicate_instance()
    all_findings += check_no_circular_dependency_gateway_intelligence_platform()
    all_findings += check_gateway_capability_authorization_present()
    all_findings += check_gateway_no_network_auth_scope_creep()
    all_findings += check_gateway_registry_describe_omits_handler()
    all_findings += check_gateway_bypass_new_direct_composition_consumers()
    all_findings += check_relationship_framework_files_present_and_isolated()
    all_findings += check_no_duplicate_relationship_engine()
    all_findings += check_relationship_framework_provider_wiring_intact()
    all_findings += check_stage17_files_present_and_isolated()
    all_findings += check_no_duplicate_explainability_engine()
    all_findings += check_no_confidence_computation_introduced_stage17()
    all_findings += check_explainability_still_unwired()
    all_findings += check_correlation_policy_versioned()
    all_findings += check_stage18_files_present_and_isolated()
    all_findings += check_no_duplicate_knowledge_platform_engines()
    all_findings += check_no_confidence_computation_introduced_stage18()
    all_findings += check_knowledge_platform_still_unwired()
    all_findings += check_stage19_files_present_and_isolated()
    all_findings += check_no_duplicate_product_platform_engines()
    all_findings += check_no_confidence_computation_introduced_stage19()
    all_findings += check_product_platform_still_unwired()
    all_findings += check_product_platform_no_python_pipeline_coupling()
    all_findings += check_commercial_orchestrator_files_present()
    all_findings += check_no_duplicate_commercial_orchestrator_functions()
    all_findings += check_commercial_orchestrator_protected_engines_intact()
    all_findings += check_commercial_orchestrator_no_new_scorer()
    all_findings += check_commercial_orchestrator_still_unwired()

    print("=== Project TITAN Architecture Governance Check (advisory) ===")
    metrics = compute_gateway_adoption_metrics()
    if metrics["total_known_consumers"]:
        print(
            f"Gateway adoption (Stage 15, informational -- not a pass/fail gate): "
            f"{metrics['gateway_backed']}/{metrics['total_known_consumers']} known consumers "
            f"Gateway-backed ({metrics['adoption_percentage']}%); "
            f"{metrics['direct_composition_legacy']} direct-composition legacy "
            f"(see TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md for the full classification).\n"
        )
    if not all_findings:
        print(f"Clean: all {len(REQUIRED_ADRS)} ADRs present, all cited references resolve, no unreviewed "
              "confidence/evidence/reliability functions found, ownership matrix in sync, "
              "documented routes still registered, Evidence Registry scaffolding boundary intact, "
              "no AR-000 regression detected (or network unavailable to check), no unreviewed "
              "graph/relationship/correlation-shaped Python files found, R3's producer chain "
              "intact, ADR-0010's tracked graph IDs (R1-R7) all present, no relationship-shape "
              "or vocabulary drift, no dormant/dead-export/zombie-pipeline status changes, "
              "Migration Blueprint not prematurely executed, Canonical Evidence Core clean "
              "(no duplicate models, no schema drift, no version-conflict regression, "
              "validation pipeline intact, all migration adapters intact, feature flags still "
              "disabled by default, serialization future-formats still stubbed, all CEC files "
              "present), Enterprise Evidence Registry clean (no duplicate registry, version "
              "arithmetic safe, lifecycle terminal states intact, evidence-duplication guard "
              "intact, indexes reindexed on mutation, relationship fields/indexes in sync, "
              "supersession stamps superseded_at, registration always indexes evidence, all "
              "EER files present and isolated), Enterprise Evidence Service Platform clean "
              "(no duplicate service, no duplicate contracts, no contract version drift, no "
              "registry private-field bypass, relationship-resolution.js still unwired by "
              "default, validation service still delegates rather than reimplements, all "
              "EESP files present and isolated), Enterprise Intelligence Platform Services "
              "clean (no duplicate IntelligenceService/ThreatIntelligenceService, no duplicate "
              "EnterpriseQueryService or query bypass, no contract version drift, no duplicate "
              "EIPS contracts, no registry private-field bypass, correlation-engine.js still "
              "unwired by default, validation service still delegates, exactly one shared "
              "ServicePlatformMetrics instance threaded through every component, no circular "
              "dependency back into evidence-registry/, all EIPS files present and isolated), "
              "Enterprise Intelligence Gateway clean (no duplicate gateway/context/registry/"
              "dispatcher/lifecycle/metrics engines, capabilities still delegate to "
              "IntelligenceService, no contract version drift, no duplicate EIG contracts, no "
              "registry private-field bypass, evidence.relationships capability still "
              "pass-through-only per ADR-0010, validation capability still delegates, exactly "
              "one shared ServicePlatformMetrics instance threaded through gateway-service.js "
              "and gateway-metrics.js, no circular dependency back into intelligence-platform/ "
              "or evidence-registry/, capability authorization present, no network-auth scope "
              "creep, all EIG files present and isolated, registry describe()/describeAll() "
              "still omit the handler function, no new scripts/ consumer bypasses the Gateway "
              "beyond the one tracked, deprecated Stage 13 exception), Stage 17 Correlation & "
              "Explainability clean (both Track A files present and isolated, no duplicate "
              "IntelligenceExplainabilityService, no confidence-computing/weighting/ranking "
              "function introduced pending ADR-0007, explainability-engine.js/correlation-policy.js "
              "still unwired from index.js, correlation policy still versioned and auditable), "
              "Stage 18 Knowledge Platform clean (all 9 knowledge-platform/ files present and "
              "isolated, no duplicate KnowledgeObjectService/KnowledgeNavigationService/"
              "AnalystViewService/ExecutiveViewService/KnowledgeQualityService/KnowledgePlatform "
              "engine, no confidence-computing/weighting/ranking function introduced pending "
              "ADR-0007, knowledge-platform/ still unwired from index.js/gateway-service.js/"
              "intelligence-service.js), Stage 19 Product Platform clean (all 8 "
              "product-platform/ files present and isolated, no duplicate ProductEngineService/"
              "ProductProfileService/ProductPackagingService/ProductQualityService/"
              "ProductPlatform engine, no confidence-computing/weighting/ranking function "
              "introduced pending ADR-0007, product-platform/ still unwired from index.js/"
              "gateway-service.js/intelligence-service.js/knowledge-platform.js, no Python "
              "dossier/report pipeline coupling detected), Stage 20A Commercial Quality "
              "Orchestrator clean (both p39-handlers.js and commercial_quality_orchestrator.py "
              "present, no duplicate orchestrator functions, all protected P20/P21/P25/P26/"
              "commercial_readiness_governor.py/dossier_quality_engine.py signatures intact, no "
              "new confidence/trust/quality/certification scorer introduced, p39-handlers.js "
              "still unwired from index.js).")
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
