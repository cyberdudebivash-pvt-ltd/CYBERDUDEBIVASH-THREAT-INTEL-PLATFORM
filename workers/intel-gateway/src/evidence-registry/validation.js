/**
 * Evidence entity validation  -  Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Pure validation functions, no I/O. Deliberately permissive on the Core fields
 * (they're all optional in production today - P20's own buildEvidenceChainBlock
 * defensively handles every field being absent) and stricter on the new Integrity
 * fields, since those don't exist in any live data yet and this scaffolding gets
 * to define their contract cleanly.
 */

const RELIABILITY_CODES = Object.freeze(["A", "B", "C", "D", "E", "F"]);
const UUID_V4_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SHA256_HEX_PATTERN = /^[0-9a-f]{64}$/i;

import {
  EVIDENCE_RELATIONSHIP_FIELDS,
  TLP_CLASSIFICATIONS,
  VERIFICATION_STATUSES,
  VISIBILITY_LEVELS,
} from "./entity.js";

/**
 * @typedef {Object} ValidationResult
 * @property {boolean} valid
 * @property {string[]} errors
 */

/**
 * @param {import('./entity.js').EvidenceEntity} entity
 * @returns {ValidationResult}
 */
export function validateEvidenceEntity(entity) {
  const errors = [];

  if (!entity || typeof entity !== "object") {
    return { valid: false, errors: ["entity must be an object"] };
  }

  if (entity.reliability_code !== undefined && !RELIABILITY_CODES.includes(entity.reliability_code)) {
    errors.push(`reliability_code must be one of ${RELIABILITY_CODES.join(", ")} when present`);
  }

  if (entity.chain_of_custody !== undefined && !Array.isArray(entity.chain_of_custody)) {
    errors.push("chain_of_custody must be an array when present");
  }

  if (entity.known_limitations !== undefined && !Array.isArray(entity.known_limitations)) {
    errors.push("known_limitations must be an array when present");
  }

  if (entity.iq_breakdown !== undefined && (typeof entity.iq_breakdown !== "object" || Array.isArray(entity.iq_breakdown))) {
    errors.push("iq_breakdown must be an object when present");
  }

  if (entity.evidence_uuid !== undefined && !UUID_V4_PATTERN.test(entity.evidence_uuid)) {
    errors.push("evidence_uuid must be a valid UUID v4 when present");
  }

  if (entity.content_hash !== undefined && !SHA256_HEX_PATTERN.test(entity.content_hash)) {
    errors.push("content_hash must be a 64-character hex SHA-256 digest when present");
  }

  if (entity.schema_version !== undefined && typeof entity.schema_version !== "string") {
    errors.push("schema_version must be a string when present");
  }

  return { valid: errors.length === 0, errors };
}

// =======================================================================
// Stage 10 Phase 4  -  Canonical Evidence Core validation engine.
// validateEvidenceEntity() above is UNCHANGED  -  existing callers (none yet,
// since nothing is wired up, but the function signature/behavior is
// preserved regardless) see identical behavior. The functions below are
// new, additive, and reusable across any future repository implementation
// (Phase 3's EvidenceValidator interface wraps these).
// =======================================================================

/**
 * @typedef {Object} StrictValidationOptions
 * @property {boolean} [requireEvidenceType] - default false, matching Stage 8's permissive
 *   philosophy; set true to enforce "missing evidence type" for entities about to be published
 * @property {boolean} [requireConfidence] - default false; set true to require
 *   canonical_confidence_object be present
 * @property {boolean} [requireLifecycle] - default false; set true to require an explicit
 *   verification_status (not just the UNVERIFIED default)
 */

/**
 * @typedef {ValidationResult & {warnings: string[]}} StrictValidationResult
 */

/**
 * Validates the Stage 10 CanonicalEvidence field groups. Calls validateEvidenceEntity()
 * first and includes its errors verbatim (Reuse Before Build  -  this does not re-check what
 * that function already checks).
 * @param {import('./entity.js').CanonicalEvidence} entity
 * @param {StrictValidationOptions} [options]
 * @returns {StrictValidationResult}
 */
export function validateCanonicalEvidence(entity, options = {}) {
  const base = validateEvidenceEntity(entity);
  const errors = [...base.errors];
  const warnings = [];

  if (!entity || typeof entity !== "object") {
    return { valid: false, errors, warnings };
  }

  // Invalid IDs
  if (entity.evidence_id !== undefined && typeof entity.evidence_id !== "string") {
    errors.push("evidence_id must be a string when present");
  }
  if (entity.source_id !== undefined && typeof entity.source_id !== "string") {
    errors.push("source_id must be a string when present");
  }

  // Schema violations  -  closed vocabularies
  if (entity.visibility !== undefined && !VISIBILITY_LEVELS.includes(entity.visibility)) {
    errors.push(`visibility must be one of ${VISIBILITY_LEVELS.join(", ")} when present`);
  }
  if (
    entity.tlp_classification !== undefined &&
    !TLP_CLASSIFICATIONS.includes(entity.tlp_classification)
  ) {
    errors.push(`tlp_classification must be one of ${TLP_CLASSIFICATIONS.join(", ")} when present`);
  }
  if (
    entity.verification_status !== undefined &&
    !VERIFICATION_STATUSES.includes(entity.verification_status)
  ) {
    errors.push(`verification_status must be one of ${VERIFICATION_STATUSES.join(", ")} when present`);
  }
  if (entity.evidence_weight !== undefined) {
    if (typeof entity.evidence_weight !== "number" || entity.evidence_weight < 0 || entity.evidence_weight > 1) {
      errors.push("evidence_weight must be a number in [0, 1] when present");
    }
  }

  // Relationship inconsistencies  -  shape + within-field duplicates. Referential integrity
  // (does related_reports[i] actually exist?) is out of scope for a pure, storage-free
  // validator  -  Phase 3's "no storage implementation yet" applies here too.
  for (const field of EVIDENCE_RELATIONSHIP_FIELDS) {
    const value = entity[field];
    if (value === undefined) continue;
    if (!Array.isArray(value)) {
      errors.push(`${field} must be an array when present`);
      continue;
    }
    if (value.some((v) => typeof v !== "string")) {
      errors.push(`${field} must contain only strings`);
    }
    if (new Set(value).size !== value.length) {
      warnings.push(`${field} contains duplicate entries`);
    }
  }

  // Governance
  if (entity.version !== undefined && (!Number.isInteger(entity.version) || entity.version < 1)) {
    errors.push("version must be a positive integer when present");
  }

  // Missing confidence / lifecycle / evidence type  -  strict, opt-in checks. Off by default so
  // this function's default behavior stays permissive, matching validateEvidenceEntity()'s
  // own documented philosophy ("deliberately permissive... they're all optional in production
  // today").
  if (options.requireEvidenceType && !entity.evidence_type) {
    errors.push("evidence_type is required (requireEvidenceType option set)");
  }
  if (options.requireConfidence && !entity.canonical_confidence_object) {
    errors.push("canonical_confidence_object is required (requireConfidence option set)");
  }
  if (options.requireLifecycle && !entity.verification_status) {
    errors.push("verification_status is required (requireLifecycle option set)");
  }

  return { valid: errors.length === 0, errors, warnings };
}

/**
 * Batch validation across a collection: duplicate identifiers and version conflicts.
 * Pure function, no I/O  -  operates on whatever collection the caller already has in memory.
 * @param {import('./entity.js').CanonicalEvidence[]} entities
 * @returns {StrictValidationResult}
 */
export function validateEvidenceBatch(entities) {
  const errors = [];
  const warnings = [];

  if (!Array.isArray(entities)) {
    return { valid: false, errors: ["entities must be an array"], warnings };
  }

  const byUuid = new Map();
  entities.forEach((entity, index) => {
    if (!entity || !entity.evidence_uuid) return;
    const group = byUuid.get(entity.evidence_uuid) || [];
    group.push({ index, version: entity.version });
    byUuid.set(entity.evidence_uuid, group);
  });

  for (const [uuid, group] of byUuid) {
    if (group.length <= 1) continue;
    const versions = group.map((g) => g.version);
    const indices = group.map((g) => g.index).join(", ");
    const hasUndefinedVersion = versions.some((v) => v === undefined);
    const hasDuplicateVersion = new Set(versions).size !== versions.length;

    if (hasUndefinedVersion || hasDuplicateVersion) {
      errors.push(
        `DUPLICATE IDENTIFIER: evidence_uuid ${uuid} appears ${group.length} times ` +
          `(indices ${indices}) without distinct version numbers for each occurrence`
      );
      continue;
    }

    const sorted = [...versions].sort((a, b) => a - b);
    const isAscending = versions.every((v, i) => v === sorted[i]);
    if (!isAscending) {
      errors.push(
        `VERSION CONFLICT: evidence_uuid ${uuid} has versions [${versions.join(", ")}] ` +
          `not in ascending order across indices ${indices}`
      );
    } else {
      warnings.push(
        `evidence_uuid ${uuid} appears ${group.length} times with distinct ascending versions ` +
          `[${versions.join(", ")}]  -  treated as a version history, not a duplicate`
      );
    }
  }

  return { valid: errors.length === 0, errors, warnings };
}
