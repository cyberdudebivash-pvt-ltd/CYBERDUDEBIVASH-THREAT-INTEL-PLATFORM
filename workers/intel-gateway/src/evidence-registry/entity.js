/**
 * Canonical Evidence entity — Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Field list verified directly against the live, currently-deployed
 * `item.evidence_chain` shape in p20-handlers.js:185-244 (buildEvidenceChainBlock),
 * not copied from docs/adr/0008-canonical-evidence-framework.md's prose, which lists
 * a "corroboration_count" field that does not exist as its own field — it is the
 * `corroboration` key inside `iq_breakdown`. Corrected here rather than propagated.
 */

/**
 * @typedef {Object} EvidenceChainCore
 * Fields already live in production today (P20). Unmodified by this scaffolding —
 * this typedef documents them, it does not redefine or replace them.
 * @property {string} [evidence_id] - Free-form existing identifier (not a UUID)
 * @property {string} [reliability_code] - A-F, Admiralty/NATO-style source-type grade
 * @property {string} [source_reliability] - Display label, e.g. "F - Cannot Be Judged"
 * @property {string} [source_category] - e.g. "External Intelligence Feed"
 * @property {string} [analyst_review] - e.g. "Automated - Pending Human Review"
 * @property {string[]} [chain_of_custody] - Ordered custody event descriptions
 * @property {string[]} [known_limitations] - Analyst-noted caveats
 * @property {{source?:number, enrichment?:number, attribution?:number, corroboration?:number}} [iq_breakdown]
 */

/**
 * @typedef {Object} EvidenceIntegrityFields
 * New fields this scaffolding defines, per ADR-0008 Decision item 1. Additive only —
 * every field is optional so an EvidenceChainCore object remains a valid
 * EvidenceEntity without them (backward compatible by construction).
 * @property {string} [evidence_uuid] - Stable identity, distinct from the free-form evidence_id
 * @property {string} [content_hash] - Fingerprint for dedup/tamper-detection
 * @property {string} [schema_version] - Per this repo's SCHEMA_REGISTRY convention (P38)
 */

/**
 * @typedef {EvidenceChainCore & EvidenceIntegrityFields} EvidenceEntity
 */

export const EVIDENCE_ENTITY_CORE_FIELDS = Object.freeze([
  "evidence_id",
  "reliability_code",
  "source_reliability",
  "source_category",
  "analyst_review",
  "chain_of_custody",
  "known_limitations",
  "iq_breakdown",
]);

export const EVIDENCE_ENTITY_INTEGRITY_FIELDS = Object.freeze([
  "evidence_uuid",
  "content_hash",
  "schema_version",
]);

export const EVIDENCE_ENTITY_SCHEMA_VERSION = "evidence-registry.0.1-scaffolding";

/**
 * Constructs a well-formed EvidenceEntity from an existing evidence_chain-shaped
 * object plus the new Integrity fields. Pure function, no I/O, no storage access.
 * @param {EvidenceChainCore} core
 * @param {Partial<EvidenceIntegrityFields>} [integrity]
 * @returns {EvidenceEntity}
 */
export function createEvidenceEntity(core, integrity = {}) {
  return {
    ...core,
    evidence_uuid: integrity.evidence_uuid,
    content_hash: integrity.content_hash,
    schema_version: integrity.schema_version || EVIDENCE_ENTITY_SCHEMA_VERSION,
  };
}
