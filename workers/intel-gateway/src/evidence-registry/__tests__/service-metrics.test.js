import assert from "node:assert/strict";
import { test } from "node:test";
import { ServicePlatformMetrics } from "../service-metrics.js";

test("timed() records call count and latency for both successful and failing operations", async () => {
  const metrics = new ServicePlatformMetrics();
  await metrics.timed("op.success", async () => "ok");
  await assert.rejects(() => metrics.timed("op.failure", async () => {
    throw new Error("boom");
  }));

  const snapshot = metrics.snapshot();
  assert.equal(snapshot.call_counts["op.success"], 1);
  assert.equal(snapshot.call_counts["op.failure"], 1, "a failed operation is still counted -- it still consumed time");
  assert.ok(snapshot.call_latency_stats["op.success"], "latency must be recorded even for a near-instant call");
  assert.ok(snapshot.call_latency_stats["op.failure"], "latency must be recorded for the failing call too");
});

test("_latencyStats computes count/mean/p50/p95/max correctly for a known sample set", async () => {
  const metrics = new ServicePlatformMetrics();
  for (const ms of [10, 20, 30, 40, 50]) {
    // eslint-disable-next-line no-await-in-loop
    await metrics.timed("op.fixed", () => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  const stats = metrics.snapshot().call_latency_stats["op.fixed"];
  assert.equal(stats.count, 5);
  assert.ok(stats.mean_ms >= 0);
  assert.ok(stats.max_ms >= stats.p95_ms);
  assert.ok(stats.p95_ms >= stats.p50_ms);
});

test("recordQuery/recordProvenanceLookup bucket by the given key independently", () => {
  const metrics = new ServicePlatformMetrics();
  metrics.recordQuery("cve");
  metrics.recordQuery("cve");
  metrics.recordQuery("uuid");
  metrics.recordProvenanceLookup("version");
  const snapshot = metrics.snapshot();
  assert.deepEqual(snapshot.query_counts, { cve: 2, uuid: 1 });
  assert.deepEqual(snapshot.provenance_lookups, { version: 1 });
});

test("recordRelationshipResolution tracks both attempts and failures distinctly", () => {
  const metrics = new ServicePlatformMetrics();
  metrics.recordRelationshipResolution(true);
  metrics.recordRelationshipResolution(false);
  metrics.recordRelationshipResolution(true);
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.relationship_resolutions, 3);
  assert.equal(snapshot.relationship_resolution_failures, 1);
});

test("snapshot() returns a fresh plain object each call -- mutating it must not affect subsequent snapshots", () => {
  const metrics = new ServicePlatformMetrics();
  metrics.recordValidationFailure();
  const first = metrics.snapshot();
  first.validation_failures = 999;
  const second = metrics.snapshot();
  assert.equal(second.validation_failures, 1, "returned snapshot must be a copy, not a live reference");
});
