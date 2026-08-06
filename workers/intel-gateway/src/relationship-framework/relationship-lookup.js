/**
 * Relationship Lookup Service -- Stage 16 Phase 1 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Thin composing wrapper over Stage 12's RelationshipResolutionService -- delegates the actual
 * resolution call unchanged (Reuse Before Build, Principle 4 priority 1: "call the existing
 * function unchanged"), then enriches the result with this stage's own registry type metadata
 * (category, description) so a caller gets more than the bare {relatedEntityId, relationshipType,
 * confidence} triple, without Stage 12's own class having to know Stage 16's registry exists.
 */

/** @typedef {import('../evidence-registry/relationship-resolution.js').RelationshipResolutionService} RelationshipResolutionService */
/** @typedef {import('./relationship-registry.js').RelationshipRegistry} RelationshipRegistry */

export class RelationshipLookupService {
  /** @param {{resolution: RelationshipResolutionService, registry: RelationshipRegistry}} deps */
  constructor(deps = {}) {
    if (!deps.resolution || !deps.registry) {
      throw new Error("RelationshipLookupService requires `resolution` and `registry` dependencies");
    }
    this._resolution = deps.resolution;
    this._registry = deps.registry;
  }

  /**
   * @param {string} entityId
   * @returns {Promise<Array<{relatedEntityId: string, relationshipType: string, confidence?: number, category?: string, description?: string}>>}
   */
  async lookup(entityId) {
    const relationships = await this._resolution.resolveRelationships(entityId);
    return relationships.map((rel) => {
      const canonical = this._registry.normalizeTypeName(rel.relationshipType);
      const def = canonical ? this._registry.get(canonical) : null;
      return {
        ...rel,
        relationshipType: canonical || rel.relationshipType,
        category: def?.category,
        description: def?.description,
      };
    });
  }

  /** @returns {boolean} true once the underlying RelationshipResolutionService has a real provider */
  isWired() {
    return this._resolution.isWired();
  }
}
