/**
 * In-memory Evidence Registry repository  -  Stage 11 Phase 2 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Reference implementation of EvidenceRegistryRepositoryInterface, backed by plain in-process
 * Maps  -  deliberately NOT a KV/D1/R2-backed implementation ("Repository implementation must
 * remain abstract enough to support future storage backends" + Implementation Constraints:
 * "Do NOT introduce vendor-specific persistence"). A future, separately-authorized storage
 * backend only needs to satisfy the same interface; nothing above this class needs to change.
 *
 * Storage-mechanics-only: this class does not judge whether a lifecycle transition is legal
 * (that is lifecycle.js's job, invoked one layer up in registry-service.js). It only implements
 * the mechanical effect of create/update/supersede/archive on the underlying maps.
 */

import { deepFreeze } from "./entity.js";
import { EvidenceRegistryRepositoryInterface } from "./registry-repository-interface.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export class EvidenceNotFoundError extends Error {
  constructor(evidenceUuid) {
    super(`No evidence found for evidence_uuid "${evidenceUuid}"`);
    this.name = "EvidenceNotFoundError";
    this.evidenceUuid = evidenceUuid;
  }
}

export class DuplicateEvidenceError extends Error {
  constructor(evidenceUuid) {
    super(`Evidence with evidence_uuid "${evidenceUuid}" already exists  -  use update() or supersede(), not create()`);
    this.name = "DuplicateEvidenceError";
    this.evidenceUuid = evidenceUuid;
  }
}

function nextVersion(current) {
  const currentVersion = typeof current.version === "number" ? current.version : 1;
  return currentVersion + 1;
}

/**
 * Pure preview of what update()/supersede() would store: the merged record, with a bumped
 * version and refreshed audit_metadata, WITHOUT mutating any repository state. Exported so a
 * caller (registry-service.js's updateEvidence()) can validate the prospective result BEFORE
 * committing it  -  this repository has no transactional rollback, so validating first is how
 * "never persist invalid data" is satisfied, without duplicating this merge shape a second time
 * at the call site (Reuse Before Build).
 * @param {CanonicalEvidence} current @param {Partial<CanonicalEvidence>} patch
 * @param {string} [timestamp] - ISO-8601; defaults to now. Accepted explicitly (rather than
 *   always calling `new Date()` internally) so supersede() can stamp the new current version's
 *   `updated_at` with the exact same instant as the outgoing version's `superseded_at`.
 * @returns {CanonicalEvidence}
 */
export function computeNextVersion(current, patch, timestamp) {
  return {
    ...current,
    ...patch,
    evidence_uuid: current.evidence_uuid, // identity is not patchable
    version: nextVersion(current),
    audit_metadata: {
      ...current.audit_metadata,
      ...(patch.audit_metadata || {}),
      updated_at: timestamp || new Date().toISOString(),
    },
  };
}

export class InMemoryEvidenceRepository extends EvidenceRegistryRepositoryInterface {
  constructor() {
    super();
    /** @type {Map<string, CanonicalEvidence>} uuid -> current version */
    this._current = new Map();
    /** @type {Map<string, CanonicalEvidence[]>} uuid -> prior versions, oldest first */
    this._history = new Map();
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence | null>} */
  async get(evidenceUuid) {
    return this._current.get(evidenceUuid) || null;
  }

  /**
   * Stage 8's original upsert contract: create-or-replace the CURRENT record only, with no
   * version-history side effect. This is deliberately simpler than create()/update()  -  it is
   * the pre-Stage-11 contract, preserved exactly so a hypothetical existing caller of `put()`
   * (there are none in production today) would see unchanged behavior.
   * @param {CanonicalEvidence} entity @returns {Promise<CanonicalEvidence>}
   */
  async put(entity) {
    if (!this._history.has(entity.evidence_uuid)) {
      this._history.set(entity.evidence_uuid, []);
    }
    this._current.set(entity.evidence_uuid, entity);
    return entity;
  }

  /** @param {string} contentHash @returns {Promise<CanonicalEvidence | null>} */
  async findByContentHash(contentHash) {
    for (const entity of this._current.values()) {
      if (entity.content_hash === contentHash) return entity;
    }
    return null;
  }

  /**
   * Hard delete  -  removes the identity entirely, including its history. Stage 8's original
   * interface method, kept for interface completeness; the Registry Service (Phase 1) never
   * calls this in its normal operation flow  -  Archive is Stage 11's intended "soft delete."
   * @param {string} evidenceUuid @returns {Promise<boolean>}
   */
  async delete(evidenceUuid) {
    const existed = this._current.delete(evidenceUuid);
    this._history.delete(evidenceUuid);
    return existed;
  }

  /** @param {CanonicalEvidence} entity @returns {Promise<CanonicalEvidence>} */
  async create(entity) {
    if (this._current.has(entity.evidence_uuid)) {
      throw new DuplicateEvidenceError(entity.evidence_uuid);
    }
    this._current.set(entity.evidence_uuid, entity);
    this._history.set(entity.evidence_uuid, []);
    return entity;
  }

  /**
   * @param {string} evidenceUuid
   * @param {Partial<CanonicalEvidence>} patch
   * @returns {Promise<CanonicalEvidence>}
   */
  async update(evidenceUuid, patch) {
    const current = this._current.get(evidenceUuid);
    if (!current) throw new EvidenceNotFoundError(evidenceUuid);

    this._history.get(evidenceUuid).push(deepFreeze({ ...current }));
    const updated = computeNextVersion(current, patch);
    this._current.set(evidenceUuid, updated);
    return updated;
  }

  /**
   * @param {string} evidenceUuid
   * @param {Partial<CanonicalEvidence>} supersedingData
   * @returns {Promise<CanonicalEvidence>}
   */
  async supersede(evidenceUuid, supersedingData) {
    const current = this._current.get(evidenceUuid);
    if (!current) throw new EvidenceNotFoundError(evidenceUuid);

    const supersededAt = new Date().toISOString();
    this._history.get(evidenceUuid).push(deepFreeze({ ...current, superseded_at: supersededAt }));
    const superseding = computeNextVersion(current, supersedingData, supersededAt);
    this._current.set(evidenceUuid, superseding);
    return superseding;
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence>} */
  async archive(evidenceUuid) {
    const current = this._current.get(evidenceUuid);
    if (!current) throw new EvidenceNotFoundError(evidenceUuid);
    const archived = {
      ...current,
      audit_metadata: { ...current.audit_metadata, updated_at: new Date().toISOString() },
    };
    this._current.set(evidenceUuid, archived);
    return archived;
  }

  /**
   * Exact-match lookup across current records on every provided criteria field. A reference
   * implementation's linear scan is acceptable here (Phase 5's real indexing lives in
   * indexes.js, used by registry-service.js for the named finders); this method exists so the
   * interface contract is independently satisfiable without the indexing layer.
   * @param {Record<string, unknown>} criteria @returns {Promise<CanonicalEvidence[]>}
   */
  async lookup(criteria) {
    const entries = Object.entries(criteria || {});
    return [...this._current.values()].filter((entity) =>
      entries.every(([key, value]) => entity[key] === value)
    );
  }

  /**
   * @param {CanonicalEvidence[]} entities
   * @returns {Promise<{imported: number, skipped: number, errors: string[]}>}
   */
  async bulkImport(entities) {
    let imported = 0;
    let skipped = 0;
    const errors = [];
    for (const entity of entities) {
      if (!entity || !entity.evidence_uuid) {
        skipped += 1;
        errors.push("entity missing evidence_uuid  -  skipped");
        continue;
      }
      if (this._current.has(entity.evidence_uuid)) {
        skipped += 1;
        errors.push(`${entity.evidence_uuid} already exists  -  skipped (use update()/supersede() for existing records)`);
        continue;
      }
      this._current.set(entity.evidence_uuid, entity);
      this._history.set(entity.evidence_uuid, []);
      imported += 1;
    }
    return { imported, skipped, errors };
  }

  /** @returns {Promise<CanonicalEvidence[]>} */
  async bulkExport() {
    return [...this._current.values()];
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>} */
  async getVersionHistory(evidenceUuid) {
    const history = this._history.get(evidenceUuid) || [];
    const current = this._current.get(evidenceUuid);
    return current ? [...history, current] : [...history];
  }
}
