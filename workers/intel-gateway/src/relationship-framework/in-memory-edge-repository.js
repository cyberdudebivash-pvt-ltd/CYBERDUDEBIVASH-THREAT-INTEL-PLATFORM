/**
 * In-memory Relationship Edge Repository -- Stage 16 Phase 3 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Reference implementation of RelationshipEdgeRepositoryInterface, backed by plain in-process
 * Maps -- mirrors evidence-registry/in-memory-repository.js's own precedent exactly: "Repository
 * implementation must remain abstract enough to support future storage backends" / "Do NOT
 * introduce vendor-specific persistence." A future, separately-authorized KV/R2-backed
 * implementation only needs to satisfy the same interface; nothing above this class changes.
 *
 * This IS the persistence layer ADR-0010 Decision item 2 required before R1 could be designated
 * canonical without qualification -- resolved via Revision 5's "native persistence" path. It
 * does not rebuild the graph (no _buildGraph logic here, no p31-handlers.js import); it only
 * stores and indexes edges that a documented-shape adapter (p31-edge-adapter.js) feeds it.
 */

import { RelationshipEdgeRepositoryInterface } from "./edge-repository-interface.js";

/** @typedef {import('./edge-repository-interface.js').RelationshipEdge} RelationshipEdge */

function edgeKey(edge) {
  return `${edge.source}->${edge.relation}->${edge.target}`;
}

export class InMemoryRelationshipEdgeRepository extends RelationshipEdgeRepositoryInterface {
  constructor() {
    super();
    /** @type {Map<string, RelationshipEdge>} edgeKey -> edge */
    this._edges = new Map();
    /** @type {Map<string, Set<string>>} entityId -> Set<edgeKey> (source OR target) */
    this._byEntity = new Map();
    /** @type {Map<string, Set<string>>} relation -> Set<edgeKey> */
    this._byRelation = new Map();
  }

  _index(edge, key) {
    for (const entityId of [edge.source, edge.target]) {
      if (!this._byEntity.has(entityId)) this._byEntity.set(entityId, new Set());
      this._byEntity.get(entityId).add(key);
    }
    if (!this._byRelation.has(edge.relation)) this._byRelation.set(edge.relation, new Set());
    this._byRelation.get(edge.relation).add(key);
  }

  _deindex(edge, key) {
    for (const entityId of [edge.source, edge.target]) {
      this._byEntity.get(entityId)?.delete(key);
    }
    this._byRelation.get(edge.relation)?.delete(key);
  }

  /** @param {RelationshipEdge} edge @returns {Promise<RelationshipEdge>} */
  async put(edge) {
    if (!edge || !edge.source || !edge.target || !edge.relation) {
      throw new Error("RelationshipEdgeRepository.put requires { source, target, relation }");
    }
    const key = edgeKey(edge);
    if (this._edges.has(key)) {
      this._deindex(this._edges.get(key), key);
    }
    const stored = { ...edge };
    this._edges.set(key, stored);
    this._index(stored, key);
    return stored;
  }

  /**
   * @param {RelationshipEdge[]} edges
   * @returns {Promise<{stored: number, skipped: number, errors: string[]}>}
   */
  async putMany(edges) {
    let stored = 0;
    let skipped = 0;
    const errors = [];
    for (const edge of edges || []) {
      if (!edge || !edge.source || !edge.target || !edge.relation) {
        skipped += 1;
        errors.push(`edge missing source/target/relation -- skipped: ${JSON.stringify(edge)}`);
        continue;
      }
      await this.put(edge);
      stored += 1;
    }
    return { stored, skipped, errors };
  }

  /** @param {string} entityId @returns {Promise<RelationshipEdge[]>} */
  async getForEntity(entityId) {
    const keys = this._byEntity.get(entityId);
    if (!keys) return [];
    return [...keys].map((key) => this._edges.get(key)).filter(Boolean);
  }

  /** @param {string} relation @returns {Promise<RelationshipEdge[]>} */
  async getByRelation(relation) {
    const keys = this._byRelation.get(relation);
    if (!keys) return [];
    return [...keys].map((key) => this._edges.get(key)).filter(Boolean);
  }

  /** @returns {Promise<RelationshipEdge[]>} */
  async getAll() {
    return [...this._edges.values()];
  }

  /** @returns {Promise<number>} */
  async count() {
    return this._edges.size;
  }

  async clear() {
    this._edges.clear();
    this._byEntity.clear();
    this._byRelation.clear();
  }
}
