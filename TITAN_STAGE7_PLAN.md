# Project TITAN — Stage 7 Plan (Task 8)

**Status:** Planning only, per this task's explicit instruction. Nothing in this document is
implemented by it. This plan is itself contingent — it assumes ADR-0007 through ADR-0011 reach
Accepted status; if any do not, the corresponding scope item below is removed, not
force-implemented against an unapproved decision.

---

## Scope

Stage 7 is the first *implementation* stage of Project TITAN's evidence/confidence governance
work — Stage 6 produced decisions, Stage 7 executes the low-risk portion of them.

**In scope**, contingent on ADR approval (see Dependencies):

1. `TITAN_MIGRATION_ROADMAP.md` Phase 0 — CI governance stage (already shipped this stage,
   listed here for completeness of the Stage 6→7 transition record, not as new Stage 7 work).
2. Phase 1 — A1 (P25) gains the `reliability_code`-reading dimension (ADR-0007).
3. Phase 2 — A4 deprecation notice (ADR-0007).
4. Phase 3 — P20 Evidence schema extension: `evidence_uuid`, `content_hash`, `schema_version`
   (ADR-0008).
5. Explainable AI v1 scoping check — audit whether `/api/v1/p38/confidence-audit` already
   satisfies a "confidence-only" explainability requirement, per
   `TITAN_IMPLEMENTATION_READINESS.md`'s finding that this capability is closest to Ready.

**Explicitly out of scope for Stage 7** (remain Blocked per the readiness assessment):

- Phase 4 (P18 migration) — sequenced for Stage 7 only if Phase 3 ships early enough in Stage 7
  to also complete the required before/after narrative-diff review within the same stage;
  otherwise deferred to Stage 8. Flagged as a stretch item, not a commitment.
- Phase 5 (P31 persistence) — requires its own estimation pass before it can even be scoped
  into a stage; Stage 7 should produce that estimate but not necessarily complete the work.
- Phase 6 (Evidence lifecycle derivation function) — depends on Phase 3 shipping with enough
  runway left in the stage to also build the derivation function; likely Stage 8.
- Evidence Registry, Provenance APIs, Knowledge Graph (full) — Blocked per
  `TITAN_IMPLEMENTATION_READINESS.md`, not scoped into Stage 7 at all.
- Any `lib/` (blog repo) disposition work — DEBT-001 is a decision prerequisite, not an
  implementation task, and belongs to whoever holds blog-repo architecture-review authority,
  not necessarily this program's Stage 7.

---

## Dependencies

| Dependency | Status | Blocks |
|---|---|---|
| ADR-0007 Accepted | Pending human approval | Phases 1, 2 |
| ADR-0008 Accepted | Pending human approval | Phase 3, Explainable AI v1's data model |
| ADR-0009 Accepted | Pending human approval | Phase 4 (stretch item only) |
| A–F→A–E mapping reviewer sign-off (ADR-0009 specific) | Pending, flagged separately from general ADR approval | Phase 4 specifically |
| P31 persistence estimation pass | Not started | Phase 5 scoping (not full completion) |

If ADR-0007 or ADR-0008 is not accepted before Stage 7 begins, Stage 7's scope shrinks to
whichever of Phase 1–3 remains unblocked; this plan does not assume all five ADRs are approved
together.

---

## Deliverables

1. Phase 1 shipped: A1's new dimension, with before/after score-comparison evidence attached to
   the implementing PR (per ADR-0007's Migration Strategy).
2. Phase 2 shipped: A4 and A9 marked `@deprecated` in code and blog-side documentation.
3. Phase 3 shipped: P20 schema extension, with a coverage-tracking metric added (per DEBT-006),
   modeled on P38 gate G19's existing pattern.
4. A written estimate (not implementation) for P31 persistence, feeding Phase 5's eventual
   scoping.
5. A short written finding on whether `/api/v1/p38/confidence-audit` satisfies Explainable AI
   v1, with a recommendation to either ship a thin wrapper or mark the capability Ready as-is.
6. An updated `TITAN_OWNERSHIP_MATRIX.md` reflecting each ADR's status change from Proposed to
   Accepted (or documenting why any did not advance).

---

## Acceptance Criteria

- Regression suite remains 21/21 after every Stage 7 change.
- P33 certification remains WORLDWIDE_RELEASE, 0 blockers.
- STAGE 5.9.4 (this stage's CI governance check) reports clean after Stage 7's changes, or any
  new findings are triaged and either resolved or explicitly logged in
  `TITAN_TECH_DEBT_REGISTER.md` — not silently ignored.
- No existing API response shape loses a field; only additive fields are introduced (Phases 1
  and 3 are both additive-only by design).
- Phase 4, if attempted, ships behind `FEATURE_P18_READS_P20_RELIABILITY` defaulted `false`,
  with the narrative-diff review completed and attached to the implementing PR before the flag
  is flipped — not flipped by default at merge time.

---

## Risk Assessment

Inherits each shipped phase's own ADR-documented risks (ADR-0007/0008's Risks tables) — not
restated in full here. Stage-level risks specific to sequencing:

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ADR approval takes longer than Stage 7's timeline, leaving nothing to implement | Medium | Medium | Stage 7's scope is explicitly contingent (see Dependencies); a Stage 7 that ships zero phases because no ADR was approved is a valid, non-failure outcome, not a plan failure |
| Phase 3's schema extension reveals an unanticipated consumer that reads `evidence_chain` positionally/by key-count rather than by key-name | Low | Medium | Regression suite + STAGE 5.9.4's broken-reference check both run before merge; additive-only fields are chosen specifically to minimize this class of risk |
| Scope creep — Stage 7 absorbing Phase 4/5/6 under schedule pressure despite them being explicitly out of scope | Medium | Medium | This document is the reference for what Stage 7 actually committed to; any expansion should itself be logged, not silently absorbed |

---

## Migration Strategy

Identical to `TITAN_MIGRATION_ROADMAP.md` Phases 1–3 — this plan does not introduce a
different migration approach, it schedules a subset of the already-documented one into a
concrete stage.

---

## Testing Strategy

- Existing regression suite (`scripts/regression_tests.py`, 21/21) and P33 certification
  (`scripts/p33_production_certification.py`) run on every Stage 7 PR — no new test
  infrastructure required, both already gate the branch.
- Phase 1: new unit tests for the added A1 dimension's read-from-`evidence_chain` logic,
  including the "field absent" default-behavior case (the common case today).
- Phase 3: new unit tests for the schema-extension write path, plus a fixture-based test
  ensuring existing consumers that don't know about the new fields are unaffected.
- STAGE 5.9.4's advisory check runs on every PR automatically once merged to the default
  branch — no additional wiring needed for Stage 7's own changes to be covered by it.

---

## Success Metrics

- Phases 1–3 shipped with zero regression-suite failures and zero P33 certification blockers
  introduced.
- Evidence Chain coverage (P38 gate G19) has a documented baseline captured before Phase 3, so
  future stages can measure whether the new Integrity fields' backfill (DEBT-006) is actually
  progressing.
- STAGE 5.9.4 runs clean (or with only already-logged tech-debt findings) across Stage 7's PRs,
  the evidence needed to consider promoting it from advisory to blocking in a future stage.
- Zero new confidence/evidence/reliability-shaped functions introduced during Stage 7 without
  a corresponding ADR addendum — measured directly by STAGE 5.9.4's own detection mechanism,
  the same one that found A9 and `_computeConfidenceGraph` this stage.
