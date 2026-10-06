# Project TITAN Stage 11 — Repository Guide

**Status:** Implemented, inert. **Location:**
`workers/intel-gateway/src/evidence-registry/{registry-repository-interface.js,
in-memory-repository.js}`. Not imported by `index.js` or any production route.

## 1. Contract

`EvidenceRegistryRepositoryInterface` extends Stage 8's `EvidenceRepositoryInterface` (imported,
not duplicated) with the operations Phase 2 requires:

```
get(uuid)                          -> CanonicalEvidence | null      (Stage 8, unchanged)
put(entity)                        -> CanonicalEvidence             (Stage 8, unchanged)
findByContentHash(hash)            -> CanonicalEvidence | null      (Stage 8, unchanged)
delete(uuid)                       -> boolean                       (Stage 8, unchanged)
create(entity)                     -> CanonicalEvidence             (Stage 11 — rejects duplicates)
update(uuid, patch)                -> CanonicalEvidence             (Stage 11 — bumps version)
supersede(uuid, supersedingData)   -> CanonicalEvidence             (Stage 11 — bumps version, marks history)
archive(uuid)                      -> CanonicalEvidence             (Stage 11 — soft delete)
lookup(criteria)                   -> CanonicalEvidence[]           (Stage 11 — exact-match filter)
bulkImport(entities)               -> {imported, skipped, errors}   (Stage 11)
bulkExport()                       -> CanonicalEvidence[]           (Stage 11)
getVersionHistory(uuid)            -> CanonicalEvidence[]           (Stage 11 — oldest first, current last)
```

`create()` vs. `put()`: `create()` is strict (throws `DuplicateEvidenceError` if the identity
already exists); `put()` is Stage 8's original loose upsert (create-or-replace, no version
history side effect), preserved exactly so a hypothetical existing caller sees unchanged
behavior. `EvidenceRegistry` (the service layer) always uses `create()`/`update()`/`supersede()`
— `put()` exists only for interface completeness and backward compatibility.

## 2. The one design rule

This interface — and its implementation — is **storage-mechanics-only**. It does not judge
whether a lifecycle transition is legal; that is `lifecycle.js`'s sole responsibility, invoked by
`registry-service.js` *before* calling into a repository method. Single Responsibility: one
authority decides whether a transition is legal, a separate authority persists the result.

## 3. `InMemoryEvidenceRepository` — the reference implementation

Backed by two plain `Map`s (`_current`, `_history`) — deliberately **not** a KV/D1/R2-backed
implementation. Implementation Constraints explicitly prohibit "vendor-specific persistence,"
and Phase 2 requires the repository stay "abstract enough to support future storage backends."
A future, separately-authorized storage backend only needs to implement
`EvidenceRegistryRepositoryInterface`'s contract; nothing in `EvidenceRegistry`,
`EvidenceVersionManager`, or `EvidenceRegistryIndexes` would need to change.

**Version-history mechanics:** `update()`/`supersede()` push the outgoing current version into
`_history` (deep-frozen, via `entity.js`'s `deepFreeze()`) before installing the new current
version. `supersede()` additionally stamps the outgoing version with `superseded_at`, the one
field that distinguishes "this version was superseded" from "this version was merely updated
past" in `getVersionHistory()`'s output.

**Errors:** `DuplicateEvidenceError` (from `create()` on an existing identity) and
`EvidenceNotFoundError` (from `update()`/`supersede()`/`archive()` on a non-existent identity)
are both exported, named, catchable error classes — not generic `Error` throws — matching this
codebase's existing convention of named, informative error types.

## 4. What a future backend implementation must preserve

1. `create()` must reject an existing identity, not silently overwrite.
2. `update()`/`supersede()` must freeze the outgoing version before replacing it (immutable
   lineage — Phase 4's own requirement).
3. `archive()` must keep the record retrievable via `get()` (soft delete, not hard delete —
   `delete()` remains the separate, rarely-used hard-delete operation).
4. `getVersionHistory()` must return oldest-first, current-last.
5. Every method's async signature must be preserved exactly (`EvidenceRegistry` `await`s all of
   them) even if a synchronous backend could technically resolve immediately.

## 5. Test coverage

`__tests__/in-memory-repository.test.js` (17 tests) covers every method, including the
falsy-zero version regression guard (Section 4 of `TITAN_STAGE11_VERSIONING_GUIDE.md`) and
immutability of historical entries.
