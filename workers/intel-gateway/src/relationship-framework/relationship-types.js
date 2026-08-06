/**
 * Canonical Relationship Type Vocabulary -- Stage 16 Phase 2 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Documented-data-shape only -- this file does not import p31-handlers.js. Its vocabulary is
 * sourced from two places, both cited per entry below, and every R1-sourced entry was verified
 * by reading p31-handlers.js's actual `addEdge(...)` call sites directly (not assumed), per this
 * platform's own ZERO FABRICATION principle (p31-handlers.js's own file header):
 *
 *   1. R1's OBSERVED relation strings -- read directly from p31-handlers.js's `_buildGraph()`
 *      (lines ~200-303) and `buildP31RelationshipBlock()` (lines ~792-819). R1 emits these
 *      entity-to-entity semantic edges: attributed_to, uses_technique, employs_technique,
 *      references, exploits (verified exact source/target pairing per entry below). R1 ALSO
 *      emits four edges this registry deliberately excludes as out of Phase 2's scope --
 *      classified_as (advisory->threat_type), published_by (advisory->intel_source),
 *      contains_ioc_type (advisory->ioc_type bucket), severity_level (advisory->severity
 *      cluster) -- these are pipeline/classification bookkeeping edges to synthetic bucket
 *      nodes, not semantic relationships between the Evidence/Threat/IOC/Campaign/ATT&CK entity
 *      classes Phase 2 names. mapped_to_tactic (advisory->tactic) IS included (ATT&CK-adjacent,
 *      fits the "attack" category cleanly). R1's own casing is inconsistent between the two
 *      functions (lowercase snake_case in `_buildGraph`, UPPER_SNAKE_CASE in
 *      `buildP31RelationshipBlock` for the 3 types both emit); this registry normalizes to one
 *      canonical UPPER_SNAKE_CASE form per type and records the lowercase form as an alias,
 *      rather than "fixing" R1, which this stage has no authorization to modify.
 *   2. ADR-0010's own "Future Considerations" section, which names R2's (`knowledge_graph.py`)
 *      edge-type vocabulary -- mentions/references/maps_to/observed/associated_with/linked_to --
 *      as "more developed than anything currently documented for R1 and is a candidate for
 *      direct reuse rather than reinvention." R2 itself is not imported or touched; only its
 *      already-published vocabulary (quoted in ADR-0010's own text) is reused here as names, for
 *      entity classes R1 does not emit relationships for today (Evidence, generic
 *      cross-Campaign/IOC association).
 *
 * Every type is versioned and confidence-aware per Stage 16 Phase 2's own requirement. Adding a
 * type is additive (bump RELATIONSHIP_CATALOG_VERSION, append -- never renumber or remove an
 * existing entry; deprecate per this repo's Deprecation Instead of Deletion policy if one is
 * ever retired).
 */

/** @typedef {"Advisory"|"ThreatActor"|"MitreTechnique"|"CVE"|"Evidence"|"Campaign"|"IOC"|"ThreatReport"} RelationshipEntityClass */

/**
 * @typedef {object} RelationshipTypeDefinition
 * @property {string} name - canonical UPPER_SNAKE_CASE identifier
 * @property {string[]} aliases - other-cased/legacy strings that normalize to `name` (e.g. R1's
 *   lowercase _buildGraph() edge labels)
 * @property {"evidence"|"threat"|"ioc"|"campaign"|"attack"} category - Phase 2's five named
 *   relationship classes
 * @property {RelationshipEntityClass[]} validSourceTypes
 * @property {RelationshipEntityClass[]} validTargetTypes
 * @property {boolean} requiresConfidence - true if a relationship of this type without a
 *   numeric confidence score fails validation (relationship-validation.js)
 * @property {string} description
 * @property {string} version - this type definition's own version (independent of
 *   RELATIONSHIP_CATALOG_VERSION), bumped only if this specific entry's semantics change
 * @property {string} source - where this type's vocabulary was verified/sourced from
 */

export const RELATIONSHIP_CATALOG_VERSION = "1.0.0";

/** @type {RelationshipTypeDefinition[]} */
const DEFINITIONS = [
  {
    name: "ATTRIBUTED_TO",
    aliases: ["attributed_to"],
    category: "threat",
    validSourceTypes: ["Advisory", "CVE", "Evidence"],
    validTargetTypes: ["ThreatActor"],
    requiresConfidence: true,
    description: "Source entity is attributed to a threat actor.",
    version: "1.0.0",
    source: "p31-handlers.js _buildGraph() line ~231 and buildP31RelationshipBlock() line ~800 (both verified)",
  },
  {
    name: "USES_TECHNIQUE",
    aliases: ["uses_technique"],
    category: "attack",
    validSourceTypes: ["Advisory", "Evidence"],
    validTargetTypes: ["MitreTechnique"],
    requiresConfidence: true,
    description: "Advisory (or, by extension, an Evidence record) employs a MITRE ATT&CK technique.",
    version: "1.0.0",
    source: "p31-handlers.js _buildGraph() line ~240 and buildP31RelationshipBlock() line ~807 (both verified)",
  },
  {
    name: "EMPLOYS_TECHNIQUE",
    aliases: ["employs_technique"],
    category: "attack",
    validSourceTypes: ["ThreatActor"],
    validTargetTypes: ["MitreTechnique"],
    requiresConfidence: true,
    description: "Threat actor employs a technique, derived from co-occurrence with an attributed advisory (a weaker signal than USES_TECHNIQUE's direct pipeline mapping -- kept distinct, not merged).",
    version: "1.0.0",
    source: "p31-handlers.js _buildGraph() line ~245 (verified)",
  },
  {
    name: "MAPPED_TO_TACTIC",
    aliases: ["mapped_to_tactic"],
    category: "attack",
    validSourceTypes: ["Advisory"],
    validTargetTypes: ["MitreTechnique"],
    requiresConfidence: true,
    description: "Advisory maps to a MITRE ATT&CK kill-chain tactic. Target type modeled as MitreTechnique (this catalog does not define a separate Tactic entity class; a tactic is treated as a coarser technique-family node).",
    version: "1.0.0",
    source: "p31-handlers.js _buildGraph() line ~302 (verified)",
  },
  {
    name: "REFERENCES",
    aliases: ["references"],
    category: "evidence",
    validSourceTypes: ["Advisory", "ThreatReport", "Evidence"],
    validTargetTypes: ["CVE", "ThreatReport", "Evidence"],
    requiresConfidence: true,
    description: "Source entity references/mentions a CVE, report, or evidence record.",
    version: "1.0.0",
    source: "p31-handlers.js _buildGraph() line ~272 and buildP31RelationshipBlock() line ~815 (both verified); name also matches ADR-0010 Future Considerations' R2 vocabulary",
  },
  {
    name: "EXPLOITS",
    aliases: ["exploits"],
    category: "threat",
    validSourceTypes: ["ThreatActor"],
    validTargetTypes: ["CVE"],
    requiresConfidence: true,
    description: "Threat actor exploits a specific CVE, derived from actor-CVE co-occurrence in an advisory.",
    version: "1.0.0",
    source: "p31-handlers.js _buildGraph() line ~275 (verified)",
  },
  {
    name: "MENTIONS",
    aliases: ["mentions"],
    category: "evidence",
    validSourceTypes: ["Evidence", "ThreatReport"],
    validTargetTypes: ["ThreatActor", "CVE", "IOC", "Campaign", "MitreTechnique"],
    requiresConfidence: false,
    description: "Evidence or report mentions an entity without asserting a stronger relationship. Not emitted by R1 today -- named per ADR-0010's own recommendation to reuse R2's vocabulary rather than invent a new one for Evidence-class relationships R1 does not yet cover.",
    version: "1.0.0",
    source: "ADR-0010 Future Considerations (R2/knowledge_graph.py vocabulary name, quoted not imported)",
  },
  {
    name: "MAPS_TO",
    aliases: ["maps_to"],
    category: "attack",
    validSourceTypes: ["CVE", "IOC"],
    validTargetTypes: ["MitreTechnique"],
    requiresConfidence: true,
    description: "CVE or IOC maps to an ATT&CK technique via enrichment rather than direct pipeline observation. Not emitted by R1 today.",
    version: "1.0.0",
    source: "ADR-0010 Future Considerations (R2/knowledge_graph.py vocabulary name, quoted not imported)",
  },
  {
    name: "OBSERVED",
    aliases: ["observed"],
    category: "ioc",
    validSourceTypes: ["IOC"],
    validTargetTypes: ["Campaign", "ThreatActor"],
    requiresConfidence: true,
    description: "IOC was observed in connection with a campaign or actor. Not emitted by R1 today.",
    version: "1.0.0",
    source: "ADR-0010 Future Considerations (R2/knowledge_graph.py vocabulary name, quoted not imported)",
  },
  {
    name: "ASSOCIATED_WITH",
    aliases: ["associated_with"],
    category: "campaign",
    validSourceTypes: ["Campaign", "IOC", "Evidence"],
    validTargetTypes: ["Campaign", "ThreatActor", "IOC"],
    requiresConfidence: false,
    description: "General-purpose association weaker than ATTRIBUTED_TO/OBSERVED -- used when no more specific type applies. Not emitted by R1 today.",
    version: "1.0.0",
    source: "ADR-0010 Future Considerations (R2/knowledge_graph.py vocabulary name, quoted not imported)",
  },
  {
    name: "LINKED_TO",
    aliases: ["linked_to"],
    category: "campaign",
    validSourceTypes: ["Campaign", "Evidence", "ThreatReport"],
    validTargetTypes: ["Campaign", "Evidence", "ThreatReport"],
    requiresConfidence: false,
    description: "Symmetric cross-reference between two campaigns, evidence records, or reports. Not emitted by R1 today.",
    version: "1.0.0",
    source: "ADR-0010 Future Considerations (R2/knowledge_graph.py vocabulary name, quoted not imported)",
  },
];

/** Frozen, ready-to-register catalog -- consumed by relationship-registry.js, not mutated here. */
export const RELATIONSHIP_TYPE_DEFINITIONS = Object.freeze(
  DEFINITIONS.map((def) =>
    Object.freeze({
      ...def,
      aliases: Object.freeze([...def.aliases]),
      validSourceTypes: Object.freeze([...def.validSourceTypes]),
      validTargetTypes: Object.freeze([...def.validTargetTypes]),
    })
  )
);
