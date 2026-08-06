/**
 * Relationship Edge Repository Interface -- Stage 16 Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * This is the persistence layer ADR-0010 Decision item 2 named as R1's missing prerequisite,
 * resolved per ADR-0010 Revision 5 (native persistence, not R6 adoption -- see that revision for
 * the full reasoning). Contract only, mirroring evidence-registry/repository-interface.js's
 * exact shape and rationale: every method throws; this class defines what a storage backend must
 * satisfy, it is not itself one. No KV/R2/D1 binding is referenced anywhere in this file.
 *
 * Edge shape stored here is `{ source, target, relation, confidence, evidence, verified }` --
 * the exact, unmodified shape p31-handlers.js's `_buildGraph()` already produces (verified by
 * reading its `addEdge()` closure directly) and `handleP31Relationships()` already returns over
 * HTTP as `relationships: edges.slice(0, 100)`. This repository does not redefine that shape; it
 * persists it as-is (Reuse Before Build -- adopt the existing shape, do not invent a new one).
 */

const NOT_IMPLEMENTED = "RelationshipEdgeRepositoryInterface is a contract, not an implementation. " +
  "See in-memory-edge-repository.js for the reference implementation, or provide your own that " +
  "satisfies this same contract.";

/**
 * @typedef {object} RelationshipEdge
 * @property {string} source - entity id, e.g. "advisory:CVE-2026-0001" or "actor:fin7"
 * @property {string} target - entity id
 * @property {string} relation - relationship type name or alias (relationship-registry.js
 *   normalizes casing)
 * @property {number} confidence - 0..1
 * @property {string} [evidence] - free-text evidence/provenance note, matching R1's own field
 * @property {boolean} [verified] - matches R1's own `confidence >= 0.75` convention
 */

export class RelationshipEdgeRepositoryInterface {
  /**
   * @param {RelationshipEdge} edge
   * @returns {Promise<RelationshipEdge>}
   */
  async put(edge) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /**
   * @param {RelationshipEdge[]} edges
   * @returns {Promise<{stored: number, skipped: number, errors: string[]}>}
   */
  async putMany(edges) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /**
   * All edges where `entityId` is the source OR the target -- matches
   * handleP31Relationships()'s own filter semantics (`e.source.includes(entityId) ||
   * e.target.includes(entityId)`), except this uses exact match, not substring, since a
   * persisted store can afford an exact index where a per-request linear scan used `.includes`
   * as a cheap fuzzy match. See p31-edge-adapter.js for the substring-compatibility note.
   * @param {string} entityId
   * @returns {Promise<RelationshipEdge[]>}
   */
  async getForEntity(entityId) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /** @param {string} relation @returns {Promise<RelationshipEdge[]>} */
  async getByRelation(relation) {
    throw new Error(NOT_IMPLEMENTED);
  }

  /** @returns {Promise<RelationshipEdge[]>} every persisted edge */
  async getAll() {
    throw new Error(NOT_IMPLEMENTED);
  }

  /** @returns {Promise<number>} count of persisted edges */
  async count() {
    throw new Error(NOT_IMPLEMENTED);
  }

  /** Removes every persisted edge. Used when refreshing from a new R1 snapshot, not a per-edge operation. */
  async clear() {
    throw new Error(NOT_IMPLEMENTED);
  }
}
