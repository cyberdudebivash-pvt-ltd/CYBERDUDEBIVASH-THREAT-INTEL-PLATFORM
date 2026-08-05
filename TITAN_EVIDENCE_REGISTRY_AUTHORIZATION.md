# Project TITAN Stage 8 — Enterprise Evidence Registry Authorization (Phase 8)

**Decision: CONDITIONAL GO — scoped exactly to Phase 9's narrow allowance (entity/schema/
identifiers/serialization/validation/repository interfaces/feature flags). The full Evidence
Registry (persistence service, APIs, UI, migrations) remains explicitly Blocked and is not
authorized by this report.**

This is not a full green light. It is a narrow, deliberately-bounded authorization for inert
scaffolding, matching the smallest scope Stage 8's own Phase 9 permits, chosen because that
scope's blast radius is genuinely zero (not imported into any live route, not customer-visible,
reversible by deleting new files) — not because the broader Registry question is settled.

---

## Implementation Authorization

| Item | Authorized? | Scope |
|---|---|---|
| Canonical Evidence entity shape (JSDoc typedef, matching ADR-0008's E1 extension) | **Yes** | New, isolated file, zero imports into production router |
| Evidence identifiers (`evidence_uuid` generation) | **Yes** | Pure function, no storage side effect |
| Schema / serialization | **Yes** | Type definitions + a serialize/deserialize pair, no I/O |
| Validation | **Yes** | Pure validation functions against the schema |
| Repository interface (contract only) | **Yes** | An interface/abstract-shape definition for what a future persistence layer would implement — **not an implementation** |
| Feature flag | **Yes** | A named, off-by-default constant establishing the convention for when this is eventually wired in |
| Evidence Registry service (actual persistence) | **No — Blocked** | Requires ADR-0008 formal Acceptance + Migration Roadmap Phase 3 (P20 schema extension) shipped first |
| Evidence APIs (any route) | **No — Blocked** | Requires ADR-0012 Acceptance + Registry service existing first |
| Customer-visible UI / Evidence Explorer | **No — explicit Stage 8 Non-Goal** | Not authorized under any condition this stage |
| Migration of existing `evidence_chain` data | **No — Blocked** | Beyond scaffolding, requires its own migration plan per ADR-0008's Migration Strategy |

## Blocked Items (and why)

1. **Evidence Registry service** — blocked on ADR-0008 moving from "ready for human Acceptance
   review" (this stage's finding) to actually Accepted by a human reviewer. This program has
   never treated itself as having authority to self-approve canonical ownership decisions, and
   Stage 8 does not change that — verifying AR-000 removed a blocker to *approval*, it did not
   substitute for approval itself.
2. **Evidence APIs** — additionally blocked on ADR-0012 Acceptance (versioning policy must
   govern a new API family before it launches under it).
3. **DEBT-000B (R1 vs. R3 graph fragmentation)** — does not block Evidence entity scaffolding
   directly (Phase 9 excludes relationship fields per ADR-0008's own Future Considerations —
   EPIC 1's relationship field group is explicitly deferred to ADR-0010, not part of this
   phase), but does block any *future* phase that would add relationship references to the
   Evidence entity.

## Migration Preconditions (for the Blocked items, not for what's authorized here)

Per `TITAN_MIGRATION_ROADMAP.md` Phase 3 (unchanged by this stage): P20 schema extension
(`evidence_uuid`, `content_hash`, `schema_version` added to the *existing, live*
`item.evidence_chain`) must ship and prove stable before any Registry work begins, so the
Registry is built against a validated shape rather than a moving target. Phase 9's scaffolding
(this report) is compatible with, but does not itself satisfy, that precondition — the
scaffolding defines a *standalone* entity shape; wiring it to Migration Roadmap Phase 3's live
schema extension is future work, not done here.

## Required Refactoring

**None.** This is the entire point of scoping Phase 9 this narrowly — new, additive files only,
zero modification to any existing P-layer handler, zero modification to `index.js`'s import
chain or route table.

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scaffolding code drifts from ADR-0008's eventual Accepted shape, requiring rework | Medium | Low | Scope is intentionally minimal (types/validation only) specifically to minimize rework surface if ADR-0008's Decision changes during human review |
| Someone imports the scaffolding into a live route before ADR-0008/0012 are Accepted, jumping ahead of authorization | Low | Medium | Feature flag defaults off; code review discipline (this program's own CLAUDE.md governance) is the actual control, same as for any other unauthorized change |
| Scaffolding becomes a second dormant tree like `lib/` if the broader Registry is never authorized | Low-Medium | Low | Unlike `lib/`, this scaffolding is tiny (a handful of files, not 43 modules) and explicitly labeled as Phase 9 scaffolding pending Registry authorization — the "why does this exist" question ADR-0013 had to answer for `lib/` is pre-empted by this report's own existence |

## Rollback Strategy

Delete the new files. Nothing imports them into the production router, so no other code is
affected. This is the simplest rollback of any change this program has made — stated
explicitly because Stage 8's own Engineering Requirements ask for one, not because meaningful
risk exists.

## Go / No-Go Decision

**GO, for Phase 9's scaffolding scope only, effective immediately.**
**NO-GO, for the Evidence Registry service, Evidence APIs, or any customer-visible capability,
pending human ADR-0008 (and, for APIs, ADR-0012) Acceptance.**

Rationale: AR-000 — the concern that motivated pausing all forward implementation at the end of
Stage 7 — is resolved by direct production verification (`TITAN_AR000_RESOLUTION.md`). Nothing
else discovered this stage introduces a new blocker to the narrow scaffolding Phase 9 permits.
The broader Registry remains gated behind exactly the same human-approval requirement every
ADR in this program has carried since Stage 6 — Stage 8 clears a precondition to that approval,
it does not grant it.
