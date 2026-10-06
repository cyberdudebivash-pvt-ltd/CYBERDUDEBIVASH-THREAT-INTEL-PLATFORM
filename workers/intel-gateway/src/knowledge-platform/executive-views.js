/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18 Phase 5, Executive
 * Intelligence Views. Not imported by index.js or any production route. See README.md.
 *
 * Composes KnowledgeObjectService (Phase 2) and KnowledgeNavigationService (Phase 3) only --
 * introduces no new correlation, provenance, or confidence computation.
 *
 * Design constraint from Phase 5's own charter: "Every statement must trace back to evidence or
 * be explicitly identified as an analyst recommendation." Every item this file returns carries an
 * explicit `basis` field ("evidence" or "analyst_recommendation") for exactly that reason.
 *
 * This deliberately does NOT compute a business-impact or operational-impact SCORE. The P16-P38
 * handler stack has its own business-impact concept (P28's buildP28BusinessImpactBlock), but it
 * operates on a different data model (flat feed items) and has zero shared code with this
 * lineage (established Stage 15, re-confirmed Stage 17/18 readiness reports) -- reproducing or
 * approximating it here without that stack's own inputs would be exactly the "speculative
 * reasoning" Stage 18's own Implementation Rules forbid. Instead, `businessImpact()`/
 * `operationalImpact()` surface the evidentiary INPUTS an executive or analyst would use to form
 * that judgment, and say so explicitly.
 */

export class ExecutiveViewService {
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
      throw new Error("ExecutiveViewService requires knowledgeObject and navigation dependencies");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`knowledge.executiveView.${name}`, fn);
    return fn();
  }

  _distinctDimensionCount(knowledgeObject) {
    return Object.values(knowledgeObject.relationships).filter((values) => values.length > 0).length;
  }

  _businessImpact(knowledgeObject) {
    const category = knowledgeObject.subject.evidence_category || "unclassified";
    const type = knowledgeObject.subject.evidence_type || "unspecified type";
    return {
      statement:
        `Evidence classified as ${category} (${type}), correlated with ` +
        `${knowledgeObject.supportingEvidence.length} related record(s) across ` +
        `${this._distinctDimensionCount(knowledgeObject)} intelligence dimension(s).`,
      basis: "evidence",
      note:
        "This platform does not compute a business-impact score. Business impact is an " +
        "analyst/executive judgment informed by the evidence cited here.",
    };
  }

  _operationalImpact(knowledgeObject) {
    return {
      statement:
        `${knowledgeObject.intelligenceGaps.length} collection gap(s) identified; ` +
        `${knowledgeObject.supportingEvidence.length} corroborating record(s) available for ` +
        "operational response planning.",
      basis: "evidence",
      note: "This platform does not compute an operational-impact score.",
    };
  }

  _strategicObservations(knowledgeObject) {
    const observations = [];
    if (knowledgeObject.supportingEvidence.length > 0) {
      observations.push({
        statement: `${knowledgeObject.supportingEvidence.length} independently-correlated record(s) support this evidence.`,
        basis: "evidence",
      });
    }
    if (knowledgeObject.intelligenceGaps.length > 0) {
      const count = knowledgeObject.intelligenceGaps.length;
      observations.push({
        statement: `${count} referenced entit${count === 1 ? "y" : "ies"} lack${count === 1 ? "s" : ""} corroborating evidence in the registry.`,
        basis: "evidence",
      });
    }
    if (observations.length === 0) {
      observations.push({ statement: "No additional structural observations available from current evidence.", basis: "evidence" });
    }
    return observations;
  }

  /** Evidence references only -- no interpretation. Subject plus up to 5 correlated records. */
  _keyEvidence(knowledgeObject) {
    const subject = { ...knowledgeObject.subject, basis: "evidence" };
    const related = knowledgeObject.supportingEvidence.slice(0, 5).map((record) => ({
      evidence_uuid: record.evidence_uuid,
      evidence_id: record.evidence_id,
      evidence_type: record.evidence_type,
      basis: "evidence",
    }));
    return [subject, ...related];
  }

  /** Recommended actions: explicitly labeled analyst recommendations, derived from Phase 2's collection recommendations. */
  _recommendedActions(knowledgeObject) {
    return knowledgeObject.collectionRecommendations.map((recommendation) => ({
      action: recommendation.recommendation,
      dimension: recommendation.dimension,
      basis: "analyst_recommendation",
    }));
  }

  _intelligenceLimitations(knowledgeObject, contradictoryResult) {
    const limitations = [];
    if (knowledgeObject.intelligenceGaps.length > 0) {
      limitations.push({
        statement: `${knowledgeObject.intelligenceGaps.length} collection gap(s) present -- see Intelligence Gap View.`,
        basis: "evidence",
      });
    }
    if (knowledgeObject.confidenceAsRecorded.canonical_confidence_object == null) {
      limitations.push({
        statement: "No canonical confidence value has been recorded for this evidence (ADR-0007 pending -- see docs/adr/0007-canonical-confidence-framework.md).",
        basis: "evidence",
      });
    }
    if (contradictoryResult.contradictory.length > 0) {
      limitations.push({
        statement: `${contradictoryResult.contradictory.length} contradictory record(s) (verification_status=DISPUTED) found among correlated evidence.`,
        basis: "evidence",
      });
    }
    if (limitations.length === 0) {
      limitations.push({ statement: "No limitations identified from current evidence.", basis: "evidence" });
    }
    return limitations;
  }

  /**
   * Builds the full Executive Intelligence Briefing for one evidence record.
   * @param {string} evidenceUuid
   */
  async executiveBriefing(evidenceUuid) {
    return this._timed("executiveBriefing", async () => {
      const [knowledgeObject, contradictoryResult] = await Promise.all([
        this._knowledgeObject.build(evidenceUuid),
        this._navigation.contradictoryEvidence(evidenceUuid),
      ]);

      if (!knowledgeObject.found) {
        return { evidenceUuid, found: false, reason: "not_found", generatedAt: new Date().toISOString() };
      }

      return {
        evidenceUuid,
        found: true,
        businessImpact: this._businessImpact(knowledgeObject),
        operationalImpact: this._operationalImpact(knowledgeObject),
        strategicObservations: this._strategicObservations(knowledgeObject),
        keyEvidence: this._keyEvidence(knowledgeObject),
        recommendedActions: this._recommendedActions(knowledgeObject),
        intelligenceLimitations: this._intelligenceLimitations(knowledgeObject, contradictoryResult),
        generatedAt: new Date().toISOString(),
      };
    });
  }
}
