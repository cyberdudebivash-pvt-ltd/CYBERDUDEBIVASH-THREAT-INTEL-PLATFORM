/**
 * Enterprise Intelligence Platform Services (EIPS) -- Project TITAN Stage 17 Phase 4,
 * Correlation Policy Framework (Track A only). Not imported by index.js or any production route,
 * matching this lineage's unbroken Stage 8-16 convention (see ../evidence-registry/README.md).
 *
 * Scope boundary (see TITAN_STAGE17_READINESS_REPORT.md Sec 4): every rule below is a structural,
 * deterministic check over fields ../evidence-registry/entity.js already defines
 * (EVIDENCE_RELATIONSHIP_FIELDS, EVIDENCE_ENTITY_INTEGRITY_FIELDS, VERIFICATION_STATUSES). No
 * function in this file reads, computes, weights, or propagates `canonical_confidence_object` --
 * that field is P25's (docs/adr/0007-canonical-confidence-framework.md is Proposed, not Accepted;
 * see explainability-engine.js for how it is surfaced verbatim, never here). Confidence
 * propagation, confidence-weighted inclusion, and confidence-weighted conflict resolution are
 * Stage 17B work items -- see TITAN_STAGE17_CORRELATION_EXPLAINABILITY_REPORT.md's Deferred
 * Capability Register.
 *
 * Pure functions only, no new storage -- mirrors correlation-engine.js's own "no new
 * storage/indexing" discipline one level down (structural policy over data those engines already
 * fetch, not a new data source).
 */

/** @typedef {import('../evidence-registry/entity.js').CanonicalEvidence} CanonicalEvidence */

const RELATIONSHIP_FIELDS = Object.freeze([
  "related_reports",
  "related_cves",
  "related_threat_actors",
  "related_campaigns",
  "related_attack_techniques",
  "related_iocs",
]);

export const CORRELATION_POLICY_VERSION = "17.1.0";

/**
 * Rule identifiers this module implements, for auditability (Phase 4: "policies must be
 * auditable and versioned"). Kept as a flat list rather than free prose so a governance check or
 * a test can assert against it directly.
 */
export const CORRELATION_POLICY_RULES = Object.freeze([
  "evidence-inclusion.has-relationship-or-lineage",
  "provenance-validity.non-empty-lineage-with-source",
  "duplicate-evidence.shared-content-hash",
  "conflict-detection.disputed-verification-status",
  "conflict-detection.cross-record-status-disagreement",
  "unsupported-evidence.zero-relationships-and-zero-provenance",
]);

function _relationshipCount(evidence) {
  if (!evidence) return 0;
  let count = 0;
  for (const field of RELATIONSHIP_FIELDS) {
    const values = evidence[field];
    if (Array.isArray(values)) count += values.length;
  }
  return count;
}

/**
 * Evidence inclusion policy: an evidence record qualifies for correlation output if it is not a
 * completely isolated, contextless record -- it must carry at least one relationship reference or
 * at least one prior version (lineage entry count is the caller's to supply, since only the
 * Provenance Engine knows it; this function is intentionally storage-agnostic).
 * @param {CanonicalEvidence} evidence
 * @param {{lineageCount?: number}} [context]
 * @returns {{included: boolean, reason: string, rule: string}}
 */
export function evaluateEvidenceInclusion(evidence, context = {}) {
  const rule = "evidence-inclusion.has-relationship-or-lineage";
  if (!evidence) {
    return { included: false, reason: "no evidence record supplied", rule };
  }
  const relCount = _relationshipCount(evidence);
  const lineageCount = context.lineageCount || 0;
  if (relCount === 0 && lineageCount === 0) {
    return {
      included: false,
      reason: "evidence has zero relationship references and zero lineage entries -- no basis for correlation",
      rule,
    };
  }
  return { included: true, reason: `${relCount} relationship reference(s), ${lineageCount} lineage entrie(s)`, rule };
}

/**
 * Provenance validity policy: a lineage array (as returned by EvidenceProvenanceEngine's
 * getEvidenceLineage/getSourceLineage) is valid only if non-empty and its oldest entry carries
 * some attribution (source_id, created_by, or producer_implementation) -- an empty
 * audit_metadata object is a lineage entry that exists but proves nothing.
 * @param {Array<object>} lineageEntries
 * @returns {{valid: boolean, reason: string, rule: string}}
 */
export function evaluateProvenanceValidity(lineageEntries) {
  const rule = "provenance-validity.non-empty-lineage-with-source";
  if (!Array.isArray(lineageEntries) || lineageEntries.length === 0) {
    return { valid: false, reason: "no lineage entries", rule };
  }
  const oldest = lineageEntries[0];
  const hasAttribution = Boolean(
    oldest && (oldest.source_id || oldest.created_by || oldest.producer_implementation)
  );
  if (!hasAttribution) {
    return { valid: false, reason: "oldest lineage entry has no source_id/created_by/producer_implementation", rule };
  }
  return { valid: true, reason: `${lineageEntries.length} lineage entrie(s), attributed`, rule };
}

/**
 * Duplicate evidence policy: groups records by content_hash (Stage 8 integrity field, designed
 * for exactly this -- "fingerprint for dedup/tamper-detection", entity.js) where more than one
 * distinct evidence_uuid shares the same hash. Does not mutate or drop anything -- flags groups
 * for the caller to handle per Phase E ("duplicate evidence handling", not deletion).
 * @param {CanonicalEvidence[]} evidenceList
 * @returns {Array<{contentHash: string, evidenceUuids: string[]}>}
 */
export function detectDuplicateEvidence(evidenceList) {
  const byHash = new Map();
  for (const evidence of evidenceList || []) {
    const hash = evidence?.content_hash;
    const uuid = evidence?.evidence_uuid;
    if (!hash || !uuid) continue;
    if (!byHash.has(hash)) byHash.set(hash, new Set());
    byHash.get(hash).add(uuid);
  }
  const duplicates = [];
  for (const [contentHash, uuids] of byHash.entries()) {
    if (uuids.size > 1) duplicates.push({ contentHash, evidenceUuids: [...uuids] });
  }
  return duplicates;
}

/**
 * Conflict detection policy: two deterministic, schema-native rules only.
 *  1. Any record whose verification_status is "DISPUTED" (entity.js's own enum, designed for
 *     exactly this signal -- not inferred from any other field).
 *  2. Among a set of records that are already correlated (the caller supplies a correlated set,
 *     e.g. IntelligenceCorrelationService.correlateEvidence()'s output), a status disagreement:
 *     one record VERIFIED while another in the same set is DISPUTED or UNVERIFIED.
 * Neither rule touches canonical_confidence_object or evidence_weight.
 * @param {CanonicalEvidence[]} evidenceList
 * @returns {{disputed: string[], statusDisagreement: boolean, statuses: Record<string, number>}}
 */
export function detectConflicts(evidenceList) {
  const list = evidenceList || [];
  const disputed = list.filter((e) => e?.verification_status === "DISPUTED").map((e) => e.evidence_uuid).filter(Boolean);

  const statuses = {};
  for (const evidence of list) {
    const status = evidence?.verification_status;
    if (status) statuses[status] = (statuses[status] || 0) + 1;
  }
  const distinctStatuses = Object.keys(statuses);
  const statusDisagreement =
    distinctStatuses.includes("VERIFIED") &&
    distinctStatuses.some((s) => s === "DISPUTED" || s === "UNVERIFIED");

  return { disputed, statusDisagreement, statuses, rule: "conflict-detection.disputed-verification-status" };
}

/**
 * Unsupported evidence policy: flags (never deletes) evidence that has neither a relationship
 * reference nor a provenance lineage entry -- the strictest of this module's rules, intended for
 * an explicit analyst review queue, not automatic rejection. Distinct from evaluateEvidenceInclusion
 * (which is a softer "don't correlate this" signal) -- this is "this evidence record cannot
 * currently support any conclusion at all."
 * @param {CanonicalEvidence} evidence
 * @param {{relatedCount?: number, provenanceCount?: number}} [context]
 * @returns {{unsupported: boolean, reason: string, rule: string}}
 */
export function rejectUnsupportedEvidence(evidence, context = {}) {
  const rule = "unsupported-evidence.zero-relationships-and-zero-provenance";
  const relatedCount = context.relatedCount ?? _relationshipCount(evidence);
  const provenanceCount = context.provenanceCount ?? 0;
  if (relatedCount === 0 && provenanceCount === 0) {
    return {
      unsupported: true,
      reason: "zero relationship references and zero provenance lineage entries -- flagged for analyst review, not auto-rejected",
      rule,
    };
  }
  return { unsupported: false, reason: `${relatedCount} relationship reference(s), ${provenanceCount} provenance entrie(s)`, rule };
}

/** Auditability/introspection surface -- what Phase 4 means by "versioned and auditable". */
export function describePolicy() {
  return {
    version: CORRELATION_POLICY_VERSION,
    rules: [...CORRELATION_POLICY_RULES],
    deferredRules: [
      "confidence-propagation (ADR-0007 Proposed, not Accepted)",
      "confidence-weighted-inclusion (ADR-0007 Proposed, not Accepted)",
      "confidence-weighted-conflict-resolution (ADR-0007 Proposed, not Accepted)",
    ],
  };
}

/**
 * Aggregating evaluation -- runs every Track A policy against one evidence record plus its
 * already-fetched correlation/provenance context, and returns one combined report. This is the
 * single entry point explainability-engine.js calls; it does not duplicate any rule's logic
 * (Single Source of Truth -- each rule lives in exactly one exported function above).
 * @param {CanonicalEvidence} evidence
 * @param {{correlatedEvidence?: CanonicalEvidence[], lineageEntries?: Array<object>}} [context]
 */
export function evaluate(evidence, context = {}) {
  const correlatedEvidence = context.correlatedEvidence || [];
  const lineageEntries = context.lineageEntries || [];

  const inclusion = evaluateEvidenceInclusion(evidence, { lineageCount: lineageEntries.length });
  const provenance = evaluateProvenanceValidity(lineageEntries);
  const duplicates = detectDuplicateEvidence([evidence, ...correlatedEvidence]);
  const conflicts = detectConflicts([evidence, ...correlatedEvidence]);
  const unsupported = rejectUnsupportedEvidence(evidence, {
    relatedCount: _relationshipCount(evidence),
    provenanceCount: lineageEntries.length,
  });

  return {
    policyVersion: CORRELATION_POLICY_VERSION,
    inclusion,
    provenance,
    duplicates,
    conflicts,
    unsupported,
  };
}
