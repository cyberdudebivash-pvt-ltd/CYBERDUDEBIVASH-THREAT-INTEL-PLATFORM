/**
 * Canonical Evidence Core serialization  -  Stage 10 Phase 5 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Supports JSON, Markdown, and an internal DTO (plain object, already the entity's own
 * shape  -  no transformation needed, documented as its own format for interface completeness).
 * STIX and public-API serialization are explicitly stubbed, not implemented  -  Phase 5's own
 * instruction is "Future STIX compatibility, Future API compatibility... Do not expose public
 * APIs yet." A stub that throws a clear, dated message is preferred over silently omitting
 * the format (Observable Everything: a caller finds out why, not just that it failed).
 */

import { EvidenceExporterInterface, EvidenceImporterInterface, EvidenceSerializerInterface } from "./interfaces.js";
import { validateCanonicalEvidence } from "./validation.js";

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

export const SUPPORTED_SERIALIZATION_FORMATS = Object.freeze(["json", "markdown", "dto"]);
export const FUTURE_SERIALIZATION_FORMATS = Object.freeze(["stix", "api"]);

const NOT_YET_AUTHORIZED = (format) =>
  `${format} serialization is a named future capability (Stage 10 Phase 5: "Future ${format} ` +
  "compatibility\"), not implemented this stage. Requesting it is not a bug in the caller  -  it " +
  "means this capability hasn't been built yet, and building it is out of this stage's scope.";

/**
 * Default JSON implementation of EvidenceSerializerInterface. Plain JSON.stringify/parse  - 
 * no custom reviver/replacer, since CanonicalEvidence is already a plain-data shape (no
 * class instances, no circular references) by construction (createCanonicalEvidence() in
 * entity.js only ever returns plain objects).
 */
export class JsonEvidenceSerializer extends EvidenceSerializerInterface {
  /**
   * @param {CanonicalEvidence} entity
   * @returns {string}
   */
  serialize(entity) {
    return JSON.stringify(entity, null, 2);
  }

  /**
   * @param {string} payload
   * @returns {CanonicalEvidence}
   */
  deserialize(payload) {
    return JSON.parse(payload);
  }
}

/**
 * Default Markdown implementation  -  a human-readable rendering, not intended to round-trip
 * (deserialize() throws; Markdown is a presentation format here, matching this platform's
 * existing report-generation convention of Markdown as an output-only format).
 */
export class MarkdownEvidenceSerializer extends EvidenceSerializerInterface {
  /**
   * @param {CanonicalEvidence} entity
   * @returns {string}
   */
  serialize(entity) {
    const lines = [
      `## Evidence ${entity.evidence_uuid || entity.evidence_id || "(no identifier)"}`,
      "",
      `- **Type:** ${entity.evidence_type || "_unclassified_"}`,
      `- **Category:** ${entity.evidence_category || "_unclassified_"}`,
      `- **Visibility:** ${entity.visibility || "INTERNAL"}`,
      `- **TLP:** ${entity.tlp_classification || "_unset_"}`,
      `- **Source:** ${entity.source_name || entity.source_id || "_unattributed_"} (${entity.source_category || "unknown category"})`,
      `- **Reliability:** ${entity.reliability_code || "_unrated_"}  -  ${entity.source_reliability || ""}`,
      `- **Verification status:** ${entity.verification_status || "UNVERIFIED"}`,
      `- **Schema version:** ${entity.schema_version || "_unversioned_"}`,
    ];
    if (entity.known_limitations && entity.known_limitations.length > 0) {
      lines.push("", "**Known limitations:**");
      for (const limitation of entity.known_limitations) lines.push(`- ${limitation}`);
    }
    const relatedFieldLabels = {
      related_reports: "Related reports",
      related_cves: "Related CVEs",
      related_threat_actors: "Related threat actors",
      related_campaigns: "Related campaigns",
      related_attack_techniques: "Related ATT&CK techniques",
    };
    for (const [field, label] of Object.entries(relatedFieldLabels)) {
      const values = entity[field];
      if (values && values.length > 0) {
        lines.push("", `**${label}:** ${values.join(", ")}`);
      }
    }
    return lines.join("\n");
  }

  /**
   * @param {string} _payload
   * @returns {never}
   */
  deserialize(_payload) {
    throw new Error(
      "MarkdownEvidenceSerializer.deserialize is intentionally unimplemented  -  Markdown is an " +
        "output-only presentation format in this scaffolding, matching this platform's existing " +
        "report-generation convention. Use JsonEvidenceSerializer or DtoEvidenceSerializer to " +
        "round-trip."
    );
  }
}

/**
 * Default "internal DTO" implementation  -  CanonicalEvidence's own in-memory shape IS the DTO;
 * this class exists so "internal DTO" is a real, addressable format (per Phase 5's own list)
 * rather than an implicit assumption, and so a future caller has one obvious place to look.
 */
export class DtoEvidenceSerializer extends EvidenceSerializerInterface {
  /** @param {CanonicalEvidence} entity @returns {CanonicalEvidence} */
  serialize(entity) {
    return { ...entity };
  }

  /** @param {CanonicalEvidence} dto @returns {CanonicalEvidence} */
  deserialize(dto) {
    return { ...dto };
  }
}

/**
 * @param {string} format
 * @returns {EvidenceSerializerInterface}
 */
export function getSerializer(format) {
  switch (format) {
    case "json":
      return new JsonEvidenceSerializer();
    case "markdown":
      return new MarkdownEvidenceSerializer();
    case "dto":
      return new DtoEvidenceSerializer();
    case "stix":
    case "api":
      throw new Error(NOT_YET_AUTHORIZED(format));
    default:
      throw new Error(
        `Unknown serialization format "${format}". Supported: ${SUPPORTED_SERIALIZATION_FORMATS.join(", ")}. ` +
          `Named future formats (not yet implemented): ${FUTURE_SERIALIZATION_FORMATS.join(", ")}.`
      );
  }
}

/**
 * Default EvidenceImporter: deserialize (JSON only  -  the only round-trippable format) then
 * validate. Composes JsonEvidenceSerializer + validateCanonicalEvidence rather than
 * reimplementing either.
 */
export class DefaultEvidenceImporter extends EvidenceImporterInterface {
  constructor() {
    super();
    this._serializer = new JsonEvidenceSerializer();
  }

  /**
   * @param {string} payload
   * @param {{sourceTrust?: number}} [_opts] - reserved for a future weighting scheme; unused
   *   this stage, kept in the signature so callers written against this interface today don't
   *   need to change when it's implemented
   * @returns {Promise<{imported: CanonicalEvidence, warnings: string[]}>}
   */
  async import(payload, _opts = {}) {
    const entity = this._serializer.deserialize(payload);
    const result = validateCanonicalEvidence(entity);
    if (!result.valid) {
      throw new Error(`Cannot import invalid evidence: ${result.errors.join("; ")}`);
    }
    return { imported: entity, warnings: result.warnings };
  }
}

/** Default EvidenceExporter: delegates to getSerializer() per requested format. */
export class DefaultEvidenceExporter extends EvidenceExporterInterface {
  /**
   * @param {CanonicalEvidence[]} entities
   * @param {"json"|"markdown"} format
   * @returns {Promise<string>}
   */
  async export(entities, format) {
    const serializer = getSerializer(format);
    if (format === "json") {
      return JSON.stringify(entities.map((e) => JSON.parse(serializer.serialize(e))), null, 2);
    }
    return entities.map((e) => serializer.serialize(e)).join("\n\n---\n\n");
  }
}
