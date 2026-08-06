/**
 * Canonical Evidence Core schema registry  -  Stage 10 Phase 2 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Tracks the schema version lineage, provides compatibility checks for migration support, and
 * generates developer documentation directly from entity.js's own field-name constants
 * (EVIDENCE_ENTITY_CORE_FIELDS etc.) rather than a hand-maintained duplicate list  -  if a field
 * is added to entity.js without updating this file, the generated docs pick it up on the next
 * run instead of silently going stale.
 */

import {
  EVIDENCE_CLASSIFICATION_FIELDS,
  EVIDENCE_ENTITY_CORE_FIELDS,
  EVIDENCE_ENTITY_INTEGRITY_FIELDS,
  EVIDENCE_ENTITY_SCHEMA_VERSION,
  EVIDENCE_GOVERNANCE_FIELDS,
  EVIDENCE_QUALITY_FIELDS,
  EVIDENCE_RELATIONSHIP_FIELDS,
  EVIDENCE_SOURCE_METADATA_FIELDS,
  CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION,
} from "./entity.js";

/**
 * Ordered schema version history, oldest first. Each entry documents what changed and
 * whether it's backward compatible with its predecessor  -  additive-only versions (the only
 * kind this scaffolding has produced so far) are compatible by construction, since every new
 * field is optional (see entity.js's own field-by-field "backward compatible" notes).
 */
export const SCHEMA_VERSION_HISTORY = Object.freeze([
  Object.freeze({
    version: EVIDENCE_ENTITY_SCHEMA_VERSION,
    stage: "Stage 8 Phase 9",
    change: "Initial EvidenceEntity: EvidenceChainCore (P20's live shape) + EvidenceIntegrityFields",
    backwardCompatibleWithPrevious: null, // no predecessor
  }),
  Object.freeze({
    version: "canonical-evidence-core.1.0.0-draft",
    stage: "Stage 10 Phase 1-2",
    change:
      "Additive: Classification, Source Metadata, Quality, Relationships, Governance field groups",
    backwardCompatibleWithPrevious: true,
  }),
  Object.freeze({
    version: CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION,
    stage: "Stage 11 Phase 5",
    change: "Additive: related_iocs field (Relationships group) for Enterprise Evidence Registry indexing",
    backwardCompatibleWithPrevious: true,
  }),
]);

/**
 * Field groups, keyed by name, sourced directly from entity.js's exported constants  -  the
 * single source of truth for "what fields exist," not re-declared here.
 */
export const FIELD_GROUPS = Object.freeze({
  "Identity / Core (Stage 8)": EVIDENCE_ENTITY_CORE_FIELDS,
  "Integrity (Stage 8)": EVIDENCE_ENTITY_INTEGRITY_FIELDS,
  "Classification (Stage 10)": EVIDENCE_CLASSIFICATION_FIELDS,
  "Source Metadata (Stage 10)": EVIDENCE_SOURCE_METADATA_FIELDS,
  "Quality (Stage 10)": EVIDENCE_QUALITY_FIELDS,
  "Relationships (Stage 10)": EVIDENCE_RELATIONSHIP_FIELDS,
  "Governance (Stage 10)": EVIDENCE_GOVERNANCE_FIELDS,
});

/**
 * Migration/compatibility support: is `fromVersion` safely readable by code written against
 * `toVersion`'s schema? True whenever moving strictly forward through SCHEMA_VERSION_HISTORY
 * via additive-only steps (the only kind of step this history currently records)  -  every
 * field the older version has is still present and unchanged in the newer one.
 * @param {string} fromVersion
 * @param {string} toVersion
 * @returns {boolean}
 */
export function isForwardCompatible(fromVersion, toVersion) {
  const fromIndex = SCHEMA_VERSION_HISTORY.findIndex((entry) => entry.version === fromVersion);
  const toIndex = SCHEMA_VERSION_HISTORY.findIndex((entry) => entry.version === toVersion);
  if (fromIndex === -1 || toIndex === -1) return false;
  if (fromIndex > toIndex) return false;
  // All recorded steps between fromIndex (exclusive) and toIndex (inclusive) must be additive.
  for (let i = fromIndex + 1; i <= toIndex; i += 1) {
    if (SCHEMA_VERSION_HISTORY[i].backwardCompatibleWithPrevious !== true) return false;
  }
  return true;
}

/**
 * A record written against the newer schema can always be read by older code that only knows
 * about a subset of fields  -  optional-field JSON objects degrade gracefully when read by code
 * that doesn't recognize the newer fields (it simply doesn't access them). This is true for
 * any pair in this history precisely because every step so far has been additive-only; it is
 * documented as its own function (rather than folded into isForwardCompatible) because a
 * future *non*-additive version bump would need to break this symmetry explicitly, and having
 * two functions makes that the more visible, more deliberate code change.
 * @param {string} newerVersion
 * @param {string} olderVersion
 * @returns {boolean}
 */
export function isBackwardCompatible(newerVersion, olderVersion) {
  return isForwardCompatible(olderVersion, newerVersion);
}

/**
 * Generates Markdown developer documentation directly from FIELD_GROUPS and
 * SCHEMA_VERSION_HISTORY. "Generate developer documentation automatically where feasible"
 * (Phase 2)  -  this is the feasible part: field names and version history are structured data
 * already; prose descriptions remain in entity.js's JSDoc, which this function does not
 * attempt to parse (JSDoc-to-Markdown extraction is a real but separate tool, out of scope
 * for a hand-rolled scaffolding script).
 * @returns {string}
 */
export function generateSchemaDocumentation() {
  const lines = [
    "# Canonical Evidence Core  -  Generated Schema Reference",
    "",
    "_Generated by `schema.js#generateSchemaDocumentation()`  -  do not hand-edit; regenerate",
    "instead. Field-level prose documentation lives in `entity.js`'s JSDoc, not here._",
    "",
    "## Version history",
    "",
    "| Version | Stage | Change | Backward compatible with previous |",
    "|---|---|---|---|",
  ];
  for (const entry of SCHEMA_VERSION_HISTORY) {
    lines.push(
      `| \`${entry.version}\` | ${entry.stage} | ${entry.change} | ${
        entry.backwardCompatibleWithPrevious === null ? " - " : entry.backwardCompatibleWithPrevious
      } |`
    );
  }
  lines.push("", "## Field groups", "");
  for (const [groupName, fields] of Object.entries(FIELD_GROUPS)) {
    lines.push(`### ${groupName}`, "");
    for (const field of fields) lines.push(`- \`${field}\``);
    lines.push("");
  }
  return lines.join("\n");
}
