/**
 * Enterprise Evidence Service Platform  -  Stage 12 Phase 2, Internal Query Engine
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * "One Query Engine": twelve lookup dimensions, each named `lookupBy*` for one uniform
 * convention, delegating to EvidenceRegistry's (Stage 11) existing finder methods. This is not
 * a second index  -  indexes.js's ten Maps (Stage 11 Phase 5) remain the only index structures
 * in this codebase; this class adds no storage of its own, only a consistent naming layer over
 * methods EvidenceRegistry already exposes (plus one composed method, lookupByEvidenceId, for
 * the one dimension indexes.js indexes but EvidenceRegistry itself never surfaces  -  see that
 * method's own docstring).
 *
 * "Query engine remains internal"  -  no route in index.js references this file (same boundary
 * as every other file in this directory; extended zero-blast-radius.test.js covers it).
 */

import { EvidenceRegistry } from "./registry-service.js";
import { ServicePlatformMetrics } from "./service-metrics.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export class EvidenceQueryEngine {
  /** @param {EvidenceRegistry} registry @param {ServicePlatformMetrics} [metrics] */
  constructor(registry, metrics) {
    this._registry = registry;
    this._metrics = metrics || new ServicePlatformMetrics();
  }

  _record(dimension) {
    this._metrics.recordQuery(dimension);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence | null>} */
  async lookupByUuid(evidenceUuid) {
    this._record("uuid");
    return this._registry.getEvidence(evidenceUuid);
  }

  /**
   * The one dimension indexes.js builds (`byEvidenceId`) that EvidenceRegistry's own finder
   * methods never surface (a pre-existing Stage 11 gap, observed not fixed  -  see
   * TITAN_STAGE12_SERVICE_ARCHITECTURE.md's Known Gaps section; fixing it would mean adding a
   * method to registry-service.js, a Stage 11 file, out of scope for this stage's "no
   * duplicated logic" additive-only mandate). Uses `findEvidence()`'s generic criteria lookup
   * (a linear scan over current records) instead of the unused index  -  functionally correct,
   * not index-accelerated. Phase 8's benchmarks measure whether that gap is actually material at
   * this registry's current scale.
   * @param {string} evidenceId @returns {Promise<CanonicalEvidence[]>}
   */
  async lookupByEvidenceId(evidenceId) {
    this._record("evidenceId");
    return this._registry.findEvidence({ evidence_id: evidenceId });
  }

  /** @param {string} reportId @returns {Promise<CanonicalEvidence[]>} */
  async lookupByReport(reportId) {
    this._record("report");
    return this._registry.findByReport(reportId);
  }

  /** @param {string} cve @returns {Promise<CanonicalEvidence[]>} */
  async lookupByCve(cve) {
    this._record("cve");
    return this._registry.findByCVE(cve);
  }

  /** @param {string} campaign @returns {Promise<CanonicalEvidence[]>} */
  async lookupByCampaign(campaign) {
    this._record("campaign");
    return this._registry.findByCampaign(campaign);
  }

  /** @param {string} actor @returns {Promise<CanonicalEvidence[]>} */
  async lookupByThreatActor(actor) {
    this._record("threatActor");
    return this._registry.findByThreatActor(actor);
  }

  /** @param {string} ioc @returns {Promise<CanonicalEvidence[]>} */
  async lookupByIoc(ioc) {
    this._record("ioc");
    return this._registry.findByIOC(ioc);
  }

  /** @param {string} technique @returns {Promise<CanonicalEvidence[]>} */
  async lookupByAttackTechnique(technique) {
    this._record("attackTechnique");
    return this._registry.findByAttackTechnique(technique);
  }

  /**
   * Evidence's own related_* index (Stage 11), not P31/ADR-0010's relationship graph  -  see
   * relationship-resolution.js for that separate, explicitly-scoped concern.
   * @param {string} entityId @returns {Promise<CanonicalEvidence[]>}
   */
  async lookupByRelationship(entityId) {
    this._record("relationship");
    return this._registry.findByRelationship(entityId);
  }

  /** @param {string} tier @returns {Promise<CanonicalEvidence[]>} */
  async lookupByConfidence(tier) {
    this._record("confidence");
    return this._registry.findByConfidenceTier(tier);
  }

  /** @param {string} sourceId @returns {Promise<CanonicalEvidence[]>} */
  async lookupBySource(sourceId) {
    this._record("source");
    return this._registry.findBySource(sourceId);
  }

  /**
   * @param {string} evidenceUuid @param {number} [versionNumber] - omit for current version
   * @returns {Promise<CanonicalEvidence | null>}
   */
  async lookupByVersion(evidenceUuid, versionNumber) {
    this._record("version");
    return this._registry.resolveVersion(evidenceUuid, versionNumber);
  }
}
