/**
 * Evidence identifier generation  -  Phase 9 scaffolding (Project TITAN Stage 8).
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

async function sha256Hex(canonicalString) {
  const bytes = new TextEncoder().encode(canonicalString);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
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
  return sha256Hex(canonical);
}

/**
 * Stage 11 Phase 7 addition  -  content hash scoped to CanonicalEvidence's stable, substantive
 * fields only. computeContentHash() above (Stage 8) is correct for the narrower EvidenceEntity
 * shape it was written for, but naively reusing it on a full CanonicalEvidence would fold in
 * volatile fields Stage 10 added that are NOT substantive to "is this the same evidence"
 * (audit_metadata.created_at/updated_at are freshly stamped on every createCanonicalEvidence()
 * call; feature_flag_metadata.enabled_at likewise; version/canonical_confidence_object/
 * verification_status/evidence_weight/visibility are governance or scoring metadata, not the
 * evidence's substance). Hashing those would make every fresh construction of otherwise-
 * identical evidence produce a different hash, defeating cross-report reuse detection (Phase 7)
 * entirely  -  this function picks the explicit substantive-field subset instead, reusing the
 * same canonicalization + SHA-256 approach as computeContentHash() (sha256Hex above), not a
 * different hashing scheme.
 * @param {import('./entity.js').CanonicalEvidence} evidence
 * @returns {Promise<string>} hex-encoded SHA-256 digest
 */
export async function computeCanonicalEvidenceContentHash(evidence) {
  const substantive = {
    evidence_id: evidence.evidence_id,
    reliability_code: evidence.reliability_code,
    source_reliability: evidence.source_reliability,
    source_category: evidence.source_category,
    analyst_review: evidence.analyst_review,
    chain_of_custody: evidence.chain_of_custody,
    known_limitations: evidence.known_limitations,
    iq_breakdown: evidence.iq_breakdown,
    evidence_type: evidence.evidence_type,
    evidence_category: evidence.evidence_category,
    tlp_classification: evidence.tlp_classification,
    source_id: evidence.source_id,
    source_name: evidence.source_name,
    related_reports: evidence.related_reports,
    related_cves: evidence.related_cves,
    related_threat_actors: evidence.related_threat_actors,
    related_campaigns: evidence.related_campaigns,
    related_attack_techniques: evidence.related_attack_techniques,
    related_iocs: evidence.related_iocs,
  };
  const canonical = JSON.stringify(substantive, Object.keys(substantive).sort());
  return sha256Hex(canonical);
}
