/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18 Phase 4, Analyst
 * Intelligence Views. Not imported by index.js or any production route. See README.md.
 *
 * Six analyst-framed views, every one composing KnowledgeObjectService (Phase 2) and/or
 * KnowledgeNavigationService (Phase 3) -- this file introduces no new correlation, provenance,
 * explanation, or confidence logic of its own. Where a "priority" or "timeline" ordering is
 * produced, it is a deterministic sort/group over already-computed fields, not a new score.
 *
 * ADR-0007 boundary: confidenceContext() surfaces KnowledgeObjectService's own verbatim
 * confidenceAsRecorded field unchanged -- "surface existing values only," per Stage 18's own
 * Phase 4 charter. Nothing here computes a new confidence value.
 */

export class AnalystViewService {
  /**
   * @param {{knowledgeObject: import('./knowledge-object.js').KnowledgeObjectService,
   *   navigation: import('./knowledge-navigation.js').KnowledgeNavigationService,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    this._knowledgeObject = deps.knowledgeObject;
    this._navigation = deps.navigation;
    this._metrics = deps.metrics || null;
    if (!this._knowledgeObject || !this._navigation) {
      throw new Error("AnalystViewService requires knowledgeObject and navigation dependencies");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`knowledge.analystView.${name}`, fn);
    return fn();
  }

  /** Investigation View: the full Knowledge Object, unmodified -- the analyst's primary entry point. @param {string} evidenceUuid */
  async investigationView(evidenceUuid) {
    return this._timed("investigationView", () => this._knowledgeObject.build(evidenceUuid));
  }

  /**
   * Correlation View: related, similar, and contradictory evidence side by side -- three
   * Navigation calls composed into one analyst-framed response.
   * @param {string} evidenceUuid
   */
  async correlationView(evidenceUuid) {
    return this._timed("correlationView", async () => {
      const [related, similar, contradictory] = await Promise.all([
        this._navigation.relatedIntelligence(evidenceUuid),
        this._navigation.similarIntelligence(evidenceUuid),
        this._navigation.contradictoryEvidence(evidenceUuid),
      ]);
      return {
        evidenceUuid,
        relatedIntelligence: related.correlated || [],
        similarIntelligence: similar.similar || [],
        contradictoryEvidence: contradictory.contradictory || [],
        statusDisagreement: contradictory.statusDisagreement || false,
      };
    });
  }

  /**
   * Evidence Timeline: version lineage (Stage 11), oldest-first as the registry already orders
   * it, reshaped into a compact per-version summary.
   * @param {string} evidenceUuid
   */
  async evidenceTimeline(evidenceUuid) {
    return this._timed("evidenceTimeline", async () => {
      const lineage = await this._navigation.historicalIntelligence(evidenceUuid);
      return {
        evidenceUuid,
        timeline: (lineage || []).map((version) => ({
          version: version.version,
          created_at: version.audit_metadata?.created_at,
          updated_at: version.audit_metadata?.updated_at,
          verification_status: version.verification_status,
        })),
      };
    });
  }

  /**
   * Confidence Context: surfaces the existing verbatim confidence fields only -- does not
   * compute, weight, or interpret a new value. Phase 4's own instruction: "Do not compute new
   * confidence values."
   * @param {string} evidenceUuid
   */
  async confidenceContext(evidenceUuid) {
    return this._timed("confidenceContext", async () => {
      const knowledgeObject = await this._knowledgeObject.build(evidenceUuid);
      if (!knowledgeObject.found) return { evidenceUuid, found: false, reason: "not_found" };
      return { evidenceUuid, found: true, confidenceAsRecorded: knowledgeObject.confidenceAsRecorded };
    });
  }

  /** Intelligence Gap View: gaps and their templated recommendations, analyst-framed. @param {string} evidenceUuid */
  async intelligenceGapView(evidenceUuid) {
    return this._timed("intelligenceGapView", async () => {
      const knowledgeObject = await this._knowledgeObject.build(evidenceUuid);
      if (!knowledgeObject.found) return { evidenceUuid, found: false, reason: "not_found", gaps: [], recommendations: [] };
      return { evidenceUuid, found: true, gaps: knowledgeObject.intelligenceGaps, recommendations: knowledgeObject.collectionRecommendations };
    });
  }

  /**
   * Collection Priority View: recommendations grouped by dimension and ordered by gap count
   * descending -- a deterministic presentation ordering over already-computed recommendations,
   * not a new score or model.
   * @param {string} evidenceUuid
   */
  async collectionPriorityView(evidenceUuid) {
    return this._timed("collectionPriorityView", async () => {
      const knowledgeObject = await this._knowledgeObject.build(evidenceUuid);
      if (!knowledgeObject.found) return { evidenceUuid, found: false, reason: "not_found", priorities: [] };

      const byDimension = new Map();
      for (const recommendation of knowledgeObject.collectionRecommendations) {
        if (!byDimension.has(recommendation.dimension)) byDimension.set(recommendation.dimension, []);
        byDimension.get(recommendation.dimension).push(recommendation);
      }
      const priorities = [...byDimension.entries()]
        .map(([dimension, recommendations]) => ({ dimension, gapCount: recommendations.length, recommendations }))
        .sort((a, b) => b.gapCount - a.gapCount);

      return { evidenceUuid, found: true, priorities };
    });
  }
}
