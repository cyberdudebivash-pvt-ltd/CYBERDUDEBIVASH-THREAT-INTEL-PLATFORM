# Project TITAN Stage 11 — Evidence Lifecycle Specification

**Status:** Implemented, inert. **Location:**
`workers/intel-gateway/src/evidence-registry/lifecycle.js` (pure transition-graph logic) +
`registry-service.js` (per-identity state tracking). Not imported by `index.js` or any
production route.

## 1. The nine states

| State | Meaning |
|---|---|
| `DRAFT` | Newly registered, not yet processed |
| `COLLECTED` | Collection step complete |
| `VALIDATED` | Passed validation |
| `CORRELATED` | Correlated against other intelligence |
| `PUBLISHED` | Live, authoritative content |
| `UPDATED` | Published content has been edited (same identity, new version) |
| `SUPERSEDED` | This identity's content is no longer the live reference for its topic |
| `ARCHIVED` | Terminal — retained, retrievable, no longer active |
| `REJECTED` | Terminal — did not pass the pipeline |

## 2. Transition graph

```
DRAFT ──────► COLLECTED ──────► VALIDATED ──────► CORRELATED ──────► PUBLISHED
  │               │                 │                  │                │  ▲
  │               │                 │                  │                ▼  │ (self-loop)
  └───────────────┴─────────────────┴──────────────────┴──────────►  UPDATED
                                                                          │
                                                          PUBLISHED ──►  SUPERSEDED ──► ARCHIVED
                                                          UPDATED   ──►  SUPERSEDED
                                                          PUBLISHED ──────────────────► ARCHIVED
                                                          UPDATED   ──────────────────► ARCHIVED

  DRAFT / COLLECTED / VALIDATED / CORRELATED ──► REJECTED   (escape hatch, any pre-publication state)
```

Machine-readable form (`lifecycle.js`'s `LIFECYCLE_TRANSITIONS`):

| From | Legal next states |
|---|---|
| `DRAFT` | `COLLECTED`, `REJECTED` |
| `COLLECTED` | `VALIDATED`, `REJECTED` |
| `VALIDATED` | `CORRELATED`, `REJECTED` |
| `CORRELATED` | `PUBLISHED`, `REJECTED` |
| `PUBLISHED` | `UPDATED`, `SUPERSEDED`, `ARCHIVED` |
| `UPDATED` | `UPDATED`, `SUPERSEDED`, `ARCHIVED` |
| `SUPERSEDED` | `ARCHIVED` |
| `ARCHIVED` | *(none — terminal)* |
| `REJECTED` | *(none — terminal)* |

**Design rationale for the two non-obvious rules:**

- **`REJECTED` is reachable from every pre-publication state, not just `DRAFT`.** Evidence can
  fail at collection, validation, or correlation time — the reject path doesn't require walking
  the full pipeline first.
- **`UPDATED` self-loops.** Repeated edits to already-published content shouldn't need to
  round-trip through `PUBLISHED` between each edit; `UPDATED -> UPDATED` is legal so a record
  can be edited multiple times in sequence.
- **`updateEvidence()` is only legal from `PUBLISHED`/`UPDATED`.** Editing a `DRAFT` record isn't
  a lifecycle-significant "Updated" event — a draft is freely revisable pre-publication.
  Attempting `updateEvidence()` on a `DRAFT` record throws `IllegalLifecycleTransitionError`
  (verified by `__tests__/registry-service.test.js`).

## 3. Enforcement

Every transition, whether a pure state advance (`transitionLifecycle()`) or bundled with a
content change (`updateEvidence()`/`supersedeEvidence()`/`archiveEvidence()`), is checked against
this graph before being applied:

- `canTransition(from, to)` — pure boolean check, no exception.
- `assertValidTransition(from, to)` — throws `IllegalLifecycleTransitionError` (naming both
  states and the legal alternatives) for an illegal transition, or a plain `Error` for an
  unrecognized state name.

"Every transition must be validated... Illegal transitions must fail" (Phase 3) is satisfied by
construction: `EvidenceRegistry` never mutates its internal `_lifecycleStates` map except
through `_recordTransition()`, which always calls `assertValidTransition()` first — verified by
the governance script's `check_lifecycle_terminal_states_intact()`, which fails the build
(advisory) if `registry-service.js` ever stops referencing `assertValidTransition`.

## 4. Audit trail

Every transition — including the very first one, registration itself (`from: null`) — produces
an immutable, frozen audit entry via `buildTransitionAuditEntry(from, to, context)`:

```js
{ from: "PUBLISHED", to: "UPDATED", at: "2026-08-06T...", reason: "corrected CVE reference", actor: "analyst-1" }
```

`EvidenceRegistry.getAuditTrail(evidenceUuid)` returns the full ordered trail for one identity.
"Every transition must be auditable" (Phase 3) — this is the mechanism.

## 5. Where lifecycle state lives (and why not on `CanonicalEvidence` itself)

Lifecycle state is tracked by `EvidenceRegistry` internally (`Map<evidence_uuid, state>`), **not**
as a field on the `CanonicalEvidence` object. This is deliberate: Stage 10 already established
`CanonicalEvidence` as immutable once published (`publishEvidenceEntity`'s deep-freeze); baking
a mutable "current lifecycle state" into that same object would either violate that immutability
contract or require unfreezing/re-freezing on every transition. Instead, lifecycle state is
registry metadata *about* an evidence identity — matching "One Evidence Lifecycle": a single
registry instance is the one authority on where an identity currently stands, independent of how
many immutable version snapshots exist in its history.
