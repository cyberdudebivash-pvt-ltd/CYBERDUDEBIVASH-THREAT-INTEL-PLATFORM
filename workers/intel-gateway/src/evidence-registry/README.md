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
