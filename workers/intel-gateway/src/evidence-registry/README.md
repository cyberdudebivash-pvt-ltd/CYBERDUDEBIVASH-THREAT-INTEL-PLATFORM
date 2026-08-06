# Evidence Registry — Phase 9 Scaffolding (Project TITAN Stage 8)

**This directory is not imported by `index.js` or any other production file. It has zero
runtime effect. It exists solely as the narrow, authorized scaffolding described in
`TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md`'s Go/No-Go decision.**

## What this is

Per Stage 8 Phase 9's explicit, narrow authorization: canonical Evidence entity shape,
identifier generation, serialization, validation, and a repository *interface* (contract only,
no implementation). Nothing here talks to storage, nothing here is reachable from any HTTP
route, nothing here is customer-visible.

## What this is not

- **Not** the Evidence Registry service (EPIC 2 in `EVIDENCE_ENGINE_DISCOVERY.md`'s original
  terms) — that requires ADR-0008 formal Acceptance and is explicitly Blocked.
- **Not** wired into `item.evidence_chain` (P20, `p20-handlers.js:185-244`) — this is a
  standalone extension of that shape, not a modification of it. P20's existing field,
  consumers, and CI gate (P38 G19) are completely untouched.
- **Not** an API. No route in `index.js` references any file in this directory.

## Relationship to the canonical E1 shape (P20 `evidence_chain`)

`entity.js`'s `EVIDENCE_ENTITY_FIELDS` starts from P20's **verified, currently-live** field set
(read directly from `p20-handlers.js:185-244` while writing this, not assumed from
`docs/adr/0008-canonical-evidence-framework.md`'s prose, which is slightly imprecise on this
point — see the note in `entity.js` for the correction) and adds the three Integrity fields
ADR-0008 Decision item 1 names as the required additive extension: `evidence_uuid`,
`content_hash`, `schema_version`.

## Feature flag

`feature-flags.js` exports `EVIDENCE_REGISTRY_FLAGS.SCAFFOLDING_ENABLED`, hardcoded `false`.
Nothing currently reads this flag (nothing is wired up yet) — it exists to establish the naming
convention a future stage's actual integration work should follow, per Stage 8's Engineering
Requirements ("Feature-flagged").

## Next steps (not performed here — see `TITAN_STAGE9_READINESS.md`)

1. Human review and Acceptance of ADR-0008.
2. Migration Roadmap Phase 3 (extend the *live* `item.evidence_chain` with the same three
   Integrity fields this scaffolding defines standalone) ships and proves stable.
3. Only then does wiring this scaffolding into the live schema become an authorized next step.

---

## Stage 10 extension — Canonical Evidence Core (CEC)

**Everything above this line is Stage 8 and is unmodified.** Stage 10 (Project TITAN) enlarged
this directory's domain model, still with zero runtime effect — nothing below changes what
"Not imported by `index.js`" means; it's still true. Full documentation lives in four top-level
docs (not duplicated here in full):

| Document | Covers |
|---|---|
| `TITAN_STAGE10_CANONICAL_EVIDENCE_MODEL_SPEC.md` | The `CanonicalEvidence` domain model: field groups, design decisions, immutability contract |
| `TITAN_STAGE10_SCHEMA_REFERENCE.md` | Generated field/version-history reference (run `schema.js#generateSchemaDocumentation()` to regenerate) |
| `TITAN_STAGE10_EVIDENCE_INTERFACE_SPECIFICATION.md` | All 7 interfaces (`EvidenceValidatorInterface`, `EvidenceProviderInterface`, `EvidenceSerializerInterface`, `EvidenceImporterInterface`, `EvidenceExporterInterface`, `EvidenceMigrationAdapterInterface`, plus Stage 8's `EvidenceRepositoryInterface`) |
| `TITAN_STAGE10_EVIDENCE_MIGRATION_GUIDE.md` | The 4 migration adapters, and what wiring one in would look like (illustrative, not performed) |

### File layout

```
entity.js               Stage 8 EvidenceEntity + Stage 10 CanonicalEvidence domain model
identifiers.js           Stage 8 — evidence_uuid / content_hash generation (unmodified)
validation.js            Stage 8 validateEvidenceEntity (unmodified) + Stage 10 validators
interfaces.js            Stage 10 — 6 new interface contracts (+ working defaults where noted)
repository-interface.js  Stage 8 EvidenceRepositoryInterface (unmodified, imported not duplicated)
serialization.js         Stage 10 — JSON/Markdown/DTO serializers, import/export
migration-adapters.js    Stage 10 — 4 pure-function adapters from legacy shapes
schema.js                Stage 10 — version history, compatibility checks, doc generator
feature-flags.js         Stage 8 EVIDENCE_REGISTRY_FLAGS (unmodified) + Stage 10 CEC_FLAGS
__tests__/               node:test suite — unit, integration smoke, backward-compat, perf smoke
```

### Running the tests

```
cd workers/intel-gateway/src/evidence-registry
node --test
```

Zero new dependencies — uses Node's built-in `node:test`/`node:assert`, matching this platform's
existing hand-rolled-test-runner convention (`regression_tests.py`). As of Stage 11 Phase 10:
153 tests, 0 failures. A `package.json` (`{"type": "module"}`) is scoped to this directory only —
it does not affect the parent Worker's build; it exists solely so Node resolves these files as
ESM without an auto-reparse warning.

### The one design rule that makes this directory low-risk to extend

Every file in this directory (including the migration adapters, which is where the temptation to
break this would be strongest) operates on **documented data shapes** — none of them `import`
a real `pNN-handlers.js` file or `index.js`. This means the directory's contents can grow
arbitrarily more capable without changing its "zero blast radius" property. Three independent
mechanisms guard this property so it can't silently regress:

1. `__tests__/zero-blast-radius.test.js` — nothing *outside* this directory references it.
2. `__tests__/internal-integration-smoke.test.js`'s second test — nothing *inside* this directory
   imports a handler/router file.
3. `scripts/titan_architecture_governance_check.py`'s `check_evidence_registry_scaffolding_boundary()`
   and `check_migration_adapters_intact()` — the same two properties, checked in CI (advisory).

### Feature flags: two independent gates, don't confuse them

- `EVIDENCE_REGISTRY_FLAGS.SCAFFOLDING_ENABLED` (Stage 8, `feature-flags.js`) — the **only** flag
  that would ever gate wiring this scaffolding into a live production route. Hardcoded `false`.
  Still gated on ADR-0008 Acceptance, exactly as Stage 8 left it.
- `CEC_FLAGS` (Stage 10, same file) — governs only whether this directory's own inert code may be
  *exercised* (e.g., by its own test suite, or local dev). `development`/`testing` default to
  enabled; `canary`/`production` default to disabled. **Flipping a `CEC_FLAGS` value to `true`
  has zero production blast radius by itself** — it is read by nothing outside this directory's
  own tests. Do not mistake "CEC_FLAGS.production is disabled" for "wired into production and
  gated" — it is neither wired nor readable from production code at all.

### Extending this directory further

1. Read the relevant top-level doc first (table above) — most extensions are additive to an
   existing field group, interface, or adapter, not a new top-level concept.
2. Add tests in `__tests__/` before considering a change done — `node --test` should stay
   green (currently 61/61).
3. If you add a new file, or a new exported symbol that could plausibly duplicate an existing
   evidence-domain concept, run `python3 scripts/titan_architecture_governance_check.py` — the
   Stage 10 checks (`check_no_duplicate_evidence_domain_model` et al.) exist to catch exactly
   that category of drift early.
4. Never import a `pNN-handlers.js` file or `index.js` from anywhere in this directory. If a
   future task genuinely requires that (i.e., it *is* the authorized wiring step), that is an
   architectural event requiring its own explicit authorization — see
   `TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md`'s precedent for what that authorization looked like
   for this directory's original creation.

---

## Stage 11 extension — Enterprise Evidence Registry (EER)

**Everything above this line is Stage 8/10 and is unmodified**, except two small, documented
additions to `entity.js` and `identifiers.js` (see
`TITAN_STAGE11_REGISTRY_ARCHITECTURE.md` §6). Stage 11 activated the CEC with a working internal
registry service — still zero runtime effect, still not imported by `index.js`. Full
documentation lives in five more top-level docs:

| Document | Covers |
|---|---|
| `TITAN_STAGE11_REGISTRY_ARCHITECTURE.md` | Component map, design principles, what changed in Stage 10 files and why |
| `TITAN_STAGE11_LIFECYCLE_SPECIFICATION.md` | The 9 lifecycle states, transition graph, audit trail |
| `TITAN_STAGE11_VERSIONING_GUIDE.md` | Version numbering, lineage immutability, schema compatibility |
| `TITAN_STAGE11_REPOSITORY_GUIDE.md` | The repository interface and its in-memory reference implementation |
| `TITAN_STAGE11_INTERNAL_SERVICE_GUIDE.md` | `EvidenceRegistry`'s full API surface, with usage examples |
| `TITAN_STAGE11_EVIDENCE_MIGRATION_GUIDE_UPDATE.md` | How Stage 10's migration adapters now feed a real registry |
| `TITAN_STAGE11_COMPLETION_REPORT.md` | Proof Before Change, blast radius, Reuse Report, compliance checklist |

### File layout additions

```
registry-repository-interface.js   Stage 11 — extends EvidenceRepositoryInterface (create/update/
                                    supersede/archive/lookup/bulk import-export/version history)
in-memory-repository.js            Stage 11 — reference repository implementation (in-memory only)
lifecycle.js                       Stage 11 — pure transition-graph validation, 9 states
versioning.js                      Stage 11 — version/lineage queries, schema-compat passthrough
indexes.js                         Stage 11 — 10-dimension backend-independent indexing
registry-metrics.js                Stage 11 — in-memory observability counters
registry-service.js                Stage 11 — the ONE EvidenceRegistry service class
feature-flags.js                   (extended) + Stage 11 EER_FLAGS
```

### The `EvidenceRegistry` in one line

`new EvidenceRegistry()` composes an in-memory repository, the lifecycle engine, a version
manager, indexes, and metrics into a single internal service exposing `registerEvidence`,
`getEvidence`, `findEvidence`, `findByCVE`/`findByThreatActor`/`findByReport`/etc.,
`updateEvidence`, `supersedeEvidence`, `archiveEvidence`, `resolveVersion`, `bulkImport`/
`bulkExport`, and `getMetricsSnapshot`. See `TITAN_STAGE11_INTERNAL_SERVICE_GUIDE.md` for the
full reference with examples.

### Feature flags, updated

A third, independent gate joins the two documented above: `EER_FLAGS` (Stage 11, same file as
`CEC_FLAGS`) — identical shape and defaults (`development`/`testing` enabled,
`canary`/`production` disabled), same "zero production blast radius regardless of value"
property, since nothing outside this directory's own tests reads it.
