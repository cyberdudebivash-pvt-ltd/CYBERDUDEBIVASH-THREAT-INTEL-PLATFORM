import assert from "node:assert/strict";
import { test } from "node:test";
import { handleIntelStaticProxy, INTEL_STATIC_PROXY } from "../intel-static-proxy.js";

// ---------------------------------------------------------------------------
// Stage 4 -- CYBERDUDEBIVASH SENTINEL APEX
//
// Contract tests for handleIntelStaticProxy(), the R2-first proxy backing
// GET /api/v1/intel/ai_index.json and
// GET /api/v1/intel/detection_rules_manifest.json (previously bare relative
// static paths -- data/ai_intelligence/ai_index.json and
// data/intelligence/detection_rules/rule_manifest.json -- that only the
// Pages static origin could serve, requiring a full pipeline run + Pages
// publish to refresh; see the function's own header comment in index.js).
// ---------------------------------------------------------------------------

const AI_INDEX_PATH = "/api/v1/intel/ai_index.json";
const RULES_PATH    = "/api/v1/intel/detection_rules_manifest.json";

function fakeR2(store = {}) {
  return {
    calls: [],
    async get(key) {
      this.calls.push(key);
      if (!(key in store)) return null;
      const value = store[key];
      return { body: JSON.stringify(value) };
    },
  };
}

test("unknown path returns null so the caller's dispatcher keeps routing", async () => {
  const result = await handleIntelStaticProxy({}, "/api/v1/intel/does_not_exist.json", "GET");
  assert.equal(result, null);
});

test("non-GET method is rejected with 405", async () => {
  const resp = await handleIntelStaticProxy({}, AI_INDEX_PATH, "POST");
  assert.equal(resp.status, 405);
  assert.equal(resp.headers.get("Allow"), "GET");
});

test("R2 hit returns R2's content directly, without touching gh-pages", async () => {
  const r2 = fakeR2({ "intelligence/ai_index.json": [{ advisory_id: "intel--abc", title: "R2-sourced record" }] });
  const originalFetch = globalThis.fetch;
  let ghPagesFetched = false;
  globalThis.fetch = async () => { ghPagesFetched = true; throw new Error("must not reach gh-pages when R2 has the object"); };
  try {
    const resp = await handleIntelStaticProxy({ INTEL_R2: r2 }, AI_INDEX_PATH, "GET");
    assert.equal(resp.status, 200);
    const body = await resp.json();
    assert.deepEqual(body, [{ advisory_id: "intel--abc", title: "R2-sourced record" }]);
    assert.equal(ghPagesFetched, false);
    assert.deepEqual(r2.calls, ["intelligence/ai_index.json"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("R2 miss (object not found) falls back to gh-pages raw content", async () => {
  const r2 = fakeR2({}); // empty -- get() returns null for any key
  const originalFetch = globalThis.fetch;
  let requestedUrl = null;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return { ok: true, json: async () => ({ source: "gh-pages-fallback" }) };
  };
  try {
    const resp = await handleIntelStaticProxy({ INTEL_R2: r2 }, RULES_PATH, "GET");
    assert.equal(resp.status, 200);
    const body = await resp.json();
    assert.deepEqual(body, { source: "gh-pages-fallback" });
    assert.match(requestedUrl, /gh-pages\/data\/intelligence\/detection_rules\/rule_manifest\.json$/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("R2 binding missing entirely falls back to gh-pages", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ source: "gh-pages-fallback" }) });
  try {
    const resp = await handleIntelStaticProxy({}, AI_INDEX_PATH, "GET");
    assert.equal(resp.status, 200);
    assert.deepEqual(await resp.json(), { source: "gh-pages-fallback" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("R2 read throwing falls back to gh-pages instead of failing the request", async () => {
  const r2 = { async get() { throw new Error("simulated R2 outage"); } };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ source: "gh-pages-fallback" }) });
  try {
    const resp = await handleIntelStaticProxy({ INTEL_R2: r2 }, AI_INDEX_PATH, "GET");
    assert.equal(resp.status, 200);
    assert.deepEqual(await resp.json(), { source: "gh-pages-fallback" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("gh-pages fallback itself failing returns an honest 502, never fabricated content", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 404 });
  try {
    const resp = await handleIntelStaticProxy({}, AI_INDEX_PATH, "GET");
    assert.equal(resp.status, 502);
    const body = await resp.json();
    assert.equal(body.error, "upstream_unavailable");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("gh-pages fetch throwing (e.g. timeout) returns an honest 502", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("simulated timeout"); };
  try {
    const resp = await handleIntelStaticProxy({}, RULES_PATH, "GET");
    assert.equal(resp.status, 502);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("all proxied paths are registered with distinct R2 keys and gh paths", () => {
  assert.equal(Object.keys(INTEL_STATIC_PROXY).length, 7);
  assert.equal(INTEL_STATIC_PROXY[AI_INDEX_PATH].r2Key, "intelligence/ai_index.json");
  assert.equal(INTEL_STATIC_PROXY[RULES_PATH].r2Key, "intelligence/detection_rules_manifest.json");
  const r2Keys = Object.values(INTEL_STATIC_PROXY).map((e) => e.r2Key);
  assert.equal(new Set(r2Keys).size, r2Keys.length, "R2 keys must be unique across all entries");
});

// ---------------------------------------------------------------------------
// P0 RUNTIME INTELLIGENCE STATE RECOVERY mission (2026-09-10): 5 new entries
// serving index.html's ENGINE_URLS (nexus/cortex/quantum/sovereign/genesis),
// each with ghBranch: "main" instead of the original two entries' default
// "gh-pages" -- their fallback content was never in the gh-pages deploy
// bundle (build_dist_artifact.py's INCLUDE_DIRS excludes data/ entirely),
// so falling back to gh-pages for these would 404 even when main has a
// servable (if stale) copy.
// ---------------------------------------------------------------------------
const NEXUS_PATH = "/api/v1/intel/nexus_output.json";

test("default ghBranch (unset on an entry) still falls back to gh-pages -- existing entries unaffected", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = null;
  globalThis.fetch = async (url) => { requestedUrl = url; return { ok: true, json: async () => ({ source: "gh-pages-fallback" }) }; };
  try {
    await handleIntelStaticProxy({}, AI_INDEX_PATH, "GET");
    assert.match(requestedUrl, /\/gh-pages\//);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("ghBranch: 'main' entries fall back to the main branch, not gh-pages", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = null;
  globalThis.fetch = async (url) => { requestedUrl = url; return { ok: true, json: async () => ({ source: "main-fallback" }) }; };
  try {
    const resp = await handleIntelStaticProxy({}, NEXUS_PATH, "GET");
    assert.equal(resp.status, 200);
    assert.match(requestedUrl, /\/main\/data\/nexus\/nexus_output\.json$/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("nexus_output.json prefers R2 over the main-branch fallback", async () => {
  const r2 = fakeR2({ "data/nexus/nexus_output.json": { generated_at: "fresh-from-r2" } });
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error("must not reach main branch when R2 has the object"); };
  try {
    const resp = await handleIntelStaticProxy({ INTEL_R2: r2 }, NEXUS_PATH, "GET");
    assert.deepEqual(await resp.json(), { generated_at: "fresh-from-r2" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("all 5 new engine routes are registered with ghBranch main and path-mirrored R2 keys", () => {
  for (const [path, r2Key] of [
    ["/api/v1/intel/nexus_output.json", "data/nexus/nexus_output.json"],
    ["/api/v1/intel/genesis_output.json", "data/genesis/genesis_output.json"],
    ["/api/v1/intel/cortex_output.json", "data/cortex/cortex_output.json"],
    ["/api/v1/intel/quantum_output.json", "data/quantum/quantum_output.json"],
    ["/api/v1/intel/sovereign_output.json", "data/sovereign/sovereign_output.json"],
  ]) {
    const entry = INTEL_STATIC_PROXY[path];
    assert.ok(entry, `${path} must be registered`);
    assert.equal(entry.r2Key, r2Key);
    assert.equal(entry.ghPath, r2Key);
    assert.equal(entry.ghBranch, "main");
  }
});

// ---------------------------------------------------------------------------
// Stage 4 deployment-decoupling proof (report Section 13/30): the SAME
// handler, with no code change between calls, must reflect a runtime data
// change immediately -- proving the frontend/API contract does not require
// a git commit or Pages deploy to pick up new intelligence.
// ---------------------------------------------------------------------------
test("DEPLOYMENT-DECOUPLING PROOF: changing R2's stored object changes the response with zero code change", async () => {
  const store = { "intelligence/ai_index.json": [{ advisory_id: "intel--v1", title: "before update" }] };
  const r2 = fakeR2(store);
  const env = { INTEL_R2: r2 };

  const before = await handleIntelStaticProxy(env, AI_INDEX_PATH, "GET");
  assert.deepEqual(await before.json(), [{ advisory_id: "intel--v1", title: "before update" }]);

  // Simulates the real production path: scripts/r2_upload.py's Upload 3c
  // step writing a freshly-generated file straight to R2 -- no git commit,
  // no Pages deploy, same handler code as the call above.
  store["intelligence/ai_index.json"] = [{ advisory_id: "intel--v2", title: "after runtime update, no deploy" }];

  const after = await handleIntelStaticProxy(env, AI_INDEX_PATH, "GET");
  assert.deepEqual(await after.json(), [{ advisory_id: "intel--v2", title: "after runtime update, no deploy" }]);
});
