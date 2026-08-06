/**
 * Canonical Evidence entity  -  Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Field list verified directly against the live, currently-deployed
 * `item.evidence_chain` shape in p20-handlers.js:185-244 (buildEvidenceChainBlock),
 * not copied from docs/adr/0008-canonical-evidence-framework.md's prose, which lists
 * a "corroboration_count" field that does not exist as its own field  -  it is the
 * `corroboration` key inside `iq_breakdown`. Corrected here rather than propagated.
 */

/**
 * @typedef {Object} EvidenceChainCore
 * Fields already live in production today (P20). Unmodified by this scaffolding  - 
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
 * New fields this scaffolding defines, per ADR-0008 Decision item 1. Additive only  - 
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

// =======================================================================
// Stage 10  -  Canonical Evidence Core (CEC) additive extension.
// Not imported by index.js or any production route  -  see README.md, whose
// "Next steps (not performed here)" section is unchanged by this extension:
// wiring into the live P20 schema still requires ADR-0008 Acceptance first.
// This extension only enlarges the scaffolding's own domain model, which the
// original README already anticipated ("a future stage's actual integration
// work")  -  it does not shorten the path to production wiring, and every
// Stage 8 field/function above is unmodified.
// =======================================================================

/**
 * @typedef {Object} EvidenceClassificationFields
 * Stage 10 Phase 1. All optional  -  no current producer populates these; a
 * CanonicalEvidence remains valid without them (backward compatible).
 * @property {string} [evidence_type] - Open vocabulary (e.g. "OSINT", "TECHNICAL_ARTIFACT",
 *   "ANALYST_ASSERTED")  -  validated against a registry in validation.js, not a hard enum,
 *   matching TITAN_GRAPH_INTERFACE_SPECIFICATION.md's relationship_type precedent
 * @property {string} [evidence_category] - Nature of the evidence itself (e.g. "INDICATOR",
 *   "NARRATIVE", "ATTRIBUTION_CLAIM")  -  distinct from source_category (which describes the
 *   *source*, not the evidence)
 * @property {"INTERNAL"|"CUSTOMER_FACING"|"RESTRICTED"} [visibility] - Defaults to
 *   "INTERNAL" via createCanonicalEvidence() below  -  new records must be explicitly
 *   promoted to CUSTOMER_FACING, never default to it (Principle 9: secure by default)
 * @property {"TLP:RED"|"TLP:AMBER"|"TLP:AMBER+STRICT"|"TLP:GREEN"|"TLP:CLEAR"} [tlp_classification] -
 *   Standard TLP 2.0 values (FIRST.org), not a platform-invented scale
 */

/**
 * @typedef {Object} EvidenceSourceMetadataFields
 * `source_category` is intentionally NOT redefined here  -  it already exists on
 * EvidenceChainCore; redefining it here would create exactly the kind of duplicate field
 * this program's Single Source of Truth principle exists to prevent.
 * @property {string} [source_id] - Stable identifier for the source (distinct from source_name)
 * @property {string} [source_name] - Human-readable source name
 * @property {string} [collection_timestamp] - ISO-8601, when this platform collected the evidence
 * @property {string} [publication_timestamp] - ISO-8601, when the source published it
 * @property {string} [last_verified] - ISO-8601, most recent verification pass
 */

/**
 * @typedef {Object} EvidenceQualityFields
 * `reliability_code` / `source_reliability` are intentionally NOT redefined here  -  both
 * already exist on EvidenceChainCore. `canonical_confidence_object` is a *reference*, not a
 * re-computation: it holds whatever computeEnterpriseTrustScore(item) (p25-handlers.js,
 * ADR-0007's canonical A1 source) already returned for the item this evidence supports  - 
 * shape `{dims, totalEarned, totalMax, pct, tier, tierColor}`, verified directly against
 * p25-handlers.js's return statement, not assumed.
 * @property {Object} [canonical_confidence_object] - Verbatim output of P25's
 *   computeEnterpriseTrustScore(item); this typedef does not redeclare its internal shape,
 *   per Reuse Before Build  -  P25 remains the one place that shape is defined
 * @property {"UNVERIFIED"|"PARTIALLY_VERIFIED"|"VERIFIED"|"DISPUTED"} [verification_status]
 * @property {number} [evidence_weight] - 0.0-1.0, how much this evidence should weigh in
 *   downstream scoring  -  a new concept; no existing implementation defines this today
 */

/**
 * @typedef {Object} EvidenceRelationshipFields
 * Lightweight reference arrays only (entity_id strings, per
 * TITAN_GRAPH_INTERFACE_SPECIFICATION.md's EntityRef.entity_id convention)  -  NOT full
 * relationship records. Full relationship metadata (type, confidence, evidence_references
 * pointing back at THIS evidence, lifecycle, etc.) lives in the CanonicalRelationship schema
 * (TITAN_GRAPH_INTERFACE_SPECIFICATION.md Part A)  -  duplicating that structure here would
 * violate Single Source of Truth. This section is the inverse direction: which reports/CVEs/
 * actors/campaigns/techniques *this evidence itself* speaks to.
 * @property {string[]} [related_reports]
 * @property {string[]} [related_cves]
 * @property {string[]} [related_threat_actors]
 * @property {string[]} [related_campaigns]
 * @property {string[]} [related_attack_techniques]
 * @property {string[]} [related_iocs] - Stage 11 Phase 5 addition: indicator values (hash/IP/
 *   domain/etc.) this evidence speaks to, mirroring the other related_* arrays exactly. Added
 *   because Stage 11's registry indexing requires an IOC index and no existing field covered
 *   it  -  verified against the live `item.iocs` shape (p20/p22/p18-handlers.js: array of
 *   `{value, confidence, ...}` objects) rather than assumed; this field stores only the
 *   `.value` strings, matching every other related_* field's "lightweight reference array,
 *   not embedded records" convention.
 */

/**
 * @typedef {Object} EvidenceGovernanceFields
 * @property {number} [version] - Record revision number, starts at 1, increments on edit  - 
 *   distinct from schema_version (which versions the *shape*, not this specific record).
 *   Mirrors CanonicalRelationship.version exactly, for consistency across this program's two
 *   canonical object types.
 * @property {{created_at?: string, updated_at?: string, created_by?: string,
 *   producer_implementation?: string}} [audit_metadata] - `producer_implementation` names
 *   which engine/adapter produced this record (e.g. "migration-adapter:p20-evidence-chain")  - 
 *   same rationale as CanonicalRelationship.audit.producer_implementation
 * @property {{flag_state?: string, enabled_at?: (string|null), environment?: string}}
 *   [feature_flag_metadata] - Which feature-flag state was active when this record was
 *   produced; an audit trail for the flagged-rollout period, not a runtime dependency
 */

/**
 * @typedef {EvidenceEntity & EvidenceClassificationFields & EvidenceSourceMetadataFields &
 *   EvidenceQualityFields & EvidenceRelationshipFields & EvidenceGovernanceFields} CanonicalEvidence
 * The Stage 10 Canonical Evidence Core object. A superset of the Stage 8 EvidenceEntity  - 
 * every Stage 8 field remains valid and unchanged; nothing is renamed or removed (Principle 5).
 */

export const EVIDENCE_CLASSIFICATION_FIELDS = Object.freeze([
  "evidence_type", "evidence_category", "visibility", "tlp_classification",
]);

export const EVIDENCE_SOURCE_METADATA_FIELDS = Object.freeze([
  "source_id", "source_name", "collection_timestamp", "publication_timestamp", "last_verified",
]);

export const EVIDENCE_QUALITY_FIELDS = Object.freeze([
  "canonical_confidence_object", "verification_status", "evidence_weight",
]);

export const EVIDENCE_RELATIONSHIP_FIELDS = Object.freeze([
  "related_reports", "related_cves", "related_threat_actors", "related_campaigns",
  "related_attack_techniques", "related_iocs",
]);

export const EVIDENCE_GOVERNANCE_FIELDS = Object.freeze([
  "version", "audit_metadata", "feature_flag_metadata",
]);

export const TLP_CLASSIFICATIONS = Object.freeze([
  "TLP:RED", "TLP:AMBER", "TLP:AMBER+STRICT", "TLP:GREEN", "TLP:CLEAR",
]);

export const VISIBILITY_LEVELS = Object.freeze(["INTERNAL", "CUSTOMER_FACING", "RESTRICTED"]);

export const VERIFICATION_STATUSES = Object.freeze([
  "UNVERIFIED", "PARTIALLY_VERIFIED", "VERIFIED", "DISPUTED",
]);

/**
 * Canonical Evidence Core schema version. Distinct from, and layered on top of,
 * EVIDENCE_ENTITY_SCHEMA_VERSION ("evidence-registry.0.1-scaffolding")  -  that version string
 * is not renamed or bumped by this change (existing scaffolding consumers still see the same
 * value from createEvidenceEntity). This new constant versions the expanded CanonicalEvidence
 * shape specifically.
 *
 * Bumped 1.0.0-draft -> 1.1.0-draft in Stage 11 Phase 5 for the additive `related_iocs` field
 * (see EvidenceRelationshipFields above)  -  additive-only, so 1.0.0-draft objects remain valid
 * 1.1.0-draft objects with `related_iocs` simply absent (schema.js's SCHEMA_VERSION_HISTORY
 * records this as `backwardCompatibleWithPrevious: true`, per its own established convention).
 */
export const CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION = "canonical-evidence-core.1.1.0-draft";

/**
 * Constructs a well-formed CanonicalEvidence from an existing EvidenceEntity (Stage 8 shape,
 * unchanged) plus the new Stage 10 field groups. Every new field is optional. Omitting the
 * `extension` argument entirely still upgrades `schema_version` to
 * CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION (this function's whole purpose is producing the
 * newer shape) while leaving every Stage 8 field on `base` untouched.
 * @param {EvidenceEntity} base - Typically the output of createEvidenceEntity()
 * @param {Partial<EvidenceClassificationFields & EvidenceSourceMetadataFields &
 *   EvidenceQualityFields & EvidenceRelationshipFields & EvidenceGovernanceFields> &
 *   {schema_version?: string}} [extension]
 * @returns {CanonicalEvidence}
 */
export function createCanonicalEvidence(base, extension = {}) {
  const now = new Date().toISOString();
  return {
    ...base,
    schema_version: extension.schema_version || CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION,
    evidence_type: extension.evidence_type,
    evidence_category: extension.evidence_category,
    visibility: extension.visibility || "INTERNAL",
    tlp_classification: extension.tlp_classification,
    source_id: extension.source_id,
    source_name: extension.source_name,
    collection_timestamp: extension.collection_timestamp,
    publication_timestamp: extension.publication_timestamp,
    last_verified: extension.last_verified,
    canonical_confidence_object: extension.canonical_confidence_object,
    verification_status: extension.verification_status || "UNVERIFIED",
    evidence_weight: extension.evidence_weight,
    related_reports: extension.related_reports || [],
    related_cves: extension.related_cves || [],
    related_threat_actors: extension.related_threat_actors || [],
    related_campaigns: extension.related_campaigns || [],
    related_attack_techniques: extension.related_attack_techniques || [],
    related_iocs: extension.related_iocs || [],
    version: extension.version !== undefined ? extension.version : 1,
    audit_metadata: {
      created_at: extension.audit_metadata?.created_at || now,
      updated_at: extension.audit_metadata?.updated_at || now,
      created_by: extension.audit_metadata?.created_by || null,
      producer_implementation: extension.audit_metadata?.producer_implementation || null,
    },
    feature_flag_metadata: {
      flag_state: extension.feature_flag_metadata?.flag_state || "SCAFFOLDING_ENABLED:false",
      enabled_at: extension.feature_flag_metadata?.enabled_at || null,
      environment: extension.feature_flag_metadata?.environment || "development",
    },
  };
}

/**
 * Recursively freezes plain object/array values (Object.freeze() alone is shallow). Extracted
 * from publishEvidenceEntity() (Stage 10) in Stage 11 Phase 4 so version-history freezing
 * (versioning.js, in-memory-repository.js) can reuse the exact same recursion instead of
 * duplicating it  -  Reuse Before Build. publishEvidenceEntity()'s own behavior is unchanged by
 * this extraction (same inputs still produce the same outputs; covered by entity.test.js).
 * @param {unknown} value
 * @returns {unknown} the same value, deep-frozen
 */
export function deepFreeze(value) {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) {
    return value;
  }
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}

/**
 * Deep-freezes a CanonicalEvidence so it satisfies Stage 10 Phase 1's "must be immutable
 * once published" requirement. Nested fields (audit_metadata, canonical_confidence_object, the
 * related_* arrays) are frozen too, via deepFreeze().
 * @param {CanonicalEvidence} evidence
 * @returns {Readonly<CanonicalEvidence>}
 */
export function publishEvidenceEntity(evidence) {
  const published = {
    ...evidence,
    published_at: evidence.published_at || new Date().toISOString(),
  };
  return deepFreeze(published);
}

/**
 * @param {CanonicalEvidence} evidence
 * @returns {boolean}
 */
export function isPublished(evidence) {
  return Boolean(
    evidence && typeof evidence === "object" && Object.isFrozen(evidence) && evidence.published_at
  );
}
