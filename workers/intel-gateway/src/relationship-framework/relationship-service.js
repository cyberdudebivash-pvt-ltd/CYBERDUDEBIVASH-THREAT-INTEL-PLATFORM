/**
 * Relationship Service -- Stage 16 Phase 1 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * "One Relationship Service" -- the single aggregating facade Phase 1 names as this stage's
 * primary deliverable, mirroring Stage 12's EvidenceService, Stage 13's IntelligenceService, and
 * Stage 14's EnterpriseGateway pattern one layer up each time. Composes:
 *   - relationship-registry.js's RelationshipRegistry (Phase 2)
 *   - edge-repository / p31-edge-adapter / relationship-provider (Phase 3 -- persistence + the
 *     concrete P31RelationshipProvider, resolving ADR-0010 Decision item 2 per Revision 5)
 *   - Stage 12's RelationshipResolutionService, constructed HERE with the real provider (this is
 *     the actual "wiring" Stage 12's own docstring deferred as future, separately-authorized work
 *     -- ADR-0010 is now Accepted, this is that authorization exercised)
 *   - relationship-traversal.js's RelationshipTraversalService (Phase 1 + 3)
 *   - relationship-validation.js's RelationshipValidationService (Phase 1 + 3 + 8)
 *   - relationship-metrics.js's RelationshipMetricsService (Phase 1 + 7)
 *   - relationship-lookup.js's RelationshipLookupService (Phase 1)
 *
 * Constructing a RelationshipService does NOT change Stage 12/13's own default (zero-arg)
 * construction behavior anywhere -- intelligence-service.js's `IntelligenceService` constructor
 * still defaults `relationshipResolution` to an unwired NullRelationshipProvider-backed instance
 * unless a caller explicitly injects `relationshipService.resolution` (this class's own
 * `resolution` getter) in its place. That injection is Phase 4/5's own composition step
 * (correlation wiring, Gateway integration), demonstrated in this stage's integration test and
 * documented in TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md, not hardcoded as a new default
 * -- changing IntelligenceService's default would be an unrequested, unjustified modification to
 * a file Stage 16 has no defect-based reason to touch.
 */

import { RelationshipResolutionService } from "../evidence-registry/relationship-resolution.js";
import { RelationshipRegistry } from "./relationship-registry.js";
import { InMemoryRelationshipEdgeRepository } from "./in-memory-edge-repository.js";
import { P31RelationshipProvider } from "./relationship-provider.js";
import { RelationshipTraversalService } from "./relationship-traversal.js";
import { RelationshipValidationService } from "./relationship-validation.js";
import { RelationshipMetricsService } from "./relationship-metrics.js";
import { RelationshipLookupService } from "./relationship-lookup.js";

/** @typedef {import('./edge-repository-interface.js').RelationshipEdgeRepositoryInterface} RelationshipEdgeRepositoryInterface */
/** @typedef {import('./edge-repository-interface.js').RelationshipEdge} RelationshipEdge */

export class RelationshipService {
  /**
   * @param {{repository?: RelationshipEdgeRepositoryInterface, registry?: RelationshipRegistry,
   *   metrics?: RelationshipMetricsService}} [deps]
   */
  constructor(deps = {}) {
    this.registry = deps.registry || new RelationshipRegistry();
    this.metrics = deps.metrics || new RelationshipMetricsService();
    this._repository = deps.repository || new InMemoryRelationshipEdgeRepository();

    this._provider = new P31RelationshipProvider({ repository: this._repository });
    // The real wiring: Stage 12's consumption contract, now backed by a concrete provider
    // instead of the NullRelationshipProvider default. Stage 12's own class, its own metrics
    // counter, its own isWired() method -- none of it re-implemented here.
    this.resolution = new RelationshipResolutionService({ provider: this._provider });

    this.lookup = new RelationshipLookupService({ resolution: this.resolution, registry: this.registry });
    this.traversal = new RelationshipTraversalService({ repository: this._repository, metrics: this.metrics });
    this.validation = new RelationshipValidationService({ registry: this.registry, metrics: this.metrics });
  }

  /**
   * Validates then persists a batch of already-adapted edges (see p31-edge-adapter.js for
   * converting raw P31 output into this shape first). Invalid edges are reported, not silently
   * dropped or silently stored -- callers decide whether to proceed with the valid subset.
   * @param {RelationshipEdge[]} edges
   * @returns {Promise<{validation: ReturnType<RelationshipValidationService['validateBatch']>, ingest: {stored: number, skipped: number, errors: string[]}}>}
   */
  async ingestEdges(edges) {
    const validation = this.validation.validateBatch(edges);
    const validEdges = edges.filter((_, index) => validation.results[index].valid);
    const ingest = await this._provider.ingestEdges(validEdges);
    return { validation, ingest };
  }

  /** @param {string} entityId */
  async lookupRelationships(entityId) {
    return this.lookup.lookup(entityId);
  }

  /** @param {string} entityId @param {Parameters<RelationshipTraversalService['traverse']>[1]} [options] */
  async traverse(entityId, options) {
    return this.traversal.traverse(entityId, options);
  }

  /** @param {string} fromEntityId @param {string} toEntityId @param {Parameters<RelationshipTraversalService['shortestPath']>[2]} [options] */
  async shortestPath(fromEntityId, toEntityId, options) {
    return this.traversal.shortestPath(fromEntityId, toEntityId, options);
  }

  /** @returns {Promise<number>} total persisted edge count */
  async edgeCount() {
    return this._repository.count();
  }

  getMetricsSnapshot() {
    return this.metrics.snapshot();
  }
}
