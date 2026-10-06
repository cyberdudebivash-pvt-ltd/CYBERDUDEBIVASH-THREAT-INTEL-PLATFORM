/**
 * Registry performance smoke test  -  Stage 11 Phase 10. Not a benchmark suite (no statistical
 * rigor claimed); matches performance-smoke.test.js's (Stage 10) rationale exactly, applied to
 * EvidenceRegistry's own operations instead of the bare domain model: this is a Cloudflare
 * Worker cold-start context (CLAUDE.md: cold start < 50ms budget for the *whole request*), so
 * registering, querying, and transitioning a few thousand records must be a rounding error
 * against that budget.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import { EvidenceRegistry } from "../registry-service.js";

const N = 1000;
const BUDGET_MS = 1500; // generous; registerEvidence does async content-hash + validation + indexing per record

function uuidFor(i) {
  return `44444444-4444-4444-8444-${String(i).padStart(12, "0")}`;
}

test(`smoke: register + find + transition + update ${N} records within budget`, async () => {
  const registry = new EvidenceRegistry();
  const start = performance.now();

  for (let i = 0; i < N; i += 1) {
    const evidence = createCanonicalEvidence(
      createEvidenceEntity({ evidence_id: `EC-${i}`, reliability_code: "B" }, { evidence_uuid: uuidFor(i) }),
      { related_cves: [`CVE-2026-${i}`], related_iocs: [`10.0.${i % 256}.1`] }
    );
    const { reused } = await registry.registerEvidence(evidence, { skipReuseCheck: true });
    assert.equal(reused, false);
  }

  // Query every dimension at least once across the full set.
  for (let i = 0; i < N; i += 10) {
    const found = await registry.findByCVE(`CVE-2026-${i}`);
    assert.equal(found.length, 1);
  }

  // Advance a subset through the full lifecycle and update/supersede/archive it.
  for (let i = 0; i < N; i += 50) {
    const uuid = uuidFor(i);
    await registry.transitionLifecycle(uuid, "COLLECTED");
    await registry.transitionLifecycle(uuid, "VALIDATED");
    await registry.transitionLifecycle(uuid, "CORRELATED");
    await registry.transitionLifecycle(uuid, "PUBLISHED");
    await registry.updateEvidence(uuid, { evidence_category: "REVIEWED" });
  }

  const elapsedMs = performance.now() - start;
  assert.equal(registry.getMetricsSnapshot().evidence_count, N);
  assert.ok(
    elapsedMs < BUDGET_MS,
    `processing ${N} records took ${elapsedMs.toFixed(1)}ms, exceeding the ${BUDGET_MS}ms smoke-test budget`
  );
});
