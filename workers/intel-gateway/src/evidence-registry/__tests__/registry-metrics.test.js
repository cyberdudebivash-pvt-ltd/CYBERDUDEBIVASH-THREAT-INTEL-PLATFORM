import assert from "node:assert/strict";
import { test } from "node:test";
import { EvidenceRegistryMetrics } from "../registry-metrics.js";

test("snapshot starts all-zero / all-empty", () => {
  const metrics = new EvidenceRegistryMetrics();
  assert.deepEqual(metrics.snapshot(), {
    evidence_count: 0,
    lifecycle_transitions: 0,
    lifecycle_transitions_by_type: {},
    validation_failures: 0,
    version_updates: 0,
    migration_events: 0,
    adapter_usage: {},
    feature_flag_activations: {},
  });
});

test("recordEvidenceCountDelta increments and decrements", () => {
  const metrics = new EvidenceRegistryMetrics();
  metrics.recordEvidenceCountDelta(1);
  metrics.recordEvidenceCountDelta(1);
  metrics.recordEvidenceCountDelta(-1);
  assert.equal(metrics.snapshot().evidence_count, 1);
});

test("recordLifecycleTransition tallies total and by-transition-type", () => {
  const metrics = new EvidenceRegistryMetrics();
  metrics.recordLifecycleTransition("DRAFT", "COLLECTED");
  metrics.recordLifecycleTransition("DRAFT", "COLLECTED");
  metrics.recordLifecycleTransition("COLLECTED", "VALIDATED");
  const snap = metrics.snapshot();
  assert.equal(snap.lifecycle_transitions, 3);
  assert.deepEqual(snap.lifecycle_transitions_by_type, {
    "DRAFT->COLLECTED": 2,
    "COLLECTED->VALIDATED": 1,
  });
});

test("recordValidationFailure / recordVersionUpdate counters", () => {
  const metrics = new EvidenceRegistryMetrics();
  metrics.recordValidationFailure();
  metrics.recordValidationFailure();
  metrics.recordVersionUpdate();
  const snap = metrics.snapshot();
  assert.equal(snap.validation_failures, 2);
  assert.equal(snap.version_updates, 1);
});

test("recordMigrationEvent tallies total and per-adapter usage", () => {
  const metrics = new EvidenceRegistryMetrics();
  metrics.recordMigrationEvent("p20-evidence-chain");
  metrics.recordMigrationEvent("p20-evidence-chain");
  metrics.recordMigrationEvent("p-layer-report-item");
  const snap = metrics.snapshot();
  assert.equal(snap.migration_events, 3);
  assert.deepEqual(snap.adapter_usage, { "p20-evidence-chain": 2, "p-layer-report-item": 1 });
});

test("recordFeatureFlagActivation tallies per-flag activation counts", () => {
  const metrics = new EvidenceRegistryMetrics();
  metrics.recordFeatureFlagActivation("EER_ENABLED");
  metrics.recordFeatureFlagActivation("EER_ENABLED");
  assert.deepEqual(metrics.snapshot().feature_flag_activations, { EER_ENABLED: 2 });
});

test("snapshot() returns a copy  -  mutating it does not affect the live counters", () => {
  const metrics = new EvidenceRegistryMetrics();
  metrics.recordEvidenceCountDelta(1);
  const snap = metrics.snapshot();
  snap.evidence_count = 999;
  snap.adapter_usage.tampered = 1;
  assert.equal(metrics.snapshot().evidence_count, 1);
  assert.deepEqual(metrics.snapshot().adapter_usage, {});
});
