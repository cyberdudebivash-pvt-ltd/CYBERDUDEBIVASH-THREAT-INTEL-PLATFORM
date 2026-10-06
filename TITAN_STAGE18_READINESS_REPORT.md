# Project TITAN — Stage 18 Readiness Report

## Enterprise Intelligence Knowledge Platform

**Program:** Project TITAN, Stage 18
**Date:** 2026-08-07
**Scope of this document:** Pre-Implementation Gate verification + Phase 1 (Knowledge Domain
Inventory), per this stage's own charter.

---

## 0. Correction to the Executive Directive's framing

Stage 18's directive lists "Canonical Confidence Framework (implemented within existing
governance boundaries)" alongside genuinely-completed items (Canonical Evidence Framework,
Evidence Registry, Gateway, etc.). Repository evidence does not support reading this as "ADR-0007
is resolved":

| Check | Method | Result |
|---|---|---|
| ADR-0007 status | `docs/adr/0007-canonical-confidence-framework.md` line 4 | **`Status: Proposed`** — unchanged since Stage 17 |
| ADR-0007 in the ADR index | `docs/adr/README.md` | Still listed **Proposed**, alongside ADR-0009/0013 |
| ADR-0007 in the Acceptance Record | `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` | **Does not appear** — only ADR-0008/0010/0011/0012 have Accepted dispositions |

What Stage 17 actually delivered, and what "implemented within existing governance boundaries"
correctly describes, is narrower: `canonical_confidence_object`/`verification_status`/
`evidence_weight` are surfaced **verbatim, never computed**, and a governance check
(`check_no_confidence_computation_introduced_stage17`) mechanically enforces that this stays true.
That is not a resolution of ADR-0007 — it is a documented way of building useful capability
*around* the still-open question. Stage 18's own brief is already written consistently with this
(Phase 4: "Confidence Context (surface existing values only)... Do not compute new confidence
values"; no phase asks for confidence computation) — this section exists so that consistency is
verified, not assumed, per this program's First Principle.

**Conclusion: ADR-0007 remains Proposed. Stage 18 must maintain the identical verbatim-only
discipline Stage 17 established — no new code in this stage may compute, weight, rank, or
propagate a confidence value.**

---

## 1. Pre-Implementation Gate — Verification Results

| Item | Verified how | Result |
|---|---|---|
| Current repository state | `git status` | Clean |
| Current main branch | `git fetch origin main` + `git log -5 origin/main` | Tip is `08be801a`, "Project TITAN Stage 17 (Track A)... (#127)" |
| Stage 17 merge integrity | `git merge-base --is-ancestor`, then direct content check (`git show origin/main:.../explainability-engine.js`) | PR #127 was squash-merged (new SHA `08be801a`, not the original `91df859f` — expected for a squash merge); file content confirmed present and correct on `origin/main` |
| Development branch | Old `claude/titan-stage-17-continuation-yir0z9` pointed at the now-merged, superseded commit. Per this program's "merged PR → restart branch" policy: `git checkout -B claude/titan-stage-17-continuation-yir0z9 origin/main` | Branch restarted cleanly from fresh `main` |
| Gateway operational status | Re-read `gateway-service.js`; re-ran its test suite | 9 capabilities pre-registered (8 Stage 14 + Stage 17's `intelligence.explainability`), all present and delegating correctly |
| Correlation service status | Re-read `correlation-engine.js` | `IntelligenceCorrelationService` intact, including Stage 17's `correlateByAttackTechnique`/`aggregateSources` additions |
| Explainability service status | Re-read `explainability-engine.js` | `IntelligenceExplainabilityService` intact; `explainEvidence()`/`buildAnalystReasoningObject()` both present |
| Evidence Registry integrity | Fresh `node --test` | 196/196 PASS |
| Governance baseline | Fresh `python3 scripts/titan_architecture_governance_check.py` | **6 findings — identical to the Stage 15/16/17-recorded baseline, 0 new** |
| Regression baseline | Fresh `python3 scripts/regression_tests.py` | **21/21 PASS** |
| Certification baseline | Fresh `python3 scripts/p33_production_certification.py` | **WORLDWIDE_RELEASE, 21/26, 5 pre-existing warnings, 0 blockers** |
| Node test baseline (all 3 lineage directories) | Fresh `node --test` × 3 | `evidence-registry/` 196/196, `intelligence-platform/` 106/106, `enterprise-gateway/` 98/98 — **400/400**, matching Stage 17's final recorded state exactly |
| Architecture Acceptance Record | Re-read `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` | Unchanged: ADR-0008/0010/0011/0012 Accepted; ADR-0007/0009/0013 absent (Proposed) |
| ADR status | See §0 | ADR-0007 Proposed; ADR-0010 Accepted (Stage 16); no ADR changes since Stage 17 |
| Competing Stage 18 work | Repository search | None found |

**Gate outcome: no blocker.** Stage 18 proceeds in full — unlike Stage 17, this stage's own brief
does not ask for anything that crosses the ADR-0007 boundary, so no phase-level partitioning is
required. The one standing constraint (verbatim-only confidence, §0) applies throughout and is
enforced the same way Stage 17 enforced it: structurally, plus a governance check.

---

## 2. Phase 1 — Knowledge Domain Inventory

### 2.1 Canonical entity types (unchanged from Stage 17 — repository evidence, not re-derived)

The only entity-relationship vocabulary this lineage defines is `entity.js`'s
`EVIDENCE_RELATIONSHIP_FIELDS`: **CVEs, threat actors, campaigns, IOCs, reports, ATT&CK
techniques.** Stage 18's brief additionally lists "Advisories," "Tactical Dossiers," and
"Detection content" as examples of knowledge objects. Repository evidence:

| Brief's example | Canonical representation found? | Disposition |
|---|---|---|
| CVEs, threat actors, malware, campaigns, ATT&CK techniques, indicators, reports | Yes — `EVIDENCE_RELATIONSHIP_FIELDS` | Knowledge Objects build directly on these |
| Advisories | No separate type — an advisory is an evidence record (`evidence_type`/`evidence_category`, open vocabulary per `entity.js`), not a distinct relationship dimension | Represented as evidence, not a new object type |
| Tactical Dossiers | **Not found anywhere in `evidence-registry/`, `intelligence-platform/`, or `enterprise-gateway/`.** Only appears in Stage 17's own brief prose, as a *downstream consumer* of Analyst Reasoning Objects ("this output should be consumable by Tactical Dossiers...") — not as an implemented entity or schema concept | **Not implemented as an object type.** Per Phase 1's own instruction ("do not invent unsupported object types"), Knowledge Objects are not built around a "Tactical Dossier" type. A Tactical Dossier remains a *future* commercial product that would *consume* Knowledge Objects — consistent with this stage's own Commercial Objective section |
| Detection content | **Not found** in this lineage (it exists only in the architecturally separate P16-P38 handler stack — e.g. `buildDetectionBlock` in `p19-handlers.js` — which Stage 15 already established has zero shared code with this lineage) | Not implemented as a Knowledge Object dimension |

**Conclusion:** the Knowledge Object Layer is built on exactly the six relationship dimensions
Stage 12-17 already established, plus the evidence record itself. No new entity type is invented.

### 2.2 What already exists that Phase 2-6 must compose, not duplicate

| Capability | Canonical owner | Reused by Stage 18 as |
|---|---|---|
| Evidence lookup (by CVE/actor/campaign/IOC/report/technique/source/confidence tier) | `IntelligenceLookupService` (Stage 13) | Knowledge Object's own evidence fetch |
| Evidence-to-evidence correlation | `IntelligenceCorrelationService` (Stage 13, extended Stage 17) | Knowledge Navigation's `relatedIntelligence`/base for `similarIntelligence` |
| Provenance (6 lineage views) | `EvidenceProvenanceEngine` (Stage 12) | Knowledge Navigation's `historicalIntelligence`; Knowledge Object's `provenance` field |
| Explainable Intelligence / Analyst Reasoning Object | `IntelligenceExplainabilityService` (Stage 17) | Knowledge Object's `summary`/`supportingEvidence`/`contradictoryEvidence`/`intelligenceGaps`/`confidenceAsRecorded` fields — reused verbatim, not recomputed |
| Structural correlation policy (conflict detection, inclusion, duplicates) | `correlation-policy.js` (Stage 17) | Knowledge Navigation's `contradictoryEvidence`; Knowledge Quality's completeness checks |
| Gateway capability registration | `EnterpriseGateway.registerCapability()`/`_registerDefaultCapabilities()` (Stage 14) | Phase 7's 5 new capabilities |
| Metrics/observability | `ServicePlatformMetrics.timed()` (Stage 12) | Phase 8's latency measurements — zero new instrumentation code |

**Genuine gaps** (justify new code, per Reuse Before Build's own escalation order): a unified
Knowledge Object shape combining the above (nothing currently returns "relationships +
explanation + collection recommendations" as one object); a deterministic structural-similarity
navigation method (nothing currently computes "similar" evidence, only "related"); Analyst/
Executive presentation views (nothing currently shapes explainability output for those two
audiences); a Knowledge Quality validation framework (nothing currently validates a *Knowledge
Object's* completeness — `correlation-policy.js` validates *evidence*, a narrower, lower-level
concern this stage composes rather than duplicates).

---

## 3. Architectural placement decision

Following the same precedent Stage 14 (`enterprise-gateway/`) and Stage 16
(`relationship-framework/`) set — a new platform-level capability gets its own directory under
`workers/intel-gateway/src/`, composing the previous layer via dependency injection rather than
being folded into it — Stage 18 introduces `workers/intel-gateway/src/knowledge-platform/`. It
depends on exactly one thing: an already-constructed `IntelligenceService` instance (specifically
its already-public `lookup`, `correlation`, `provenance`, and `explainability` properties), plus
one narrow, one-hop-down import of `intelligence-platform/correlation-policy.js`'s
`detectConflicts()` (a pure function, no DI needed — the same "one authorized hop" every prior
stage takes for its own immediately-lower layer).

**Correction made during implementation:** the original plan for this section proposed adding
`this.knowledge` directly onto `IntelligenceService`, mirroring Stage 17's `.explainability`
addition. That would create a circular dependency (`intelligence-platform ->
knowledge-platform -> intelligence-platform`, via `correlation-policy.js`) and was not implemented.
Instead, `KnowledgePlatform` stays external: `intelligence-service.js` is **not modified by this
stage at all**, and Gateway integration (Phase 7) uses `EnterpriseGateway`'s existing, unmodified
`registerCapability()` extension point rather than a change to `gateway-service.js`'s
`_registerDefaultCapabilities()`. See `knowledge-platform/README.md` for the corrected
architecture and `TITAN_STAGE18_KNOWLEDGE_PLATFORM_REPORT.md` for the full rationale. Net effect:
Stage 18 modifies zero pre-existing files in `evidence-registry/`, `intelligence-platform/`, or
`enterprise-gateway/` — a purely additive new directory, an even smaller blast radius than
Stage 17's.

Per the unbroken Stage 8-17 precedent (documented in `TITAN_STAGE17_READINESS_REPORT.md` §3), this
new directory is **not wired into `index.js` or any live production route**. Wiring any part of
this lineage into a live route remains its own, separately-authorized architectural event,
independent of this stage.

Implementation proceeds under this plan; see `TITAN_STAGE18_KNOWLEDGE_PLATFORM_REPORT.md` for what
was actually built, measured, and tested.
