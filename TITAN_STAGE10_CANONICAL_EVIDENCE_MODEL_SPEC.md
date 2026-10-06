# Project TITAN Stage 10 — Canonical Evidence Core (CEC) Domain Model Specification

**Status:** Implemented, inert. **Location:** `workers/intel-gateway/src/evidence-registry/entity.js`.
**Not imported by `index.js` or any production route** — see `README.md` in that directory and
`TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md`. This document specifies the domain model Stage 10
Phase 1 built; it does not authorize wiring it into production (that remains gated on ADR-0008
Acceptance, unchanged from Stage 8).

## 1. Purpose

Stage 10's mission was explicitly **not** to build the Enterprise Evidence Registry — it was to
implement the domain model every future evidence-handling capability depends on, with zero
customer-visible functionality. This document specifies that model: `CanonicalEvidence`.

## 2. Relationship to Stage 8's `EvidenceEntity`

`CanonicalEvidence` is a strict superset of Stage 8's `EvidenceEntity`:

```
CanonicalEvidence = EvidenceEntity & EvidenceClassificationFields & EvidenceSourceMetadataFields
                    & EvidenceQualityFields & EvidenceRelationshipFields & EvidenceGovernanceFields
```

Every Stage 8 field (`evidence_id`, `reliability_code`, `source_reliability`, `source_category`,
`analyst_review`, `chain_of_custody`, `known_limitations`, `iq_breakdown`, `evidence_uuid`,
`content_hash`, `schema_version`) remains valid and unchanged — nothing is renamed or removed
(Principle 5, Backward Compatibility). `createCanonicalEvidence(base, extension)` takes an
`EvidenceEntity` (typically `createEvidenceEntity()`'s own output) as `base` and layers the six
new field groups on top via `extension`.

## 3. The six field groups

| Group | Constant | Fields | Notes |
|---|---|---|---|
| Identity / Core | `EVIDENCE_ENTITY_CORE_FIELDS` (Stage 8) | `evidence_id`, `reliability_code`, `source_reliability`, `source_category`, `analyst_review`, `chain_of_custody`, `known_limitations`, `iq_breakdown` | Verified against P20's live `item.evidence_chain` shape, not ADR-0008's prose |
| Integrity | `EVIDENCE_ENTITY_INTEGRITY_FIELDS` (Stage 8) | `evidence_uuid`, `content_hash`, `schema_version` | ADR-0008 Decision item 1 |
| Classification | `EVIDENCE_CLASSIFICATION_FIELDS` | `evidence_type`, `evidence_category`, `visibility`, `tlp_classification` | TLP 2.0 values (FIRST.org), not a platform-invented scale |
| Source Metadata | `EVIDENCE_SOURCE_METADATA_FIELDS` | `source_id`, `source_name`, `collection_timestamp`, `publication_timestamp`, `last_verified` | `source_category` deliberately NOT redefined here — already on Core |
| Quality | `EVIDENCE_QUALITY_FIELDS` | `canonical_confidence_object`, `verification_status`, `evidence_weight` | `canonical_confidence_object` is a *reference* to P25's `computeEnterpriseTrustScore()` output, never recomputed here |
| Relationships | `EVIDENCE_RELATIONSHIP_FIELDS` | `related_reports`, `related_cves`, `related_threat_actors`, `related_campaigns`, `related_attack_techniques` | Lightweight `entity_id` string arrays only — full relationship records live in the separate `CanonicalRelationship` schema (`TITAN_GRAPH_INTERFACE_SPECIFICATION.md`); this is the inverse direction (what this evidence itself speaks to) |
| Governance | `EVIDENCE_GOVERNANCE_FIELDS` | `version`, `audit_metadata`, `feature_flag_metadata` | `version` mirrors `CanonicalRelationship.version` for cross-object-type consistency |

Full field-level types are in `entity.js`'s JSDoc typedefs
(`EvidenceClassificationFields`, `EvidenceSourceMetadataFields`, `EvidenceQualityFields`,
`EvidenceRelationshipFields`, `EvidenceGovernanceFields`, composed into `CanonicalEvidence`). See
`TITAN_STAGE10_SCHEMA_REFERENCE.md` for the generated field list and version history.

## 4. Design decisions and their rationale

**Every Stage 10 field is optional.** No current producer populates any of them; a
`CanonicalEvidence` built from a bare `EvidenceEntity` (or even `{}`) remains structurally valid.
This is what makes the type additive rather than a breaking redefinition.

**`visibility` defaults to `"INTERNAL"`, never `"CUSTOMER_FACING"`.** Principle 9 (Security
First): a new record must be explicitly promoted, never default to customer-visible.

**`canonical_confidence_object` is carried, never recomputed.** Single Source of Truth: P25's
`computeEnterpriseTrustScore()` remains the one place trust scores are computed. Nothing in the
CEC redeclares that shape (`{dims, totalEarned, totalMax, pct, tier, tierColor}`) — it is typed
as an opaque reference in the JSDoc specifically so a future shape change upstream doesn't
require a matching change here.

**Relationship fields are reference arrays, not embedded records.** Duplicating
`CanonicalRelationship`'s full structure (type, confidence, lifecycle, evidence_references)
inside `CanonicalEvidence` would violate Single Source of Truth in the other direction — two
places defining what a relationship is. The CEC only stores which entities *this evidence*
speaks to; the relationship graph (Stage 9's separate governance track) owns everything else.

**`version` is distinct from `schema_version`.** `schema_version` versions the *shape* (which
field groups exist); `version` versions a specific *record* (incremented on edit). Conflating
these was a real risk this spec avoids by keeping them as two fields with two different
constants (`CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION` vs. per-record `version`).

## 5. Immutability contract

Phase 1's requirement: "must be immutable once published." Implemented as
`publishEvidenceEntity(evidence)`:

- Stamps `published_at` (ISO-8601) if not already present.
- Recursively deep-freezes the resulting object — `Object.freeze()` alone is shallow, so a plain
  freeze would still allow `evidence.audit_metadata.updated_at = "..."` to succeed silently.
  `publishEvidenceEntity`'s `freezeDeep` walks every nested plain object/array (`audit_metadata`,
  `canonical_confidence_object`, every `related_*` array) so mutation attempts throw
  (`TypeError`, strict mode) rather than silently no-op.
- `isPublished(evidence)` checks `Object.isFrozen(evidence) && evidence.published_at` — a cheap,
  observable way for a future consumer to distinguish a draft from a published record without
  needing its own frozen-state bookkeeping.

This is verified by `__tests__/entity.test.js` and exercised at both individual-record and
2,000-record-batch scale by `__tests__/performance-smoke.test.js`.

## 6. Known model-level nuance: `undefined` fields and JSON

`createCanonicalEvidence()` explicitly sets every unset optional field to `undefined` (not
omitting the key). This is a deliberate, stable, enumerable shape — `Object.keys()` on any two
`CanonicalEvidence` records returns the same key set regardless of which optional fields are
populated, which is useful for schema introspection and for `schema.js`'s field-group model.
The one place this matters operationally: `JSON.stringify` (used by `JsonEvidenceSerializer`,
Phase 5) drops `undefined`-valued keys per the JSON specification itself, not as a defect in this
serializer. A consumer checking `evidence.field !== undefined` sees identical behavior whether
the key is present-with-undefined or JSON-round-trip-absent; only a strict key-set comparison
(as `assert.deepStrictEqual` performs) would observe a difference. Documented here so a future
integrator isn't surprised by it; `__tests__/serialization.test.js` encodes this expectation
explicitly.

## 7. What this document does not cover

Persistence, public APIs, customer-visible reports, the Enterprise Evidence Registry service,
and the Knowledge Graph are all explicitly out of scope for Stage 10 (see
`TITAN_STAGE10_ENGINEERING_SPECIFICATION.md`'s Stage 11 Preview — not implemented). This spec
covers the domain model only.
