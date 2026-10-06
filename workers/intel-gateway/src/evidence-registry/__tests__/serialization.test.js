import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import {
  DefaultEvidenceExporter,
  DefaultEvidenceImporter,
  DtoEvidenceSerializer,
  JsonEvidenceSerializer,
  MarkdownEvidenceSerializer,
  getSerializer,
} from "../serialization.js";

function sampleEvidence() {
  return createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: "EV-100", reliability_code: "A" }, { evidence_uuid: "11111111-1111-4111-8111-111111111111" }),
    { evidence_type: "OSINT", related_cves: ["CVE-2026-1234"] }
  );
}

test("JsonEvidenceSerializer round-trips a CanonicalEvidence exactly", () => {
  const evidence = sampleEvidence();
  const serializer = new JsonEvidenceSerializer();
  const json = serializer.serialize(evidence);
  const roundTripped = serializer.deserialize(json);
  // JSON has no `undefined`  -  plain JSON.stringify (which this serializer intentionally uses,
  // per its own docstring: "no custom reviver/replacer") omits any key whose value is
  // `undefined` (e.g. optional CanonicalEvidence fields sampleEvidence() leaves unset). That's
  // JSON's own behavior, not a defect in this serializer, so the correct round-trip comparison
  // is against what JSON itself can represent, not the pre-serialization object.
  assert.deepEqual(roundTripped, JSON.parse(JSON.stringify(evidence)));
});

test("MarkdownEvidenceSerializer produces readable output and refuses to round-trip", () => {
  const evidence = sampleEvidence();
  const serializer = new MarkdownEvidenceSerializer();
  const markdown = serializer.serialize(evidence);
  assert.match(markdown, /## Evidence 11111111-1111-4111-8111-111111111111/);
  assert.match(markdown, /OSINT/);
  assert.match(markdown, /CVE-2026-1234/);
  assert.throws(() => serializer.deserialize(markdown), /intentionally unimplemented/);
});

test("DtoEvidenceSerializer round-trips via structural equality (not reference equality)", () => {
  const evidence = sampleEvidence();
  const serializer = new DtoEvidenceSerializer();
  const dto = serializer.serialize(evidence);
  assert.notEqual(dto, evidence, "must be a copy, not the same reference");
  assert.deepEqual(dto, evidence);
});

test("getSerializer: stix and api are named future capabilities, not silently missing", () => {
  assert.throws(() => getSerializer("stix"), /Future stix compatibility/);
  assert.throws(() => getSerializer("api"), /Future api compatibility/);
});

test("getSerializer: unknown format lists what is and isn't supported", () => {
  assert.throws(() => getSerializer("xml"), /Unknown serialization format/);
});

test("DefaultEvidenceImporter: imports valid JSON and surfaces validation warnings", async () => {
  const evidence = createCanonicalEvidence(createEvidenceEntity({}), {
    related_cves: ["CVE-1", "CVE-1"], // duplicate -> warning, still valid
  });
  const importer = new DefaultEvidenceImporter();
  const { imported, warnings } = await importer.import(JSON.stringify(evidence));
  assert.equal(imported.related_cves.length, 2);
  assert.equal(warnings.length, 1);
});

test("DefaultEvidenceImporter: rejects structurally invalid evidence", async () => {
  const invalid = JSON.stringify({ visibility: "NOT_A_REAL_LEVEL" });
  const importer = new DefaultEvidenceImporter();
  await assert.rejects(() => importer.import(invalid), /Cannot import invalid evidence/);
});

test("DefaultEvidenceExporter: exports an array to JSON and Markdown", async () => {
  const exporter = new DefaultEvidenceExporter();
  const evidences = [sampleEvidence(), sampleEvidence()];

  const json = await exporter.export(evidences, "json");
  const parsed = JSON.parse(json);
  assert.equal(parsed.length, 2);

  const markdown = await exporter.export(evidences, "markdown");
  assert.equal(markdown.split("\n\n---\n\n").length, 2);
});
