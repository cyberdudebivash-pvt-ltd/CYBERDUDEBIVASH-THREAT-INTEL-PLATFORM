/**
 * Evidence repository interface — Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Contract only. Every method throws - this class defines the shape a future,
 * authorized persistence implementation must satisfy; it is not itself a
 * storage backend. No KV/R2/D1 binding is referenced anywhere in this file,
 * intentionally - per Stage 8 Phase 9's "Repository interfaces" (not
 * "Repository implementations") authorization.
 */

const NOT_IMPLEMENTED = "EvidenceRepositoryInterface is a contract, not an implementation. " +
  "Persistence requires its own authorization - see TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md. " +
  "This scaffolding does not authorize any storage backend.";

export class EvidenceRepositoryInterface {
  /**
   * @param {string} evidenceUuid
   * @returns {Promise<import('./entity.js').EvidenceEntity | null>}
   */
  async get(evidenceUuid) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /**
   * @param {import('./entity.js').EvidenceEntity} entity
   * @returns {Promise<import('./entity.js').EvidenceEntity>}
   */
  async put(entity) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /**
   * @param {string} contentHash
   * @returns {Promise<import('./entity.js').EvidenceEntity | null>}
   */
  async findByContentHash(contentHash) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /**
   * @param {string} evidenceUuid
   * @returns {Promise<boolean>}
   */
  async delete(evidenceUuid) {
    throw new Error(NOT_IMPLEMENTED);
  }
}
