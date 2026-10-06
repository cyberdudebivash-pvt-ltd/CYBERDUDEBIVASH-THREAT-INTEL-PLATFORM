# ADR-0008: Canonical Evidence Framework

**Date:** 2026-08-05
**Status:** **Accepted** — 2026-08-06, by executive architecture authority (see "Approval"
section below and `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`). Proposed → Revised twice (Stage 7
raised a blocker re: E9–E12's live status; Stage 8 resolved it — see "Revision 2") → Ready for
human Acceptance review (Stage 8) → Accepted (Stage 12 gate).
**Deciders (proposed reviewers):** Platform Governance Lead, Chief Threat Intelligence
Architect, Intelligence Engineering (P-layer stack owner), Blog/EIOS Engineering
**Program:** Project TITAN, Stage 6
**Related:** ADR-0009 (Source Reliability Ownership), ADR-0010 (Relationship Graph
Ownership), ADR-0011 (Evidence Lifecycle Ownership) are all sub-decisions that depend on this
ADR's canonical Evidence entity decision. Read this one first.

---

## Context

`EVIDENCE_ENGINE_DISCOVERY.md` (Stage 5) ran a 10-EPIC gap analysis of Stage 5's requested
Enterprise Evidence Intelligence Engine against existing infrastructure and found substantial
partial prior art for almost every EPIC, concluding that none of the six ADRs Stage 5 itself
required to proceed had been written. This ADR is the first of those six to be formally
proposed (EPIC 1/2's ownership question; EPICs 3–10 remain sequenced behind it per the
existing discovery document).

---

## Problem Statement

**What is the canonical schema and system of record for an "Evidence" entity in the
CYBERDUDEBIVASH® ecosystem, and which existing evidence-shaped implementation, if any, becomes
that canonical source rather than a consumer or adapter of it?**

This is distinct from ADR-0007 (confidence scores) and ADR-0009 (source reliability grades):
this ADR concerns the evidence **record** — what facts are attached to an intelligence item,
where they're stored, and what identity/integrity guarantees they carry — not the numeric
scores computed from it.

---

## Existing Implementations

Restated and extended from `EVIDENCE_ENGINE_DISCOVERY.md` §2 (EPIC 1) and
`TITAN_STAGE6_VALIDATION.md` §2–3:

| ID | System | Repo | Fields (verified) | Gap vs. Stage 5's ask |
|---|---|---|---|---|
| E1 | `item.evidence_chain` | intel-platform, `p20-handlers.js:185-244` | `evidence_id`, `source_reliability`, `reliability_code` (A–F), `source_category`, `analyst_review`, `chain_of_custody[]`, `known_limitations[]`, `iq_breakdown{}`, `corroboration_count` | No UUID, hash/fingerprint, immutable record ID, signature metadata, or version number — the entire "Integrity" field group Stage 5 asks for is absent |
| E2 | `buildEvidenceAttribution()` | intel-platform, `p18-handlers.js:78` | Independently computed A–E letter grade from substring-matching `item.source`/`item.feed_source` | Narrower than E1; render-time derived, not stored; feeds P19 narrative directly |
| E3 | `buildP32EvidenceTransparencyBlock` | intel-platform, `p32-handlers.js:804+` | Maps 5 claim types (KEV, CVSS, EPSS, Attribution, IOC count) to `{claim, source, verification, confidence, reasoning}` | Claim-level, not the 8 report-section grain Stage 5 asked for; not keyed to a stable Evidence ID because none exists yet |
| E4 (heuristic, not a record) | `p23-handlers.js:683` certification gate | intel-platform | `{ name: "Evidence Chain", pass: !!(ec && ec.source_reliability) }` | Presence check only, no duplicate/orphan/schema validation |
| E5 (heuristic, new this stage) | `_evidenceAudit` / `_hasEvidence` | intel-platform, `p37-handlers.js:202` | Local recompute from `cvss_score`/`cve_ids`/`iocs`/`kev_present`/`epss_score`/`ttps` | Fourth independent "has evidence" definition (see `TITAN_STAGE6_VALIDATION.md` §3) |
| E6 (heuristic, new this stage) | `handleP35Evidence` | intel-platform, `p35-handlers.js:371` | Fifth independent definition, different field set than E5 | Same category as E5 |
| E7 | `KnowledgeGraph` | blog, `engine/sentinel_engine/knowledge_graph.py` | Entity+typed-relation graph (Report/Actor/Malware/CVE/Technique/IOC); no first-class `Evidence` node type | Relationship substrate exists; evidence-specific node type does not (see ADR-0010) |
| **E8 (new this stage)** | `interface Evidence` | blog, `lib/intelligence/schema.ts:71-77` | `{ source, date, attribution: 'observed_fact'\|'analyst_assessment'\|'hypothesis', confidence, notes }` | Simple, clean, already-typed — but zero production consumers (`TITAN_STAGE6_VALIDATION.md` §2); no identity/integrity fields either |

Note the field-name coincidence: E8's type is literally named `Evidence` in TypeScript, the
same word Stage 5/6 use for the canonical entity this ADR defines — pure naming coincidence
given E8 has no relationship to either discovery effort, verified by its zero-consumer status
and absence from any prior TITAN document.

---

## Decision

**`item.evidence_chain` (E1, P20, intel-platform) is designated the canonical Evidence record
schema**, extended additively with the missing Integrity field group. No new Evidence Registry,
database, or API is built by this ADR — per Stage 6's own NON-GOALS, this decision establishes
*what the record looks like and who owns its shape*, not the registry that will eventually
store many of them (EPIC 2, a distinct, larger undertaking sequenced after this ADR in
`TITAN_STAGE7_PLAN.md`).

1. **E1 is canonical.** Its existing nine fields are the base schema. Additively extend with:
   `evidence_uuid` (stable identity, distinct from the existing free-form `evidence_id`),
   `content_hash` (fingerprint for dedup/tamper-detection, EPIC 8/Validation's "Duplicate
   evidence identifiers" rule depends on this existing), `schema_version` (per this repo's
   established `SCHEMA_REGISTRY` convention, see ADR discussion below).
2. **E2 (P18 `buildEvidenceAttribution`) is marked Deprecated — Pending Migration.** It is
   migrated to consume E1's `reliability_code` rather than independently deriving its own
   A–E grade (mechanics and the A–F/A–E scale reconciliation are ADR-0009's concern, not
   duplicated here — this ADR only establishes that E2 stops being an independent evidence
   source and becomes a formatter/consumer of E1).
3. **E3 (P32 evidence-transparency block) is retained and extended, not replaced.** Once
   E1 carries a stable `evidence_uuid`, E3's claim objects gain an optional
   `evidence_uuid` reference field, closing the "claims aren't keyed to a canonical Evidence
   ID" gap `EVIDENCE_ENGINE_DISCOVERY.md` §2 (EPIC 3) identified — additive, no existing field
   removed.
4. **E4, E5, E6 (certification/audit heuristics) are retained as-is for now, flagged for a
   follow-up consolidation** once E1's schema extension ships: all three should eventually
   check evidence presence via one shared helper reading E1's canonical fields rather than
   three independently-invented predicates. Not required for this ADR's approval; logged in
   `TITAN_TECH_DEBT_REGISTER.md` as a sequenced follow-up (low risk, but real duplicate-logic
   removal work, not a schema decision).
5. **E7 (blog `KnowledgeGraph`) is out of this ADR's scope** — see ADR-0010. E1 does not
   currently have a node type in either relationship graph; adding one is future EPIC-1-adjacent
   work sequenced after both this ADR and ADR-0010 are approved.
6. **E8 (`lib/intelligence/schema.ts`'s `Evidence` type) is excluded from canonical candidacy**
   for the same reason A8 was excluded in ADR-0007 — zero production consumers. Its
   `attribution` enum (`observed_fact` / `analyst_assessment` / `hypothesis`) is a genuinely
   useful, currently-absent provenance concept that E1 does not have; logged as a Future
   Consideration below rather than adopted now, since adopting a field from an unintegrated
   system into a canonical schema without evaluating it properly would itself be a small
   version of the "reuse without verifying" failure mode this program exists to prevent.

---

## Rationale

- **E1 has the richest existing field set of any live candidate** (9 fields vs. E2's single
  derived letter grade, E8's 5 fields) and is the only one already wired into a scoring
  pipeline (`computeP20QualityScore`) and a CI gate (P38 G19).
- **E1 is intel-platform-owned**, consistent with Stage 2's already-settled precedent that
  intel-platform is system of record for core intelligence data and the blog is a consumer —
  the same precedent `EVIDENCE_ENGINE_DISCOVERY.md` §4 already applied to the "Registry
  responsibilities" ADR subject. Choosing E1 over E7/E8 (both blog-side) keeps this consistent
  rather than introducing a second system-of-record precedent for evidence specifically.
- **Additive-only extension satisfies both repos' Architecture Preservation Rule** — this is
  documented, evidence-backed rationale for why E1 is insufficient as-is (missing Integrity
  fields is a real, named gap, not a stylistic preference), and the fix is field addition, not
  replacement.
- **E2's migration to consuming E1 directly resolves a concretely observed defect**
  (`EVIDENCE_ENGINE_DISCOVERY.md` §3's three-way disagreement example), not a hypothetical one.

---

## Alternatives Considered

1. **Build a new Evidence schema from scratch, informed by all of E1/E2/E7/E8.** Rejected:
   violates Reuse Before Build when E1 already covers 9 of the needed fields; a greenfield
   schema would also orphan E1's existing CI gate (P38 G19) and `computeP20QualityScore`
   integration, a larger blast radius than an additive extension for no proven benefit.
2. **Adopt E8 (`lib/intelligence/schema.ts`) as canonical, migrate P20 to match it.** Rejected:
   E8's schema is simpler than Stage 5's own EPIC 1 requirements (no identity/integrity fields
   either), has no live consumers to preserve, and migrating P20 — a heavily-consumed,
   CI-gated, live production engine — to match an unintegrated design inverts the correct
   direction of migration risk.
3. **Treat E1 and E2 as permanently coexisting, non-competing systems** (the same resolution
   Issue 15 reached for the report-structure "three tiers" finding). Considered seriously —
   Issue 15's precedent is real — but rejected here because unlike the report-structure case,
   E1 and E2 are not different tiers of one hierarchy; they are two computations of the *same*
   thing (source-type reliability) for the *same* audience (P19's SOC/executive narrative,
   which currently reads E2), which is exactly the "real duplication" category Issue 15 itself
   distinguished from "unlabeled tiers."

---

## Migration Strategy

See `TITAN_MIGRATION_ROADMAP.md` Phase 1, 4. Summary:

1. **Phase 1 (additive, low risk):** Add `evidence_uuid`, `content_hash`, `schema_version` to
   E1's `evidence_chain` shape. Populate only on write for new/re-processed items; existing
   items without these fields continue to function exactly as today (all current E1 consumers
   already treat individual `evidence_chain` fields as optional-if-absent).
2. **Phase 4 (dependent on ADR-0009's letter-scale reconciliation shipping first):** Migrate
   E2 (`buildEvidenceAttribution`) to read E1's `reliability_code` instead of re-deriving from
   substring matching, preserving E2's existing output shape (a letter-grade string) so P19's
   narrative rendering requires no change — only the computation source changes.

---

## Compatibility Impact

- **No field is removed from E1.** All additions are new, optional fields.
- **E2's output type is unchanged** (still a letter-grade string) — only its computation
  source changes in Phase 4, making this compatible with every existing P19 consumer without
  their own code changing.
- **E3's extension is additive** (`evidence_uuid` as a new optional field on existing claim
  objects).
- **No API route, response shape (beyond the additive fields above), or CI gate is removed.**

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `evidence_uuid` backfill for existing items never happens, leaving two classes of evidence records indefinitely | Medium | Medium | Track backfill coverage as a named metric in `TITAN_TECH_DEBT_REGISTER.md`, same pattern as P38 G19's existing "Evidence Chain Coverage" gate |
| E2's migration changes displayed letter grades for some sources (A–F to A–E mapping is lossy at the boundary) | Medium | Medium (customer-visible narrative text changes) | Explicit mapping table and staged rollout defined in ADR-0009; not silently absorbed into this ADR |
| Schema extension adds fields three different heuristics (E4/E5/E6) still don't use, prolonging fragmentation | High (if left unaddressed) | Low (no correctness impact, ongoing maintenance cost) | Logged explicitly in tech debt register as a required follow-up, not assumed to self-resolve |

---

## Rollback Strategy

Phase 1 is purely additive field population — rollback is ceasing to write the new fields;
no consumer breaks because none read them before this change. Phase 4's rollback is reverting
E2 to its prior substring-matching implementation, which remains in version control and is not
deleted (Deprecation Instead of Deletion) until a documented migration period elapses after
Phase 4 ships successfully.

---

## Future Considerations

- E8's `attribution: observed_fact | analyst_assessment | hypothesis` enum is a candidate
  addition to E1's schema in a future revision — logged, not adopted, pending its own
  evaluation once E8's broader disposition is settled.
- EPIC 1's "relationships" field group (Evidence→CVE/Actor/Campaign/Malware/IOC/ATT&CK) is
  explicitly deferred to ADR-0010 and not addressed here.
- The Evidence Registry itself (EPIC 2 — centralized creation/update/validation/dedup/
  versioning) remains unbuilt. This ADR only fixes what a canonical Evidence record looks like;
  building the registry that manages many of them is `TITAN_IMPLEMENTATION_READINESS.md`'s
  concern, assessed separately.

---

## Revision — 2026-08-05, Stage 7

**New candidates, blog repository, very likely live** (`TITAN_STAGE7_VALIDATION.md` §2A):

| ID | System | Verified export | Computes |
|---|---|---|---|
| E9 | `evidence-manager.js` | `EvidenceManager.addEvidence()` | Typed evidence records (12 types: article/threat_report/ioc/malware/file/hash/pcap/url/domain/screenshot/external_reference/detection_rule/note) stored in Redis against an "investigation" |
| E10 | `evidence-validator.js` | `EvidenceValidator.validateFinding()` | Checks a finding for required statement/evidence/reasoning/assumptions/limitations fields |
| E11 | `evidence-conflict-engine.js` | `EvidenceConflictEngine.detectConflicts()` | Attribution/timeline/motive/tactical/victimology/scope conflict detection across an investigation |
| E12 | `evidence-traceability-engine.js` | `EvidenceTraceabilityEngine.ensureTraceability()` | Traces product statements back to findings/IOCs/sources, computes traced-vs-orphaned coverage % |

Routed via `api/v1/analysis/{assessments,findings}.js`, `api/v1/workbench/{investigations,
cases}.js` (per the reachability trace). E9's `EVIDENCE_TYPES` enum is a real identity/typing
scheme this ADR's Integrity field group (Decision item 1) does not currently account for.

**This is a more sophisticated, more complete evidence *lifecycle* system (creation,
validation, conflict detection, traceability) than E1 (P20's `evidence_chain`) currently has**,
even though E1 remains the more consumed implementation *within the P-layer stack specifically*.
E9–E12 appear to serve an "investigation/case" grain (an analyst working a case, assembling
evidence toward findings) rather than E1's "single intelligence item" grain — these may be
genuinely different, complementary levels (an investigation aggregates many items' evidence)
rather than directly-competing implementations of the same thing, but **this ADR's original
Decision did not have this system in view when concluding E1 should be canonical**, and that
gap must be closed before Accepted status, not assumed away.

**Same blocking-approval status as ADR-0007's revision.** This ADR should not be Accepted until
a human reviewer confirms E9–E12's live status and either (a) designates them a distinct,
complementary "Investigation Evidence" capability outside this ADR's "Intelligence Item
Evidence" scope with its own future ADR, or (b) determines they should be reconciled with E1
directly. Not decided here.

---

## Revision 2 — 2026-08-05, Stage 8 (resolves Revision 1's blocker)

Direct HTTP verification confirms E9–E12 (`evidence-manager.js` and siblings, reached only via
`api/v1/analysis/*` and `api/v1/workbench/*`) are not deployed — same Vercel platform-level
`NOT_FOUND` evidence as ADR-0007's A10. Full detail: `TITAN_AR000_RESOLUTION.md`. **Reclassified
from "blocking open question" to "excluded, zero production consumers."** This ADR's Decision
stands as originally written and is ready for human Acceptance review.

## Approval

**Accepted, 2026-08-06.** Decided by executive architecture authority (cyberdudebivash,
Project TITAN executive/repository owner) via direct confirmation, recorded in
`TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`. This is an executive-authority acceptance, not a
completed multi-party review — the individually-named sign-offs below were not independently
obtained and remain unchecked; recorded accurately rather than implied. If any named Decider
later raises a substantive objection, reopen per this ADR's own Revision pattern rather than
treating this Acceptance as unconditional.

- [ ] Platform Governance Lead (not independently obtained — see note above)
- [ ] Chief Threat Intelligence Architect / P-layer stack owner (P20, P18, P32 owner) (not independently obtained)
- [ ] Blog/EIOS engineering owner (acknowledgment of E7/E8 scoping, not a blocking approval —
      neither is modified by this ADR) (not independently obtained)

Code implementing this decision (Stage 10's Canonical Evidence Core, Stage 11's Evidence
Registry) already exists, merged ahead of this Acceptance — see DEBT-021 for that history.
