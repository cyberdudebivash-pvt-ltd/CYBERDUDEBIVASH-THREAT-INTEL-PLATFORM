/**
 * P31 Edge Adapter -- Stage 16 Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Pure functions operating on a DOCUMENTED DATA SHAPE, not an import of p31-handlers.js itself --
 * the exact discipline evidence-registry/migration-adapters.js already established and documents
 * in its own module docstring ("Every adapter here is a pure function operating on a documented
 * DATA SHAPE... This is a deliberate design choice... keeping this directory's zero blast radius
 * property trivially true"). This file follows that same rule for the sibling
 * relationship-framework/ directory.
 *
 * Source shape (verified by reading p31-handlers.js directly, not assumed):
 *   `_buildGraph()`'s `addEdge()` closure (line ~200) produces
 *     `{ source, target, relation, confidence, evidence, verified }`
 *   `handleP31Relationships()` (line ~1003) returns this same shape verbatim over HTTP as
 *     `{ relationships: edges.slice(0, 100), ... }`.
 * Nothing in this file calls either function. A caller who has ALREADY obtained edges from one
 * of them (e.g. a Worker-request-time composition root with a real `env`, or a fixture in a
 * test) passes the resulting array in; this module only adapts its shape.
 */

/** @typedef {import('./edge-repository-interface.js').RelationshipEdge} RelationshipEdge */
/** @typedef {import('../evidence-registry/relationship-resolution.js').RelationshipProviderInterface} RelationshipProviderInterface */

/**
 * Validates that an object matches R1's documented edge shape closely enough to trust. Not
 * exhaustive schema validation (relationship-validation.js owns that, one layer up) -- just
 * enough to fail loudly on an obviously-wrong input rather than silently persisting garbage.
 * @param {unknown} raw
 * @returns {raw is RelationshipEdge}
 */
export function isP31EdgeShape(raw) {
  return Boolean(
    raw &&
      typeof raw === "object" &&
      typeof raw.source === "string" &&
      typeof raw.target === "string" &&
      typeof raw.relation === "string" &&
      typeof raw.confidence === "number"
  );
}

/**
 * Adapts a raw P31 edge into the exact RelationshipEdge shape edge-repository-interface.js
 * expects. Effectively an identity/normalization pass (R1's shape and the repository's shape
 * were deliberately designed to match -- Reuse Before Build), with defensive defaulting for the
 * two optional fields R1 does not always populate.
 * @param {unknown} raw
 * @returns {RelationshipEdge}
 */
export function adaptP31EdgeToRepositoryShape(raw) {
  if (!isP31EdgeShape(raw)) {
    throw new Error(
      `p31-edge-adapter: input does not match R1's documented edge shape {source, target, ` +
        `relation, confidence, evidence?, verified?} -- got ${JSON.stringify(raw)}`
    );
  }
  return {
    source: raw.source,
    target: raw.target,
    relation: raw.relation,
    confidence: raw.confidence,
    evidence: typeof raw.evidence === "string" ? raw.evidence : "",
    verified: typeof raw.verified === "boolean" ? raw.verified : raw.confidence >= 0.75,
  };
}

/**
 * Adapts a batch. Silently-skips (counts, does not throw on) any element that doesn't match the
 * shape, since a real R1 snapshot is not expected to be perfectly uniform and one bad element
 * should not fail an entire ingest -- mirrors migration-adapters.js's own bulkImport-style
 * tolerance (evidence-registry/in-memory-repository.js's bulkImport()) rather than inventing a
 * new error-handling convention.
 * @param {unknown[]} rawEdges
 * @returns {{adapted: RelationshipEdge[], skipped: number}}
 */
export function adaptP31EdgeBatch(rawEdges) {
  const adapted = [];
  let skipped = 0;
  for (const raw of rawEdges || []) {
    if (isP31EdgeShape(raw)) {
      adapted.push(adaptP31EdgeToRepositoryShape(raw));
    } else {
      skipped += 1;
    }
  }
  return { adapted, skipped };
}

/**
 * Adapts a RelationshipEdge (repository shape) into Stage 12's RelationshipProviderInterface
 * return shape `{relatedEntityId, relationshipType, confidence}`, from the perspective of
 * `entityId` -- i.e. picks whichever end of the edge is NOT `entityId` as `relatedEntityId`.
 * Mirrors handleP31Relationships()'s own filter semantics
 * (`e.source.includes(entityId) || e.target.includes(entityId)`) at the CALLER level
 * (relationship-provider.js decides matching); this function only does the shape conversion for
 * an edge already known to involve `entityId`.
 * @param {RelationshipEdge} edge @param {string} entityId
 * @returns {{relatedEntityId: string, relationshipType: string, confidence: number}}
 */
export function adaptEdgeToProviderShape(edge, entityId) {
  const relatedEntityId = edge.source === entityId ? edge.target : edge.source;
  return {
    relatedEntityId,
    relationshipType: edge.relation,
    confidence: edge.confidence,
  };
}
