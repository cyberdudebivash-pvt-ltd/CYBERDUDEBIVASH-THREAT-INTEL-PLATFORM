/**
 * P31 Relationship Provider -- Stage 16 Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * The concrete RelationshipProviderInterface implementation Stage 12's relationship-resolution.js
 * module docstring named as future, separately-authorized wiring: "a concrete provider (e.g. one
 * backed by p31-handlers.js's buildP31RelationshipBlock()) requires ADR-0010 Acceptance first...
 * and is out of this stage's scope." ADR-0010 is now Accepted (Stage 16) -- this class is that
 * wiring. It composes (does not re-implement):
 *   - Stage 16's own edge-repository-interface.js / in-memory-edge-repository.js (persistence,
 *     satisfying ADR-0010 Decision item 2 via Revision 5's native-persistence path)
 *   - Stage 16's own p31-edge-adapter.js (documented-shape conversion, no p31-handlers.js import)
 *   - Stage 12's RelationshipProviderInterface contract (implements it, does not redefine it)
 *
 * Still does not import p31-handlers.js. Getting real edges INTO the repository this class reads
 * from is a separate, explicit step (`ingestEdges()` below, or seeding the repository directly)
 * -- performed by whoever composes this at a point where a live P31 edge array is actually
 * available (e.g. a Worker request handler with a real `env`, or a snapshot script, mirroring
 * exactly how scripts/enterprise_gateway_snapshot.mjs composes the dormant service platform
 * today). This class's own test suite uses fixture edges, matching every sibling directory's
 * "not imported by index.js, tested via node --test" convention.
 */

import { RelationshipProviderInterface } from "../evidence-registry/relationship-resolution.js";
import { adaptEdgeToProviderShape } from "./p31-edge-adapter.js";

/** @typedef {import('./edge-repository-interface.js').RelationshipEdgeRepositoryInterface} RelationshipEdgeRepositoryInterface */

export class P31RelationshipProvider extends RelationshipProviderInterface {
  /** @param {{repository: RelationshipEdgeRepositoryInterface}} deps */
  constructor(deps = {}) {
    super();
    if (!deps.repository) {
      throw new Error("P31RelationshipProvider requires a `repository` (RelationshipEdgeRepositoryInterface) dependency");
    }
    this._repository = deps.repository;
  }

  /**
   * Ingests already-fetched, already-adapted edges into this provider's repository. Named
   * distinctly from the repository's own putMany() (which this delegates to unchanged) so
   * callers have one obvious entry point on the provider itself. Does not fetch anything itself
   * -- no env, no HTTP, no p31-handlers.js call.
   * @param {import('./edge-repository-interface.js').RelationshipEdge[]} edges
   */
  async ingestEdges(edges) {
    return this._repository.putMany(edges);
  }

  /**
   * @param {string} entityId
   * @returns {Promise<Array<{relatedEntityId: string, relationshipType: string, confidence: number}>>}
   */
  async getRelationshipsFor(entityId) {
    const edges = await this._repository.getForEntity(entityId);
    return edges.map((edge) => adaptEdgeToProviderShape(edge, entityId));
  }
}
