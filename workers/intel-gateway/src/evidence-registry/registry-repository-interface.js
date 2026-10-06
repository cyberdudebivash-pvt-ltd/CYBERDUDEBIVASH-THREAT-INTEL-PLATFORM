/**
 * Enterprise Evidence Registry repository interface  -  Stage 11 Phase 2 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Extends Stage 8's EvidenceRepositoryInterface (imported, not duplicated) with the additional
 * operations Stage 11 Phase 2 requires: create, update, supersede, archive, lookup, bulk
 * import/export, and version history. get/put/findByContentHash/delete are inherited exactly as
 * Stage 8 defined them  -  this class does not override or redeclare them.
 *
 * "Repository implementation must remain abstract enough to support future storage backends"  - 
 * this interface stays storage-agnostic (no KV/D1/R2 reference anywhere in this file). A
 * concrete backend only needs to satisfy this contract; see in-memory-repository.js for the
 * reference implementation this stage ships (deliberately not vendor-specific persistence).
 *
 * This class is deliberately storage-mechanics-only. It does not know about lifecycle-transition
 * legality (Draft -> Published rules, etc.)  -  that is lifecycle.js's sole responsibility,
 * invoked by registry-service.js *before* calling into a repository method. Single
 * Responsibility: one authority decides whether a transition is legal (lifecycle.js), one
 * authority persists the result (this contract's implementations).
 */

import { EvidenceRepositoryInterface } from "./repository-interface.js";

const NOT_IMPLEMENTED = (name) =>
  `${name} is a contract, not a default implementation for this method  -  provide a concrete ` +
  "override. See README.md.";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export class EvidenceRegistryRepositoryInterface extends EvidenceRepositoryInterface {
  /**
   * Stores a genuinely new evidence record. Must reject (throw) if `entity.evidence_uuid`
   * already exists  -  unlike `put()` (inherited, upsert semantics), `create()` never silently
   * overwrites, so the registry service layer can rely on it to catch a real
   * duplicate-registration bug rather than masking one.
   * @param {CanonicalEvidence} entity
   * @returns {Promise<CanonicalEvidence>}
   */
  async create(entity) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.create"));
  }

  /**
   * Applies `patch` on top of the current version, storing the result as a NEW version (current
   * version moves into history). Must reject if `evidenceUuid` does not exist.
   * @param {string} evidenceUuid
   * @param {Partial<CanonicalEvidence>} patch
   * @returns {Promise<CanonicalEvidence>}
   */
  async update(evidenceUuid, patch) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.update"));
  }

  /**
   * Marks the current version at `evidenceUuid` as superseded (moved into history with a
   * `superseded_at` timestamp) and installs `supersedingData` as the new current version.
   * @param {string} evidenceUuid
   * @param {Partial<CanonicalEvidence>} supersedingData
   * @returns {Promise<CanonicalEvidence>}
   */
  async supersede(evidenceUuid, supersedingData) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.supersede"));
  }

  /**
   * Marks the record as archived. Archived evidence remains retrievable and indexed (archival
   * is a lifecycle state, not a deletion)  -  this method only flips the storage-level marker;
   * lifecycle legality of the Archived transition is checked by the caller via lifecycle.js.
   * @param {string} evidenceUuid
   * @returns {Promise<CanonicalEvidence>}
   */
  async archive(evidenceUuid) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.archive"));
  }

  /**
   * Multi-field lookup across current (non-historical) versions. `criteria` is a plain object
   * of field -> expected-value pairs (e.g. `{evidence_id: "EC-1"}`); an implementation may
   * support richer matching, but exact-match-on-provided-fields is the minimum contract.
   * @param {Record<string, unknown>} criteria
   * @returns {Promise<CanonicalEvidence[]>}
   */
  async lookup(criteria) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.lookup"));
  }

  /**
   * @param {CanonicalEvidence[]} entities
   * @returns {Promise<{imported: number, skipped: number, errors: string[]}>}
   */
  async bulkImport(entities) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.bulkImport"));
  }

  /**
   * @returns {Promise<CanonicalEvidence[]>} every CURRENT (non-historical) record
   */
  async bulkExport() {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.bulkExport"));
  }

  /**
   * Full, immutable version lineage for one evidence identity, oldest first, including the
   * current version as the last entry.
   * @param {string} evidenceUuid
   * @returns {Promise<CanonicalEvidence[]>}
   */
  async getVersionHistory(evidenceUuid) {
    throw new Error(NOT_IMPLEMENTED("EvidenceRegistryRepositoryInterface.getVersionHistory"));
  }
}
