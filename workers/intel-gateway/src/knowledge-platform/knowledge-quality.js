/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18 Phase 6, Knowledge
 * Quality Framework. Not imported by index.js or any production route. See README.md.
 *
 * Mirrors intelligence-platform/correlation-policy.js's (Stage 17) exact style and versioning
 * convention: pure functions over an already-built Knowledge Object (Phase 2's output), no new
 * storage, no confidence computation. Validates the Knowledge Object's own structural
 * completeness -- a distinct, higher-level concern from correlation-policy.js's per-evidence
 * checks, composed rather than duplicated (evaluateKnowledgeObjectQuality() below calls a
 * Knowledge Object's already-computed fields; it does not re-run evidence-level policy checks
 * correlation-policy.js already owns).
 */

/** @typedef {ReturnType<import('./knowledge-object.js').KnowledgeObjectService['build']>} KnowledgeObjectResult */

export const KNOWLEDGE_QUALITY_VERSION = "18.1.0";

export const KNOWLEDGE_QUALITY_RULES = Object.freeze([
  "completeness.evidence-fields-present",
  "provenance.lineage-available",
  "correlation.coverage-present",
  "explanation.summary-available",
  "references.missing-reference-count",
  "assertions.every-statement-has-basis",
]);

const REQUIRED_SUBJECT_FIELDS = Object.freeze(["evidence_uuid", "evidence_id", "evidence_type", "evidence_category"]);

/**
 * Evidence completeness: the Knowledge Object's `subject` carries the minimum identifying fields
 * a downstream consumer (Tactical Dossier, Executive Briefing) needs to cite it.
 * @param {object} knowledgeObject
 */
export function validateEvidenceCompleteness(knowledgeObject) {
  const rule = "completeness.evidence-fields-present";
  const subject = knowledgeObject?.subject || {};
  const missingFields = REQUIRED_SUBJECT_FIELDS.filter((field) => subject[field] == null);
  return { complete: missingFields.length === 0, missingFields, rule };
}

/** Provenance availability: at least one evidence-lineage entry exists. @param {object} knowledgeObject */
export function validateProvenanceAvailability(knowledgeObject) {
  const rule = "provenance.lineage-available";
  const lineageCount = knowledgeObject?.provenance?.evidenceLineage?.length || 0;
  return { available: lineageCount > 0, lineageCount, rule };
}

/** Correlation coverage: at least one supporting/related record was found. @param {object} knowledgeObject */
export function validateCorrelationCoverage(knowledgeObject) {
  const rule = "correlation.coverage-present";
  const supportingCount = knowledgeObject?.supportingEvidence?.length || 0;
  return { covered: supportingCount > 0, supportingCount, rule };
}

/** Explanation availability: a non-empty deterministic summary was generated. @param {object} knowledgeObject */
export function validateExplanationAvailability(knowledgeObject) {
  const rule = "explanation.summary-available";
  const available = typeof knowledgeObject?.summary === "string" && knowledgeObject.summary.length > 0;
  return { available, rule };
}

/**
 * Missing references: the Knowledge Object's own intelligenceGaps ARE the missing-reference
 * count -- this function does not re-detect gaps (explainability-engine.js already owns that),
 * it reports the count for quality-scoring purposes.
 * @param {object} knowledgeObject
 */
export function detectMissingReferences(knowledgeObject) {
  const rule = "references.missing-reference-count";
  const gaps = knowledgeObject?.intelligenceGaps || [];
  return { hasMissingReferences: gaps.length > 0, count: gaps.length, gaps, rule };
}

/**
 * Unsupported assertions: every statement a presentation view (Analyst/Executive) produces must
 * carry an explicit `basis` of "evidence" or "analyst_recommendation" (Phase 5's own charter).
 * Anything else -- missing, or an unrecognized value -- is an unsupported assertion.
 * @param {Array<{basis?: string}>} items
 */
export function detectUnsupportedAssertions(items) {
  const rule = "assertions.every-statement-has-basis";
  const unsupported = (items || []).filter((item) => item?.basis !== "evidence" && item?.basis !== "analyst_recommendation");
  return { hasUnsupportedAssertions: unsupported.length > 0, unsupported, rule };
}

/** Auditability/introspection surface, mirroring correlation-policy.js's describePolicy(). */
export function describeQualityFramework() {
  return { version: KNOWLEDGE_QUALITY_VERSION, rules: [...KNOWLEDGE_QUALITY_RULES] };
}

/**
 * Aggregating evaluation -- runs every quality check against one Knowledge Object (plus,
 * optionally, a flattened list of presentation-view items to check for unsupported assertions)
 * and returns one combined report.
 * @param {object} knowledgeObject
 * @param {{assertionItems?: Array<{basis?: string}>}} [context]
 */
export function evaluateKnowledgeObjectQuality(knowledgeObject, context = {}) {
  return {
    qualityVersion: KNOWLEDGE_QUALITY_VERSION,
    completeness: validateEvidenceCompleteness(knowledgeObject),
    provenance: validateProvenanceAvailability(knowledgeObject),
    correlation: validateCorrelationCoverage(knowledgeObject),
    explanation: validateExplanationAvailability(knowledgeObject),
    missingReferences: detectMissingReferences(knowledgeObject),
    unsupportedAssertions: detectUnsupportedAssertions(context.assertionItems || []),
  };
}

/**
 * Thin class wrapper exposing the pure functions above as instance methods -- the shape the
 * Gateway's createServiceMethodHandler() adapter expects (mirrors EvidenceValidationService's
 * identical "wrap pure functions for capability registration" pattern, evidence-registry/
 * evidence-service.js). Every method below delegates verbatim; no logic is duplicated.
 */
export class KnowledgeQualityService {
  /** @param {{knowledgeObject: import('./knowledge-object.js').KnowledgeObjectService}} deps */
  constructor(deps = {}) {
    this._knowledgeObject = deps.knowledgeObject;
    if (!this._knowledgeObject) {
      throw new Error("KnowledgeQualityService requires a knowledgeObject dependency");
    }
  }

  validateEvidenceCompleteness(knowledgeObject) {
    return validateEvidenceCompleteness(knowledgeObject);
  }

  validateProvenanceAvailability(knowledgeObject) {
    return validateProvenanceAvailability(knowledgeObject);
  }

  validateCorrelationCoverage(knowledgeObject) {
    return validateCorrelationCoverage(knowledgeObject);
  }

  validateExplanationAvailability(knowledgeObject) {
    return validateExplanationAvailability(knowledgeObject);
  }

  detectMissingReferences(knowledgeObject) {
    return detectMissingReferences(knowledgeObject);
  }

  detectUnsupportedAssertions(items) {
    return detectUnsupportedAssertions(items);
  }

  describeQualityFramework() {
    return describeQualityFramework();
  }

  evaluate(knowledgeObject, context) {
    return evaluateKnowledgeObjectQuality(knowledgeObject, context);
  }

  /**
   * Convenience method for Gateway callers: builds the Knowledge Object for `evidenceUuid` via
   * the injected KnowledgeObjectService, then evaluates it -- one round trip instead of two.
   * @param {string} evidenceUuid
   * @param {{assertionItems?: Array<{basis?: string}>}} [context]
   */
  async evaluateForEvidence(evidenceUuid, context = {}) {
    const knowledgeObject = await this._knowledgeObject.build(evidenceUuid);
    if (!knowledgeObject.found) return { evidenceUuid, found: false, reason: "not_found" };
    return { evidenceUuid, found: true, quality: evaluateKnowledgeObjectQuality(knowledgeObject, context) };
  }
}
