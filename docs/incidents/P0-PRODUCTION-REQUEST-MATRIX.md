# P0 — Production Request Matrix

**Captured:** 2026-09-03, 12:42–12:45 UTC
**Target:** `https://intel.cyberdudebivash.com/`
**Method:** real Chromium 1194 (Playwright), not jsdom. Every request the page issued was
recorded with its status, content type, body size and cache headers.
**Deployed SHA at capture:** `497832fd4` (`origin/main`, PR #351 squash-merge)
**Companion:** `docs/incidents/P0-EMPTY-DASHBOARD-ROOT-CAUSE.md`

---

## 0. Harness note (stated up front, because it bounds every claim below)

This environment's egress relay resets Chromium's own TLS tunnels
(`net::ERR_CONNECTION_RESET`; the relay reports `ws_closed_mid_exchange` for
`intel.cyberdudebivash.com:443`). That is the same proxy limitation the previous
investigation hit and recorded as its blind spot.

It was worked around rather than accepted: **every browser request is intercepted and
fulfilled by the Node process**, whose HTTP stack does traverse the proxy successfully.
Chromium still navigates to the real `https://intel.cyberdudebivash.com/` origin, so
origin, relative-URL resolution, cookie/SW scope, script execution order and the real
production HTML/JS/JSON bodies are all genuine. What is *not* genuine is the transport
beneath them — so this harness can prove **what the page requests, what production
answers, and how the page's JavaScript reacts**, which is exactly what this incident
turns on. It cannot prove per-connection TLS/HTTP-2 behaviour, and no claim below
depends on that.

One consequence worth naming: service-worker registration fails under interception, so
`swController` reads `false` in these captures. Service-worker behaviour is therefore
**out of scope of this matrix** and is neither confirmed nor refuted by it.

---

## 1. Headline measurement

| Metric | Value |
|---|---|
| Total requests per page load (all origins) | 109 |
| Requests to `intel.cyberdudebivash.com/api/*` | **27** |
| Distinct `/api/*` endpoints | 20 |
| Calls to `/api/health` | **0** — the page never calls it |
| Bytes of `/api/*` payload per load | **40,661,248 (≈40.6 MB)** |
| Commercial FREE tier per-minute limit (`RATE_LIMITS`, `index.js:184`) | 30 |
| Commercial FREE tier per-day quota (`DAILY_QUOTAS`, `daily-quota.js`) | 50 |

**One render of the customer dashboard spends 27 of the FREE tier's 30 requests per
minute, and 27 of its 50 requests per day.**

---

## 2. Per-endpoint matrix

All 27 requests are `GET`, anonymous (no `X-API-Key`, no `Authorization`), same-origin,
and all returned `200` at capture time — the quota for this capture's egress IP was not
yet exhausted.

| Endpoint | Calls / load | Status | Content-Type | Bytes each | Cache-Control | CF-Cache |
|---|---|---|---|---|---|---|
| `/api/feed.json` | **5** | 200 | application/json | 6,639,808 | `public, max-age=120` | – |
| `/api/reports/index.json` | 3 | 200 | application/json | 100,226 | `public, max-age=300` | – |
| `/api/ai/tracker.json` | 2 | 200 | application/json | 227,583 | `public, max-age=300` | – |
| `/api/v1/intel/latest.json` | 1 | 200 | application/json | 6,639,808 | `public, max-age=120` | – |
| `/api/v1/cve/live` | 1 | 200 | application/json | 38,636 | `public, max-age=60` | – |
| `/api/v1/news/feed` | 1 | 200 | application/json | 12,555 | `public, max-age=300` | – |
| `/api/v1/intel/campaigns` | 1 | 200 | application/json | 3,228 | `public, max-age=60` | – |
| `/api/v1/intel/apex.json` | 1 | 200 | application/json | 2,508 | `public, max-age=120` | – |
| `/api/v1/intel/epss` | 1 | 200 | application/json | 2,443 | `public, max-age=120` | – |
| `/api/v1/intel/apt` | 1 | 200 | application/json | 1,520 | `public, max-age=120` | – |
| `/api/v1/intel/ransomware` | 1 | 200 | application/json | 1,364 | `public, max-age=120` | – |
| `/api/v1/intel/ai_summary.json` | 1 | 200 | application/json | 1,113 | `public, max-age=120` | – |
| `/api/v1/intel/cybermap` | 1 | 200 | application/json | 999 | `public, max-age=120` | – |
| `/api/v1/intel/darkweb` | 1 | 200 | application/json | 697 | `public, max-age=300` | – |
| `/api/platform/stats` | 1 | 200 | application/json | 418 | `public, max-age=60` | – |
| `/api/v1/intel/stats` | 1 | 200 | application/json | 354 | `public, max-age=60` | – |
| `/api/metrics` | 1 | 200 | application/json | 353 | `public, max-age=60` | – |
| `/api/v1/intel/defcon` | 1 | 200 | application/json | 253 | `public, max-age=60` | – |
| `/api/v1/intel/pulse` | 1 | 200 | application/json | 115 | `public, max-age=60` | – |
| `/api/reports/stats.json` | 1 | 200 | application/json | **0** | `public, max-age=300` | – |
| **Total** | **27** | | | **40.6 MB** | | |

Notes on two rows:

- **`/api/reports/stats.json` returns a zero-byte body with a JSON content type.** A
  consumer that calls `.json()` on it gets a parse error, not an empty object. This is a
  pre-existing contract defect, unrelated to the outage; recorded here because the matrix
  is the right place for it.
- **CF-Cache is empty on every row** — these responses are Worker-generated and are not
  being served from Cloudflare's edge cache, so every one of the 27 calls reaches the
  Worker and is metered.

---

## 3. Component → consumer → endpoint wiring

| Dashboard component | Consuming script | Endpoint(s) | Plane before fix | Failure behaviour before fix |
|---|---|---|---|---|
| SYNC status, threat grid, Total Advisories, Critical, High, Avg Risk, IOCs, LIVE counter | `index.html` `loadGOCIntel()` (`MANIFEST_URLS`) | `/api/feed.json`, `/api/v1/intel/latest.json`, `/api/v1/intel/apex.json`, `/api/preview/`, then `raw.githubusercontent.com` mirror | commercial FREE | **`SYNC: LOADING` + `NO DATA`, permanently** |
| `#sapx-card-grid` cards | `js/card_renderer_integration.js` | `/api/feed.json`, fallback `/api/preview` | commercial FREE | "NO CURRENT THREAT INTELLIGENCE" |
| Live-intel bridge `__GOC_LIVE_INTEL` | `index.html` v148 bridge | `/api/feed.json` | commercial FREE | silent |
| KPI strip / metrics | `js/sentinel-live-feeds.js` | `/api/v1/intel/stats`, `/api/metrics`, `/api/platform/stats` | commercial FREE | `—` placeholders |
| DEFCON, cyber map, pulse, ransomware, APT, EPSS, campaigns, dark web | `js/sentinel-live-feeds.js` | the matching `/api/v1/intel/*` routes | commercial FREE | "…DATA UNAVAILABLE" per widget |
| AI Prediction Engine / AI Cyber Brain | `js/sentinel-live-feeds.js`, `index.html` | `/api/v1/intel/ai_summary.json`, `/api/ai/tracker.json` | commercial FREE | "AI PREDICTIONS UNAVAILABLE" |
| Reports badge (`REPORTS 23,018`) | `index.html` | `/api/reports/index.json`, `/api/reports/latest.json`, `/api/reports/stats.json` | commercial FREE | badge unavailable |
| CVE tracker | `index.html` | `/api/v1/cve/live`, `/api/v1/cve/detail` | commercial FREE | "NO CVEs MATCH" |
| Global news strip | `js/sentinel-live-feeds.js` | `/api/v1/news/feed` | commercial FREE | falls back to hard-coded **SAMPLE** headlines |
| Health | *(nothing)* | `/api/health` | **exempt** | n/a — the only exempt path, and the page never calls it |

That last row is the whole shape of the incident in one line: the single endpoint the
entitlement gate exempts is the single endpoint the dashboard does not use, which is why
`/api/health` reported 500 healthy advisories at the exact moment the dashboard reported
zero.

After the fix, every endpoint in this table except the auth/admin/payment routes (which
are not in it) is served by the **first-party web read plane**; see
`workers/intel-gateway/src/first-party-plane.js`. Live membership is queryable at
`/api/v1/observability/first-party-plane`.

---

## 4. Request amplification (separate defect, not the outage)

`/api/feed.json` is fetched **5 times per page load**, and `/api/v1/intel/latest.json` —
byte-identical to it (both 6,639,808 bytes, same `generated_at`) — once more. **≈39.8 MB
of the 40.6 MB total is six copies of the same 6.6 MB document.**

Four independent loaders each fetch it without coordination:

1. `index.html` `loadGOCIntel()` — `MANIFEST_URLS[0]`
2. `js/card_renderer_integration.js` — `CONFIG.API_URL`
3. `index.html` v148 "LIVE DATA BRIDGE" (`index.html:21703`)
4. `index.html` `_cdb`-prefixed metric/tab-count paths

This is a real and serious defect on its own terms — it is 6× the necessary bandwidth on
every page view, it is most of the 27-call quota cost, and it is the concrete evidence
behind the frontend-convergence work (Phase 17). **It is deliberately not fixed in this
change**: converging four loaders inside a 1.4 MB `index.html` during an active P0 is an
architectural event under `CLAUDE.md`'s Architecture Preservation Rule and needs its own
blast-radius assessment, not a same-commit drive-by. Tracked as follow-up F-1 in the
root-cause report.

Note that fixing the amplification alone would **not** have fixed the outage: 27 → ~10
calls per load still exceeds a 50/day budget on the fifth page view. The plane
separation is the fix; the amplification is a multiplier on top of it.

---

## 5. Reproduction

```bash
# 1. Confirm the backend is healthy and the dashboard's own endpoints are not.
curl -s https://intel.cyberdudebivash.com/api/health | jq '{advisory_count, feed_index}'
#   → {"advisory_count": 500, "feed_index": "live:500_items"}

# 2. Demonstrate the gate is reachable from one IP with a burst.
#    First 429 observed at request 23 of 70 (FREE per-minute limit is 30).
for i in $(seq 1 70); do
  curl -s -o /dev/null -w "%{http_code} " \
    "https://intel.cyberdudebivash.com/api/v1/intel/stats?probe=$i"
done

# 3. Verify plane membership after the fix.
curl -s https://intel.cyberdudebivash.com/api/v1/observability/first-party-plane | jq
```

Empirical result of step 2 at capture time: `200` ×22, then `429` at request 23.
