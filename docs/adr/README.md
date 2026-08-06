# Architecture Decision Records — Index

This directory did not exist before Project TITAN Stage 6. It was created to hold ADR-0007
through ADR-0011, the five ownership decisions Stage 6 was chartered to produce. Stage 7 (PR
#110) added ADR-0012, filling the sixth Stage 5 subject (API versioning) Stage 6 had explicitly
left open — see `TITAN_IMPLEMENTATION_READINESS.md`'s Intelligence Provenance APIs assessment
for that gap's original framing. Stage 7 also added ADR-0013, a per-module disposition table
for the `cyberdudebivash-blog` `lib/` tree (Task 7's own subject), numbered into this same
sequence though shaped differently (a table of dispositions, not a single ownership Decision).
**Correction, Stage 11.5 (2026-08-06):** this index previously listed only ADR-0007–0011 even
after ADR-0012 and ADR-0013 existed on disk — a documentation-drift gap that fed an inaccurate
claim into `TITAN_TECH_DEBT_REGISTER.md`'s DEBT-021 (corrected the same day). The index below is
now synchronized with the actual contents of this directory.

## Why numbering starts at 0007

There is no ADR-0001 through ADR-0006 in this repository. The numbers are Project TITAN's own
— Stage 5's dispatch named the six ADR subjects it required (Evidence ownership, Evidence
lifecycle, Relationship model, API versioning, Registry responsibilities, Source reliability),
and this task's own instructions independently numbered five of those same subjects ADR-0007
through ADR-0011. This index preserves that numbering rather than renumbering from 0001, so
that anyone following a reference to "ADR-0007" from the task history or from
`CONFIDENCE_FRAMEWORK_DISCOVERY.md` / `EVIDENCE_ENGINE_DISCOVERY.md` finds the same document.
**This does not imply six prior ADRs exist in this repository** — documented explicitly here so
the gap isn't mistaken for a missing-files defect.

Do not confuse this sequence with `cyberdudebivash-blog`'s own `docs/adr/0001-phase-2a-
isolation.md` and `docs/adr/0002-multidimensional-confidence.md`. Those are a separate,
pre-existing numbering sequence in a different repository, for a different, unrelated
subsystem (the `lib/governance` publication-control-plane initiative — see
`TITAN_STAGE6_VALIDATION.md` §2 for how that system relates, and does not relate, to the
decisions below).

This repository's prose-only decision log, `ARCHITECTURE_DECISIONS.md` (repo root), predates
this directory and is not renumbered or restructured by this change — it remains "this repo's
established ADR home" for the EPTP-program decisions it already records. This directory is
additive: a second, complementary decision log using a numbered-file format for Project
TITAN's cross-repo ownership questions specifically, which don't fit ARCHITECTURE_DECISIONS.md's
existing scope (single-repo runtime/deployment decisions).

## Index

| ADR | Title | Status | Decides |
|---|---|---|---|
| [0007](./0007-canonical-confidence-framework.md) | Canonical Confidence Framework | Proposed | Which system computes authoritative per-item confidence |
| [0008](./0008-canonical-evidence-framework.md) | Canonical Evidence Framework | **Accepted** (2026-08-06) | Canonical Evidence record schema and system of record |
| [0009](./0009-source-reliability-ownership.md) | Source Reliability Ownership | Proposed | Canonical source-reliability grade and scale reconciliation |
| [0010](./0010-relationship-graph-ownership.md) | Relationship Graph Ownership | Proposed | Canonical entity-relationship graph (target-state, persistence-gated) |
| [0011](./0011-evidence-lifecycle-ownership.md) | Evidence Lifecycle Ownership | **Accepted** (2026-08-06) | Canonical evidence lifecycle state model |
| [0012](./0012-api-versioning-interface-governance.md) | API Versioning & Interface Governance | **Accepted** (2026-08-06) | Cross-surface API versioning policy; depends on ADR-0008 for Evidence API shape specifically |
| [0013](./0013-typescript-rc1-disposition.md) | TypeScript RC1 Subsystem — Production Architecture Assessment | Proposed | Per-module disposition of the dormant `cyberdudebivash-blog` `lib/` tree (DEBT-001) — a disposition table, not a single ownership Decision |

ADR-0008, ADR-0011, and ADR-0012 are **Accepted** (2026-08-06, executive architecture authority —
see each ADR's "Approval" section and `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` for the full
record, including the individually-named sign-offs that were not independently obtained).
ADR-0007, ADR-0009, ADR-0010, and ADR-0013 remain **Proposed**, not Accepted, and do not
authorize implementation on their own. Note in particular: ADR-0010 (Relationship Graph
Ownership) is **not** Accepted — Stage 12's Relationship Resolution phase depends on it and is
scoped accordingly (thin pass-through over already-live output only, no new ownership/graph
logic) until it is. See `TITAN_STAGE7_PLAN.md` for what becomes implementable once the remaining
four are approved.

## Reading order

0008 first (it defines the Evidence entity 0009, 0010, and 0011 each depend on), then 0007
(independent of 0008, but references it), then 0009 → 0010 → 0011 in dependency order. See
each ADR's "Depends on" header line. 0012 can be read any time after 0008 (it depends on 0008
only for Evidence-specific API shape; otherwise independent). 0013 is independent of all six —
a different repository, a different subject.

## Related documents

- `TITAN_STAGE6_VALIDATION.md` — discovery validation and discrepancies these ADRs account for
- `TITAN_OWNERSHIP_MATRIX.md` — the consolidated, single-table view of ADR-0007–0011's ownership
  decisions specifically (ADR-0012/0013 are policy/disposition documents, not ownership
  decisions in this matrix's sense, and are intentionally not rows in it)
- `TITAN_MIGRATION_ROADMAP.md` — the sequenced, dated implementation plan for approved ADRs
- `TITAN_TECH_DEBT_REGISTER.md` — unresolved items these ADRs surface but don't close
- `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` — where ADR-0008/0011/0012's Acceptance dispositions
  get formally recorded (added Stage 11.5)
- `CONFIDENCE_FRAMEWORK_DISCOVERY.md`, `EVIDENCE_ENGINE_DISCOVERY.md` — Stage 4/5 source
  material these ADRs decide against
