/**
 * Enterprise Evidence Registry (EER) service  -  Stage 11 Phases 1, 6, 7 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * The single canonical EvidenceRegistry class ("One Evidence Registry... One Registry API
 * (Internal)"). Composes, rather than reimplements, every lower-level piece this stage and
 * Stage 10 already built:
 *   - InMemoryEvidenceRepository (Phase 2) for storage mechanics
 *   - lifecycle.js (Phase 3) for transition legality  -  this class is the ONE place that tracks
 *     "which state is evidence X currently in" (per-registry-instance state), matching "One
 *     Evidence Lifecycle"
 *   - EvidenceVersionManager (Phase 4) for version/lineage queries
 *   - EvidenceRegistryIndexes (Phase 5) for the named finders
 *   - EvidenceRegistryMetrics (Phase 9) for observability
 *   - validateCanonicalEvidence (Stage 10 Phase 4) for validation
 *   - computeCanonicalEvidenceContentHash (Stage 11 Phase 7 addition to identifiers.js) for
 *     cross-report reuse detection
 *
 * Internal service only  -  every method here is a plain async class method, not an HTTP
 * handler. No route in index.js references this file (enforced by
 * zero-blast-radius.test.js / check_evidence_registry_scaffolding_boundary()).
 */

import { computeCanonicalEvidenceContentHash } from "./identifiers.js";
import { InMemoryEvidenceRepository, computeNextVersion } from "./in-memory-repository.js";
import { EvidenceRegistryIndexes } from "./indexes.js";
import {
  IllegalLifecycleTransitionError,
  assertValidTransition,
  buildTransitionAuditEntry,
  canTransition,
  isValidLifecycleState,
} from "./lifecycle.js";
import { EvidenceRegistryMetrics } from "./registry-metrics.js";
import { validateCanonicalEvidence } from "./validation.js";
import { EvidenceVersionManager } from "./versioning.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export class EvidenceValidationError extends Error {
  constructor(errors) {
    super(`Evidence failed validation: ${errors.join("; ")}`);
    this.name = "EvidenceValidationError";
    this.errors = errors;
  }
}

export class UnregisteredEvidenceError extends Error {
  constructor(evidenceUuid) {
    super(`"${evidenceUuid}" is not registered in this registry (no lifecycle state tracked)`);
    this.name = "UnregisteredEvidenceError";
    this.evidenceUuid = evidenceUuid;
  }
}

export class EvidenceRegistry {
  /**
   * @param {{repository?: object, indexes?: EvidenceRegistryIndexes,
   *   versionManager?: EvidenceVersionManager, metrics?: EvidenceRegistryMetrics}} [deps]
   */
  constructor(deps = {}) {
    this._repository = deps.repository || new InMemoryEvidenceRepository();
    this._indexes = deps.indexes || new EvidenceRegistryIndexes();
    this._versionManager = deps.versionManager || new EvidenceVersionManager(this._repository);
    this._metrics = deps.metrics || new EvidenceRegistryMetrics();
    /** @type {Map<string, string>} evidence_uuid -> current lifecycle state */
    this._lifecycleStates = new Map();
    /** @type {Map<string, object[]>} evidence_uuid -> ordered audit trail */
    this._lifecycleAuditTrail = new Map();
  }

  // ---- Phase 1 "Validate evidence" ------------------------------------------------------

  /**
   * @param {CanonicalEvidence} evidence
   * @param {import('./validation.js').StrictValidationOptions} [options]
   */
  validateEvidence(evidence, options) {
    return validateCanonicalEvidence(evidence, options);
  }

  // ---- Phase 1 "Register evidence" + Phase 6 registerEvidence() + Phase 7 reuse ---------

  /**
   * @param {CanonicalEvidence} evidence
   * @param {{initialState?: string, skipReuseCheck?: boolean, validationOptions?: object,
   *   actor?: string}} [options]
   * @returns {Promise<{evidence: CanonicalEvidence, reused: boolean}>}
   */
  async registerEvidence(evidence, options = {}) {
    const validation = this.validateEvidence(evidence, options.validationOptions);
    if (!validation.valid) {
      this._metrics.recordValidationFailure();
      throw new EvidenceValidationError(validation.errors);
    }
    if (!evidence.evidence_uuid) {
      throw new Error(
        "registerEvidence requires evidence.evidence_uuid  -  generate one via " +
          "identifiers.js's generateEvidenceUuid() before calling this method"
      );
    }

    // Cross-report reuse (Phase 7): "No duplication." A content-hash match against an
    // already-registered CURRENT record means this is the same underlying evidence being cited
    // again (e.g. by a different report)  -  return the existing record rather than creating a
    // duplicate. Uses computeCanonicalEvidenceContentHash (Stage 11), not Stage 8's
    // computeContentHash, specifically because it is stable across fresh audit_metadata
    // timestamps  -  see identifiers.js's docstring.
    let candidate = evidence;
    if (!options.skipReuseCheck) {
      const contentHash = candidate.content_hash || (await computeCanonicalEvidenceContentHash(candidate));
      candidate = { ...candidate, content_hash: contentHash };
      const existing = await this._repository.findByContentHash(contentHash);
      if (existing) {
        return { evidence: existing, reused: true };
      }
    }

    const initialState = options.initialState || "DRAFT";
    if (!isValidLifecycleState(initialState)) {
      throw new Error(`Unknown initial lifecycle state "${initialState}"`);
    }

    const stored = await this._repository.create(candidate);
    this._lifecycleStates.set(stored.evidence_uuid, initialState);
    this._lifecycleAuditTrail.set(stored.evidence_uuid, [
      buildTransitionAuditEntry(null, initialState, { reason: "initial registration", actor: options.actor }),
    ]);
    this._indexes.index(stored);
    this._metrics.recordEvidenceCountDelta(1);
    return { evidence: stored, reused: false };
  }

  // ---- Phase 1 "Retrieve evidence" + Phase 6 getEvidence() -------------------------------

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence | null>} */
  async getEvidence(evidenceUuid) {
    return this._repository.get(evidenceUuid);
  }

  // ---- Phase 6 findEvidence() + named finders (Phase 5 indexing surfaced here) ----------

  /** @param {Record<string, unknown>} criteria @returns {Promise<CanonicalEvidence[]>} */
  async findEvidence(criteria) {
    return this._repository.lookup(criteria);
  }

  async _materialize(evidenceUuids) {
    const found = await Promise.all(evidenceUuids.map((uuid) => this._repository.get(uuid)));
    return found.filter(Boolean);
  }

  /** @param {string} cve @returns {Promise<CanonicalEvidence[]>} */
  async findByCVE(cve) {
    return this._materialize(this._indexes.byCve(cve));
  }

  /** @param {string} actor @returns {Promise<CanonicalEvidence[]>} */
  async findByThreatActor(actor) {
    return this._materialize(this._indexes.byThreatActor(actor));
  }

  /** @param {string} reportId @returns {Promise<CanonicalEvidence[]>} */
  async findByReport(reportId) {
    return this._materialize(this._indexes.byReport(reportId));
  }

  /** @param {string} campaign @returns {Promise<CanonicalEvidence[]>} */
  async findByCampaign(campaign) {
    return this._materialize(this._indexes.byCampaign(campaign));
  }

  /** @param {string} technique @returns {Promise<CanonicalEvidence[]>} */
  async findByAttackTechnique(technique) {
    return this._materialize(this._indexes.byAttackTechnique(technique));
  }

  /** @param {string} ioc @returns {Promise<CanonicalEvidence[]>} */
  async findByIOC(ioc) {
    return this._materialize(this._indexes.byIoc(ioc));
  }

  /** @param {string} sourceId @returns {Promise<CanonicalEvidence[]>} */
  async findBySource(sourceId) {
    return this._materialize(this._indexes.bySource(sourceId));
  }

  /** @param {string} tier @returns {Promise<CanonicalEvidence[]>} */
  async findByConfidenceTier(tier) {
    return this._materialize(this._indexes.byConfidenceTier(tier));
  }

  /**
   * Phase 6 findByRelationship(): union across every related_* dimension for one entity id.
   * @param {string} entityId @returns {Promise<CanonicalEvidence[]>}
   */
  async findByRelationship(entityId) {
    return this._materialize(this._indexes.byRelatedEntity(entityId));
  }

  // ---- lifecycle state accessors ---------------------------------------------------------

  /** @param {string} evidenceUuid @returns {string | undefined} */
  getLifecycleState(evidenceUuid) {
    return this._lifecycleStates.get(evidenceUuid);
  }

  /** @param {string} evidenceUuid @returns {ReadonlyArray<object>} */
  getAuditTrail(evidenceUuid) {
    return this._lifecycleAuditTrail.get(evidenceUuid) || [];
  }

  _requireTrackedState(evidenceUuid) {
    const state = this._lifecycleStates.get(evidenceUuid);
    if (!state) throw new UnregisteredEvidenceError(evidenceUuid);
    return state;
  }

  _recordTransition(evidenceUuid, fromState, toState, context) {
    assertValidTransition(fromState, toState);
    this._lifecycleStates.set(evidenceUuid, toState);
    const trail = this._lifecycleAuditTrail.get(evidenceUuid) || [];
    trail.push(buildTransitionAuditEntry(fromState, toState, context));
    this._lifecycleAuditTrail.set(evidenceUuid, trail);
    this._metrics.recordLifecycleTransition(fromState, toState);
  }

  /**
   * Advances lifecycle state without changing the evidence content itself  -  e.g. DRAFT ->
   * COLLECTED -> VALIDATED -> CORRELATED -> PUBLISHED, the pipeline steps that don't involve an
   * edit. Content-changing transitions go through updateEvidence()/supersedeEvidence() instead,
   * which combine a content change with a state transition in one call. "Every transition must
   * be validated... Illegal transitions must fail"  -  assertValidTransition (inside
   * _recordTransition) throws IllegalLifecycleTransitionError for an illegal one.
   * @param {string} evidenceUuid @param {string} toState
   * @param {{reason?: string, actor?: string}} [context]
   * @returns {Promise<{evidenceUuid: string, fromState: string, toState: string}>}
   */
  async transitionLifecycle(evidenceUuid, toState, context = {}) {
    const fromState = this._requireTrackedState(evidenceUuid);
    this._recordTransition(evidenceUuid, fromState, toState, context);
    return { evidenceUuid, fromState, toState };
  }

  // ---- Phase 1 "Update evidence" ---------------------------------------------------------

  /**
   * @param {string} evidenceUuid @param {Partial<CanonicalEvidence>} patch
   * @param {{reason?: string, actor?: string, validationOptions?: object}} [context]
   * @returns {Promise<CanonicalEvidence>}
   */
  async updateEvidence(evidenceUuid, patch, context = {}) {
    const fromState = this._requireTrackedState(evidenceUuid);
    if (!canTransition(fromState, "UPDATED")) {
      throw new IllegalLifecycleTransitionError(fromState, "UPDATED");
    }

    const current = await this._repository.get(evidenceUuid);
    const prospective = computeNextVersion(current, patch);
    const validation = this.validateEvidence(prospective, context.validationOptions);
    if (!validation.valid) {
      this._metrics.recordValidationFailure();
      throw new EvidenceValidationError(validation.errors);
    }

    const updated = await this._repository.update(evidenceUuid, patch);
    this._indexes.reindex(current, updated);
    this._recordTransition(evidenceUuid, fromState, "UPDATED", context);
    this._metrics.recordVersionUpdate();
    return updated;
  }

  // ---- Phase 1 "Supersede evidence" ------------------------------------------------------

  /**
   * @param {string} evidenceUuid @param {Partial<CanonicalEvidence>} supersedingData
   * @param {{reason?: string, actor?: string, validationOptions?: object}} [context]
   * @returns {Promise<CanonicalEvidence>}
   */
  async supersedeEvidence(evidenceUuid, supersedingData, context = {}) {
    const fromState = this._requireTrackedState(evidenceUuid);
    if (!canTransition(fromState, "SUPERSEDED")) {
      throw new IllegalLifecycleTransitionError(fromState, "SUPERSEDED");
    }

    const current = await this._repository.get(evidenceUuid);
    const prospective = computeNextVersion(current, supersedingData);
    const validation = this.validateEvidence(prospective, context.validationOptions);
    if (!validation.valid) {
      this._metrics.recordValidationFailure();
      throw new EvidenceValidationError(validation.errors);
    }

    const superseded = await this._repository.supersede(evidenceUuid, supersedingData);
    this._indexes.reindex(current, superseded);
    this._recordTransition(evidenceUuid, fromState, "SUPERSEDED", context);
    this._metrics.recordVersionUpdate();
    return superseded;
  }

  // ---- Phase 1 "Archive evidence" + Phase 6 archiveEvidence() ----------------------------

  /**
   * @param {string} evidenceUuid @param {{reason?: string, actor?: string}} [context]
   * @returns {Promise<CanonicalEvidence>}
   */
  async archiveEvidence(evidenceUuid, context = {}) {
    const fromState = this._requireTrackedState(evidenceUuid);
    if (!canTransition(fromState, "ARCHIVED")) {
      throw new IllegalLifecycleTransitionError(fromState, "ARCHIVED");
    }
    const archived = await this._repository.archive(evidenceUuid);
    this._recordTransition(evidenceUuid, fromState, "ARCHIVED", context);
    return archived;
  }

  // ---- Phase 1 "Resolve versions" + Phase 6 resolveVersion() + Phase 4 passthroughs -----

  /**
   * @param {string} evidenceUuid @param {number} [versionNumber] - omit for the current version
   * @returns {Promise<CanonicalEvidence | null>}
   */
  async resolveVersion(evidenceUuid, versionNumber) {
    if (versionNumber === undefined || versionNumber === null) {
      return this._versionManager.getCurrentVersion(evidenceUuid);
    }
    return this._versionManager.resolveVersion(evidenceUuid, versionNumber);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getVersionLineage(evidenceUuid) {
    return this._versionManager.getVersionLineage(evidenceUuid);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getHistoricalVersions(evidenceUuid) {
    return this._versionManager.getHistoricalVersions(evidenceUuid);
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getSupersededVersions(evidenceUuid) {
    return this._versionManager.getSupersededVersions(evidenceUuid);
  }

  // ---- Phase 2 "Bulk import / Bulk export", validated + tracked at this layer ------------

  /**
   * Validates each entity, then delegates storage to the repository's bulkImport(), then
   * tracks lifecycle state + indexes for whatever was genuinely newly created (repository-level
   * duplicates are skipped, matching create()'s semantics, not silently overwritten).
   * @param {CanonicalEvidence[]} entities
   * @param {{initialState?: string, validationOptions?: object}} [options]
   * @returns {Promise<{imported: number, skipped: number, errors: string[]}>}
   */
  async bulkImport(entities, options = {}) {
    const toImport = [];
    const validationErrors = [];
    for (const entity of entities) {
      const validation = this.validateEvidence(entity, options.validationOptions);
      if (validation.valid) {
        toImport.push(entity);
      } else {
        this._metrics.recordValidationFailure();
        validationErrors.push(`${entity?.evidence_uuid || "(unknown)"}: ${validation.errors.join("; ")}`);
      }
    }

    const before = new Set((await this._repository.bulkExport()).map((entity) => entity.evidence_uuid));
    const result = await this._repository.bulkImport(toImport);

    const initialState = options.initialState || "DRAFT";
    for (const entity of toImport) {
      if (before.has(entity.evidence_uuid)) continue; // pre-existing; repository skipped it
      const stored = await this._repository.get(entity.evidence_uuid);
      if (!stored) continue; // also skipped (e.g. missing uuid, caught by the repository itself)
      this._lifecycleStates.set(stored.evidence_uuid, initialState);
      this._lifecycleAuditTrail.set(stored.evidence_uuid, [
        buildTransitionAuditEntry(null, initialState, { reason: "bulk import" }),
      ]);
      this._indexes.index(stored);
      this._metrics.recordEvidenceCountDelta(1);
    }

    return {
      imported: result.imported,
      skipped: result.skipped + validationErrors.length,
      errors: [...validationErrors, ...result.errors],
    };
  }

  /** @returns {Promise<CanonicalEvidence[]>} */
  async bulkExport() {
    return this._repository.bulkExport();
  }

  // ---- Phase 9 observability --------------------------------------------------------------

  /** Point-in-time snapshot of every registry metric. */
  getMetricsSnapshot() {
    return this._metrics.snapshot();
  }

  /**
   * Records that a feature-flag check resolved to an active state. Nothing in this class calls
   * this today (EER_ENABLED does not gate anything inside EvidenceRegistry itself  -  the class
   * always functions when explicitly instantiated, matching CEC_FLAGS's precedent); a future,
   * separately-authorized integration point would call this at the moment it checks
   * resolveEerFlags() and finds EER_ENABLED true, so "feature flag activation" (Phase 9's own
   * tracked metric) has a real counter to increment once that integration exists.
   * @param {string} flagName
   */
  noteFeatureFlagActivation(flagName) {
    this._metrics.recordFeatureFlagActivation(flagName);
  }

  /**
   * Records that a migration adapter was used to produce evidence now being registered. Nothing
   * calls this automatically (adapters are pure functions with no registry awareness, per
   * migration-adapters.js's own zero-coupling design)  -  a caller that adapts legacy data via
   * P20EvidenceChainAdapter/etc. and then registers the result may call this to keep Phase 9's
   * "migration events" / "adapter usage" metrics accurate.
   * @param {string} adapterName
   */
  noteMigrationEvent(adapterName) {
    this._metrics.recordMigrationEvent(adapterName);
  }
}
