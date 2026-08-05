/**
 * Evidence entity validation — Phase 9 scaffolding (Project TITAN Stage 8).
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
