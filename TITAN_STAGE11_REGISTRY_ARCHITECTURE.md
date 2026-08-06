# Project TITAN Stage 11 — Enterprise Evidence Registry (EER) Architecture

**Status:** Implemented, inert. **Location:** `workers/intel-gateway/src/evidence-registry/`.
**Not imported by `index.js` or any production route.** This document describes the internal
registry service Stage 11 activated on top of Stage 10's Canonical Evidence Core (CEC) — it
does not authorize wiring it into production (unchanged: still gated on ADR-0008 Acceptance).

## 1. Mission

Stage 10 built the domain model (`CanonicalEvidence`) every future evidence-handling capability
depends on. Stage 11 activates that foundation with a working **Enterprise Evidence Registry**:
a governed, versioned, feature-flagged internal service that manages evidence lifecycle,
relationships, and reuse — still invisible to customers, still zero HTTP surface, still zero
persistence outside an in-memory reference implementation.

## 2. Implementation principles, and where each lives

| Principle | Where it's satisfied |
|---|---|
| One Evidence Registry | `registry-service.js`'s single `EvidenceRegistry` class — enforced by the governance script's `check_no_duplicate_evidence_registry()` |
| One Evidence Repository | `EvidenceRegistryRepositoryInterface` (contract) + `InMemoryEvidenceRepository` (the one reference implementation) |
| One Evidence Lifecycle | `lifecycle.js`'s single transition graph; `EvidenceRegistry` is the one authority tracking current state per identity |
| One Version Authority | `EvidenceVersionManager`, composing the repository's version-history storage |
| One Evidence Identity | `evidence_uuid` (Stage 8), unchanged — the repository's primary key |
| One Registry API (Internal) | `EvidenceRegistry`'s public methods — no HTTP layer, no second API surface |
| Zero Duplicate Persistence | `InMemoryEvidenceRepository` is the only storage; nothing else stores a `CanonicalEvidence` |
| Zero Breaking Changes | Every Stage 8/10 export/behavior verified unchanged (`__tests__/backward-compatibility.test.js`) |
| Feature-Flag Controlled | `feature-flags.js`'s `EER_FLAGS`, all-disabled for canary/production |
| Backward Compatible | Additive-only; see Section 6 |

## 3. Component map

```
                         ┌─────────────────────────┐
                         │   EvidenceRegistry       │  registry-service.js
                         │   (the ONE service)      │  — Phases 1, 6, 7
                         └────────────┬─────────────┘
             ┌───────────┬────────────┼────────────┬───────────────┐
             ▼           ▼            ▼             ▼               ▼
  ┌──────────────┐ ┌───────────┐ ┌──────────┐ ┌─────────────┐ ┌───────────────┐
  │ InMemory     │ │ lifecycle │ │ Evidence │ │ Evidence    │ │ Evidence      │
  │ Evidence     │ │ .js       │ │ Version  │ │ Registry    │ │ Registry      │
  │ Repository   │ │ (Phase 3) │ │ Manager  │ │ Indexes     │ │ Metrics       │
  │ (Phase 2)    │ │           │ │ (Phase 4)│ │ (Phase 5)   │ │ (Phase 9)     │
  └──────────────┘ └───────────┘ └──────────┘ └─────────────┘ └───────────────┘
         │                              │
         ▼                              ▼
  validateCanonicalEvidence      schema.js's isForwardCompatible /
  (Stage 10 Phase 4, reused,     isBackwardCompatible (Stage 10 Phase 2,
   not reimplemented)             reused, not reimplemented)
```

Every arrow is composition (a constructor dependency or a direct function call), never
reimplementation — see each file's own docstring for its specific "Reuse Before Build" citation.

## 4. Why an in-memory reference repository, not a real backend

Implementation Constraints explicitly prohibit "vendor-specific persistence," and Phase 2 itself
requires the repository stay "abstract enough to support future storage backends."
`InMemoryEvidenceRepository` satisfies `EvidenceRegistryRepositoryInterface` using plain
in-process `Map`s — no KV/D1/R2 binding is referenced anywhere in `evidence-registry/`. A future,
separately-authorized storage backend only needs to implement the same interface; nothing above
the repository layer (`EvidenceRegistry`, `EvidenceVersionManager`) would need to change.

## 5. The one design rule every layer follows

No file in this directory imports a live `pNN-handlers.js` file or `index.js`. This is the same
"zero blast radius regardless of sophistication" property `migration-adapters.js` established in
Stage 10, now extended across the registry service, repository, lifecycle engine, version
manager, and indexes. Three independent mechanisms enforce it:

1. `__tests__/zero-blast-radius.test.js` — nothing *outside* this directory references it.
2. `__tests__/internal-integration-smoke.test.js` — nothing *inside* this directory imports a
   handler/router file.
3. The governance script's `check_evidence_registry_scaffolding_boundary()` (Stage 8) and
   `check_eer_files_present_and_isolated()` (Stage 11) — the same two properties, checked in CI.

## 6. What changed in Stage 10 files, and why

Two Stage 10 files were extended (not replaced) to support Stage 11:

- **`entity.js`**: added `related_iocs` to `EvidenceRelationshipFields` (Phase 5 required an IOC
  index; no existing field covered it — verified against the live `item.iocs` shape, not
  assumed) and bumped `CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION` to `1.1.0-draft` (additive-only,
  recorded in `schema.js`'s `SCHEMA_VERSION_HISTORY` with `backwardCompatibleWithPrevious: true`).
  Also extracted `publishEvidenceEntity`'s deep-freeze recursion into its own exported
  `deepFreeze()` function — a pure refactor, zero behavior change — so version-history freezing
  (`in-memory-repository.js`) could reuse it instead of duplicating the recursion.
- **`identifiers.js`**: added `computeCanonicalEvidenceContentHash()` alongside Stage 8's
  `computeContentHash()` (unchanged). Necessary because naively reusing `computeContentHash` on
  a full `CanonicalEvidence` would fold in volatile Stage 10 fields (`audit_metadata.created_at`,
  freshly stamped on every construction) into the hash, making cross-report reuse detection
  (Phase 7) never match two otherwise-identical records. See
  `TITAN_STAGE11_EVIDENCE_MIGRATION_GUIDE_UPDATE.md` for the full story.

Neither change altered an existing export's behavior — verified by
`__tests__/backward-compatibility.test.js` (unchanged, still passing) and dedicated new tests in
`__tests__/identifiers.test.js`.

## 7. Test coverage

153 tests across 15 files as of Stage 11 (`node --test` from `workers/intel-gateway/src/
evidence-registry/`), zero new dependencies. See `TITAN_STAGE11_COMPLETION_REPORT.md` for the
full validation-gate results.

## 8. Related documents

| Document | Covers |
|---|---|
| `TITAN_STAGE11_LIFECYCLE_SPECIFICATION.md` | The 9 lifecycle states, transition graph, audit trail |
| `TITAN_STAGE11_VERSIONING_GUIDE.md` | Version numbering, lineage immutability, schema compatibility |
| `TITAN_STAGE11_REPOSITORY_GUIDE.md` | The repository interface and its in-memory reference implementation |
| `TITAN_STAGE11_INTERNAL_SERVICE_GUIDE.md` | `EvidenceRegistry`'s full API surface, with usage examples |
| `TITAN_STAGE11_EVIDENCE_MIGRATION_GUIDE_UPDATE.md` | How Stage 10's migration adapters now feed a real registry |
| `TITAN_STAGE11_COMPLETION_REPORT.md` | Proof Before Change, blast radius, Reuse Report, compliance checklist |
