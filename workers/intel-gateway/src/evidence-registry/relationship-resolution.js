/**
 * Enterprise Evidence Service Platform  -  Stage 12 Phase 4, Relationship Resolution
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * DELIBERATELY SCOPED NARROWER than Phase 4's full brief. The stage brief asks this phase to
 * "Consume: Canonical Relationship Framework" (p31-handlers.js / ADR-0010's subject). ADR-0010
 * (Relationship Graph Ownership) is NOT part of this stage's Acceptance  -  it remains Proposed
 * (see docs/adr/0010-relationship-graph-ownership.md, TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md).
 * Only ADR-0008, ADR-0011, and ADR-0012 were Accepted for this stage.
 *
 * Two established constraints both point the same direction:
 *   1. Governance: this program has never treated an "internal only, so it's fine" reading as
 *      sufficient to bypass an ADR gate  -  DEBT-021 exists specifically because Stage 10-11 did
 *      exactly that for ADR-0008/0011, and this stage's own Executive Architecture Acceptance
 *      milestone (Stage 11.5) was inserted to stop that pattern, not extend it to a fourth ADR.
 *   2. Architecture: `zero-blast-radius.test.js`/`check_evidence_registry_scaffolding_boundary()`
 *      enforce that nothing in this directory imports a live handler/router file. Importing
 *      `buildP31RelationshipBlock` from `p31-handlers.js` directly would violate that boundary
 *      regardless of ADR-0010's status  -  it would give this "inert scaffolding" a real
 *      production import for the first time since Stage 8.
 *
 * So: this class defines the CONSUMPTION CONTRACT ("Consume... No new graph engine. No graph
 * rewrite.") without a concrete P31 import. `RelationshipProviderInterface` below is a
 * dependency-injection point, exactly mirroring interfaces.js's `EvidenceProviderInterface`
 * pattern (Stage 10)  -  a contract whose concrete, live-data-backed implementation is future,
 * separately-authorized wiring (requires both ADR-0010 Acceptance AND resolving DEBT-000B's
 * R1-vs-R6 ownership question), not something this stage builds. `NullRelationshipProvider`
 * (the default) makes that explicit rather than silently returning empty data as if it were a
 * real answer.
 */

import { ServicePlatformMetrics } from "./service-metrics.js";

const NOT_WIRED = (name) =>
  `${name}: no RelationshipProviderInterface has been supplied. Relationship Resolution is ` +
  "scoped this stage to a consumption contract only  -  wiring a concrete provider (e.g. one " +
  "backed by p31-handlers.js's buildP31RelationshipBlock()) requires ADR-0010 Acceptance first " +
  "(currently Proposed) and is out of this stage's scope. See relationship-resolution.js's " +
  "module docstring.";

/**
 * Contract only. A concrete implementation adapts whatever the eventually-canonical relationship
 * framework exposes (P31 today; ADR-0010 has not yet decided the long-term target) into this
 * shape. Mirrors EvidenceProviderInterface (interfaces.js, Stage 10) exactly, for consistency.
 */
export class RelationshipProviderInterface {
  /**
   * @param {string} entityId
   * @returns {Promise<Array<{relatedEntityId: string, relationshipType: string, confidence?: number}>>}
   */
  async getRelationshipsFor(entityId) {
    throw new Error(NOT_WIRED("RelationshipProviderInterface.getRelationshipsFor"));
  }
}

/**
 * Explicit "not wired" default, not a silent empty-array stand-in  -  callers that haven't
 * injected a real provider get a clearly-labelled error, not a confidently-empty result that
 * could be mistaken for "this entity genuinely has no relationships."
 */
export class NullRelationshipProvider extends RelationshipProviderInterface {
  async getRelationshipsFor(entityId) {
    throw new Error(NOT_WIRED("NullRelationshipProvider.getRelationshipsFor"));
  }
}

export class RelationshipResolutionService {
  /**
   * @param {{provider?: RelationshipProviderInterface, metrics?: ServicePlatformMetrics}} [deps]
   */
  constructor(deps = {}) {
    this._provider = deps.provider || new NullRelationshipProvider();
    this._metrics = deps.metrics || new ServicePlatformMetrics();
  }

  /**
   * @param {string} entityId
   * @returns {Promise<Array<{relatedEntityId: string, relationshipType: string, confidence?: number}>>}
   */
  async resolveRelationships(entityId) {
    try {
      const result = await this._provider.getRelationshipsFor(entityId);
      this._metrics.recordRelationshipResolution(true);
      return result;
    } catch (error) {
      this._metrics.recordRelationshipResolution(false);
      throw error;
    }
  }

  /** @returns {boolean} true once a real (non-Null) provider has been injected */
  isWired() {
    return !(this._provider instanceof NullRelationshipProvider);
  }
}
