# Project TITAN — Stage 17 Readiness Report

## Enterprise Intelligence Correlation & Explainable Intelligence Platform

**Program:** Project TITAN, Stage 17
**Date:** 2026-08-06
**Scope of this document:** Pre-Implementation Gate verification + Phase 1 (Correlation Domain
Audit) + Phase A (Governance Reconciliation / Dependency Matrix), per this stage's own charter.

---

## 0. Correction to the assumed baseline

The continuation brief for this session states that a prior session "completed" a Stage 17
Readiness Report and was about to ask how to proceed when it hit a usage limit. Repository
evidence does not support treating that as completed prior work:

| Check | Method | Result |
|---|---|---|
| `TITAN_STAGE17_READINESS_REPORT.md` exists anywhere in the working tree | `find` | **Not found** |
| Referenced anywhere in git history, any branch | `git log --all --oneline \| grep -i stage17` | **Zero commits** |
| Any Stage 17 artifact on `origin/main` or the current branch | `git log --all` | **Zero matches** |

**Conclusion:** the prior session's file, if it was created, was created in an ephemeral
container's working directory and was never committed before the session ended (session
transcripts show file creation immediately followed by a question to the user, then "Usage limit
reached" — no commit step in between). Per this program's own First Principle ("repository
evidence overrides transcripts... if repository evidence contradicts assumptions: stop, document,
continue only from verified state"), this report is a fresh, independently-verified Pre-Implementation
Gate and Dependency Matrix, not a continuation of unseen prior analysis. Where this report reaches
the same conclusion the transcript describes (ADR-0007 status, in particular), that is because both
sessions read the same underlying file — not because the earlier conclusion was assumed.

---

## 1. Pre-Implementation Gate — Verification Results

| Item | Verified how | Result |
|---|---|---|
| Current repository state | `git status` | Clean, nothing to commit |
| Current branch | `git branch -a` / `git rev-parse` | `claude/titan-stage-17-continuation-yir0z9`, local HEAD identical to `origin/claude/titan-stage-17-continuation-yir0z9` (`6b025288`) |
| Repository drift vs. `main` | `git rev-list --left-right --count origin/main...HEAD` | `55  56` — expected, not anomalous: `main` carries this repo's continuous automated commit stream (feed syndication, telemetry, guardian reports — visible in `git log`), unrelated to Stage 17. No merge-conflict markers found (`<<<<<<<`/`=======`/`>>>>>>>`, repo-wide) |
| Stage 16 merge integrity | `git log --oneline` | `2f19e66a` "Project TITAN Stage 16: Enterprise Relationship Framework (ADR-0010 Accepted) (#126)" present on current branch history; `TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md` and `TITAN_STAGE16_GOVERNANCE_REPORT.md` both present and consistent with each other (governance-blocked report dated same day as the subsequent Accepted/implemented report — matches ADR-0010's own revision history) |
| Enterprise Gateway operational status | Read `enterprise-gateway/gateway-service.js`, ran its test suite | `EnterpriseGateway` class present, composes `IntelligenceService`, pre-registers 8 capabilities (`evidence.lookup`, `intelligence.query`, `intelligence.correlation`, `intelligence.validation`, `intelligence.threatProfile`, `evidence.provenance`, `evidence.relationships`, `platform.metrics`). **Not imported by `index.js` or any live Cloudflare Worker route** — internal-only, by design, unbroken since Stage 14 (see §3) |
| Evidence Registry integrity | Read `evidence-registry/entity.js`, `registry-service.js`; ran its test suite | `EvidenceRegistry`/`EvidenceService`/`CanonicalEvidence` present and intact. 196/196 `node --test` pass |
| Evidence Service integrity | Read `evidence-registry/evidence-service.js` | `EvidenceService` facade (Lookup/Version/Lifecycle/Validation/Relationship/Metrics) intact, delegates verbatim to `EvidenceRegistry` — no duplicated logic |
| Current governance baseline | `python3 scripts/titan_architecture_governance_check.py` | **6 findings — identical to the baseline recorded in `TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md`/`TITAN_STAGE16_GOVERNANCE_REPORT.md`, 0 new.** Exit code 0 (advisory) |
| Current regression baseline | `python3 scripts/regression_tests.py` | **21/21 PASS** |
| Current certification baseline | `python3 scripts/p33_production_certification.py` | **WORLDWIDE_RELEASE, 21/26 checks, 5 pre-existing warnings (evidence-chain/detection-bundle/HTML-report-count — data-pipeline characteristics unrelated to this stage), 0 blockers** |
| Node test baseline (all 3 lineage directories) | `node --test` × 3 | `evidence-registry/` 196/196, `intelligence-platform/` 68/68, `enterprise-gateway/` 95/95 — **359/359**, matching Stage 15/16's recorded baseline exactly |
| Architecture Acceptance Record | Read `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` | Records **Accepted**: ADR-0008, ADR-0011, ADR-0012 (Stage 11.5, 2026-08-06) + ADR-0010 (Stage 16 Addendum, 2026-08-06). **ADR-0007 does not appear in this record.** |
| ADR-0007 status | Read `docs/adr/0007-canonical-confidence-framework.md` directly + `docs/adr/README.md` index | **`Status: Proposed`** — "Revised twice... Ready for human Acceptance review" but not accepted. Confirmed in both the ADR file itself and the index table |
| Competing Stage 17 work | Repository search | No other Stage 17 branches, PRs, or artifacts found |

**Gate outcome:** no hard blocker. Unlike Stage 16 (where the ADR under review, ADR-0010, was the
entire subject of that stage and triggered a full stop), ADR-0007 here blocks only a subset of
Stage 17's ten phases. Repository evidence supports partitioning, not stopping — see §4.

---

## 2. Phase 1 — Correlation Domain Audit

### 2.1 Two architecturally separate systems exist — Stage 17 extends one, not both

`TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md` §2.3 (re-verified, unchanged this session) already
established that this repository contains two systems with **zero shared code**:

| | P16–P38 handler stack | Evidence Registry / Intelligence Platform / Enterprise Gateway lineage |
|---|---|---|
| Location | `workers/intel-gateway/src/p{16-38}-handlers.js`, `index.js` | `evidence-registry/`, `intelligence-platform/`, `enterprise-gateway/` |
| Data model | Flat `item` object from `env.INTEL_R2`'s `feeds/feed.json` | `CanonicalEvidence` (Stage 10 schema) |
| Wiring | Live production, routed from `index.js` | **Not imported by `index.js` or any production route — every file in all three directories says so in its own header comment**, unbroken since Stage 8 |
| Existing "correlation" | `handleP18Correlation` (CVE cross-source clustering over flat feed items) | `IntelligenceCorrelationService` (`intelligence-platform/correlation-engine.js`) |
| Existing "confidence explanation" | `buildConfidenceExplanationBlock`, `buildP22ContradictionBlock` (P22) | None — genuine gap (§2.3) |

Stage 17's brief names its reuse targets as "Evidence Registry," "Evidence Services," "Gateway,"
and "Provenance" — capitalized terms that match the second column's vocabulary exactly, and this
is the lineage every prior stage (8, 10, 11, 12, 13, 14, 15, 16) built on. **Stage 17 extends this
lineage. It does not touch the P16–P38 handler stack** — building a translation layer between the
two would itself be the "unauthorized architectural event" Stage 15 already declined to build.

### 2.2 Prior art already covering part of Stage 17's brief

| Stage 17 asks for | Already exists as | Gap |
|---|---|---|
| "Evidence Correlation Engine... composes Evidence Registry/Services" (Phase 2) | `IntelligenceCorrelationService` (Stage 13): `correlateEvidence`, `correlateBySource`, `correlateByReport`, `correlateByIOC`, `correlateByRelationship`, `aggregateConfidence` (tier tally, not computation) | No `correlateByAttackTechnique` (asymmetric with the other four `correlateBy*` methods — `EvidenceQueryEngine.lookupByAttackTechnique` exists but isn't exposed at this layer); no multi-source aggregation view analogous to `aggregateConfidence`'s tally shape |
| "Provenance preserved" (Phase 2/4) | `EvidenceProvenanceEngine` (Stage 12): 6 lineage views (evidence/version/relationship/confidence/source/audit) | None — directly reusable as-is |
| "Explainable Intelligence Engine" (Phase 3) | **Nothing.** Grep for `explain`/`Explain` across `evidence-registry/`, `intelligence-platform/`, `enterprise-gateway/`: zero matches (the only hits are in the architecturally separate P22/P25/P27/P32 handler files) | Genuine gap — new code justified |
| "Analyst Reasoning Output" (Phase 5) | **Nothing** in this lineage | Genuine gap — new code justified. Deliberately implemented as **one** engine with Phase 3 (see §5), not two, per Single Source of Truth |
| "Correlation Policy framework" (Phase 4) | **Nothing** in this lineage | Genuine gap for the ADR-independent policies; confidence-propagation policies explicitly out of scope (§4) |
| "Gateway Integration" (Phase 6) | `EnterpriseGateway.registerCapability()` — documented "extension point for a future capability beyond the 8 pre-registered," DI-composed, no hardcoded service wiring | Direct extension point exists; no gap |

### 2.3 Canonical intelligence entities currently supported (this lineage)

From `evidence-registry/entity.js`'s `EVIDENCE_RELATIONSHIP_FIELDS` (the only entity-relationship
vocabulary this lineage defines — not invented for this report): `related_reports`,
`related_cves`, `related_threat_actors`, `related_campaigns`, `related_attack_techniques`,
`related_iocs`. Plus `EVIDENCE_QUALITY_FIELDS`: `canonical_confidence_object` (documented in
`correlation-engine.js`/`provenance-engine.js` as a verbatim projection of P25's
`computeEnterpriseTrustScore()` output — never recomputed in this lineage), `verification_status`
(enum: `UNVERIFIED`, `PARTIALLY_VERIFIED`, `VERIFIED`, `DISPUTED`), `evidence_weight`. No entity
type outside this set is invented by this report or by the implementation that follows it.

---

## 3. A second, ADR-independent architectural boundary

Stage 17's brief asks to "expose all new capabilities through the Gateway" and reuse "Gateway"
generally. Repository evidence (Stage 15/16 reports, and this session's direct reads of
`evidence-registry/README.md`, `relationship-framework/README.md`, and every file header in the
three lineage directories) shows a second, independent constraint that predates and does not
depend on ADR-0007:

> **No file in `evidence-registry/`, `intelligence-platform/`, or `enterprise-gateway/` has ever
> been wired into `index.js` or a live Cloudflare Worker route — even after its governing ADR was
> Accepted.** Stage 16 (ADR-0010, Accepted the same day it shipped) explicitly kept its own
> implementation unwired: *"Not wired into `index.js` or any live production route... requires
> separate authorization"* (`TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md`, Status line and §11).

This is enforced mechanically, not just by convention: `zero-blast-radius.test.js` in each
directory asserts nothing outside the directory imports it, and
`scripts/titan_architecture_governance_check.py` has directory-specific "still unwired" checks
(e.g. `check_relationship_resolution_still_unwired`) that fail if a live handler import appears.

**Implication for this stage:** even the ADR-0007-independent parts of Stage 17 are only safe to
wire as far as this lineage's existing precedent goes — composed into `IntelligenceService` and
registered as an internal Gateway capability via `registerCapability()`, exactly like the 8
capabilities already there, but **not** added as a new route in `index.js`. That last step has
required its own explicit authorization for every one of the six stages that came before this one,
independent of whichever ADR was in play, and this report treats Stage 17 the same way rather than
being the first stage to break that pattern without a documented reason to.

---

## 4. Phase A — Dependency Matrix

| Stage 17 Phase | ADR dependency | Canonical owner (if ADR-gated) | Existing implementation reused | Status | Safe to implement now |
|---|---|---|---|---|---|
| 1. Correlation Domain Audit | None | — | This document | Complete | **Yes** |
| 2. Evidence Correlation Engine | None for evidence/source/report/IOC dimensions. Relationship dimension depends on ADR-0010 — **Accepted** (Stage 16) | — | `IntelligenceCorrelationService` (extend, not replace) | New: 2 methods (`correlateByAttackTechnique`, `aggregateSources`) | **Yes** |
| 3. Explainable Intelligence Engine | Confidence-dimension attribution/weighting sub-asks depend on ADR-0007 — **Proposed**. Supporting evidence / lineage / provenance / missing-evidence / gaps do not | ADR-0007: undecided (candidate owner P25 per schema comment, not ratified) | `EvidenceProvenanceEngine`, `IntelligenceCorrelationService`, `EvidenceQueryEngine` | New: `IntelligenceExplainabilityService`, confidence fields surfaced **verbatim only** | **Yes**, minus confidence attribution/weighting |
| 4. Correlation Policies | "Confidence propagation," "evidence weighting" (as a scoring/numeric concept) depend on ADR-0007. Evidence inclusion, provenance validation, duplicate handling, conflict detection do not | ADR-0007 for the confidence-adjacent policies | New module, composes Query Engine + entity schema enums | New: `correlation-policy.js` | **Yes**, minus confidence-weighted policies |
| 5. Analyst Reasoning Output | "Confidence contributors" depends on ADR-0007. Summary/supporting evidence/contradictory evidence/provenance chain/gaps do not | ADR-0007 for confidence contributors | Same engine as Phase 3 (Single Source of Truth — not a second implementation) | New (folded into Phase 3's engine) | **Yes**, minus confidence contributor ranking |
| 6. Gateway Integration | None (mechanical) | — | `EnterpriseGateway.registerCapability()` | New: 1 capability registration | **Yes** — as an internal capability only, not an `index.js` route (§3) |
| 7. Governance Expansion | "Confidence is traceable" depends on ADR-0007. Evidence traceability, provenance validation, unsupported-evidence detection, Gateway-only-access enforcement do not | ADR-0007 for confidence traceability | `scripts/titan_architecture_governance_check.py` (extend) | New: 5 checks | **Yes**, minus confidence-traceability check |
| 8. Observability & Performance | None | — | `service-performance-smoke.test.js` pattern (Stage 15) | New: measured benchmark | **Yes** |
| 9. Documentation | None | — | Stage 15/16 report format | New: this document + completion report | **Yes** |
| 10. Validation & Certification | Explainability-consistency tests that assert confidence-contributor ranking depend on ADR-0007; everything else does not | ADR-0007 for that one test category | `node --test`, `regression_tests.py`, `titan_architecture_governance_check.py`, `p33_production_certification.py` | Run as-is + new suites | **Yes**, minus confidence-ranking consistency tests |

---

## 5. Decision: partition and proceed (Track A), defer Track B

Per this task's own execution model ("if a dependency is blocked by ADR ownership, document it
explicitly, defer only that portion, and continue implementing all remaining production-ready
capabilities"), and because §4 shows every phase has a governance-safe subset:

- **Track A (implemented this stage):** correlation engine extensions (2 methods), a new
  Explainability/Analyst-Reasoning engine that surfaces existing evidence, provenance, and
  relationship data — including the existing `canonical_confidence_object`/`verification_status`
  fields **verbatim, never computed or weighted** — a deterministic Correlation Policy module
  scoped to structural rules only, Gateway capability registration, governance checks (including a
  new automated check that the ADR-0007 boundary itself holds), tests, and documentation.
- **Track B (deferred — Stage 17B):** confidence propagation, confidence contributors/weighting,
  a confidence-aware correlation policy, and the one governance check and test category that would
  require them. See the Deferred Capability Register in the completion report for the itemized
  list and the exact unblock condition (ADR-0007 Accepted — the same documented, evidence-based
  condition Stage 16 used for ADR-0010, not a new standard invented for this stage).

This mirrors, rather than departs from, the codebase's own established practice: Stage 12's
`relationship-resolution.js` and Stage 13's `correlateByRelationship()` both shipped
ADR-0010-independent scaffolding while ADR-0010 was still Proposed, then had a concrete provider
injected the day ADR-0010 was Accepted — without changing their own code. Track A's confidence
fields are structured the same way: passthrough-only now, ready to carry a governed value the day
ADR-0007 is Accepted, with no shape change required at that point.

Implementation proceeds under this plan; see `TITAN_STAGE17_CORRELATION_EXPLAINABILITY_REPORT.md`
for what was actually built, measured, and tested.
