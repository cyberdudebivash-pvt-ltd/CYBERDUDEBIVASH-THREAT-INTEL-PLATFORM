# Commercial Gateway Performance Report

**Project TITAN Stage 21 — Enterprise Intelligence Gateway Commercial Activation**
**Measured, not estimated.** Source: `workers/intel-gateway/src/commercial-catalog/__tests__/service-performance-smoke.test.js`
**Environment:** Node v22.22.2, this container, 2 independent runs (`node --test` and `node --expose-gc --test`)

---

## 1. Method

Mirrors `enterprise-gateway/__tests__/service-performance-smoke.test.js`'s established per-layer
smoke-test convention (every sibling directory — `evidence-registry`, `intelligence-platform`,
`knowledge-platform`, `product-platform`, `relationship-framework`, `enterprise-gateway` — already
has one of these; `commercial-catalog` did not until Phase 9). Not a formal benchmark suite (no
statistical-rigor claims beyond straightforward percentile arithmetic over N in-process samples,
no warm-up/JIT isolation, single-process). Every category isolates `commercial-catalog/`'s **own**
overhead (adapter validation/mapping/translation, registry lookup, contract check, readiness
aggregation) — not a re-benchmark of the underlying Gateway/platform work a full dispatch call
executes through, which each lower layer's own smoke test already measures.

Each latency category records `performance.now()` per individual call (not just aggregate elapsed),
enabling real average/median/p95/worst computation. Run: `cd
workers/intel-gateway/src/commercial-catalog && node --test __tests__/service-performance-smoke.test.js`.

## 2. Results (2 independent runs)

| Category | n | Average | Median | p95 | Worst |
|---|---:|---:|---:|---:|---:|
| Gateway/full-stack composition (cold, x1) | 1 | 2.18–2.23ms | — | — | — |
| Registry lookup (`describeCapability`) | 200 | 0.001ms | 0.000ms | 0.003ms | 0.045–0.053ms |
| **Adapter dispatch** (new Stage 21 capability, `commercial.knowledgeObject/build`) | 200 | 1.04–1.11ms | 0.58–0.60ms | 3.4–4.8ms | 8.4–9.9ms |
| **Gateway dispatch** (pre-existing capability, `evidence.lookup/byCVE`, same commercial-composed gateway) | 200 | 0.06–0.07ms | 0.042–0.044ms | 0.08–0.12ms | 2.1–4.1ms |
| Contract validation (`checkContractCompatibility`) | 200 | 0.001–0.002ms | 0.000–0.001ms | 0.002ms | 0.14–0.16ms |
| Commercial readiness generation (`buildCommercialReadinessReport`) | 50 | 0.032–0.037ms | 0.017–0.018ms | 0.051–0.053ms | 0.59–0.72ms |

All figures in milliseconds. Ranges reflect the two independent runs (see raw output below); both
runs are internally consistent (no run varied by more than ~1.5x on any p95 figure).

## 3. Memory

```
[Stage 21 perf] memory: heapUsed delta across 100 full-stack compositions: 2.73MB (27.9KB/composition, gc=not exposed)
[Stage 21 perf] memory: heapUsed delta across 100 full-stack compositions: 2.76MB (28.3KB/composition, gc=forced)
```
**~28KB of retained heap per full `createCommercialGateway()` composition** (IntelligenceService +
EnterpriseGateway + KnowledgePlatform + ProductPlatform + 19 registered capabilities + metrics),
consistent with and without a forced GC pass before measuring.

## 4. CPU

```
[Stage 21 perf] CPU: user+system time across 200 commercial.readinessSummary dispatches: 27.95ms total (0.140ms/call)
[Stage 21 perf] CPU: user+system time across 200 commercial.readinessSummary dispatches: 31.08ms total (0.155ms/call)
```
**~0.14–0.16ms of user+system CPU time per dispatch** of a P39-backed adapter (the cheapest
adapter class — pure-function composition, no evidence-registry round-trip).

## 5. Interpretation against the CLAUDE.md performance baseline

| Baseline (non-negotiable) | Stage 21 measurement | Status |
|---|---|---|
| API response < 500ms p95 (cached) / < 2s p95 (computed) | Adapter dispatch p95 3.4–4.8ms; Gateway dispatch p95 0.08–0.12ms | Well within budget — this measures in-process dispatch, not network/edge round-trip, so it is a lower bound on end-to-end latency, not the full picture |
| Cold start < 50ms (Cloudflare Worker) | Full-stack composition (cold) 2.18–2.23ms | Within budget with wide margin |
| No response-time regression | Pre-existing `evidence.lookup/byCVE` dispatch through the **same commercial-composed gateway**: p95 0.08–0.12ms, consistent with `enterprise-gateway`'s own pre-Stage-21 smoke test figures for the identical operation | No regression — composing commercial-catalog/ on top of the Gateway does not measurably slow down existing capability dispatch |
| Bundle size: no regression | Not applicable at this stage — `commercial-catalog/` is not imported by `index.js` or bundled into any deployed Worker route (confirmed §"Not registered, not routed" in `COMMERCIAL_SERVICE_REGISTRY.md`) | N/A, zero bundle impact by construction |

## 6. Why a new adapter is slower than a pre-existing dispatch

`commercial.knowledgeObject/build`'s p95 (3.4–4.8ms) is roughly 30–40x `evidence.lookup/byCVE`'s
p95 (0.08–0.12ms) through the same gateway. This is expected and not a regression: the former is a
**compound operation** (`KnowledgeObjectService.build()` calls both `IntelligenceLookupService` and
`IntelligenceExplainabilityService` internally to build its 7-field object — see
`COMMERCIAL_SERVICE_CATALOG.md` §3.2), while the latter is a single-hop lookup. This mirrors
`enterprise-gateway`'s own precedent for `intelligence.explainability/explainEvidence` (a compound
operation given its own, honestly wider budget in that layer's smoke test rather than reused against
a single-hop budget) — the same "budget should reflect real cost, not hide it" principle applies
here.

## 7. Raw console output (both runs, `[Stage 21 perf]` lines only)

```
Run 1 (node --test):
[Stage 21 perf] createCommercialGateway() full-stack composition (cold): 2.226ms
[Stage 21 perf] registry lookup (describeCapability, commercial.knowledgeObject): avg=0.001ms median=0.000ms p95=0.003ms worst=0.045ms (n=200)
[Stage 21 perf] adapter dispatch (commercial.knowledgeObject/build): avg=1.114ms median=0.596ms p95=4.759ms worst=9.874ms (n=200)
[Stage 21 perf] gateway dispatch (pre-existing evidence.lookup/byCVE, commercial-composed gateway): avg=0.073ms median=0.044ms p95=0.118ms worst=4.122ms (n=200)
[Stage 21 perf] contract validation (checkContractCompatibility, CommercialAdaptersContract): avg=0.002ms median=0.001ms p95=0.002ms worst=0.162ms (n=200)
[Stage 21 perf] commercial readiness generation (buildCommercialReadinessReport): avg=0.037ms median=0.018ms p95=0.053ms worst=0.723ms (n=50)
[Stage 21 perf] memory: heapUsed delta across 100 full-stack compositions: 2.73MB (27.9KB/composition, gc=not exposed)
[Stage 21 perf] CPU: user+system time across 200 commercial.readinessSummary dispatches: 27.95ms total (0.140ms/call)

Run 2 (node --expose-gc --test):
[Stage 21 perf] createCommercialGateway() full-stack composition (cold): 2.183ms
[Stage 21 perf] registry lookup (describeCapability, commercial.knowledgeObject): avg=0.001ms median=0.000ms p95=0.003ms worst=0.053ms (n=200)
[Stage 21 perf] adapter dispatch (commercial.knowledgeObject/build): avg=1.037ms median=0.582ms p95=3.382ms worst=8.372ms (n=200)
[Stage 21 perf] gateway dispatch (pre-existing evidence.lookup/byCVE, commercial-composed gateway): avg=0.059ms median=0.042ms p95=0.084ms worst=2.121ms (n=200)
[Stage 21 perf] contract validation (checkContractCompatibility, CommercialAdaptersContract): avg=0.001ms median=0.000ms p95=0.002ms worst=0.137ms (n=200)
[Stage 21 perf] commercial readiness generation (buildCommercialReadinessReport): avg=0.032ms median=0.017ms p95=0.051ms worst=0.591ms (n=50)
[Stage 21 perf] memory: heapUsed delta across 100 full-stack compositions: 2.76MB (28.3KB/composition, gc=forced)
[Stage 21 perf] CPU: user+system time across 200 commercial.readinessSummary dispatches: 31.08ms total (0.155ms/call)
```

All 8 performance smoke tests pass in both runs (budgets: composition < 200ms; registry lookup p95
< 2ms; adapter/gateway dispatch p95 < 30ms; contract validation p95 < 2ms; readiness p95 < 10ms —
every measured figure above lands well inside its budget, with headroom, matching this platform's
existing convention of budgeting for stability rather than tuning to the exact measurement).
