# Project TITAN Stage 11 — Migration Guide Update

**Status:** Implemented, inert. This document is an **additive update** to
`TITAN_STAGE10_EVIDENCE_MIGRATION_GUIDE.md`, not a replacement — everything in that document
remains accurate. Read it first; this document covers only what changed.

## 1. What Stage 10 left open

Stage 10's migration guide described four adapters (`P20EvidenceChainAdapter`,
`CanonicalRelationshipAdapter`, `P25ConfidenceAdapter`, `ReportItemAdapter`) and an illustrative
"what wiring one in would look like" code sample — explicitly **not performed**, because Stage
10 had nothing for an adapted record to be registered *into*. The registry didn't exist yet.

## 2. What Stage 11 adds

`registry-service.js`'s `EvidenceRegistry` is now that destination. The illustrative sample in
`TITAN_STAGE10_EVIDENCE_MIGRATION_GUIDE.md` §4 is now a **tested, working code path** —
`__tests__/migration-to-registry-integration.test.js` — though still not wired into any real
caller. The adapters themselves are unchanged (Reuse Before Build: Stage 11 composes them, it
does not modify their logic) except for one addition:

- **`ReportItemAdapter`** now also extracts `related_iocs` from `item.iocs` (an array of
  `{value, confidence, ...}` objects, the same verified live shape as its other fields), because
  Stage 11 Phase 5 added `related_iocs` to `CanonicalEvidence` for registry indexing and this
  adapter's whole job is populating every relevant field it can find on a report item.

## 3. A real bug this stage found in the migration path, and fixed

Registering the *same* legacy evidence twice (e.g. two different reports both citing the same
underlying P20 `evidence_chain`) needs to be recognized as a duplicate, not create two separate
records — that's Stage 10 Phase 7's whole "no duplication" requirement, now actually exercised
by `EvidenceRegistry.registerEvidence()`'s reuse check. The reuse check works by comparing
content hashes. But Stage 8's `computeContentHash()` (correct for the narrower `EvidenceEntity`
shape it was written for) would hash `audit_metadata.created_at` if applied to a full
`CanonicalEvidence` — a field freshly stamped with `new Date().toISOString()` on every single
`createCanonicalEvidence()` call. That means adapting the *same* legacy record twice, moments
apart, would produce two *different* hashes, and reuse detection would never fire — exactly the
duplication Phase 7 exists to prevent, silently reintroduced through a timing accident.

**Fix:** `identifiers.js` gained `computeCanonicalEvidenceContentHash()`, scoped to
`CanonicalEvidence`'s actual substantive fields (excluding `evidence_uuid`, `content_hash`,
`version`, `audit_metadata`, `feature_flag_metadata`, `canonical_confidence_object`,
`verification_status`, `evidence_weight`, `visibility` — all governance/scoring/timestamp
metadata, not evidence substance). `registerEvidence()` uses this function, not Stage 8's
original. Verified stable-across-fresh-timestamps by
`__tests__/identifiers.test.js`, and end-to-end by
`__tests__/migration-to-registry-integration.test.js`'s dedup test (adapting the same P20
`evidence_chain` twice, under two different uuids, correctly returns `reused: true` the second
time).

## 4. Updated call sequence (supersedes Stage 10's illustrative sample)

```js
import { generateEvidenceUuid } from "./evidence-registry/identifiers.js";
import { ReportItemAdapter } from "./evidence-registry/migration-adapters.js";
import { resolveEerFlags } from "./evidence-registry/feature-flags.js";
import { EvidenceRegistry } from "./evidence-registry/registry-service.js";

// Illustrative only — NOT performed inside index.js or any production route today.
const { EER_ENABLED } = resolveEerFlags(currentEnvironment);
if (EER_ENABLED) {
  const registry = new EvidenceRegistry();
  const adapter = new ReportItemAdapter();
  const evidence = { ...adapter.adapt(item), evidence_uuid: generateEvidenceUuid() };
  const { evidence: stored, reused } = await registry.registerEvidence(evidence);
  registry.noteMigrationEvent(adapter.sourceShapeName());
  // ... a future stage decides what happens next; not specified or authorized here.
}
```

Three preconditions this remains illustrative against, unchanged from Stage 10: `EER_ENABLED`
defaults `false` for `canary`/`production`; nothing outside `evidence-registry/` imports
anything from it; ADR-0008 has not been formally Accepted.

## 5. Non-goals, unchanged

Same as Stage 10: no persistence service beyond the in-memory reference repository, no public
API, no customer-visible report change, no automatic/scheduled migration job.
