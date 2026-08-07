/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18 Phase 3, Knowledge
 * Navigation. Not imported by index.js or any production route. See README.md.
 *
 * Six navigation methods, every one composing an already-existing, already-public method from
 * Stage 12/13/17 -- no new storage, no new correlation/provenance/explanation logic re-derived.
 * `similarIntelligence()` is the one genuinely new computation (Phase 3's own gap, per
 * TITAN_STAGE18_READINESS_REPORT.md Sec 2.2): a deterministic, structural (Jaccard-index-style)
 * overlap score over relationship field VALUES already on each record -- arithmetic over existing
 * data, not semantic/ML similarity, not speculative reasoning.
 *
 * ADR-0007 boundary: nothing in this file reads, computes, or compares
 * `canonical_confidence_object`/`evidence_weight`. `contradictoryEvidence()` reuses Stage 17's
 * `correlation-policy.js#detectConflicts()` verbatim (Single Source of Truth) rather than
 * reimplementing conflict detection.
 */

import { detectConflicts } from "../intelligence-platform/correlation-policy.js";

/** @typedef {import('../evidence-registry/entity.js').CanonicalEvidence} CanonicalEvidence */

const RELATIONSHIP_FIELDS = Object.freeze([
  "related_cves",
  "related_threat_actors",
  "related_campaigns",
  "related_iocs",
  "related_reports",
  "related_attack_techniques",
]);

export class KnowledgeNavigationService {
  /**
   * @param {{lookup: import('../intelligence-platform/intelligence-service.js').IntelligenceLookupService,
   *   correlation: import('../intelligence-platform/correlation-engine.js').IntelligenceCorrelationService,
   *   provenance: import('../evidence-registry/provenance-engine.js').EvidenceProvenanceEngine,
   *   explainability: import('../intelligence-platform/explainability-engine.js').IntelligenceExplainabilityService,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    this._lookup = deps.lookup;
    this._correlation = deps.correlation;
    this._provenance = deps.provenance;
    this._explainability = deps.explainability;
    this._metrics = deps.metrics || null;
    if (!this._lookup || !this._correlation || !this._provenance || !this._explainability) {
      throw new Error("KnowledgeNavigationService requires lookup, correlation, provenance, and explainability dependencies");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`knowledge.navigation.${name}`, fn);
    return fn();
  }

  /** @param {CanonicalEvidence} evidence @returns {Set<string>} */
  _relationshipValueSet(evidence) {
    const values = new Set();
    for (const field of RELATIONSHIP_FIELDS) {
      for (const value of evidence?.[field] || []) values.add(value);
    }
    return values;
  }

  /** Jaccard index: intersection size / union size, 0 when both sets are empty. Pure arithmetic, deterministic. */
  _jaccard(setA, setB) {
    if (setA.size === 0 && setB.size === 0) return 0;
    let intersectionSize = 0;
    for (const value of setA) if (setB.has(value)) intersectionSize += 1;
    const unionSize = new Set([...setA, ...setB]).size;
    return unionSize === 0 ? 0 : Number((intersectionSize / unionSize).toFixed(4));
  }

  /** Related intelligence: direct passthrough to IntelligenceCorrelationService.correlateEvidence(). @param {string} evidenceUuid */
  async relatedIntelligence(evidenceUuid) {
    return this._timed("relatedIntelligence", () => this._correlation.correlateEvidence(evidenceUuid));
  }

  /**
   * Supporting evidence: same canonical source as relatedIntelligence() (Single Source of Truth
   * -- both describe the same relationship-correlated evidence set under Phase 3's two named
   * concepts). @param {string} evidenceUuid
   */
  async supportingEvidence(evidenceUuid) {
    return this.relatedIntelligence(evidenceUuid);
  }

  /**
   * Similar intelligence: structural overlap score against every already-correlated candidate.
   * Deliberately scoped to the correlated set (not the whole registry) -- two records with zero
   * relationship overlap are already excluded by correlateEvidence() itself, so there is nothing
   * to score outside that set.
   * @param {string} evidenceUuid
   * @param {{minScore?: number}} [options]
   * @returns {Promise<{evidenceUuid: string, similar: Array<{evidence_uuid: string, similarityScore: number, sharedValues: string[]}>, reason?: string}>}
   */
  async similarIntelligence(evidenceUuid, options = {}) {
    return this._timed("similarIntelligence", async () => {
      const subject = await this._lookup.getEvidence(evidenceUuid);
      if (!subject) return { evidenceUuid, similar: [], reason: "not_found" };

      const minScore = options.minScore ?? 0;
      const { correlated } = await this._correlation.correlateEvidence(evidenceUuid);
      const subjectSet = this._relationshipValueSet(subject);

      const scored = (correlated || [])
        .map((candidate) => {
          const candidateSet = this._relationshipValueSet(candidate);
          return {
            evidence_uuid: candidate.evidence_uuid,
            similarityScore: this._jaccard(subjectSet, candidateSet),
            sharedValues: [...subjectSet].filter((value) => candidateSet.has(value)),
          };
        })
        .filter((entry) => entry.similarityScore >= minScore)
        .sort((a, b) => b.similarityScore - a.similarityScore);

      return { evidenceUuid, similar: scored };
    });
  }

  /**
   * Contradictory evidence: reuses correlation-policy.js's detectConflicts() (Stage 17) against
   * the subject plus its correlated set -- does not reimplement conflict detection.
   * @param {string} evidenceUuid
   */
  async contradictoryEvidence(evidenceUuid) {
    return this._timed("contradictoryEvidence", async () => {
      const subject = await this._lookup.getEvidence(evidenceUuid);
      if (!subject) return { evidenceUuid, contradictory: [], statusDisagreement: false, reason: "not_found" };

      const { correlated } = await this._correlation.correlateEvidence(evidenceUuid);
      const candidateSet = [subject, ...(correlated || [])];
      const conflictReport = detectConflicts(candidateSet);
      const contradictory = candidateSet.filter(
        (record) => record.evidence_uuid !== evidenceUuid && conflictReport.disputed.includes(record.evidence_uuid)
      );

      return { evidenceUuid, contradictory, statusDisagreement: conflictReport.statusDisagreement, statuses: conflictReport.statuses };
    });
  }

  /** Historical intelligence: direct passthrough to EvidenceProvenanceEngine.getVersionLineage(). @param {string} evidenceUuid */
  async historicalIntelligence(evidenceUuid) {
    return this._timed("historicalIntelligence", () => this._provenance.getVersionLineage(evidenceUuid));
  }

  /**
   * Collection gaps: delegates to IntelligenceExplainabilityService.explainEvidence()'s own
   * per-dimension gap detection (Stage 17) rather than re-deriving it -- that algorithm is
   * private to explainability-engine.js by design (Single Source of Truth); this method reuses
   * its output instead of duplicating its loop over the six relationship dimensions.
   * @param {string} evidenceUuid
   */
  async collectionGaps(evidenceUuid) {
    return this._timed("collectionGaps", async () => {
      const explanation = await this._explainability.explainEvidence(evidenceUuid);
      if (!explanation.found) return { evidenceUuid, gaps: [], reason: "not_found" };
      return { evidenceUuid, gaps: explanation.collectionGaps };
    });
  }
}
