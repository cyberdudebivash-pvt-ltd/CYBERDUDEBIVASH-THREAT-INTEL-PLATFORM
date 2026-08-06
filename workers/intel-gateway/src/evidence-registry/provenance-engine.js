/**
 * Enterprise Evidence Service Platform  -  Stage 12 Phase 3, Provenance Engine
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Six lineage views (evidence, version, relationship, confidence, source, audit), every one
 * composed by reading EvidenceRegistry's (Stage 11) existing getVersionLineage()/getAuditTrail()
 * and projecting specific fields across that already-stored history. No new storage: this class
 * holds no state of its own and writes nothing  -  "No external interfaces," and no internal
 * persistence either. Version lineage entries are already deep-frozen by in-memory-repository.js
 * (Stage 11); this class only reads them.
 */

import { EvidenceRegistry } from "./registry-service.js";
import { ServicePlatformMetrics } from "./service-metrics.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export class EvidenceProvenanceEngine {
  /** @param {EvidenceRegistry} registry @param {ServicePlatformMetrics} [metrics] */
  constructor(registry, metrics) {
    this._registry = registry;
    this._metrics = metrics || new ServicePlatformMetrics();
  }

  _record(kind) {
    this._metrics.recordProvenanceLookup(kind);
  }

  /**
   * Where this evidence identity came from: its full version lineage's audit_metadata, oldest
   * first. Distinct from getAuditLineage() (lifecycle transitions)  -  this is about authorship/
   * production, not state changes.
   * @param {string} evidenceUuid
   * @returns {Promise<{version: number, created_at?: string, updated_at?: string, created_by?: string, producer_implementation?: string}[]>}
   */
  async getEvidenceLineage(evidenceUuid) {
    this._record("evidence");
    const lineage = await this._registry.getVersionLineage(evidenceUuid);
    return lineage.map((entry) => ({ version: entry.version, ...(entry.audit_metadata || {}) }));
  }

  /**
   * Direct passthrough to EvidenceRegistry.getVersionLineage()  -  Stage 11 already defines
   * "version lineage" completely; this method exists only so Provenance Engine callers have one
   * consistent `get*Lineage` naming convention across all six kinds, not because the underlying
   * data differs.
   * @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>}
   */
  async getVersionLineage(evidenceUuid) {
    this._record("version");
    return this._registry.getVersionLineage(evidenceUuid);
  }

  /**
   * How this evidence's related_* fields (Stage 10's EvidenceRelationshipFields) changed across
   * its version history  -  which reports/CVEs/actors/campaigns/techniques/IOCs were referenced
   * at each version. Evidence-centric relationship provenance; not P31/ADR-0010's relationship
   * graph (see relationship-resolution.js for that separate concern).
   * @param {string} evidenceUuid
   * @returns {Promise<{version: number, related_reports: string[], related_cves: string[], related_threat_actors: string[], related_campaigns: string[], related_attack_techniques: string[], related_iocs: string[]}[]>}
   */
  async getRelationshipLineage(evidenceUuid) {
    this._record("relationship");
    const lineage = await this._registry.getVersionLineage(evidenceUuid);
    return lineage.map((entry) => ({
      version: entry.version,
      related_reports: entry.related_reports || [],
      related_cves: entry.related_cves || [],
      related_threat_actors: entry.related_threat_actors || [],
      related_campaigns: entry.related_campaigns || [],
      related_attack_techniques: entry.related_attack_techniques || [],
      related_iocs: entry.related_iocs || [],
    }));
  }

  /**
   * How `canonical_confidence_object` and `verification_status` changed across this evidence's
   * version history. `canonical_confidence_object` is a verbatim reference to P25's
   * computeEnterpriseTrustScore() output (Stage 10)  -  this method projects that field's history,
   * it does not recompute or reinterpret it (Single Source of Truth: P25 remains the one place
   * that score is computed).
   * @param {string} evidenceUuid
   * @returns {Promise<{version: number, canonical_confidence_object: object | undefined, verification_status: string | undefined, evidence_weight: number | undefined}[]>}
   */
  async getConfidenceLineage(evidenceUuid) {
    this._record("confidence");
    const lineage = await this._registry.getVersionLineage(evidenceUuid);
    return lineage.map((entry) => ({
      version: entry.version,
      canonical_confidence_object: entry.canonical_confidence_object,
      verification_status: entry.verification_status,
      evidence_weight: entry.evidence_weight,
    }));
  }

  /**
   * How source attribution (source_id/source_name/collection_timestamp/publication_timestamp/
   * last_verified  -  Stage 10's EvidenceSourceMetadataFields) changed across version history.
   * @param {string} evidenceUuid
   * @returns {Promise<{version: number, source_id: string | undefined, source_name: string | undefined, collection_timestamp: string | undefined, publication_timestamp: string | undefined, last_verified: string | undefined}[]>}
   */
  async getSourceLineage(evidenceUuid) {
    this._record("source");
    const lineage = await this._registry.getVersionLineage(evidenceUuid);
    return lineage.map((entry) => ({
      version: entry.version,
      source_id: entry.source_id,
      source_name: entry.source_name,
      collection_timestamp: entry.collection_timestamp,
      publication_timestamp: entry.publication_timestamp,
      last_verified: entry.last_verified,
    }));
  }

  /**
   * Direct passthrough to EvidenceRegistry.getAuditTrail()  -  Stage 11's lifecycle transition
   * audit trail (from/to/at/reason/actor per transition), unmodified. Named `getAuditLineage`
   * here only for naming consistency with this engine's other five methods.
   * @param {string} evidenceUuid @returns {ReadonlyArray<object>}
   */
  getAuditLineage(evidenceUuid) {
    this._record("audit");
    return this._registry.getAuditTrail(evidenceUuid);
  }
}
