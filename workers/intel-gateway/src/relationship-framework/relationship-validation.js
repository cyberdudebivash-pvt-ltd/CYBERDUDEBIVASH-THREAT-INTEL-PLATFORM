/**
 * Relationship Validation Service -- Stage 16 Phase 1 + Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Validates relationship edges against the canonical registry (relationship-registry.js) --
 * type known, entity-class pair permitted, confidence in range, no bare self-loop -- plus
 * corpus-level cycle/orphan detection, addressing ADR-0010's own explicitly-deferred "relationship
 * cycles, orphan detection" concern (its Future Considerations section named these as "Stage 6
 * Phase 8 (Validation) concerns," not decided by the ADR itself -- Stage 16 Phase 8 implements
 * them here). Composes RelationshipRegistry rather than re-deriving type rules (Reuse Before
 * Build); does not duplicate evidence-registry/validation.js's CanonicalEvidence validation,
 * which is a different entity type entirely.
 */

/** @typedef {import('./edge-repository-interface.js').RelationshipEdge} RelationshipEdge */
/** @typedef {import('./relationship-registry.js').RelationshipRegistry} RelationshipRegistry */
/** @typedef {import('./relationship-metrics.js').RelationshipMetricsService} RelationshipMetricsService */

/**
 * @typedef {object} ValidationResult
 * @property {boolean} valid
 * @property {string[]} errors
 */

export class RelationshipValidationService {
  /** @param {{registry: RelationshipRegistry, metrics?: RelationshipMetricsService}} deps */
  constructor(deps = {}) {
    if (!deps.registry) {
      throw new Error("RelationshipValidationService requires a `registry` (RelationshipRegistry) dependency");
    }
    this._registry = deps.registry;
    this._metrics = deps.metrics || null;
  }

  _fail(errors) {
    if (this._metrics) {
      for (const error of errors) this._metrics.recordValidationFailure(error.split(":")[0]);
    }
    return { valid: false, errors };
  }

  /**
   * Validates one edge in isolation: known type, permitted entity-class pair (if entity classes
   * are supplied), confidence range, no bare self-loop.
   * @param {RelationshipEdge} edge
   * @param {{sourceEntityClass?: string, targetEntityClass?: string}} [options]
   * @returns {ValidationResult}
   */
  validateEdge(edge, options = {}) {
    const errors = [];
    if (!edge || !edge.source || !edge.target || !edge.relation) {
      return this._fail(["SCHEMA: edge missing required source/target/relation field(s)"]);
    }
    if (edge.source === edge.target) {
      errors.push(`SELF_LOOP: edge "${edge.relation}" has identical source and target ("${edge.source}")`);
    }
    const canonical = this._registry.normalizeTypeName(edge.relation);
    if (!canonical) {
      errors.push(`UNKNOWN_TYPE: "${edge.relation}" is not a registered relationship type`);
    } else {
      const pairCheck = this._registry.validateEntityPair(canonical, options.sourceEntityClass, options.targetEntityClass);
      if (!pairCheck.valid) errors.push(`ENTITY_CLASS: ${pairCheck.reason}`);

      const def = this._registry.get(canonical);
      if (def.requiresConfidence && typeof edge.confidence !== "number") {
        errors.push(`MISSING_CONFIDENCE: "${canonical}" requires a numeric confidence score`);
      }
    }
    if (typeof edge.confidence === "number" && (edge.confidence < 0 || edge.confidence > 1)) {
      errors.push(`CONFIDENCE_RANGE: confidence ${edge.confidence} is outside [0, 1]`);
    }

    if (errors.length > 0) return this._fail(errors);
    return { valid: true, errors: [] };
  }

  /**
   * Validates a batch, returning per-edge results plus a summary -- mirrors
   * evidence-registry/validation.js's validateEvidenceBatch() shape for consistency across the
   * platform's validation services, without importing it (different entity type).
   * @param {RelationshipEdge[]} edges
   * @returns {{valid: boolean, results: ValidationResult[], validCount: number, invalidCount: number}}
   */
  validateBatch(edges) {
    const results = (edges || []).map((edge) => this.validateEdge(edge));
    const validCount = results.filter((r) => r.valid).length;
    return {
      valid: validCount === results.length,
      results,
      validCount,
      invalidCount: results.length - validCount,
    };
  }

  /**
   * Corpus-level orphan detection: entities that appear as a `target` of some edge but never as
   * the `source` or `target` of any OTHER edge -- i.e. degree-1 leaf nodes reachable only one
   * way. Returns entity ids, not edges; a "finding," not a hard failure (orphan nodes are often
   * legitimate leaves, e.g. a CVE referenced exactly once).
   * @param {RelationshipEdge[]} edges
   * @returns {string[]}
   */
  findOrphanEntities(edges) {
    const degree = new Map();
    for (const edge of edges || []) {
      degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
    }
    return [...degree.entries()].filter(([, count]) => count === 1).map(([entityId]) => entityId);
  }

  /**
   * Corpus-level cycle detection (DFS, three-color marking) over the full edge set treated as a
   * directed graph. Returns one representative entity-id cycle per detected cycle, not every
   * edge in it -- a finding for a human/analyst to inspect, not a traversal-blocking error
   * (relationship-traversal.js's own visited-set already guarantees traversal TERMINATES
   * regardless of cycles; this is corpus-quality reporting, a separate concern).
   * @param {RelationshipEdge[]} edges
   * @returns {string[][]} array of cycles, each a list of entity ids in cycle order
   */
  findCycles(edges) {
    /** @type {Map<string, string[]>} */
    const adjacency = new Map();
    for (const edge of edges || []) {
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
      adjacency.get(edge.source).push(edge.target);
    }

    const WHITE = 0;
    const GRAY = 1;
    const BLACK = 2;
    const color = new Map();
    const cycles = [];

    const visit = (node, path) => {
      color.set(node, GRAY);
      path.push(node);
      for (const neighbor of adjacency.get(node) || []) {
        const neighborColor = color.get(neighbor) || WHITE;
        if (neighborColor === GRAY) {
          const cycleStart = path.indexOf(neighbor);
          cycles.push([...path.slice(cycleStart), neighbor]);
        } else if (neighborColor === WHITE) {
          visit(neighbor, path);
        }
      }
      path.pop();
      color.set(node, BLACK);
    };

    for (const node of adjacency.keys()) {
      if ((color.get(node) || WHITE) === WHITE) visit(node, []);
    }
    return cycles;
  }
}
