/**
 * Relationship Traversal Service -- Stage 16 Phase 1 + Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Multi-hop BFS traversal over the edges edge-repository-interface.js persists. No new graph
 * engine -- this is a bounded breadth-first walk over the SAME edge records the repository
 * already stores (fed by p31-edge-adapter.js from R1's documented shape); it does not
 * re-implement `_buildGraph()`'s construction logic, and it is not itself a graph database (Stage
 * 16's own NON-GOALS: "No duplicate traversal engine," "No new graph database").
 *
 * Cycle-safe by construction (visited-set), addressing ADR-0010's own explicitly-deferred
 * concern ("This ADR does not address relationship cycles, orphan detection... those are Stage 6
 * Phase 8 (Validation) concerns" -- cycle-SAFETY here is a traversal-termination guarantee;
 * cycle-DETECTION-as-a-finding is relationship-validation.js's job, Phase 8 as originally
 * scoped, now implemented in Stage 16).
 */

/** @typedef {import('./edge-repository-interface.js').RelationshipEdge} RelationshipEdge */
/** @typedef {import('./edge-repository-interface.js').RelationshipEdgeRepositoryInterface} RelationshipEdgeRepositoryInterface */
/** @typedef {import('./relationship-metrics.js').RelationshipMetricsService} RelationshipMetricsService */

export const DEFAULT_MAX_DEPTH = 3;
export const DEFAULT_MAX_NODES = 500;

export class RelationshipTraversalService {
  /** @param {{repository: RelationshipEdgeRepositoryInterface, metrics?: RelationshipMetricsService}} deps */
  constructor(deps = {}) {
    if (!deps.repository) {
      throw new Error("RelationshipTraversalService requires a `repository` dependency");
    }
    this._repository = deps.repository;
    this._metrics = deps.metrics || null;
  }

  async _timed(name, fn) {
    if (!this._metrics) return fn();
    const start = performance.now();
    try {
      return await fn();
    } finally {
      this._metrics.recordTraversalLatency(name, performance.now() - start);
    }
  }

  /**
   * Bounded, cycle-safe BFS from `startEntityId` out to `maxDepth` hops, visiting at most
   * `maxNodes` distinct entities (both bounds exist so a densely-connected corpus can't turn one
   * traversal call into an unbounded scan -- Performance Before Features).
   * @param {string} startEntityId
   * @param {{maxDepth?: number, maxNodes?: number, minConfidence?: number}} [options]
   * @returns {Promise<{startEntityId: string, visited: string[], edges: RelationshipEdge[], truncated: boolean, depthReached: number}>}
   */
  async traverse(startEntityId, options = {}) {
    return this._timed("traverse", async () => {
      const maxDepth = options.maxDepth ?? DEFAULT_MAX_DEPTH;
      const maxNodes = options.maxNodes ?? DEFAULT_MAX_NODES;
      const minConfidence = options.minConfidence ?? 0;

      const visited = new Set([startEntityId]);
      const collectedEdgeKeys = new Set();
      const collectedEdges = [];
      let frontier = [startEntityId];
      let depthReached = 0;
      let truncated = false;

      for (let depth = 0; depth < maxDepth; depth += 1) {
        if (frontier.length === 0) break;
        const nextFrontier = [];
        for (const entityId of frontier) {
          if (visited.size >= maxNodes) {
            truncated = true;
            break;
          }
          const edges = await this._repository.getForEntity(entityId);
          for (const edge of edges) {
            if (edge.confidence < minConfidence) continue;
            const key = `${edge.source}->${edge.relation}->${edge.target}`;
            if (!collectedEdgeKeys.has(key)) {
              collectedEdgeKeys.add(key);
              collectedEdges.push(edge);
            }
            const neighbor = edge.source === entityId ? edge.target : edge.source;
            if (!visited.has(neighbor)) {
              if (visited.size >= maxNodes) {
                truncated = true;
                continue;
              }
              visited.add(neighbor);
              nextFrontier.push(neighbor);
            }
          }
        }
        if (nextFrontier.length > 0) depthReached = depth + 1;
        frontier = nextFrontier;
        if (truncated) break;
      }

      return {
        startEntityId,
        visited: [...visited],
        edges: collectedEdges,
        truncated,
        depthReached,
      };
    });
  }

  /**
   * Shortest path (fewest hops) between two entities via BFS, or null if unreachable within
   * `maxDepth`. Built on the same per-entity lookup as traverse() (Reuse Before Build -- no
   * second graph-walk primitive).
   * @param {string} fromEntityId @param {string} toEntityId @param {{maxDepth?: number}} [options]
   * @returns {Promise<{path: string[], edges: RelationshipEdge[]} | null>}
   */
  async shortestPath(fromEntityId, toEntityId, options = {}) {
    return this._timed("shortestPath", async () => {
      const maxDepth = options.maxDepth ?? DEFAULT_MAX_DEPTH;
      if (fromEntityId === toEntityId) return { path: [fromEntityId], edges: [] };

      const visited = new Set([fromEntityId]);
      /** @type {Map<string, {parent: string, edge: RelationshipEdge}>} */
      const cameFrom = new Map();
      let frontier = [fromEntityId];

      for (let depth = 0; depth < maxDepth; depth += 1) {
        const nextFrontier = [];
        for (const entityId of frontier) {
          const edges = await this._repository.getForEntity(entityId);
          for (const edge of edges) {
            const neighbor = edge.source === entityId ? edge.target : edge.source;
            if (visited.has(neighbor)) continue;
            visited.add(neighbor);
            cameFrom.set(neighbor, { parent: entityId, edge });
            if (neighbor === toEntityId) {
              const path = [neighbor];
              const edgesOut = [edge];
              let cursor = entityId;
              while (cursor !== fromEntityId) {
                const step = cameFrom.get(cursor);
                path.unshift(cursor);
                edgesOut.unshift(step.edge);
                cursor = step.parent;
              }
              path.unshift(fromEntityId);
              return { path, edges: edgesOut };
            }
            nextFrontier.push(neighbor);
          }
        }
        frontier = nextFrontier;
        if (frontier.length === 0) break;
      }
      return null;
    });
  }
}
