/**
 * Performance smoke test  -  Stage 10 Phase 9. Not a benchmark suite (no statistical rigor
 * claimed); a smoke test whose only job is to catch a pathological regression (e.g. an
 * accidentally-quadratic loop) before it ships, matching this platform's Level 6 (Performance)
 * priority. Thresholds are generous on purpose  -  this is a Cloudflare Worker cold-start
 * context (CLAUDE.md: cold start < 50ms budget for the *whole request*), so pure in-memory
 * object construction/validation/serialization for a few thousand records must be a rounding
 * error against that budget, not a meaningful fraction of it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { publishEvidenceEntity } from "../entity.js";
import { P20EvidenceChainAdapter } from "../migration-adapters.js";
import { JsonEvidenceSerializer } from "../serialization.js";
import { validateCanonicalEvidence, validateEvidenceBatch } from "../validation.js";

const N = 2000;
const BUDGET_MS = 500; // generous; real cost should be a small fraction of this

test(`smoke: construct + adapt + validate + serialize + publish ${N} records within budget`, () => {
  const adapter = new P20EvidenceChainAdapter();
  const serializer = new JsonEvidenceSerializer();
  const start = performance.now();

  const records = [];
  for (let i = 0; i < N; i += 1) {
    // P20EvidenceChainAdapter.adapt() already returns a full CanonicalEvidence (it composes
    // createCanonicalEvidence internally)  -  evidence_uuid isn't part of the P20 evidence_chain
    // shape it adapts from, so identity assignment happens as a separate, explicit step here,
    // the same way a real caller would attach an identity after adapting legacy data.
    const evidence = {
      ...adapter.adapt({
        evidence_id: `EV-${i}`,
        reliability_code: "B",
        iq_breakdown: { source: i % 100, enrichment: 50, attribution: 30, corroboration: 10 },
      }),
      evidence_uuid: `11111111-1111-4111-8111-${String(i).padStart(12, "0")}`,
      related_cves: [`CVE-2026-${i}`],
    };
    const { valid, errors } = validateCanonicalEvidence(evidence);
    assert.equal(valid, true, `record ${i} unexpectedly invalid: ${errors.join(", ")}`);
    serializer.serialize(evidence);
    records.push(publishEvidenceEntity(evidence));
  }

  const batchResult = validateEvidenceBatch(records);
  assert.equal(batchResult.valid, true, JSON.stringify(batchResult.errors));

  const elapsedMs = performance.now() - start;
  assert.ok(
    elapsedMs < BUDGET_MS,
    `processing ${N} records took ${elapsedMs.toFixed(1)}ms, exceeding the ${BUDGET_MS}ms smoke-test budget`
  );
});
