/**
 * Evidence Version Manager  -  Stage 11 Phase 4 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Composes a repository's version-history storage (Phase 2) with schema.js's existing
 * compatibility functions (Stage 10 Phase 2)  -  Reuse Before Build: this module does not
 * redefine what "compatible" means, it only applies that existing definition to a specific
 * evidence record's schema_version against the current CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION.
 *
 * "Version lineage must be immutable" is enforced one layer down, at the repository  -  every
 * non-current entry a repository returns from getVersionHistory() is already deep-frozen
 * (in-memory-repository.js). This class does not re-freeze anything; it only reads.
 */

import { CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION } from "./entity.js";
import { isBackwardCompatible, isForwardCompatible } from "./schema.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export class EvidenceVersionManager {
  /** @param {import('./registry-repository-interface.js').EvidenceRegistryRepositoryInterface} repository */
  constructor(repository) {
    this._repository = repository;
  }

  /** @param {string} evidenceUuid @returns {Promise<CanonicalEvidence | null>} */
  async getCurrentVersion(evidenceUuid) {
    return this._repository.get(evidenceUuid);
  }

  /**
   * Full, immutable lineage, oldest first, current version last.
   * @param {string} evidenceUuid @returns {Promise<CanonicalEvidence[]>}
   */
  async getVersionLineage(evidenceUuid) {
    return this._repository.getVersionHistory(evidenceUuid);
  }

  /** Every non-current (historical) version. @param {string} evidenceUuid */
  async getHistoricalVersions(evidenceUuid) {
    const lineage = await this.getVersionLineage(evidenceUuid);
    return lineage.slice(0, -1);
  }

  /** Historical versions explicitly marked superseded_at. @param {string} evidenceUuid */
  async getSupersededVersions(evidenceUuid) {
    const historical = await this.getHistoricalVersions(evidenceUuid);
    return historical.filter((version) => Boolean(version.superseded_at));
  }

  /**
   * Resolves a specific version number from an evidence identity's lineage, or null if that
   * version number was never recorded.
   * @param {string} evidenceUuid @param {number} versionNumber
   * @returns {Promise<CanonicalEvidence | null>}
   */
  async resolveVersion(evidenceUuid, versionNumber) {
    const lineage = await this.getVersionLineage(evidenceUuid);
    return lineage.find((version) => version.version === versionNumber) || null;
  }

  /**
   * Checks whether `evidence.schema_version` is compatible with the schema this running code
   * understands (CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION), via schema.js's existing
   * SCHEMA_VERSION_HISTORY walk  -  does not reimplement that walk.
   * @param {CanonicalEvidence} evidence
   */
  checkSchemaCompatibility(evidence) {
    const recordSchemaVersion = evidence.schema_version;
    return {
      recordSchemaVersion,
      currentSchemaVersion: CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION,
      isForwardCompatible: isForwardCompatible(recordSchemaVersion, CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION),
      isBackwardCompatible: isBackwardCompatible(CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION, recordSchemaVersion),
    };
  }

  /**
   * Migration support: returns the evidence unchanged when its schema_version is already
   * forward-compatible with the current schema (true for every version recorded in
   * SCHEMA_VERSION_HISTORY today, since every step so far has been additive-only). Throws a
   * clearly-labelled error rather than guessing at a transformation if a truly incompatible,
   * non-additive schema version is ever encountered  -  schema.js's own docstring already
   * anticipates this as "a future *non*-additive version bump," not something this stage
   * invents a speculative migration for.
   * @param {CanonicalEvidence} evidence
   * @returns {CanonicalEvidence}
   */
  migrateIfNeeded(evidence) {
    const compatibility = this.checkSchemaCompatibility(evidence);
    if (compatibility.isForwardCompatible) {
      return evidence;
    }
    throw new Error(
      `Evidence ${evidence.evidence_uuid || "(no uuid)"} has schema_version ` +
        `"${compatibility.recordSchemaVersion}", which is not forward-compatible with the ` +
        `current schema "${compatibility.currentSchemaVersion}" per schema.js's ` +
        "SCHEMA_VERSION_HISTORY. This requires a real, reviewed migration adapter, not an " +
        "automatic transformation  -  see TITAN_STAGE10_EVIDENCE_MIGRATION_GUIDE.md."
    );
  }
}
