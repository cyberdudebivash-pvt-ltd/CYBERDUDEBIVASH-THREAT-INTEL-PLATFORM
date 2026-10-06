import assert from "node:assert/strict";
import { test } from "node:test";
import { CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION, createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import { InMemoryEvidenceRepository } from "../in-memory-repository.js";
import { EvidenceVersionManager } from "../versioning.js";

function evidence(uuid, extra = {}) {
  return createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: uuid }), extra);
}

test("getCurrentVersion delegates to the repository's get()", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1"));
  const versions = new EvidenceVersionManager(repo);
  assert.deepEqual(await versions.getCurrentVersion("u1"), await repo.get("u1"));
});

test("getVersionLineage / getHistoricalVersions / getSupersededVersions after update + supersede", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { version: 1 }));
  await repo.update("u1", {}); // -> version 2
  await repo.supersede("u1", {}); // -> version 3, version 2 gets superseded_at

  const versions = new EvidenceVersionManager(repo);
  const lineage = await versions.getVersionLineage("u1");
  assert.deepEqual(lineage.map((v) => v.version), [1, 2, 3]);

  const historical = await versions.getHistoricalVersions("u1");
  assert.deepEqual(historical.map((v) => v.version), [1, 2]);

  const superseded = await versions.getSupersededVersions("u1");
  assert.deepEqual(superseded.map((v) => v.version), [2]);
});

test("resolveVersion finds a specific version number or returns null", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { version: 1 }));
  await repo.update("u1", {});
  const versions = new EvidenceVersionManager(repo);

  assert.equal((await versions.resolveVersion("u1", 1)).version, 1);
  assert.equal((await versions.resolveVersion("u1", 2)).version, 2);
  assert.equal(await versions.resolveVersion("u1", 99), null);
});

test("checkSchemaCompatibility: current schema version is forward- and backward-compatible with itself", async () => {
  const repo = new InMemoryEvidenceRepository();
  const versions = new EvidenceVersionManager(repo);
  const e = evidence("u1");
  const result = versions.checkSchemaCompatibility(e);
  assert.equal(result.recordSchemaVersion, CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION);
  assert.equal(result.isForwardCompatible, true);
  assert.equal(result.isBackwardCompatible, true);
});

test("checkSchemaCompatibility: Stage 8's original schema version is forward-compatible (additive history)", async () => {
  const repo = new InMemoryEvidenceRepository();
  const versions = new EvidenceVersionManager(repo);
  const e = { ...evidence("u1"), schema_version: "evidence-registry.0.1-scaffolding" };
  const result = versions.checkSchemaCompatibility(e);
  assert.equal(result.isForwardCompatible, true);
});

test("migrateIfNeeded: returns forward-compatible evidence unchanged", async () => {
  const repo = new InMemoryEvidenceRepository();
  const versions = new EvidenceVersionManager(repo);
  const e = evidence("u1");
  assert.equal(versions.migrateIfNeeded(e), e);
});

test("migrateIfNeeded: throws a labelled error for an unrecognized schema_version rather than guessing", async () => {
  const repo = new InMemoryEvidenceRepository();
  const versions = new EvidenceVersionManager(repo);
  const e = { ...evidence("u1"), schema_version: "some-future-incompatible-version" };
  assert.throws(() => versions.migrateIfNeeded(e), /not forward-compatible/);
});

test("getVersionLineage entries beyond the current one remain frozen (immutable lineage)", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { version: 1 }));
  await repo.update("u1", {});
  const versions = new EvidenceVersionManager(repo);
  const [first] = await versions.getVersionLineage("u1");
  assert.ok(Object.isFrozen(first));
});
