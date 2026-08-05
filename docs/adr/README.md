# Architecture Decision Records — Index

This directory did not exist before Project TITAN Stage 6. It is created now to hold ADR-0007
through ADR-0011, the five ownership decisions Stage 6 was chartered to produce.

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
| [0008](./0008-canonical-evidence-framework.md) | Canonical Evidence Framework | Proposed | Canonical Evidence record schema and system of record |
| [0009](./0009-source-reliability-ownership.md) | Source Reliability Ownership | Proposed | Canonical source-reliability grade and scale reconciliation |
| [0010](./0010-relationship-graph-ownership.md) | Relationship Graph Ownership | Proposed | Canonical entity-relationship graph (target-state, persistence-gated) |
| [0011](./0011-evidence-lifecycle-ownership.md) | Evidence Lifecycle Ownership | Proposed | Canonical evidence lifecycle state model |

All five are **Proposed**, not **Accepted**. None authorizes implementation on its own — see
each ADR's "Approval" section for required sign-offs, and `TITAN_STAGE7_PLAN.md` for what
becomes implementable once approved.

## Reading order

0008 first (it defines the Evidence entity 0009, 0010, and 0011 each depend on), then 0007
(independent of 0008, but references it), then 0009 → 0010 → 0011 in dependency order. See
each ADR's "Depends on" header line.

## Related documents

- `TITAN_STAGE6_VALIDATION.md` — discovery validation and discrepancies these ADRs account for
- `TITAN_OWNERSHIP_MATRIX.md` — the consolidated, single-table view of all decisions above
- `TITAN_MIGRATION_ROADMAP.md` — the sequenced, dated implementation plan for approved ADRs
- `TITAN_TECH_DEBT_REGISTER.md` — unresolved items these ADRs surface but don't close
- `CONFIDENCE_FRAMEWORK_DISCOVERY.md`, `EVIDENCE_ENGINE_DISCOVERY.md` — Stage 4/5 source
  material these ADRs decide against
