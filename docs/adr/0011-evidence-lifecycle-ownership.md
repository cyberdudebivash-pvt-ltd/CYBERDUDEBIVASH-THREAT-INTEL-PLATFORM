# ADR-0011: Evidence Lifecycle Ownership

**Date:** 2026-08-05
**Status:** **Accepted** — 2026-08-06, by executive architecture authority (see "Approval"
section below and `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`).
**Deciders (proposed reviewers):** Platform Governance Lead, Chief Threat Intelligence
Architect, Intelligence Engineering (P30 owner)
**Program:** Project TITAN, Stage 6
**Depends on:** ADR-0008 (Canonical Evidence Framework) — lifecycle states apply to the
Evidence entity that ADR defines.

---

## Context

Stage 5's EPIC 5 asked for an evidence lifecycle with seven named states: Collected →
Validated → Correlated → Published → Updated → Superseded → Archived, with immutable audit
history. `EVIDENCE_ENGINE_DISCOVERY.md` §2 found this "conceptually covered, not
state-machine-shaped" — real signal exists (P30's verification status, timeline, IOC lifecycle,
change tracking) but nothing enumerates it as these seven states, and none of it is
evidence-record-scoped.

---

## Problem Statement

**What is the canonical Evidence lifecycle state model, and is it a new state machine or a
derivation from existing signal?**

---

## Existing Implementations

| ID | System | Repo | What it actually computes | Scoping |
|---|---|---|---|---|
| L1 | `buildP30VerificationBlock` | intel-platform, `p30-handlers.js` | Verification status across 8 signal dimensions | Item-scoped, not evidence-record-scoped |
| L2 | `buildP30TimelineBlock` / `_computeTimeline` | intel-platform, `p30-handlers.js` | Chronological event timeline | Item-scoped |
| L3 | `_computeIOCLifecycle` | intel-platform, `p30-handlers.js` | IOC-specific lifecycle: ACTIVE / MONITORING / HISTORICAL | IOC-scoped (narrower than "evidence") |
| L4 | `buildP30ChangeTrackingBlock` | intel-platform, `p30-handlers.js` | Change tracking over time | Item-scoped |
| L5 | `layer-08-report-version-control.md` front matter | blog | Versioning fields | Report-scoped; **explicitly disclaims** touching "physical storage lifecycle" |
| **L6 (new this stage)** | `WorkflowEngine` (`lib/governance/workflow.ts`) | blog | 15-state FSM: `canTransition`, `transitionState`, `getTransitionHistory`, `resetToDraft` | **Publication workflow** (Draft→Review→Approved→Published, analyst-facing), not evidence lifecycle — different domain, zero production consumers (`TITAN_STAGE6_VALIDATION.md` §2) |

L1–L4 are real, live, item-scoped signal. L6 is the only true state-machine implementation
found anywhere in either repo, but it models a different thing (who approved this content for
publication) than what Stage 5/6 ask for (what has happened to this piece of evidence).

---

## Decision

**No new evidence-lifecycle state machine is built. A new, additive, seven-state enum
(Collected → Validated → Correlated → Published → Updated → Superseded → Archived) is defined
as a derivation layer over P30's existing signals (L1–L4), computed, not separately tracked.**

1. **P30 (L1–L4) is the canonical data source.** A new pure function (name TBD at
   implementation time, e.g., `deriveEvidenceLifecycleState(item)`) reads L1's verification
   status, L2's timeline, L3's IOC lifecycle (where applicable), and L4's change tracking, and
   maps their combination to one of the seven named states. No new field is written to `item`
   by ingestion; the state is computed on read, the same architectural pattern P25's trust score
   already uses successfully.
2. **The mapping is additive documentation + one new function, not new instrumentation.**
   Per `EVIDENCE_ENGINE_DISCOVERY.md` §4's own observation, this follows Stage 5's "Zero
   Business Logic Duplication" principle: wrap existing computations in named states rather than
   re-deriving them from raw ingestion data a second time.
3. **L5 (blog versioning) is unaffected** — it already explicitly disclaims this scope; no
   conflict to resolve.
4. **L6 (`lib/governance/workflow.ts`) is not adopted and not deprecated** — it is out of scope
   because it answers a different question (publication approval state, not evidence
   lifecycle) for a different, currently-unintegrated system (per ADR-0007/0008's treatment of
   the same `lib/` tree). It is cited here as prior art for its *audit-trail and transition-
   history design*, which the new derivation function's history requirement (below) should
   emulate, not for its FSM itself.
5. **Immutable audit history** (Stage 5's requirement) is satisfied by treating the *inputs* to
   the derivation (L1–L4, which already accumulate over time in P30) as the audit trail, rather
   than building a new append-only log. If a gap is later found where L1–L4's existing history
   does not actually preserve enough detail to reconstruct why a state transition occurred,
   that is a defect in P30 to fix directly (Stage 6 does not modify P30), not grounds for a
   parallel audit system.

---

## Rationale

- **Avoids re-instrumenting ingestion.** P30 already computes real signal from real data. A
  state machine that requires new write-time instrumentation at every ingestion point would be
  a materially larger, riskier undertaking than a read-time derivation function, for
  information P30 already has.
- **Consistent with this program's established pattern** — P25's trust score, P20's quality
  score, and now this derivation are all "compute a named, explainable output from existing
  signal" rather than "instrument new state tracking." Keeping the pattern consistent lowers
  the learning curve for whoever implements this.
- **L6 is excluded on the same evidentiary basis as A8/E8 in ADR-0007/0008** — zero production
  consumers disqualifies it from being "the" canonical anything today, independent of its
  design quality (which, for transition history specifically, is genuinely worth learning from).

---

## Alternatives Considered

1. **Build a real state machine (adopt L6's FSM pattern, retarget it at evidence).** Rejected
   for this stage: requires new write paths at every point evidence changes state, a
   materially larger scope than Stage 6's NON-GOALS permit ("This stage must not... rewrite
   APIs"), and duplicates signal P30 already computes. Revisit only if the derivation approach
   proves insufficient once implemented (see Future Considerations).
2. **Leave lifecycle uncatalogued, since P30's signal already exists and "works."** Rejected:
   Stage 5 was explicit that the absence of named states, specifically, was the gap — analysts
   and API consumers currently cannot ask "is this Superseded?" without independently
   reconstructing the answer from four different P30 blocks each time. Naming the states has
   real value even without new tracking.
3. **Scope the seven states to IOCs only, extending L3 directly.** Rejected as too narrow —
   Stage 5's EPIC 5 asks for evidence-record-level lifecycle, not IOC-only; L3 remains a useful
   input to the derivation for IOC-type evidence specifically, not a substitute for the whole
   thing.

---

## Migration Strategy

See `TITAN_MIGRATION_ROADMAP.md` Phase 6 (sequenced last among the five ADRs' migrations,
appropriately, since it depends on ADR-0008's Evidence entity existing first).

1. Ship ADR-0008's Evidence schema extension.
2. Implement `deriveEvidenceLifecycleState()` as an isolated, pure, unit-testable function
   against P30's existing outputs — no changes to P30 itself.
3. Expose the derived state as an additive field wherever Evidence records are already
   rendered (e.g., alongside E3's evidence-transparency block, per ADR-0008 item 3).
4. Do not remove or rename any of L1–L4's existing block names or shapes.

---

## Compatibility Impact

- **Zero changes to P30.** This ADR's mechanism is entirely additive — a new function
  consuming P30's existing, unmodified outputs.
- **No existing API response shape changes** until the derived state is deliberately added as
  a new field at a specific consumption point (Phase 6 implementation detail, not this ADR).
- **L5 and L6 are both untouched.**

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| P30's existing signals don't cleanly map to all seven states (e.g., no existing signal distinguishes "Correlated" from "Validated") | Medium | Medium | Named explicitly as an implementation-time risk; if a genuine gap is found, the resolution is a documented, additive extension to P30's signal (a P30 defect fix, in-scope for whoever implements this), not a reason to abandon the derivation approach |
| "Computed, not stored" state is more expensive to query at scale than a stored field | Low | Low | Same performance profile as P25's already-proven computed-on-read pattern; no new risk class introduced |
| Analysts expect a real workflow (can transition state, add notes) rather than a read-only derived label | Medium | Low–Medium | Explicitly scoped out of this ADR — if genuinely needed, it is new capability (Stage 7+ candidate), not a reason to withhold the read-only version now |

---

## Rollback Strategy

The derivation function is new, additive, and reads nothing it writes — rollback is deleting
or disabling the function and any field that exposes its output. P30 itself is never modified,
so there is no data-migration to reverse.

---

## Future Considerations

- If the read-only derived-state model proves insufficient (analysts need to *assert* a state,
  not just observe one — e.g., manually marking evidence Superseded ahead of what the signals
  alone would derive), a future ADR should evaluate whether L6's FSM pattern (transition
  validation, audit trail, `resetToDraft`-style correction path) is worth adapting at that
  point — explicitly deferred, not decided now.
- Revisit L5's "explicitly disclaims physical storage lifecycle" scoping once the Evidence
  Registry (EPIC 2, not built by this stage) exists, since "physical storage lifecycle" may
  become directly relevant once evidence records are centrally stored rather than embedded per
  item.

---

## Approval

**Accepted, 2026-08-06.** Decided by executive architecture authority (cyberdudebivash,
Project TITAN executive/repository owner) via direct confirmation, recorded in
`TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`. This is an executive-authority acceptance, not a
completed multi-party review — the individually-named sign-offs below were not independently
obtained and remain unchecked; recorded accurately rather than implied.

- [ ] Platform Governance Lead (not independently obtained — see note above)
- [ ] Chief Threat Intelligence Architect / P30 owner (not independently obtained)

Code implementing this decision (Stage 11's `lifecycle.js`) already exists, merged ahead of this
Acceptance — see DEBT-021 for that history.
