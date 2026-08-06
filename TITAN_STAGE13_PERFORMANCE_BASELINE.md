# Project TITAN Stage 13 — Performance Baseline (Phase 9)

**Program:** Project TITAN, Stage 13 (Enterprise Intelligence Platform Services)
**Scope:** `workers/intel-gateway/src/intelligence-platform/` — the Stage 13 orchestration layer
composed on top of Stage 12's Enterprise Evidence Service Platform (EESP).

## Methodology

Stage 12's `evidence-registry/__tests__/service-performance-smoke.test.js` already benchmarks
the registry/query/provenance layer Stage 13 composes. This document measures ONLY what Stage 13
adds on top of that already-benchmarked substrate — service composition (the DI graph), the
unified lookup surface, correlation, bundle validation, and the shared metrics instance's own
call overhead — so the numbers below are Stage 13's *incremental* cost, not a re-measurement of
Stage 12's.

Source: `workers/intel-gateway/src/intelligence-platform/__tests__/service-performance-smoke.test.js`
(`node --test`, no statistical rigor claimed — a smoke test with a wall-clock budget per
category, matching this platform's existing convention, not a profiler). Numbers below are
measured, not estimated, from three consecutive runs in this environment; a representative value
and the observed range are both recorded since wall-clock smoke tests carry normal environment
variance.

Every operation is measured against a live `EvidenceRegistry`/`EvidenceService` instance with
1,000 registered `CanonicalEvidence` records (matching Stage 12's own `N = 1000` convention), not
mocks.

## Results

| Category | Operation | Budget | Observed (representative / range across 3 runs) | Margin |
|---|---|---|---|---|
| Service composition | Constructing the full `IntelligenceService` DI graph (Stage 12 + 13, cold) | 50ms | 0.5ms (0.4–1.0ms) | ~50–125x under budget |
| Unified lookup | `IntelligenceLookupService`, 10 dimensions × 100 samples (1,000 lookups) over 1,000 records | 300ms | ~118ms (110–122ms) | ~2.5x under budget |
| Correlation | `IntelligenceCorrelationService` — evidence/confidence/source/report/IOC × 100 samples over 1,000 records | 500ms | ~39ms (37–43ms) | ~12–13x under budget |
| Validation | `IntelligenceValidationService` — single + bundle × 100 samples over 1,000 records | 200ms | ~7ms (6–9ms) | ~25–30x under budget |
| Metrics overhead | `ServicePlatformMetrics.timed()` per call, 10,000 samples | 100µs/call | ~4.1µs/call (3.6–4.6µs) | ~22–27x under budget |

All five categories run comfortably inside their budgets on every observed run; none is close
enough to its budget to warrant a tighter margin before Phase 10 (Internal Adoption).

## Interpretation against CLAUDE.md's platform-wide performance baseline

- **Cold start < 50ms** (whole Cloudflare Worker request): Stage 13's own composition overhead
  (~0.5ms) is a small fraction of that budget on its own, consistent with Stage 12's own §7
  finding that this layer's overhead over the bare registry "must stay a rounding error." Stage
  13 is not wired into any live request path (Phase 10 gates the one authorized exception behind
  a feature flag defaulting `false` — see `TITAN_STAGE13_OPERATIONAL_GUIDE.md`), so this number
  is a ceiling on what a future live integration would cost, not a measurement of current
  production impact (there is none).
- **API response < 500ms p95 (computed)**: every per-category budget above is either at or under
  this platform-wide ceiling, and every observed value is well inside its own tighter budget.
- **Bundle size**: no production bundle changes — this directory is not imported by `index.js`
  or any `pNN-handlers.js` file (verified by both
  `intelligence-platform/__tests__/zero-blast-radius.test.js` and this stage's governance
  checks), so it contributes zero bytes to any Worker bundle today.

## Reproducing these numbers

```
cd workers/intel-gateway/src/intelligence-platform
node --test __tests__/service-performance-smoke.test.js
```

Each test prints its own `[Stage 13 perf]`-prefixed line to stdout, mirroring Stage 12's
convention of a CI run's own log being the durable record rather than a separate report-parsing
step.

## Relationship to Stage 12's baseline

For reference, Stage 12's own measured baseline (`TITAN_STAGE12_OPERATIONAL_GUIDE.md` §7,
unchanged by this stage): `EvidenceService.registerEvidence` × 1,000 — 39.0ms (38x under a
1,500ms budget); `EvidenceQueryEngine` 12 dimensions × 100 samples — 147.4ms (3.4x under a 500ms
budget); `EvidenceProvenanceEngine` 6 lineage kinds × 100 samples — 4.2ms (119x under a 500ms
budget). Stage 13's numbers above are additive on top of these, not a replacement for them.
