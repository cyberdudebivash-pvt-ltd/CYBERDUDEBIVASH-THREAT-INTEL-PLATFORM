import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipMetricsService } from "../relationship-metrics.js";

test("snapshot starts at all-zero/empty state", () => {
  const snapshot = new RelationshipMetricsService().snapshot();
  assert.deepEqual(snapshot.traversal_latency_stats, {});
  assert.deepEqual(snapshot.correlation_counts, {});
  assert.equal(snapshot.validation_failures, 0);
  assert.equal(snapshot.confidence_propagations, 0);
  assert.equal(snapshot.average_propagated_confidence, null);
  assert.equal(snapshot.resolutions_via_provider, 0);
});

test("recordTraversalLatency accumulates and computes stats correctly", () => {
  const metrics = new RelationshipMetricsService();
  metrics.recordTraversalLatency("traverse", 10);
  metrics.recordTraversalLatency("traverse", 20);
  metrics.recordTraversalLatency("traverse", 30);
  const stats = metrics.snapshot().traversal_latency_stats.traverse;
  assert.equal(stats.count, 3);
  assert.equal(stats.mean_ms, 20);
  assert.equal(stats.max_ms, 30);
});

test("recordCorrelation increments per-dimension counts independently", () => {
  const metrics = new RelationshipMetricsService();
  metrics.recordCorrelation("relationship");
  metrics.recordCorrelation("relationship");
  metrics.recordCorrelation("evidence");
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.correlation_counts.relationship, 2);
  assert.equal(snapshot.correlation_counts.evidence, 1);
});

test("recordValidationFailure tracks total and per-reason breakdown; reason is optional", () => {
  const metrics = new RelationshipMetricsService();
  metrics.recordValidationFailure("SELF_LOOP");
  metrics.recordValidationFailure("SELF_LOOP");
  metrics.recordValidationFailure();
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.validation_failures, 3);
  assert.equal(snapshot.validation_failures_by_reason.SELF_LOOP, 2);
});

test("recordConfidencePropagation computes a correct running average", () => {
  const metrics = new RelationshipMetricsService();
  metrics.recordConfidencePropagation(0.8);
  metrics.recordConfidencePropagation(0.4);
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.confidence_propagations, 2);
  assert.equal(snapshot.average_propagated_confidence, 0.6);
});

test("recordResolutionViaProvider increments independently of other counters", () => {
  const metrics = new RelationshipMetricsService();
  metrics.recordResolutionViaProvider();
  metrics.recordResolutionViaProvider();
  assert.equal(metrics.snapshot().resolutions_via_provider, 2);
});

test("snapshot() returns a plain copy -- mutating it does not affect the live service", () => {
  const metrics = new RelationshipMetricsService();
  const snapshot = metrics.snapshot();
  snapshot.validation_failures = 999;
  assert.equal(metrics.snapshot().validation_failures, 0);
});
