# Project TITAN Stage 10 — Canonical Evidence Core Migration Guide

**Status:** Implemented, inert, zero live consumers. **Location:**
`workers/intel-gateway/src/evidence-registry/migration-adapters.js`. Mirrors
`TITAN_GRAPH_MIGRATION_BLUEPRINT.md`'s structure for the analogous graph-side migration
(Stage 9 Phase 2). **This guide documents how a future, separately-authorized stage would wire
one of these adapters in — it does not perform that wiring, and no such authorization exists as
of this writing.**

## 1. The four adapters and what each migrates

| Adapter | Source shape ("Legacy") | Verified against | Produces |
|---|---|---|---|
| `P20EvidenceChainAdapter` | P20's live `item.evidence_chain` | `p20-handlers.js`, `buildEvidenceChainBlock` (same shape `entity.js`'s `EvidenceChainCore` documents) | `CanonicalEvidence` with Core+Integrity fields populated, Stage 10 fields defaulted |
| `CanonicalRelationshipAdapter` | An array of `CanonicalRelationship` records (`TITAN_GRAPH_INTERFACE_SPECIFICATION.md` Part A) that cite a given evidence UUID | The relationship schema spec, not a live producer (none exists yet — R1's shape hasn't migrated to it) | The same `CanonicalEvidence`, with its `related_*` arrays populated from whichever relationships cite it |
| `P25ConfidenceAdapter` | P25's `computeEnterpriseTrustScore(item)` return value | `p25-handlers.js`'s own return statement, not assumed | The same `CanonicalEvidence`, with `canonical_confidence_object` (verbatim) and a derived `evidence_weight` (`pct / 100`, clamped to `[0, 1]`) |
| `ReportItemAdapter` | A whole P-layer report `item` (`item.evidence_chain`, `item.id`, `item.cve_id`/`cves`, `item.actor_tag`/`threat_actor`, `item.campaign_id`, `item.mitre_techniques`) | Defensive field-access style matching how `p20`/`p25-handlers.js` themselves already read `item` | Composes the other three adapters' logic in one call — the "Existing Report Structures" adapter |

"Existing Confidence Objects" (Phase 7's fourth named category) is `P25ConfidenceAdapter`;
"Existing Graph Structures" is `CanonicalRelationshipAdapter`; "Legacy Evidence Objects" is
`P20EvidenceChainAdapter`; "Existing Report Structures" is `ReportItemAdapter`. All four names
from Phase 7's charter are accounted for — no fifth adapter was found necessary.

## 2. The one design rule every adapter follows

**Every adapter is a pure function/class operating on a documented data shape — never an import
of the actual `pNN-handlers.js` file that produces that shape.** This is deliberate, not an
oversight:

- Adopting any of these adapters never creates a real module dependency edge from
  `evidence-registry/` into `p20-handlers.js` / `p25-handlers.js` / `p31-handlers.js`.
- This keeps the directory's "zero blast radius" property (enforced by the governance script's
  `check_evidence_registry_scaffolding_boundary()` and, as of Phase 10,
  `check_migration_adapters_intact()`) trivially true **regardless of how sophisticated these
  adapters get** — sophistication is not blast-radius risk here, only a real `import` would be.
- Each adapter's docstring cites exactly where its source shape was verified, so a shape change
  upstream is a documentation-review trigger, not a silent drift.

The practical consequence: an adapter degrades gracefully (missing fields → empty
arrays/defaults) rather than throwing, matching `p20`/`p25-handlers.js`'s own defensive style —
except where the input is structurally wrong (e.g., `null` passed to `ReportItemAdapter.adapt()`,
or `CanonicalRelationshipAdapter.adapt()` called without an `evidence` key), which throws a
specific, named error rather than silently producing a nonsensical result.

## 3. "Migration must be transparent. No consumer rewrites." — how Phase 7 satisfies this

Satisfied by construction: **nothing calls these adapters in production today**, so there is no
consumer to rewrite. When a future, separately-authorized stage does wire one in, it is choosing
to call a pure function — no existing code needs to change shape to accommodate it. The adapter
does not require its caller to restructure `item` first; it reads `item` exactly as
`p20`/`p25-handlers.js` already produce it.

## 4. What wiring one in would actually look like (illustrative only — not performed)

```js
// Inside a future, separately-authorized integration point (NOT index.js today):
import { ReportItemAdapter } from "./evidence-registry/migration-adapters.js";
import { validateCanonicalEvidence } from "./evidence-registry/validation.js";
import { resolveCecFlags } from "./evidence-registry/feature-flags.js";

const { CEC_ENABLED } = resolveCecFlags(currentEnvironment);
if (CEC_ENABLED) {
  const adapter = new ReportItemAdapter();
  const evidence = adapter.adapt(item); // item = existing P-layer report item, untouched
  const { valid, errors } = validateCanonicalEvidence(evidence);
  // ... a future stage decides what "valid" leads to; not specified or authorized here.
}
```

Three preconditions this illustration deliberately does not satisfy today, so it remains
illustrative: (1) `CEC_ENABLED` is hardcoded `false` for `canary`/`production` in
`feature-flags.js` — see Section 5; (2) no file outside `evidence-registry/` imports anything
from it (`check_evidence_registry_scaffolding_boundary()`); (3) ADR-0008 has not been formally
Accepted.

## 5. Rollback

`feature-flags.js` exports `rollbackCecFlags()`, which returns the all-disabled
(`CEC_FLAGS.production`) state unconditionally — a rollback procedure calls this one function
rather than needing to remember which environment string means "off." Because nothing is wired
in today, "rollback" for Stage 10 itself is simply: revert the commit. The function exists so a
*future* integration inherits a tested rollback primitive from day one, not so it does anything
today.

## 6. Non-goals of this migration path (explicitly deferred)

Per Stage 10's own charter: no persistence service, no public API, no customer-visible report
change, no automatic/scheduled migration job. This guide describes the shape of a future,
separately-authorized wiring decision — it is not that authorization.
