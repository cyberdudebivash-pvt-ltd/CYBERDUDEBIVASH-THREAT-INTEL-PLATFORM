/**
 * Enterprise Evidence Service Platform (EESP)  -  Stage 12 Phase 1 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * "One Evidence Service... One Service Layer... Everything else consumes these services."
 * Six focused, independently-usable services (Lookup, Version, Lifecycle, Validation,
 * Relationship, Metrics) plus one aggregating facade (EvidenceService  -  the "One" future
 * consumers should import) that composes all six. Every method here delegates to an
 * EvidenceRegistry instance's existing PUBLIC API (Stage 11, registry-service.js)  -  none of
 * these classes hold their own storage, none reach into EvidenceRegistry's private fields
 * (`_repository`/`_versionManager`/`_indexes`/`_metrics`), and none duplicate a single line of
 * Stage 11's logic. "No duplicated logic" (Phase 1's own instruction) is satisfied structurally:
 * there is nothing here to duplicate, only delegation.
 *
 * Internal service only  -  every method is a plain async class method, not an HTTP handler. No
 * route in index.js references this file (same boundary Stage 8-11 established; verified by
 * zero-blast-radius.test.js, extended this stage to cover every new file below).
 */

import { EvidenceRegistry } from "./registry-service.js";
import { validateEvidenceBatch } from "./validation.js";
import { ServicePlatformMetrics } from "./service-metrics.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

/**
 * Wraps every EvidenceRegistry read/find method under one consistent name. Distinct from
 * query-engine.js's EvidenceQueryEngine (Phase 2): this service exposes exactly the methods
 * EvidenceRegistry itself already names (getEvidence, findEvidence, findByCVE, ...); the Query
 * Engine is a separate, uniformly-named 12-dimension lookup contract layered on top. Both are
 * legitimate, non-duplicate views over the same registry  -  this one for callers who already
 * think in EvidenceRegistry's own vocabulary, the Query Engine for callers who want one uniform
 * `lookupBy*` naming convention.
 */
export class EvidenceLookupService {
  /** @param {EvidenceRegistry} registry */
  constructor(registry) {
    this._registry = registry;
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence | null>} */
  async getEvidence(evidenceUuid) {
    return this._registry.getEvidence(evidenceUuid);
  }

  /** @param {Record<string, unknown>} criteria @returns {Promise<CanonicalEvidence[]>} */
  async findEvidence(criteria) {
    return this._registry.findEvidence(criteria);
  }

  /** @param {string} cve @returns {Promise<CanonicalEvidence[]>} */
  async findByCVE(cve) {
    return this._registry.findByCVE(cve);
  }

  /** @param {string} actor @returns {Promise<CanonicalEvidence[]>} */
  async findByThreatActor(actor) {
    return this._registry.findByThreatActor(actor);
  }

  /** @param {string} reportId @returns {Promise<CanonicalEvidence[]>} */
  async findByReport(reportId) {
    return this._registry.findByReport(reportId);
  }

  /** @param {string} campaign @returns {Promise<CanonicalEvidence[]>} */
  async findByCampaign(campaign) {
    return this._registry.findByCampaign(campaign);
  }

  /** @param {string} technique @returns {Promise<CanonicalEvidence[]>} */
  async findByAttackTechnique(technique) {
    return this._registry.findByAttackTechnique(technique);
  }

  /** @param {string} ioc @returns {Promise<CanonicalEvidence[]>} */
  async findByIOC(ioc) {
    return this._registry.findByIOC(ioc);
  }

  /** @param {string} sourceId @returns {Promise<CanonicalEvidence[]>} */
  async findBySource(sourceId) {
    return this._registry.findBySource(sourceId);
  }

  /** @param {string} tier @returns {Promise<CanonicalEvidence[]>} */
  async findByConfidenceTier(tier) {
    return this._registry.findByConfidenceTier(tier);
  }
}

/**
 * Wraps EvidenceRegistry's version/lineage read methods. Does not re-expose
 * EvidenceVersionManager's checkSchemaCompatibility()/migrateIfNeeded()  -  those are not part
 * of EvidenceRegistry's public surface (only reachable via its private `_versionManager`), and
 * reaching into that private field to surface them here would itself be exactly the kind of
 * "registry bypass" Phase 7's governance check exists to catch. Left as a documented gap, not a
 * silent one: a future stage that needs schema-compatibility at the service layer should add a
 * public passthrough to EvidenceRegistry itself first (a Stage 11 file change, out of scope
 * here), not reach around it.
 */
export class EvidenceVersionService {
  /** @param {EvidenceRegistry} registry */
  constructor(registry) {
    this._registry = registry;
  }

  /** @param {string} evidenceUuid @param {number} [versionNumber] @returns {Promise<CanonicalEvidence | null>} */
  async resolveVersion(evidenceUuid, versionNumber) {
    return this._registry.resolveVersion(evidenceUuid, versionNumber);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getVersionLineage(evidenceUuid) {
    return this._registry.getVersionLineage(evidenceUuid);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getHistoricalVersions(evidenceUuid) {
    return this._registry.getHistoricalVersions(evidenceUuid);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getSupersededVersions(evidenceUuid) {
    return this._registry.getSupersededVersions(evidenceUuid);
  }
}

/**
 * Wraps EvidenceRegistry's lifecycle state accessors and transition methods. "One Evidence
 * Lifecycle": state still lives in exactly one place (the registry instance's own map,
 * unchanged from Stage 11)  -  this service holds none of its own.
 */
export class EvidenceLifecycleService {
  /** @param {EvidenceRegistry} registry */
  constructor(registry) {
    this._registry = registry;
  }

  /** @param {string} evidenceUuid @returns {string | undefined} */
  getLifecycleState(evidenceUuid) {
    return this._registry.getLifecycleState(evidenceUuid);
  }

  /** @param {string} evidenceUuid @returns {ReadonlyArray<object>} */
  getAuditTrail(evidenceUuid) {
    return this._registry.getAuditTrail(evidenceUuid);
  }

  /**
   * @param {string} evidenceUuid @param {string} toState
   * @param {{reason?: string, actor?: string}} [context]
   */
  async transitionLifecycle(evidenceUuid, toState, context) {
    return this._registry.transitionLifecycle(evidenceUuid, toState, context);
  }
}

/**
 * Wraps evidence validation. `validateEvidence()` delegates to the registry (which itself
 * delegates to validation.js's validateCanonicalEvidence  -  Stage 10)  -  unchanged chain.
 * `validateBatch()` calls validation.js's validateEvidenceBatch() directly rather than through
 * the registry: it is a pure function with no storage dependency (duplicate-identifier /
 * version-conflict checking across an in-memory collection the caller already holds), so
 * routing it through the registry would add an indirection with no registry state involved  -
 * not a bypass, since nothing storage-related is being skipped.
 */
export class EvidenceValidationService {
  /** @param {EvidenceRegistry} registry */
  constructor(registry) {
    this._registry = registry;
  }

  /**
   * @param {CanonicalEvidence} evidence
   * @param {import('./validation.js').StrictValidationOptions} [options]
   */
  validateEvidence(evidence, options) {
    return this._registry.validateEvidence(evidence, options);
  }

  /** @param {CanonicalEvidence[]} entities */
  validateBatch(entities) {
    return validateEvidenceBatch(entities);
  }
}

/**
 * Wraps EvidenceRegistry's own related_* field index (findByRelationship)  -  the "which
 * evidence cites this entity" direction. Distinct from relationship-resolution.js's
 * RelationshipResolutionService (Phase 4), which resolves CanonicalRelationship-shaped graph
 * data from an external relationship framework (P31)  -  a different, cross-cutting concern this
 * service does not touch.
 */
export class EvidenceRelationshipService {
  /** @param {EvidenceRegistry} registry */
  constructor(registry) {
    this._registry = registry;
  }

  /** @param {string} entityId @returns {Promise<CanonicalEvidence[]>} */
  async findByRelationship(entityId) {
    return this._registry.findByRelationship(entityId);
  }
}

/**
 * Composes both registry-level metrics (Stage 11's EvidenceRegistryMetrics, via
 * registry.getMetricsSnapshot()) and service-layer metrics (Stage 12's own
 * ServicePlatformMetrics, Phase 6)  -  "one place to see both" rather than two separately-read
 * snapshots. Does not duplicate either counter set; snapshot() below is a plain merge.
 */
export class EvidenceMetricsService {
  /**
   * @param {EvidenceRegistry} registry
   * @param {ServicePlatformMetrics} [serviceMetrics] - defaults to a fresh instance if the
   *   caller doesn't already have one (e.g. shared with query-engine.js/provenance-engine.js)
   */
  constructor(registry, serviceMetrics) {
    this._registry = registry;
    this._serviceMetrics = serviceMetrics || new ServicePlatformMetrics();
  }

  /** @returns {ServicePlatformMetrics} shared instance, so other Phase 2-4 components can record into it */
  get serviceMetrics() {
    return this._serviceMetrics;
  }

  /** Merged point-in-time snapshot: registry counters + service-layer counters. */
  snapshot() {
    return {
      registry: this._registry.getMetricsSnapshot(),
      service: this._serviceMetrics.snapshot(),
    };
  }
}

/**
 * "One Evidence Service"  -  the single aggregating facade Phase 1 names as this stage's primary
 * deliverable. Composes the six services above plus the one EvidenceRegistry instance they all
 * share, so a consumer needing general evidence access has exactly one thing to import and
 * instantiate. Each sub-service also remains independently importable/testable for a consumer
 * that only needs one slice (e.g. a caller that only ever validates, never looks up).
 */
export class EvidenceService {
  /** @param {{registry?: EvidenceRegistry, serviceMetrics?: ServicePlatformMetrics}} [deps] */
  constructor(deps = {}) {
    this._registry = deps.registry || new EvidenceRegistry();
    const serviceMetrics = deps.serviceMetrics || new ServicePlatformMetrics();

    this.lookup = new EvidenceLookupService(this._registry);
    this.version = new EvidenceVersionService(this._registry);
    this.lifecycle = new EvidenceLifecycleService(this._registry);
    this.validation = new EvidenceValidationService(this._registry);
    this.relationship = new EvidenceRelationshipService(this._registry);
    this.metrics = new EvidenceMetricsService(this._registry, serviceMetrics);
  }

  /** @returns {EvidenceRegistry} the underlying Stage 11 registry, for components (Phase 2-4) that need it directly */
  get registry() {
    return this._registry;
  }

  // ---- Direct passthroughs for the registry's own mutation methods -----------------------
  // Deliberately thin: EvidenceService does not wrap these in its own validation or lifecycle
  // logic (that would duplicate registry-service.js)  -  it delegates verbatim, matching "must
  // wrap Stage 11 Registry functionality... No duplicated logic."

  /**
   * @param {CanonicalEvidence} evidence
   * @param {{initialState?: string, skipReuseCheck?: boolean, validationOptions?: object, actor?: string}} [options]
   */
  async registerEvidence(evidence, options) {
    return this._registry.registerEvidence(evidence, options);
  }

  /**
   * @param {string} evidenceUuid @param {Partial<CanonicalEvidence>} patch
   * @param {{reason?: string, actor?: string, validationOptions?: object}} [context]
   */
  async updateEvidence(evidenceUuid, patch, context) {
    return this._registry.updateEvidence(evidenceUuid, patch, context);
  }

  /**
   * @param {string} evidenceUuid @param {Partial<CanonicalEvidence>} supersedingData
   * @param {{reason?: string, actor?: string, validationOptions?: object}} [context]
   */
  async supersedeEvidence(evidenceUuid, supersedingData, context) {
    return this._registry.supersedeEvidence(evidenceUuid, supersedingData, context);
  }

  /** @param {string} evidenceUuid @param {{reason?: string, actor?: string}} [context] */
  async archiveEvidence(evidenceUuid, context) {
    return this._registry.archiveEvidence(evidenceUuid, context);
  }
}
