/**
 * Enterprise Evidence Service Platform  -  Stage 12 Phase 4, Relationship Resolution
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * ORIGINALLY scoped narrower than Phase 4's full brief, because ADR-0010 (Relationship Graph
 * Ownership) was Proposed, not Accepted, at Stage 12 time. **ADR-0010 is now Accepted (Stage 16,
 * 2026-08-06 -- see docs/adr/0010-relationship-graph-ownership.md Revision 5,
 * TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md's Stage 16 Addendum).** This file itself is
 * UNCHANGED beyond this docstring and the NOT_WIRED message below: the concrete wiring lives in
 * `relationship-framework/` (Stage 16), which constructs a real `RelationshipResolutionService`
 * by injecting its own `P31RelationshipProvider` here -- see relationship-framework/relationship-service.js.
 *
 * This class stays a pure, provider-agnostic contract by design, independent of ADR-0010's
 * status, for a reason ADR-0010 acceptance does not remove: the architectural boundary
 * (`zero-blast-radius.test.js`/`check_evidence_registry_scaffolding_boundary()`) still requires
 * that nothing in THIS directory import a live handler/router file directly. Concrete wiring
 * happens by injecting a provider at a composition root (relationship-framework/, or any future
 * caller), never by adding a `p31-handlers.js` import to this file. `RelationshipProviderInterface`
 * below remains the same dependency-injection point Stage 10's `EvidenceProviderInterface`
 * pattern established. `NullRelationshipProvider` (still the default for a zero-arg
 * construction) makes "no provider was injected into THIS instance" explicit rather than
 * silently returning empty data as if it were a real answer -- that default is good DI practice
 * independent of ADR-0010, so it is unchanged.
 */

import { ServicePlatformMetrics } from "./service-metrics.js";

const NOT_WIRED = (name) =>
  `${name}: no RelationshipProviderInterface has been supplied. This class stays provider- ` +
  "agnostic by design (dependency injection, not a hardcoded data source) -- inject a concrete " +
  "provider at composition time (e.g. relationship-framework/'s P31RelationshipProvider, Stage " +
  "16, now that ADR-0010 is Accepted) to get real data. See relationship-resolution.js's " +
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
