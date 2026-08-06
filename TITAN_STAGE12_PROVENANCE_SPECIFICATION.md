# Project TITAN Stage 12 — Provenance Engine Specification

Source: `workers/intel-gateway/src/evidence-registry/provenance-engine.js`,
`EvidenceProvenanceEngine`. Six lineage views, all derived by reading `EvidenceRegistry`'s
(Stage 11) already-stored, already-deep-frozen version history
(`getVersionLineage()`/`getAuditTrail()`) and projecting specific fields. No new storage, no
write path — provenance here is entirely a read-side composition over Stage 11's existing data.

## Evidence lineage — `getEvidenceLineage(uuid)`

**What it answers:** who/what produced each version of this evidence identity, and when.
**Derivation:** maps `getVersionLineage()`'s entries to `{version, ...audit_metadata}` —
`created_at`, `updated_at`, `created_by`, `producer_implementation` (Stage 10's
`EvidenceGovernanceFields`).
**Distinct from:** Audit lineage (below) — this is about authorship/production, not lifecycle
state changes.

## Version lineage — `getVersionLineage(uuid)`

**What it answers:** the full version history itself, oldest to current.
**Derivation:** verbatim passthrough to `EvidenceRegistry.getVersionLineage()`. Exists in this
engine only so callers have one consistent `get*Lineage` naming convention across all six kinds.

## Relationship lineage — `getRelationshipLineage(uuid)`

**What it answers:** how this evidence's own `related_*` references (Stage 10's
`EvidenceRelationshipFields` — reports, CVEs, threat actors, campaigns, ATT&CK techniques, IOCs)
changed across its version history.
**Derivation:** maps `getVersionLineage()`'s entries to `{version, related_reports,
related_cves, related_threat_actors, related_campaigns, related_attack_techniques,
related_iocs}`.
**Not:** P31/ADR-0010's relationship graph. This is evidence-centric ("what does this evidence
itself reference"), not graph-centric ("what is canonically related to this entity across the
whole corpus") — see `relationship-resolution.js` for that separate, explicitly out-of-scope
concern.

## Confidence lineage — `getConfidenceLineage(uuid)`

**What it answers:** how `canonical_confidence_object` (a verbatim reference to P25's
`computeEnterpriseTrustScore()` output, per ADR-0007) and `verification_status`/`evidence_weight`
changed across versions.
**Derivation:** maps `getVersionLineage()`'s entries to `{version,
canonical_confidence_object, verification_status, evidence_weight}`.
**Single Source of Truth:** this projects an existing field's history; it does not recompute or
reinterpret the confidence score itself. P25 remains the one place that score is computed.

## Source lineage — `getSourceLineage(uuid)`

**What it answers:** how source attribution (`source_id`, `source_name`,
`collection_timestamp`, `publication_timestamp`, `last_verified` — Stage 10's
`EvidenceSourceMetadataFields`) changed across versions.
**Derivation:** maps `getVersionLineage()`'s entries to the five named fields per version.

## Audit lineage — `getAuditLineage(uuid)`

**What it answers:** every lifecycle transition this evidence identity has undergone
(from/to/at/reason/actor).
**Derivation:** verbatim passthrough to `EvidenceRegistry.getAuditTrail()` (Stage 11's
`lifecycle.js`-validated transition history). Named `getAuditLineage` here only for the same
six-method naming consistency as the other five.
**Not `async`:** unlike the other five (which each call `getVersionLineage()`, an `async`
method), this one calls `getAuditTrail()`, which is synchronous in `EvidenceRegistry` — the
signature difference is intentional, not an inconsistency.

## Metrics

Every lineage method records one `ServicePlatformMetrics.recordProvenanceLookup(kind)` call
under its own kind (`"evidence"`, `"version"`, `"relationship"`, `"confidence"`, `"source"`,
`"audit"`) — `metrics.snapshot().provenance_lookups` gives a per-kind usage breakdown.

## Performance baseline

Measured (`__tests__/service-performance-smoke.test.js`, Stage 12 Phase 8): all six lineage
kinds, 100 samples each (600 total lineage reads) against a 1,000-record registry with a
populated update history, completed in **~4.2ms**. See
`TITAN_STAGE12_OPERATIONAL_GUIDE.md` for the full baseline table.
