# Project TITAN Stage 10 — Canonical Evidence Core Interface Specification

**Status:** Implemented, inert. **Location:**
`workers/intel-gateway/src/evidence-registry/{interfaces.js,repository-interface.js}`. Mirrors
`TITAN_GRAPH_INTERFACE_SPECIFICATION.md`'s structure for the analogous graph-side interfaces
(Stage 9 Phase 2). None of these interfaces are imported by `index.js` or any production route.

## 1. Interface inventory

Seven interfaces total: one pre-existing (Stage 8, unmodified) plus six new (Stage 10 Phase 3).

| Interface | File | Stage | Has a working default implementation? |
|---|---|---|---|
| `EvidenceRepositoryInterface` | `repository-interface.js` | 8 | No — pure contract, all methods throw. Storage is explicitly out of scope. |
| `EvidenceValidatorInterface` | `interfaces.js` | 10 | Yes — delegates to `validation.js` |
| `EvidenceProviderInterface` | `interfaces.js` | 10 | Partial — `getByUuid` delegates to an injected repository; `getByRelatedEntity` is a pure contract |
| `EvidenceSerializerInterface` | `interfaces.js` | 10 | No (contract) — defaults in `serialization.js` |
| `EvidenceImporterInterface` | `interfaces.js` | 10 | No (contract) — default in `serialization.js` |
| `EvidenceExporterInterface` | `interfaces.js` | 10 | No (contract) — default in `serialization.js` |
| `EvidenceMigrationAdapterInterface` | `interfaces.js` | 10 | No (contract) — four defaults in `migration-adapters.js` |

**Design rule from Phase 3's own scope** ("no storage implementation yet, only contracts and
default adapters"): interfaces that don't require persistence (Validator, Serializer, Importer,
Exporter, MigrationAdapter) get a working default implementation alongside their contract; only
Provider (which composes Repository) and Repository itself stay pure contracts.

## 2. `EvidenceRepositoryInterface` (Stage 8, unmodified)

```
get(evidenceUuid) -> Promise<EvidenceEntity | null>
put(entity) -> Promise<EvidenceEntity>
findByContentHash(contentHash) -> Promise<EvidenceEntity | null>
delete(evidenceUuid) -> Promise<boolean>
```

Every method throws `NOT_IMPLEMENTED`. No KV/R2/D1 binding is referenced anywhere in this file —
persistence requires its own, separate authorization. Stage 10 imports this interface (does not
redefine it) wherever a repository is needed — see `EvidenceProviderInterface` below.

## 3. `EvidenceValidatorInterface`

```
validate(entity, options?) -> StrictValidationResult
validateBatch(entities) -> StrictValidationResult
```

The **only** interface whose default implementation is not a stub — both methods delegate
directly to `validation.js`'s `validateCanonicalEvidence` / `validateEvidenceBatch` (Reuse Before
Build: this class does not re-implement any check, it composes the pure functions Phase 4 built).

## 4. `EvidenceProviderInterface`

```
constructor(repository: EvidenceRepositoryInterface)
getByUuid(evidenceUuid) -> Promise<CanonicalEvidence | null>       // delegates to repository.get()
getByRelatedEntity(entityId) -> Promise<CanonicalEvidence[]>        // contract only, throws
```

Composes an **injected** `EvidenceRepositoryInterface` rather than importing a concrete one.
Calling `getByUuid` before a real repository exists throws *that* interface's own
`NOT_IMPLEMENTED` message, not a duplicate — there is exactly one "storage isn't authorized yet"
error message in this codebase, not two, by construction.

## 5. `EvidenceSerializerInterface`

```
serialize(entity: CanonicalEvidence) -> string
deserialize(payload: string) -> CanonicalEvidence
```

Three default implementations in `serialization.js`:

| Class | Round-trips? | Notes |
|---|---|---|
| `JsonEvidenceSerializer` | Yes | Plain `JSON.stringify`/`JSON.parse`, no custom reviver/replacer |
| `MarkdownEvidenceSerializer` | No — `deserialize()` throws | Output-only presentation format, matching this platform's existing report-generation convention |
| `DtoEvidenceSerializer` | Yes (structural, not reference equality) | `CanonicalEvidence`'s own shape IS the DTO; this class exists so "internal DTO" is an addressable format per Phase 5's own list |

`"stix"` and `"api"` are **named future capabilities**, not silently missing formats —
`getSerializer("stix")` / `getSerializer("api")` throw a specific, dated message
(`NOT_YET_AUTHORIZED`) rather than a generic "unknown format" error, so a caller learns *why*
(Observable Everything), and `check_serialization_future_formats_still_stubbed()` (governance
script) guards against either one silently starting to succeed.

## 6. `EvidenceImporterInterface` / `EvidenceExporterInterface`

```
import(payload, opts?) -> Promise<{imported: CanonicalEvidence, warnings: string[]}>
export(entities, format) -> Promise<string>
```

`DefaultEvidenceImporter` composes `JsonEvidenceSerializer.deserialize()` +
`validateCanonicalEvidence()` — the contract is literally "deserialize, then validate"; an
invalid payload throws before being returned as `imported`. `DefaultEvidenceExporter` delegates
to `getSerializer(format)` per entity and joins the results (JSON as an array; Markdown joined
with a `\n\n---\n\n` separator).

## 7. `EvidenceMigrationAdapterInterface`

```
adapt(legacyShape) -> CanonicalEvidence
sourceShapeName() -> string
```

Four concrete adapters in `migration-adapters.js` — see
`TITAN_STAGE10_EVIDENCE_MIGRATION_GUIDE.md` for what each one adapts from and how a future,
separately-authorized stage would actually wire one in.

## 8. Cross-cutting design property: zero blast radius by construction

None of these interfaces or their default implementations import a live `pNN-handlers.js` file
or `index.js`. `EvidenceProviderInterface` composes `EvidenceRepositoryInterface` (also a pure
contract); the migration adapters operate on **documented data shapes**, not handler imports (see
the migration guide). This means every interface in this document can grow arbitrarily more
capable without changing this property — enforced by
`__tests__/zero-blast-radius.test.js`, `__tests__/internal-integration-smoke.test.js`'s second
test, and the governance script's `check_evidence_registry_scaffolding_boundary()` /
`check_migration_adapters_intact()`.
