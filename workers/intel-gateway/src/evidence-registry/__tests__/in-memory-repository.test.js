import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import {
  DuplicateEvidenceError,
  EvidenceNotFoundError,
  InMemoryEvidenceRepository,
} from "../in-memory-repository.js";

function evidence(uuid, extra = {}) {
  return createCanonicalEvidence(createEvidenceEntity({ evidence_id: `EC-${uuid}` }, { evidence_uuid: uuid }), extra);
}

test("create + get: round-trips a new record", async () => {
  const repo = new InMemoryEvidenceRepository();
  const e = evidence("u1");
  await repo.create(e);
  assert.deepEqual(await repo.get("u1"), e);
});

test("create: rejects a duplicate evidence_uuid", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1"));
  await assert.rejects(() => repo.create(evidence("u1")), DuplicateEvidenceError);
});

test("get: returns null for an unknown uuid", async () => {
  const repo = new InMemoryEvidenceRepository();
  assert.equal(await repo.get("nope"), null);
});

test("put: upserts the current record without touching version history", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.put(evidence("u1", { version: 1 }));
  await repo.put(evidence("u1", { version: 5 })); // put does not increment -- caller controls version
  assert.equal((await repo.get("u1")).version, 5);
  assert.deepEqual(await repo.getVersionHistory("u1"), [await repo.get("u1")]);
});

test("findByContentHash: finds a matching current record", async () => {
  const repo = new InMemoryEvidenceRepository();
  const e = createCanonicalEvidence(
    createEvidenceEntity({}, { evidence_uuid: "u1", content_hash: "abc123" })
  );
  await repo.create(e);
  const found = await repo.findByContentHash("abc123");
  assert.equal(found.evidence_uuid, "u1");
  assert.equal(await repo.findByContentHash("does-not-exist"), null);
});

test("delete: hard-removes current and history", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1"));
  assert.equal(await repo.delete("u1"), true);
  assert.equal(await repo.get("u1"), null);
  assert.deepEqual(await repo.getVersionHistory("u1"), []);
  assert.equal(await repo.delete("u1"), false);
});

test("update: bumps version, freezes the prior version into history, preserves identity", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { version: 1, evidence_category: "INDICATOR" }));
  const updated = await repo.update("u1", { evidence_category: "NARRATIVE" });

  assert.equal(updated.version, 2);
  assert.equal(updated.evidence_category, "NARRATIVE");
  assert.equal(updated.evidence_uuid, "u1", "identity must not be patchable");

  const history = await repo.getVersionHistory("u1");
  assert.equal(history.length, 2);
  assert.equal(history[0].version, 1);
  assert.equal(history[0].evidence_category, "INDICATOR");
  assert.ok(Object.isFrozen(history[0]), "historical version must be immutable");
  assert.throws(() => {
    history[0].evidence_category = "TAMPERED";
  }, TypeError);
});

test("update: rejects an unknown uuid", async () => {
  const repo = new InMemoryEvidenceRepository();
  await assert.rejects(() => repo.update("nope", {}), EvidenceNotFoundError);
});

test("update: an entity.version left undefined does not crash version arithmetic (falsy-zero safe)", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { version: 0 }));
  const updated = await repo.update("u1", {});
  assert.equal(updated.version, 1, "version 0 -> next version 1, not NaN or 0 again");
});

test("supersede: moves current into history with superseded_at, installs new current", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { version: 1 }));
  const superseding = await repo.supersede("u1", { evidence_category: "CORRECTED" });

  assert.equal(superseding.version, 2);
  const history = await repo.getVersionHistory("u1");
  assert.equal(history.length, 2);
  assert.ok(history[0].superseded_at, "superseded predecessor must carry a superseded_at timestamp");
  assert.ok(Object.isFrozen(history[0]));
});

test("supersede: rejects an unknown uuid", async () => {
  const repo = new InMemoryEvidenceRepository();
  await assert.rejects(() => repo.supersede("nope", {}), EvidenceNotFoundError);
});

test("archive: keeps the record current and retrievable (soft delete, not hard delete)", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1"));
  const archived = await repo.archive("u1");
  assert.equal(archived.evidence_uuid, "u1");
  assert.deepEqual(await repo.get("u1"), archived);
});

test("archive: rejects an unknown uuid", async () => {
  const repo = new InMemoryEvidenceRepository();
  await assert.rejects(() => repo.archive("nope"), EvidenceNotFoundError);
});

test("lookup: exact-match filter across multiple criteria fields", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1", { evidence_type: "OSINT", visibility: "INTERNAL" }));
  await repo.create(evidence("u2", { evidence_type: "OSINT", visibility: "RESTRICTED" }));
  await repo.create(evidence("u3", { evidence_type: "TECHNICAL_ARTIFACT", visibility: "INTERNAL" }));

  const results = await repo.lookup({ evidence_type: "OSINT", visibility: "INTERNAL" });
  assert.equal(results.length, 1);
  assert.equal(results[0].evidence_uuid, "u1");
});

test("bulkImport: imports new records, skips duplicates and malformed entries with reasons", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1"));

  const result = await repo.bulkImport([evidence("u1"), evidence("u2"), { no_uuid: true }]);
  assert.equal(result.imported, 1);
  assert.equal(result.skipped, 2);
  assert.equal(result.errors.length, 2);
  assert.equal(await repo.get("u2") !== null, true);
});

test("bulkExport: returns every current record", async () => {
  const repo = new InMemoryEvidenceRepository();
  await repo.create(evidence("u1"));
  await repo.create(evidence("u2"));
  const exported = await repo.bulkExport();
  assert.equal(exported.length, 2);
  assert.deepEqual(
    exported.map((e) => e.evidence_uuid).sort(),
    ["u1", "u2"]
  );
});

test("getVersionHistory: unknown uuid returns an empty array, not an error", async () => {
  const repo = new InMemoryEvidenceRepository();
  assert.deepEqual(await repo.getVersionHistory("nope"), []);
});
