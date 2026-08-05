# Project TITAN — Migration Roadmap

**Status:** Planning document. **No phase below may begin until its corresponding ADR is
Accepted** (see `docs/adr/README.md`). This roadmap sequences low-risk migrations first per
this task's explicit instruction, and threads every phase through: zero downtime, zero API
breakage, backward compatibility, incremental rollout, feature flags where appropriate, CI
validation before rollout, and a rollback path.

Phases are numbered for reference; the number is not a strict calendar order guarantee, but
each phase's "Depends on" line is a hard ordering constraint.

---

## Phase 0 — CI governance (no ADR dependency)

**Depends on:** Nothing. Can ship independent of any ADR approval.
**Risk:** Low.
**Feature flag:** Not needed — advisory-only, non-blocking (see `TITAN_CI_GOVERNANCE.md`).

Ship the advisory architecture-drift check (`scripts/titan_architecture_governance_check.py`)
as a new, non-blocking CI stage. This does not implement any ADR — it only makes future drift
of the kind this stage found (P37/P35's uncatalogued heuristics, the `lib/` blind spot)
visible sooner. Recommended first because it has no dependency on any decision being approved
and de-risks every later phase by catching new fragmentation before it accumulates further.

**Rollback:** Remove the CI stage; the script is inert otherwise.

---

## Phase 1 — Confidence: P25 gains a source-reliability input dimension

**Depends on:** ADR-0007 Accepted.
**Risk:** Low. Additive field, default-off behavior for ~100% of current live items (Evidence
Chain coverage is near 0% per P38 gate G19).
**Feature flag:** Not required — the change is inert until `evidence_chain.reliability_code` is
present on an item, which today is true almost nowhere. Recommended anyway:
`FEATURE_P25_READS_EVIDENCE_CHAIN` (default `true` once shipped, since the inert-by-data-
absence property makes a flag mostly a kill-switch, not a rollout gate).
**CI validation:** Regression suite (21/21) plus a new before/after score-comparison check on
the live feed sample, run once in the implementing PR, not a permanent gate.
**Rollback:** Revert the single commit; P25's output reverts to today's shape exactly (the new
dimension is additive to an array every consumer already iterates generically).

---

## Phase 2 — Confidence: mark A4 deprecated (documentation only)

**Depends on:** ADR-0007 Accepted.
**Risk:** None (comment/doc change only).
**Feature flag:** N/A.
**CI validation:** None beyond normal review.
**Rollback:** Revert the comment.

Can run in parallel with Phase 1 — no ordering dependency between them.

---

## Phase 3 — Evidence: P20 schema extension (Integrity field group)

**Depends on:** ADR-0008 Accepted.
**Risk:** Low. New optional fields (`evidence_uuid`, `content_hash`, `schema_version`) on a
struct every consumer already treats as partially-optional.
**Feature flag:** `FEATURE_EVIDENCE_INTEGRITY_FIELDS` recommended for the write path (ingestion
population), not the read path (reads are unconditionally safe against an optional field).
**CI validation:** Regression suite; new unit tests for the population logic; P38 gate G19
("Evidence Chain Coverage") should be watched, not gated on, since this phase doesn't change
coverage, only what's captured once populated.
**Rollback:** Stop populating the new fields; no consumer breaks since none read them yet.
This phase should ship **before** Phase 4 and Phase 6, which both depend on the extended
schema existing.

---

## Phase 4 — Source reliability: P18 migrates to consume P20's grade

**Depends on:** ADR-0009 Accepted. Independent of Phase 3 (reads `reliability_code`, which
already exists on E1 today — the *new* fields from Phase 3 aren't required for this phase,
only the pre-existing `reliability_code` field is).
**Risk:** Medium — the only phase in this roadmap with a genuine customer-visible output
change (P19 narrative letter-grade display can change for items where P20's grade disagrees
with P18's old substring-match result).
**Feature flag:** `FEATURE_P18_READS_P20_RELIABILITY` — **required**, default `false` at
ship time, flipped only after the before/after narrative-diff review named below.
**CI validation:** New diff-report step (not a hard gate) that renders the narrative-visible
grade for a sample of live items under both old and new logic, for human review before the flag
flips. This is the one phase in this roadmap where "passes CI" is not sufficient sign-off by
itself — coordinate with commercial/CS per ADR-0009's Risks table.
**Rollback:** Flip the feature flag back to `false`. Old substring-match code is retained
(Deprecation Instead of Deletion) specifically so this rollback path exists without a revert.

---

## Phase 5 — Relationship graph: P31 persistence (prerequisite, not yet an implementation commitment)

**Depends on:** ADR-0010 Accepted, **and** a separate engineering-estimation pass (this
roadmap does not estimate it — see `TITAN_IMPLEMENTATION_READINESS.md`, marked Blocked).
**Risk:** Not yet assessed — this is exactly why it's marked Blocked rather than scheduled.
**Feature flag:** To be defined at implementation time.
**CI validation:** To be defined at implementation time.
**Rollback:** To be defined at implementation time.

This phase is intentionally the least specified in this roadmap. Committing to a rollout plan
for work that hasn't been scoped would violate this program's own evidence-based-only
standard. Its entry here exists to reserve its position in the sequence (after Evidence schema
work, before any Evidence-node-in-graph work), not to promise a timeline.

---

## Phase 6 — Evidence lifecycle: derivation function

**Depends on:** ADR-0011 Accepted **and** Phase 3 (extended Evidence schema) shipped, since the
derived lifecycle state is exposed alongside Evidence records.
**Risk:** Low. Pure function, reads P30's existing outputs, writes nothing to P30.
**Feature flag:** Not required for the function itself (it's inert until called). Recommended
for the *exposure* point (wherever the derived state is first rendered):
`FEATURE_EVIDENCE_LIFECYCLE_DISPLAY`.
**CI validation:** New unit tests against P30's existing signal shapes, using recorded fixtures
so the tests don't depend on live feed state.
**Rollback:** Remove the exposure point; the derivation function has no side effects to unwind.

---

## Sequencing summary

```
Phase 0 (CI governance)         — no dependency, ship anytime
Phase 1 (P25 + reliability_code) ─┐
Phase 2 (A4 deprecation notice)  ─┤ ADR-0007, parallel, independent of each other
Phase 3 (P20 schema extension)  ─── ADR-0008, prerequisite for Phase 4 and Phase 6
Phase 4 (P18 → P20 migration)   ─── ADR-0009, depends on Phase 3's field existing (reliability_code itself predates Phase 3)
Phase 5 (P31 persistence)       ─── ADR-0010, Blocked pending separate estimation
Phase 6 (Lifecycle derivation)  ─── ADR-0011, depends on Phase 3
```

No phase requires downtime. No phase removes an existing API route, response field, or CI gate.
Every phase with a customer-visible output change (Phase 4 only) has an explicit feature flag
and a non-CI human review step, not just automated gating.

---

## What this roadmap deliberately excludes

The Enterprise Evidence Registry, Provenance APIs, Knowledge Graph (beyond Phase 5's
persistence prerequisite), and Explainable AI are not phased here — per Stage 6's NON-GOALS and
this task's Task 7, they are assessed for readiness, not scheduled, in
`TITAN_IMPLEMENTATION_READINESS.md`. This roadmap only sequences the six ADRs' own migration
strategies.
