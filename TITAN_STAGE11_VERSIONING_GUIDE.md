# Project TITAN Stage 11 — Version Management Guide

**Status:** Implemented, inert. **Location:**
`workers/intel-gateway/src/evidence-registry/versioning.js` (query layer) +
`in-memory-repository.js` (storage mechanics). Not imported by `index.js` or any production
route.

## 1. Two distinct version concepts — do not conflate them

| Field | Versions... | Lives on | Changes when |
|---|---|---|---|
| `schema_version` | The **shape** of `CanonicalEvidence` (which field groups exist) | Every evidence record | The domain model itself gains/changes a field group (a Stage-level event, e.g. Stage 10 → Stage 11) |
| `version` | A **specific record's** revision number | Every evidence record | `updateEvidence()`/`supersedeEvidence()` is called on that identity |

`schema_version` compatibility is `schema.js`'s job (Stage 10 Phase 2, reused, not
reimplemented). `version` lineage is this guide's subject.

## 2. Version numbering

- New records start at `version: 1` (or whatever `extension.version` the caller explicitly
  passes to `createCanonicalEvidence` — `0` is honored, not coerced to `1`; see Section 4's
  regression note).
- Every `update()`/`supersede()` call increments `version` by exactly 1 relative to the current
  version at the time of the call (`in-memory-repository.js`'s `computeNextVersion()`).
- Version numbers are per-identity (`evidence_uuid`), not global.

## 3. Version lineage

`EvidenceVersionManager` (constructed with a repository) exposes:

| Method | Returns |
|---|---|
| `getCurrentVersion(uuid)` | The current version (delegates to `repository.get()`) |
| `getVersionLineage(uuid)` | Full ordered history, oldest first, current last |
| `getHistoricalVersions(uuid)` | Every version except the current one |
| `getSupersededVersions(uuid)` | Historical versions with a `superseded_at` timestamp |
| `resolveVersion(uuid, versionNumber)` | A specific version number, or `null` |

**"Version lineage must be immutable" (Phase 4)** is enforced one layer down, at the repository:
every entry `getVersionHistory()` returns except the current one is deep-frozen
(`in-memory-repository.js`, reusing `entity.js`'s `deepFreeze()` — see
`TITAN_STAGE11_REGISTRY_ARCHITECTURE.md` §6 for why that function was extracted). Mutating a
historical entry throws `TypeError` (strict mode), verified by
`__tests__/in-memory-repository.test.js` and `__tests__/versioning.test.js`.

## 4. A real bug this stage found and fixed

`in-memory-repository.js`'s version-bump arithmetic originally risked the exact falsy-zero
pattern Stage 10 found in `createCanonicalEvidence`'s `version` handling: `current.version || 1`
would treat an explicit `version: 0` as absent, silently resetting it to `1` instead of bumping
to `1` from a genuine zero — masking what should be a detectable version conflict two records
colliding at "version 1" when one was actually a fresh `version: 0`. Fixed to
`typeof current.version === "number" ? current.version : 1`, then `+ 1`. Guarded against
regression by the governance script's `check_registry_version_arithmetic_safe()` (verified via a
fixture harness to fire if the `||` form is reintroduced) and
`__tests__/in-memory-repository.test.js`'s "falsy-zero safe" test.

## 5. Schema compatibility (delegated, not reimplemented)

`EvidenceVersionManager.checkSchemaCompatibility(evidence)` reads `evidence.schema_version` and
checks it against the current `CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION` via `schema.js`'s existing
`isForwardCompatible`/`isBackwardCompatible` — it does not re-walk `SCHEMA_VERSION_HISTORY`
itself. `migrateIfNeeded(evidence)` returns the evidence unchanged when compatible (true for
every schema version recorded today, since every step so far has been additive-only) and throws
a labelled error — not a guessed transformation — for a hypothetical future incompatible,
non-additive schema version. See `TITAN_STAGE10_SCHEMA_REFERENCE.md` for the full version
history this compatibility check walks.

## 6. What this guide does not cover

Persistence durability, cross-instance version reconciliation, and conflict resolution across
concurrent writers are all out of scope — `InMemoryEvidenceRepository` is single-instance,
in-process, and this stage introduces no concurrency model. A future, separately-authorized
storage backend would need its own concurrency-control story; this guide describes the version
*semantics* such a backend must preserve, not how to make them safe under concurrent writes.
