/**
 * Enterprise Intelligence Platform Services (EIPS) -- Project TITAN Stage 17 Phases 1+3+5
 * (Track A), Explainable Intelligence Engine / Analyst Reasoning Object (Project TITAN). Not
 * imported by index.js or any production route, matching this lineage's unbroken Stage 8-16
 * convention (see ../evidence-registry/README.md).
 *
 * Implements Phase 3 ("Explainable Intelligence Engine") and Phase 5 ("Analyst Reasoning Output")
 * as ONE engine, not two -- both phases describe the same shape (supporting evidence,
 * contradictory evidence, provenance chain, gaps, summary) under different names, and Single
 * Source of Truth (this repo's Principle 3) means one canonical implementation, not a duplicate.
 * `buildAnalystReasoningObject()` below is a documented one-line alias of `explainEvidence()`,
 * not a second implementation.
 *
 * Composes only already-existing, already-public methods: IntelligenceLookupService (evidence +
 * per-dimension lookups), IntelligenceCorrelationService (aggregated correlation),
 * EvidenceProvenanceEngine (lineage), and correlation-policy.js (structural policy evaluation).
 * No new storage, no new indexing.
 *
 * ADR-0007 boundary (see TITAN_STAGE17_READINESS_REPORT.md Sec 4): this engine surfaces
 * `canonical_confidence_object`/`verification_status`/`evidence_weight` VERBATIM, exactly as
 * correlation-engine.js's aggregateConfidence() and provenance-engine.js's getConfidenceLineage()
 * already do -- it never computes, weights, ranks, or propagates a confidence value. Confidence
 * dimension attribution and confidence-contributor ranking are Stage 17B work items (ADR-0007 is
 * Proposed, not Accepted -- docs/adr/0007-canonical-confidence-framework.md).
 *
 * Deterministic only. The `summary` field is fixed string templating over counts computed by this
 * file, not a call to any language model -- Stage 17's own charter: "No free-form LLM reasoning."
 */

import { evaluate as evaluateCorrelationPolicy } from "./correlation-policy.js";

/** @typedef {import('../evidence-registry/entity.js').CanonicalEvidence} CanonicalEvidence */

/** Relationship field -> IntelligenceLookupService method, for per-dimension gap detection. */
const GAP_DIMENSIONS = Object.freeze([
  { field: "related_cves", method: "byCVE" },
  { field: "related_threat_actors", method: "byThreatActor" },
  { field: "related_campaigns", method: "byCampaign" },
  { field: "related_iocs", method: "byIOC" },
  { field: "related_reports", method: "byReport" },
  { field: "related_attack_techniques", method: "byAttackTechnique" },
]);

export class IntelligenceExplainabilityService {
  /**
   * @param {{lookup: import('./intelligence-service.js').IntelligenceLookupService,
   *   correlation: import('./correlation-engine.js').IntelligenceCorrelationService,
   *   provenance: import('../evidence-registry/provenance-engine.js').EvidenceProvenanceEngine,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    this._lookup = deps.lookup;
    this._correlation = deps.correlation;
    this._provenance = deps.provenance;
    this._metrics = deps.metrics || null;
    if (!this._lookup || !this._correlation || !this._provenance) {
      throw new Error("IntelligenceExplainabilityService requires lookup, correlation, and provenance dependencies");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`explainability.${name}`, fn);
    return fn();
  }

  /**
   * Per-dimension collection-gap detection: for every related_* value on the subject evidence,
   * re-queries that specific dimension via IntelligenceLookupService (a different, already-public
   * method than IntelligenceCorrelationService.correlateEvidence() uses internally -- not a
   * duplicate of its aggregation logic) and flags any value that resolves to no OTHER evidence
   * record. This is what Phase 3/F call "missing evidence" / "collection gaps": a reference the
   * subject evidence makes that the registry cannot currently corroborate.
   * @param {CanonicalEvidence} evidence
   * @returns {Promise<Array<{dimension: string, value: string, reason: string}>>}
   */
  async _detectCollectionGaps(evidence) {
    const gaps = [];
    for (const { field, method } of GAP_DIMENSIONS) {
      const values = evidence[field];
      if (!Array.isArray(values) || values.length === 0) continue;
      for (const value of values) {
        const results = await this._lookup[method](value);
        const corroborating = (results || []).filter((r) => r.evidence_uuid !== evidence.evidence_uuid);
        if (corroborating.length === 0) {
          gaps.push({
            dimension: field,
            value,
            reason: "referenced by this evidence record but no corroborating evidence found in the registry",
          });
        }
      }
    }
    return gaps;
  }

  /**
   * Verbatim confidence passthrough -- see module docstring's ADR-0007 boundary. Every value here
   * is read directly off the evidence record, never derived.
   * @param {CanonicalEvidence} evidence
   */
  _projectConfidenceVerbatim(evidence) {
    return {
      canonical_confidence_object: evidence.canonical_confidence_object ?? null,
      verification_status: evidence.verification_status ?? null,
      evidence_weight: evidence.evidence_weight ?? null,
      note:
        "Verbatim as recorded on the evidence record -- not computed, weighted, ranked, or " +
        "propagated by this engine. Canonical ownership of confidence computation is pending " +
        "ADR-0007 (Proposed, not Accepted). See docs/adr/0007-canonical-confidence-framework.md.",
    };
  }

  /** Deterministic string templating -- not a language model call. See module docstring. */
  _buildSummary({ evidenceUuid, supportingCount, disputedCount, gapCount, lineageCount }) {
    const parts = [
      `Evidence ${evidenceUuid}: ${supportingCount} supporting record(s) found via relationship correlation.`,
    ];
    parts.push(
      disputedCount > 0
        ? `${disputedCount} record(s) carry verification_status=DISPUTED among the subject and its correlated set.`
        : "No DISPUTED records found among the subject and its correlated set."
    );
    parts.push(
      gapCount > 0
        ? `${gapCount} referenced entit${gapCount === 1 ? "y has" : "ies have"} no corroborating evidence in the registry (collection gap).`
        : "No collection gaps detected across referenced entities."
    );
    parts.push(`${lineageCount} version lineage entrie(s) available.`);
    return parts.join(" ");
  }

  /**
   * The core Stage 17 Phase 3/5 deliverable: a structured, deterministic explanation for one
   * evidence record. See module docstring for the full ADR-0007 boundary and reuse map.
   * @param {string} evidenceUuid
   * @returns {Promise<object>} the Analyst Reasoning Object
   */
  async explainEvidence(evidenceUuid) {
    return this._timed("explainEvidence", async () => {
      const evidence = await this._lookup.getEvidence(evidenceUuid);
      if (!evidence) {
        return { evidenceUuid, found: false, reason: "not_found", generatedAt: new Date().toISOString() };
      }

      const [correlationResult, evidenceLineage, relationshipLineage, sourceLineage, collectionGaps] = await Promise.all([
        this._correlation.correlateEvidence(evidenceUuid),
        this._provenance.getEvidenceLineage(evidenceUuid),
        this._provenance.getRelationshipLineage(evidenceUuid),
        this._provenance.getSourceLineage(evidenceUuid),
        this._detectCollectionGaps(evidence),
      ]);

      const supportingEvidence = correlationResult.correlated || [];
      const disputedInSet = [evidence, ...supportingEvidence].filter((e) => e?.verification_status === "DISPUTED");

      const policy = evaluateCorrelationPolicy(evidence, {
        correlatedEvidence: supportingEvidence,
        lineageEntries: evidenceLineage,
      });

      return {
        evidenceUuid,
        found: true,
        summary: this._buildSummary({
          evidenceUuid,
          supportingCount: supportingEvidence.length,
          disputedCount: disputedInSet.length,
          gapCount: collectionGaps.length,
          lineageCount: evidenceLineage.length,
        }),
        subject: {
          evidence_uuid: evidence.evidence_uuid,
          evidence_id: evidence.evidence_id,
          evidence_type: evidence.evidence_type,
          evidence_category: evidence.evidence_category,
        },
        supportingEvidence,
        contradictoryEvidence: disputedInSet,
        provenance: { evidenceLineage, relationshipLineage, sourceLineage },
        collectionGaps,
        confidenceAsRecorded: this._projectConfidenceVerbatim(evidence),
        policy,
        generatedAt: new Date().toISOString(),
      };
    });
  }

  /**
   * Phase 5 naming alias -- intentionally the same object explainEvidence() returns (Single
   * Source of Truth; see module docstring). Exists so a Phase-5-vocabulary caller (Tactical
   * Dossiers, Executive Reports, per the brief) does not need to know the two briefs share one
   * implementation.
   * @param {string} evidenceUuid
   */
  async buildAnalystReasoningObject(evidenceUuid) {
    return this.explainEvidence(evidenceUuid);
  }
}
