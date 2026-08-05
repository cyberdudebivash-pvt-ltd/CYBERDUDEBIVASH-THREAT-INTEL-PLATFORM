/**
 * Evidence identifier generation — Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Uses the Web Crypto API already available in the Workers runtime (this repo's
 * existing JWT signing in index.js already depends on crypto.subtle being present,
 * so crypto.randomUUID() requires no new capability or dependency).
 */

/**
 * Generates a new evidence_uuid. Pure function (well, not pure in the strict FP
 * sense - randomUUID has side effects on entropy state - but deterministic in
 * signature and has no I/O, no network, no storage access).
 * @returns {string} RFC 4122 UUID v4
 */
export function generateEvidenceUuid() {
  return crypto.randomUUID();
}

/**
 * Computes a content_hash for tamper-detection / dedup, per ADR-0008 Decision item 1.
 * SHA-256 over a canonical JSON serialization of the fields that define the
 * evidence's substance (excludes evidence_uuid and content_hash itself, so the hash
 * is stable across identifier assignment).
 * @param {import('./entity.js').EvidenceEntity} entity
 * @returns {Promise<string>} hex-encoded SHA-256 digest
 */
export async function computeContentHash(entity) {
  const { evidence_uuid, content_hash, ...substantive } = entity;
  const canonical = JSON.stringify(substantive, Object.keys(substantive).sort());
  const bytes = new TextEncoder().encode(canonical);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}
