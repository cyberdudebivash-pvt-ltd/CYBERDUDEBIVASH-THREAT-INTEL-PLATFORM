/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18 Phase 2, Knowledge
 * Object Layer. Not imported by index.js or any production route. See README.md.
 *
 * A Knowledge Object is a reshaping of two already-existing, already-public calls --
 * IntelligenceLookupService.getEvidence() and IntelligenceExplainabilityService.explainEvidence()
 * (Stage 13/17) -- into the seven-field shape Phase 2 specifies. No new storage, no new
 * correlation logic, no new provenance logic: every field below is either read directly off the
 * evidence record (`relationships`) or copied verbatim from the explanation
 * (`summary`/`supportingEvidence`/`provenance`/`intelligenceGaps`/`confidenceAsRecorded`/
 * `policy`). `collectionRecommendations` is the one genuinely new derivation -- deterministic
 * string templating over `intelligenceGaps`, not a new analysis.
 *
 * ADR-0007 boundary (see TITAN_STAGE18_READINESS_REPORT.md Sec 0): `confidenceAsRecorded` is
 * `explainEvidence()`'s own verbatim passthrough, copied here unchanged. This file computes
 * nothing confidence-shaped.
 */

/** @typedef {import('../evidence-registry/entity.js').CanonicalEvidence} CanonicalEvidence */

const RELATIONSHIP_FIELD_TO_KEY = Object.freeze({
  related_cves: "cves",
  related_threat_actors: "threatActors",
  related_campaigns: "campaigns",
  related_iocs: "iocs",
  related_reports: "reports",
  related_attack_techniques: "attackTechniques",
});

export class KnowledgeObjectService {
  /**
   * @param {{lookup: import('../intelligence-platform/intelligence-service.js').IntelligenceLookupService,
   *   explainability: import('../intelligence-platform/explainability-engine.js').IntelligenceExplainabilityService,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    this._lookup = deps.lookup;
    this._explainability = deps.explainability;
    this._metrics = deps.metrics || null;
    if (!this._lookup || !this._explainability) {
      throw new Error("KnowledgeObjectService requires lookup and explainability dependencies");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`knowledge.${name}`, fn);
    return fn();
  }

  /**
   * Groups the evidence record's own related_* fields (Stage 10) under Phase 2's "Relationships"
   * field name. Pure field renaming/grouping -- reads only what the record already carries.
   * @param {CanonicalEvidence} evidence
   */
  _groupRelationships(evidence) {
    const relationships = {};
    for (const [field, key] of Object.entries(RELATIONSHIP_FIELD_TO_KEY)) {
      relationships[key] = evidence[field] || [];
    }
    return relationships;
  }

  /**
   * Collection recommendations: one deterministic, templated recommendation per collection gap
   * explainEvidence() already identified. Not a new analysis -- a direct, mechanical restatement
   * of an existing gap as an action, per Phase 2's own "Collection recommendations" field.
   * @param {Array<{dimension: string, value: string, reason: string}>} gaps
   */
  _buildCollectionRecommendations(gaps) {
    return (gaps || []).map((gap) => {
      const label = gap.dimension.replace(/^related_/, "").replace(/_/g, " ");
      return {
        dimension: gap.dimension,
        value: gap.value,
        recommendation: `Collect additional evidence corroborating ${label} = "${gap.value}" -- currently referenced but unsupported by any other registered evidence.`,
      };
    });
  }

  /**
   * Builds the Knowledge Object for one evidence record.
   * @param {string} evidenceUuid
   * @returns {Promise<object>}
   */
  async build(evidenceUuid) {
    return this._timed("build", async () => {
      const [evidence, explanation] = await Promise.all([
        this._lookup.getEvidence(evidenceUuid),
        this._explainability.explainEvidence(evidenceUuid),
      ]);

      if (!evidence || !explanation.found) {
        return { evidenceUuid, found: false, reason: "not_found", generatedAt: new Date().toISOString() };
      }

      return {
        evidenceUuid,
        found: true,
        summary: explanation.summary,
        subject: explanation.subject,
        relationships: this._groupRelationships(evidence),
        supportingEvidence: explanation.supportingEvidence,
        // "Related intelligence" (Phase 2) and "Supporting evidence" describe the same
        // relationship-correlated evidence set -- one canonical source (Single Source of Truth),
        // exposed under both of Phase 2's named fields rather than computed twice.
        relatedIntelligence: explanation.supportingEvidence,
        provenance: explanation.provenance,
        intelligenceGaps: explanation.collectionGaps,
        collectionRecommendations: this._buildCollectionRecommendations(explanation.collectionGaps),
        confidenceAsRecorded: explanation.confidenceAsRecorded,
        policy: explanation.policy,
        generatedAt: new Date().toISOString(),
      };
    });
  }
}
