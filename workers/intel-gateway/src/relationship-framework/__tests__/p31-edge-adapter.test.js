import assert from "node:assert/strict";
import { test } from "node:test";
import { isP31EdgeShape, adaptP31EdgeToRepositoryShape, adaptP31EdgeBatch, adaptEdgeToProviderShape } from "../p31-edge-adapter.js";

// Fixture matching R1's exact documented shape -- verified against p31-handlers.js's own
// addEdge()/handleP31Relationships() source, not invented independently.
const REAL_SHAPE_EDGE = {
  source: "advisory:CVE-2026-0001",
  target: "actor:fin7",
  relation: "attributed_to",
  confidence: 0.85,
  evidence: "CVSS: 9.1 | Source: CISA",
  verified: true,
};

test("isP31EdgeShape accepts a real-shaped edge", () => {
  assert.equal(isP31EdgeShape(REAL_SHAPE_EDGE), true);
});

test("isP31EdgeShape rejects missing/wrong-typed fields", () => {
  assert.equal(isP31EdgeShape(null), false);
  assert.equal(isP31EdgeShape({}), false);
  assert.equal(isP31EdgeShape({ source: "a", target: "b" }), false); // missing relation/confidence
  assert.equal(isP31EdgeShape({ source: "a", target: "b", relation: "x", confidence: "high" }), false); // wrong type
});

test("adaptP31EdgeToRepositoryShape passes through a well-formed edge, defaulting verified from confidence", () => {
  const adapted = adaptP31EdgeToRepositoryShape({ source: "a", target: "b", relation: "REFERENCES", confidence: 0.8 });
  assert.equal(adapted.verified, true); // 0.8 >= 0.75, matches R1's own convention
  assert.equal(adapted.evidence, "");
});

test("adaptP31EdgeToRepositoryShape throws on a malformed edge rather than silently coercing", () => {
  assert.throws(() => adaptP31EdgeToRepositoryShape({ source: "a" }), /does not match R1's documented edge shape/);
});

test("adaptP31EdgeBatch tolerates malformed elements, reporting skipped count instead of throwing", () => {
  const { adapted, skipped } = adaptP31EdgeBatch([REAL_SHAPE_EDGE, { garbage: true }, { source: "x", target: "y", relation: "MENTIONS", confidence: 0.4 }]);
  assert.equal(adapted.length, 2);
  assert.equal(skipped, 1);
});

test("adaptP31EdgeBatch on an empty/undefined input returns an empty result, not throw", () => {
  assert.deepEqual(adaptP31EdgeBatch(undefined), { adapted: [], skipped: 0 });
  assert.deepEqual(adaptP31EdgeBatch([]), { adapted: [], skipped: 0 });
});

test("adaptEdgeToProviderShape picks the OTHER end of the edge as relatedEntityId, from the source side", () => {
  const result = adaptEdgeToProviderShape(REAL_SHAPE_EDGE, "advisory:CVE-2026-0001");
  assert.equal(result.relatedEntityId, "actor:fin7");
  assert.equal(result.relationshipType, "attributed_to");
  assert.equal(result.confidence, 0.85);
});

test("adaptEdgeToProviderShape picks the OTHER end of the edge as relatedEntityId, from the target side", () => {
  const result = adaptEdgeToProviderShape(REAL_SHAPE_EDGE, "actor:fin7");
  assert.equal(result.relatedEntityId, "advisory:CVE-2026-0001");
});
