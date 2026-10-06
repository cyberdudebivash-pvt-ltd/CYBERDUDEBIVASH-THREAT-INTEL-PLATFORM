/**
 * Enterprise Intelligence Platform Services (EIPS) -- Stage 13 Phase 1 + Phase 3,
 * Intelligence Correlation Engine (Project TITAN). Not imported by index.js or any production
 * route. See README.md.
 *
 * Five correlation dimensions (evidence, confidence, source, report, IOC) plus relationship
 * correlation, every one composed by calling EvidenceQueryEngine/EvidenceService methods
 * (Stage 12) that already exist -- no new storage, no new indexing, no re-derivation of fields
 * CanonicalEvidence (Stage 10) already carries (related_cves/related_threat_actors/
 * related_campaigns/related_iocs/related_reports/related_attack_techniques,
 * canonical_confidence_object).
 *
 * Relationship correlation: ADR-0010 (Relationship Graph Ownership) is now Accepted (Stage 16,
 * 2026-08-06 -- docs/adr/0010-relationship-graph-ownership.md Revision 5;
 * TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md's Stage 16 Addendum). correlateByRelationship() below
 * is UNCHANGED by that acceptance: it still delegates verbatim to Stage 12's
 * RelationshipResolutionService (relationship-resolution.js) and implements no graph logic of
 * its own -- that pass-through design was always correct independent of ADR-0010's status
 * (Single Source of Truth: this file should not grow a second relationship-resolution path). It
 * still does not import p31-handlers.js or any other concrete relationship-graph implementation.
 * What changed is which RelationshipResolutionService instance gets injected upstream:
 * relationship-framework/ (Stage 16) now constructs one backed by a real P31RelationshipProvider
 * instead of leaving it on the NullRelationshipProvider default -- see
 * relationship-framework/relationship-service.js.
 *
 * Stage 17 Phase 2 addition: correlateByAttackTechnique() and aggregateSources() below close the
 * two asymmetries Stage 17's Correlation Domain Audit found against this file's existing
 * dimensions (see TITAN_STAGE17_READINESS_REPORT.md Sec 2.2) -- same "no new storage, direct
 * passthrough / tally over already-fetched records" pattern as every method above. Confidence
 * remains untouched by this addition: aggregateConfidence() below is unmodified.
 */

/** @typedef {import('../evidence-registry/entity.js').CanonicalEvidence} CanonicalEvidence */

export class IntelligenceCorrelationService {
  /**
   * @param {{evidenceService?: import('../evidence-registry/evidence-service.js').EvidenceService,
   *   queryEngine: import('../evidence-registry/query-engine.js').EvidenceQueryEngine,
   *   relationshipResolution?: import('../evidence-registry/relationship-resolution.js').RelationshipResolutionService,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    this._evidenceService = deps.evidenceService;
    this._queryEngine = deps.queryEngine;
    this._relationshipResolution = deps.relationshipResolution || null;
    this._metrics = deps.metrics || null;
    if (!this._evidenceService || !this._queryEngine) {
      throw new Error("IntelligenceCorrelationService requires evidenceService and queryEngine dependencies");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`correlation.${name}`, fn);
    return fn();
  }

  /**
   * Evidence correlation: every OTHER evidence record that shares at least one related_*
   * dimension (CVE/threat actor/campaign/IOC/report/ATT&CK technique) with the given evidence
   * record. Reads CanonicalEvidence's own relationship fields and re-queries via
   * EvidenceQueryEngine's existing lookupBy* methods -- no new index, no duplicate of
   * indexes.js's ten Maps (Stage 11).
   * @param {string} evidenceUuid
   * @returns {Promise<{evidenceUuid: string, correlated: CanonicalEvidence[], reason?: string}>}
   */
  async correlateEvidence(evidenceUuid) {
    return this._timed("evidence", async () => {
      const evidence = await this._evidenceService.lookup.getEvidence(evidenceUuid);
      if (!evidence) return { evidenceUuid, correlated: [], reason: "not_found" };

      const groups = await Promise.all([
        ...(evidence.related_cves || []).map((v) => this._queryEngine.lookupByCve(v)),
        ...(evidence.related_threat_actors || []).map((v) => this._queryEngine.lookupByThreatActor(v)),
        ...(evidence.related_campaigns || []).map((v) => this._queryEngine.lookupByCampaign(v)),
        ...(evidence.related_iocs || []).map((v) => this._queryEngine.lookupByIoc(v)),
        ...(evidence.related_reports || []).map((v) => this._queryEngine.lookupByReport(v)),
        ...(evidence.related_attack_techniques || []).map((v) => this._queryEngine.lookupByAttackTechnique(v)),
      ]);

      const seen = new Map();
      for (const group of groups) {
        for (const item of group) {
          if (item.evidence_uuid !== evidenceUuid) seen.set(item.evidence_uuid, item);
        }
      }
      return { evidenceUuid, correlated: [...seen.values()] };
    });
  }

  /**
   * Confidence aggregation across a set of evidence records (e.g. everything
   * correlateEvidence()/a query-service lookup returned). Projects the SAME
   * canonical_confidence_object field provenance-engine.js's getConfidenceLineage() already
   * projects -- P25's computeEnterpriseTrustScore() output, verbatim, not recomputed here
   * (Single Source of Truth: P25 remains the one place that score is computed).
   * @param {CanonicalEvidence[]} evidenceRecords
   * @returns {Promise<{total: number, withConfidence: number, byTier: Record<string, number>}>}
   */
  async aggregateConfidence(evidenceRecords) {
    return this._timed("confidence", () => {
      const byTier = {};
      let withConfidence = 0;
      for (const record of evidenceRecords || []) {
        const tier = record?.canonical_confidence_object?.tier || record?.canonical_confidence_object?.confidence_tier;
        if (tier) {
          byTier[tier] = (byTier[tier] || 0) + 1;
          withConfidence += 1;
        }
      }
      return { total: (evidenceRecords || []).length, withConfidence, byTier };
    });
  }

  /** Source correlation: direct passthrough to EvidenceQueryEngine.lookupBySource(). @param {string} sourceId */
  async correlateBySource(sourceId) {
    return this._timed("source", () => this._queryEngine.lookupBySource(sourceId));
  }

  /** Report correlation: direct passthrough to EvidenceQueryEngine.lookupByReport(). @param {string} reportId */
  async correlateByReport(reportId) {
    return this._timed("report", () => this._queryEngine.lookupByReport(reportId));
  }

  /** IOC correlation: direct passthrough to EvidenceQueryEngine.lookupByIoc(). @param {string} ioc */
  async correlateByIOC(ioc) {
    return this._timed("ioc", () => this._queryEngine.lookupByIoc(ioc));
  }

  /**
   * Relationship correlation -- pass-through only, per this file's module docstring. Throws the
   * same explicit "not wired" error the underlying service throws when no provider has been
   * injected, rather than masking it with a caught/empty result.
   * @param {string} entityId
   */
  async correlateByRelationship(entityId) {
    if (!this._relationshipResolution) {
      throw new Error(
        'correlateByRelationship: no RelationshipResolutionService was injected into ' +
          "IntelligenceCorrelationService. Relationship correlation is scoped to a pass-through " +
          "only -- ADR-0010 (Relationship Graph Ownership) is still Proposed, not Accepted. See " +
          "evidence-registry/relationship-resolution.js."
      );
    }
    return this._timed("relationship", () => this._relationshipResolution.resolveRelationships(entityId));
  }

  /**
   * ATT&CK technique correlation: direct passthrough to EvidenceQueryEngine.lookupByAttackTechnique().
   * Project TITAN Stage 17 Phase 2 addition -- this dimension was already queryable via
   * EvidenceQueryEngine (Stage 12) but, unlike source/report/IOC, had no correlateBy* wrapper at
   * this layer. Mirrors correlateBySource()/correlateByReport()/correlateByIOC() exactly; no new
   * storage, no new query logic. @param {string} technique
   */
  async correlateByAttackTechnique(technique) {
    return this._timed("attackTechnique", () => this._queryEngine.lookupByAttackTechnique(technique));
  }

  /**
   * Multi-source aggregation: source-tally view across a set of evidence records (e.g.
   * correlateEvidence()'s output), mirroring aggregateConfidence()'s tally-by-tier shape exactly
   * but keyed by source_id instead of confidence tier. Project TITAN Stage 17 Phase 2 addition --
   * closes the one asymmetry between the two aggregate* methods (confidence had a tally, source
   * did not). Reads only the already-fetched records passed in; no new query, no new storage.
   * @param {CanonicalEvidence[]} evidenceRecords
   * @returns {Promise<{total: number, withSource: number, bySource: Record<string, number>}>}
   */
  async aggregateSources(evidenceRecords) {
    return this._timed("sources", () => {
      const bySource = {};
      let withSource = 0;
      for (const record of evidenceRecords || []) {
        const sourceId = record?.source_id;
        if (sourceId) {
          bySource[sourceId] = (bySource[sourceId] || 0) + 1;
          withSource += 1;
        }
      }
      return { total: (evidenceRecords || []).length, withSource, bySource };
    });
  }
}
