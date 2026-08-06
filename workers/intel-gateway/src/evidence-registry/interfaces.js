/**
 * Canonical Evidence Core interfaces  -  Stage 10 Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Contracts for EvidenceValidator, EvidenceProvider, EvidenceSerializer, EvidenceImporter,
 * EvidenceExporter, EvidenceMigrationAdapter  -  mirrors repository-interface.js's existing
 * EvidenceRepositoryInterface pattern exactly (abstract class, NOT_IMPLEMENTED methods) for
 * consistency. EvidenceRepositoryInterface itself is NOT redefined here  -  it already exists
 * in repository-interface.js and is imported, not duplicated, per Single Source of Truth.
 *
 * Per Phase 3's own instruction ("Only contracts and default adapters"), the interfaces that
 * do not require persistence (Validator, Serializer, Importer, Exporter, MigrationAdapter) get
 * a working default implementation alongside their contract  -  only Provider (which composes
 * EvidenceRepositoryInterface) and Repository itself stay pure contracts, since storage is
 * explicitly out of scope this stage.
 */

import { validateCanonicalEvidence, validateEvidenceBatch } from "./validation.js";

const NOT_IMPLEMENTED = (name) =>
  `${name} is a contract, not a default implementation for this method  -  provide a concrete ` +
  "override. See README.md.";

/**
 * @typedef {import('./validation.js').StrictValidationOptions} StrictValidationOptions
 * @typedef {import('./validation.js').StrictValidationResult} StrictValidationResult
 */

/**
 * Contract + default (working) implementation. The default delegates entirely to
 * validation.js's pure functions (Reuse Before Build)  -  it does not reimplement any check.
 */
export class EvidenceValidatorInterface {
  /**
   * @param {import('./entity.js').CanonicalEvidence} entity
   * @param {StrictValidationOptions} [options]
   * @returns {StrictValidationResult}
   */
  validate(entity, options = {}) {
    return validateCanonicalEvidence(entity, options);
  }

  /**
   * @param {import('./entity.js').CanonicalEvidence[]} entities
   * @returns {StrictValidationResult}
   */
  validateBatch(entities) {
    return validateEvidenceBatch(entities);
  }
}

/**
 * Contract only  -  composes an injected EvidenceRepositoryInterface, so calling any method
 * before a real repository implementation exists throws that interface's own
 * NOT_IMPLEMENTED error, not a duplicate one. This is intentional: Provider does not define
 * its own storage-access error message, it inherits Repository's, so there is exactly one
 * "storage isn't authorized yet" message in this codebase, not two.
 */
export class EvidenceProviderInterface {
  /**
   * @param {import('./repository-interface.js').EvidenceRepositoryInterface} repository
   */
  constructor(repository) {
    this.repository = repository;
  }

  /**
   * @param {string} evidenceUuid
   * @returns {Promise<import('./entity.js').CanonicalEvidence | null>}
   */
  async getByUuid(evidenceUuid) {
    return this.repository.get(evidenceUuid);
  }

  /**
   * @param {string} entityId
   * @returns {Promise<import('./entity.js').CanonicalEvidence[]>}
   */
  async getByRelatedEntity(entityId) {
    throw new Error(NOT_IMPLEMENTED("EvidenceProviderInterface.getByRelatedEntity"));
  }
}

/**
 * Contract only here  -  the working default implementations (JSON/Markdown/DTO) live in
 * serialization.js (Phase 5), which extends this class rather than duplicating its shape.
 */
export class EvidenceSerializerInterface {
  /**
   * @param {import('./entity.js').CanonicalEvidence} entity
   * @returns {string}
   */
  serialize(entity) {
    throw new Error(NOT_IMPLEMENTED("EvidenceSerializerInterface.serialize"));
  }

  /**
   * @param {string} payload
   * @returns {import('./entity.js').CanonicalEvidence}
   */
  deserialize(payload) {
    throw new Error(NOT_IMPLEMENTED("EvidenceSerializerInterface.deserialize"));
  }
}

/**
 * Contract only  -  default implementation in serialization.js, composing an
 * EvidenceSerializerInterface and an EvidenceValidatorInterface rather than reimplementing
 * either (Reuse Before Build: importing is deserialize-then-validate, not new logic).
 */
export class EvidenceImporterInterface {
  /**
   * @param {string} payload
   * @param {{sourceTrust?: number}} [opts]
   * @returns {Promise<{imported: import('./entity.js').CanonicalEvidence, warnings: string[]}>}
   */
  async import(payload, opts = {}) {
    throw new Error(NOT_IMPLEMENTED("EvidenceImporterInterface.import"));
  }
}

/**
 * Contract only  -  default implementation in serialization.js, composing an
 * EvidenceSerializerInterface.
 */
export class EvidenceExporterInterface {
  /**
   * @param {import('./entity.js').CanonicalEvidence[]} entities
   * @param {"json"|"markdown"} format
   * @returns {Promise<string>}
   */
  async export(entities, format) {
    throw new Error(NOT_IMPLEMENTED("EvidenceExporterInterface.export"));
  }
}

/**
 * Contract only  -  default, concrete adapters (P20 evidence_chain, CanonicalRelationship,
 * P25 confidence object) live in migration-adapters.js (Phase 7), each extending this class.
 */
export class EvidenceMigrationAdapterInterface {
  /**
   * @param {unknown} legacyShape
   * @returns {import('./entity.js').CanonicalEvidence}
   */
  adapt(legacyShape) {
    throw new Error(NOT_IMPLEMENTED("EvidenceMigrationAdapterInterface.adapt"));
  }

  /** @returns {string} A short, stable name identifying which legacy shape this adapts. */
  sourceShapeName() {
    throw new Error(NOT_IMPLEMENTED("EvidenceMigrationAdapterInterface.sourceShapeName"));
  }
}
