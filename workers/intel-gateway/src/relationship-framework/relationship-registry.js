/**
 * Relationship Registry -- Stage 16 Phase 2 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * "Reuse the existing Registry where appropriate" (Phase 2's own instruction): this class
 * mirrors evidence-registry/registry-service.js's shape -- a Map-backed register/lookup service
 * with version awareness -- rather than introducing a new registry paradigm. It does NOT reuse
 * EvidenceRegistry itself (that registers CanonicalEvidence records, a different entity
 * entirely); reuse here means the same established *pattern*, per Principle 4's own priority
 * order ("call unchanged" does not apply when the entity type differs, so this level is
 * "compose the same idiom").
 */

import { RELATIONSHIP_TYPE_DEFINITIONS, RELATIONSHIP_CATALOG_VERSION } from "./relationship-types.js";

export class UnknownRelationshipTypeError extends Error {
  constructor(typeName) {
    super(`"${typeName}" is not a registered relationship type. See relationship-types.js for the canonical catalog.`);
    this.name = "UnknownRelationshipTypeError";
    this.typeName = typeName;
  }
}

/**
 * Canonical registry for relationship TYPE definitions (not relationship instances/edges --
 * those are edge-repository-interface.js's concern, one layer down). Version-aware: tracks the
 * catalog version it was seeded from and rejects duplicate registration of a name already
 * present, mirroring registry-service.js's DuplicateEvidenceError discipline for a different
 * entity type.
 */
export class RelationshipRegistry {
  constructor() {
    /** @type {Map<string, import('./relationship-types.js').RelationshipTypeDefinition>} */
    this._byName = new Map();
    /** @type {Map<string, string>} alias (lowercase) -> canonical name */
    this._aliasToName = new Map();
    this._catalogVersion = RELATIONSHIP_CATALOG_VERSION;
    this._seedFromCatalog();
  }

  _seedFromCatalog() {
    for (const def of RELATIONSHIP_TYPE_DEFINITIONS) {
      this.register(def);
    }
  }

  /**
   * @param {import('./relationship-types.js').RelationshipTypeDefinition} definition
   */
  register(definition) {
    if (!definition || !definition.name) {
      throw new Error("RelationshipRegistry.register requires a definition with a `name`");
    }
    if (this._byName.has(definition.name)) {
      throw new Error(
        `Relationship type "${definition.name}" is already registered -- use a new type name ` +
          "for a genuinely new relationship, or extend the existing entry in relationship-types.js " +
          "(Single Source of Truth: one canonical definition per type name, not a silent overwrite)."
      );
    }
    this._byName.set(definition.name, definition);
    for (const alias of definition.aliases || []) {
      this._aliasToName.set(alias.toLowerCase(), definition.name);
    }
    this._aliasToName.set(definition.name.toLowerCase(), definition.name);
  }

  /**
   * Resolves any known casing/alias (e.g. R1's lowercase `attributed_to`) to the canonical
   * UPPER_SNAKE_CASE name. Returns null (not throw) so callers can decide how to handle an
   * unrecognized type -- relationship-validation.js is the layer that turns "unknown" into a
   * hard failure.
   * @param {string} typeNameOrAlias
   * @returns {string | null}
   */
  normalizeTypeName(typeNameOrAlias) {
    if (!typeNameOrAlias) return null;
    return this._aliasToName.get(String(typeNameOrAlias).toLowerCase()) || null;
  }

  /** @param {string} typeNameOrAlias @returns {boolean} */
  isKnownType(typeNameOrAlias) {
    return this.normalizeTypeName(typeNameOrAlias) !== null;
  }

  /**
   * @param {string} typeNameOrAlias
   * @returns {import('./relationship-types.js').RelationshipTypeDefinition}
   * @throws {UnknownRelationshipTypeError}
   */
  get(typeNameOrAlias) {
    const canonical = this.normalizeTypeName(typeNameOrAlias);
    if (!canonical) throw new UnknownRelationshipTypeError(typeNameOrAlias);
    return this._byName.get(canonical);
  }

  /** @param {"evidence"|"threat"|"ioc"|"campaign"|"attack"} [category] @returns {import('./relationship-types.js').RelationshipTypeDefinition[]} */
  list(category) {
    const all = [...this._byName.values()];
    return category ? all.filter((def) => def.category === category) : all;
  }

  /** @returns {string} the catalog version this registry instance was seeded from */
  catalogVersion() {
    return this._catalogVersion;
  }

  /**
   * Whether a (sourceEntityClass, typeName, targetEntityClass) triple is valid per the
   * registered definition's validSourceTypes/validTargetTypes. Returns a structured result
   * rather than a boolean so callers get the reason, not just pass/fail.
   * @param {string} typeNameOrAlias @param {string} sourceEntityClass @param {string} targetEntityClass
   * @returns {{valid: boolean, reason?: string, canonicalType?: string}}
   */
  validateEntityPair(typeNameOrAlias, sourceEntityClass, targetEntityClass) {
    const canonical = this.normalizeTypeName(typeNameOrAlias);
    if (!canonical) {
      return { valid: false, reason: `Unknown relationship type "${typeNameOrAlias}"` };
    }
    const def = this._byName.get(canonical);
    if (sourceEntityClass && !def.validSourceTypes.includes(sourceEntityClass)) {
      return {
        valid: false,
        canonicalType: canonical,
        reason: `${canonical} does not permit source entity class "${sourceEntityClass}" -- valid: ${def.validSourceTypes.join(", ")}`,
      };
    }
    if (targetEntityClass && !def.validTargetTypes.includes(targetEntityClass)) {
      return {
        valid: false,
        canonicalType: canonical,
        reason: `${canonical} does not permit target entity class "${targetEntityClass}" -- valid: ${def.validTargetTypes.join(", ")}`,
      };
    }
    return { valid: true, canonicalType: canonical };
  }
}
