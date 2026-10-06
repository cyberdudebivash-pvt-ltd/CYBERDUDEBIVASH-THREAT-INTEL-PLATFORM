/**
 * Enterprise Intelligence Platform Services (EIPS) -- Stage 13 Phase 2, Enterprise Query
 * Service (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * The brief names 12 query dimensions: Evidence, Reports, CVEs, Threat Actors, Campaigns,
 * IOCs, Confidence, Sources, Vendor, Product, Malware, ATT&CK. Before adding any of these as a
 * queryable "type," Stage 13 Phase 2 research (a repo-wide audit of workers/intel-gateway/src/**,
 * every p16-p38 handler, and the Python ingestion/scoring tree) confirmed which ones already
 * have a canonical implementation this service can compose, and which do not.
 *
 * 9 of 12 dimensions: EvidenceQueryEngine (Stage 12) already exposes a `lookupBy*` method
 * operating on a real CanonicalEvidence field (Stage 10) -- delegated verbatim below, zero new
 * logic.
 *
 * 3 of 12 dimensions (Vendor, Product, Malware): NO canonical, composable implementation exists
 * for these, for three different reasons documented per-method below and in
 * TITAN_STAGE13_QUERY_DOCUMENTATION.md's "Known Gaps" section. Per this program's Reuse Before
 * Build rule ("If no canonical model exists: Document it. Do not invent one"), these methods
 * throw an explicit, specific error rather than silently returning an empty array (which could
 * be mistaken for "this platform genuinely has zero evidence for that vendor/product/malware,"
 * a false negative) or inventing a new domain model / new evidence-registry index (which would
 * mean modifying Stage 11 files, out of this stage's additive-only scope). This mirrors
 * relationship-resolution.js's NOT_WIRED pattern (Stage 12), applied to a schema gap instead of
 * an ADR gate.
 */

function uncanonicalDimensionError(dimension, explanation) {
  return new Error(
    `queryBy${dimension}: no canonical, composable ${dimension} implementation exists in this ` +
      `platform as of Stage 13 (Phase 2 research, see TITAN_STAGE13_QUERY_DOCUMENTATION.md's ` +
      `Known Gaps section). ${explanation} Per Stage 13's Reuse Before Build governance rule, ` +
      `this method documents the gap rather than inventing a new domain model or evidence-` +
      `registry index.`
  );
}

export class EnterpriseQueryService {
  /** @param {{queryEngine: import('../evidence-registry/query-engine.js').EvidenceQueryEngine}} deps */
  constructor(deps = {}) {
    this._queryEngine = deps.queryEngine;
    if (!this._queryEngine) {
      throw new Error("EnterpriseQueryService requires a shared queryEngine dependency");
    }
  }

  // ---- 9 of 12 dimensions: direct delegation to EvidenceQueryEngine, zero new logic --------

  /** @param {string} evidenceUuid */
  async queryByEvidence(evidenceUuid) {
    return this._queryEngine.lookupByUuid(evidenceUuid);
  }

  /** @param {string} reportId */
  async queryByReport(reportId) {
    return this._queryEngine.lookupByReport(reportId);
  }

  /** @param {string} cve */
  async queryByCVE(cve) {
    return this._queryEngine.lookupByCve(cve);
  }

  /** @param {string} actor */
  async queryByThreatActor(actor) {
    return this._queryEngine.lookupByThreatActor(actor);
  }

  /** @param {string} campaign */
  async queryByCampaign(campaign) {
    return this._queryEngine.lookupByCampaign(campaign);
  }

  /** @param {string} ioc */
  async queryByIOC(ioc) {
    return this._queryEngine.lookupByIoc(ioc);
  }

  /** @param {string} tier */
  async queryByConfidence(tier) {
    return this._queryEngine.lookupByConfidence(tier);
  }

  /** @param {string} sourceId */
  async queryBySource(sourceId) {
    return this._queryEngine.lookupBySource(sourceId);
  }

  /** @param {string} technique */
  async queryByAttackTechnique(technique) {
    return this._queryEngine.lookupByAttackTechnique(technique);
  }

  // ---- 3 of 12 dimensions: no canonical composable implementation -- documented gaps -------

  /**
   * GAP: no structured Vendor representation exists anywhere in this platform. The only
   * proximate reference is free-text substring matching inside P18's buildEvidenceAttribution()
   * (checking item.source for strings like "vendor"/"microsoft"/"cisco") -- not a field, index,
   * or entity. Nothing to compose.
   */
  async queryByVendor() {
    throw uncanonicalDimensionError(
      "Vendor",
      "The only proximate reference platform-wide is free-text substring matching inside P18's " +
        "buildEvidenceAttribution() (checking item.source for vendor-name strings) -- not a " +
        "structured field, index, or entity."
    );
  }

  /**
   * GAP (scoped to this service's substrate): intelligence items carry an informal,
   * schema-registered `affected_products` field elsewhere in the platform (p38-handlers.js
   * SCHEMA_REGISTRY; consumed by p20-handlers.js and scripts/alert_engine.py), but
   * CanonicalEvidence (evidence-registry/entity.js, Stage 10) has no `related_products` field
   * and EvidenceQueryEngine has no corresponding lookup method. Adding one would require
   * modifying Stage 11 evidence-registry files, out of this stage's additive-only scope.
   */
  async queryByProduct() {
    throw uncanonicalDimensionError(
      "Product",
      "Intelligence items carry an informal `affected_products` field elsewhere in the " +
        "platform (p38-handlers.js SCHEMA_REGISTRY), but CanonicalEvidence has no " +
        "related_products field and EvidenceQueryEngine has no corresponding lookup method -- " +
        "adding one means modifying Stage 11 evidence-registry files, out of this stage's " +
        "additive-only scope."
    );
  }

  /**
   * GAP: no standalone Malware entity exists anywhere in this platform. The only structured
   * reference is `actor_malware`, nested under Threat Actor (p38-handlers.js SCHEMA_REGISTRY,
   * populated by scripts/actor_intelligence_engine.py) -- not a standalone dimension.
   * p31-handlers.js's `_normalizeMalware()`/`_MALWARE_CANONICAL` have zero call sites (dead
   * code) and are not part of this stage's composable surface regardless.
   */
  async queryByMalware() {
    throw uncanonicalDimensionError(
      "Malware",
      "The only structured reference platform-wide is actor_malware, nested under Threat Actor " +
        "(p38-handlers.js SCHEMA_REGISTRY) -- not a standalone dimension. p31-handlers.js's " +
        "_normalizeMalware()/_MALWARE_CANONICAL have zero call sites (dead code)."
    );
  }
}
