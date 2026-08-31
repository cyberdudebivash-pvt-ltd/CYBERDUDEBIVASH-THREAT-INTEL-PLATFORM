import assert from "node:assert/strict";
import { test } from "node:test";
import { findItemBySlug } from "../feed-lookup.js";

// ---------------------------------------------------------------------------
// findItemBySlug() previously lived in index.js and was imported from
// "../index.js" here; that transitively imports pricing.js ->
// pricing-data.json, which Node's native ESM loader rejects outside the
// wrangler/esbuild bundler (see subscription-lifecycle.js's header
// comment), so this suite could never actually run. findItemBySlug() (plus
// r2Get() and the feed-key constants it uses) was extracted into its own
// dependency-free feed-lookup.js specifically to fix that -- same pattern
// as subscription-lifecycle.js/daily-quota.js/admin-cache-bust.js. Pure
// move, no logic or call-signature change -- every test below is unchanged.
//
// Mock R2 environment -- mirrors rx-pub-a0-handlers.test.js's mockEnv,
// matching the real Cloudflare R2Object contract (env.INTEL_R2.get(key).text()).
// ---------------------------------------------------------------------------

function mockEnv(files) {
  return {
    INTEL_R2: {
      async get(key) {
        if (!(key in files)) return null;
        return { async text() { return JSON.stringify(files[key]); } };
      },
    },
  };
}

const LATEST_PRO_KEY = "api/v1/intel/latest_pro.json";
const LATEST_KEY = "api/v1/intel/latest.json";
const TOP10_KEY = "api/v1/intel/top10.json";
const APEX_KEY = "api/v1/intel/apex.json";
const FEED_MANIFEST_KEY = "intel/feed_manifest.json";

// ---------------------------------------------------------------------------
// RX-PUB-A0.6C: reproduces the exact live finding in docs/RX_PUB_A0_6_
// PROOF_BEFORE_CHANGE.md -- an item present only in feed_manifest.json's
// leaner schema (no precomputed P20-P26 score fields) must still resolve.
// ---------------------------------------------------------------------------

test("findItemBySlug: resolves via the four enriched sources first, without touching feed_manifest.json", async () => {
  const item = { id: "intel--abc123", title: "Enriched item" };
  let feedManifestFetched = false;
  const env = {
    INTEL_R2: {
      async get(key) {
        if (key === LATEST_KEY) return { async text() { return JSON.stringify({ items: [item] }); } };
        if (key === FEED_MANIFEST_KEY) { feedManifestFetched = true; return { async text() { return JSON.stringify([]); } }; }
        return null;
      },
    },
  };
  const found = await findItemBySlug(env, "abc123");
  assert.equal(found.id, "intel--abc123");
  assert.equal(feedManifestFetched, false, "must not fetch the fallback source once an earlier source resolves");
});

test("findItemBySlug: falls back to feed_manifest.json when absent from all four enriched sources", async () => {
  // The exact scenario found live: an item that IS in the broader,
  // leaner-schema feed_manifest.json (no P20_SCORE etc.) but missing from
  // latest.json/latest_pro.json/top10.json/apex.json.
  const leanItem = {
    id: "intel--f5ff8edef07fa32b", stix_id: "intel--f5ff8edef07fa32b",
    title: "Report only in feed_manifest.json", description: "test",
    severity: "HIGH", risk_score: 7.2, cves: [], iocs: [], tags: [], threat_type: "PHISHING",
  };
  const env = mockEnv({
    [LATEST_PRO_KEY]: { items: [] },
    [LATEST_KEY]: { items: [] },
    [TOP10_KEY]: { items: [] },
    [APEX_KEY]: { items: [] },
    [FEED_MANIFEST_KEY]: [leanItem], // bare array -- feed_manifest.json's actual top-level shape
  });
  const found = await findItemBySlug(env, "f5ff8edef07fa32b");
  assert.ok(found, "must resolve via the feed_manifest.json fallback");
  assert.equal(found.id, "intel--f5ff8edef07fa32b");
  assert.equal(found.title, "Report only in feed_manifest.json");
});

test("findItemBySlug: still returns null when the slug is absent from every source including the fallback", async () => {
  const env = mockEnv({
    [LATEST_PRO_KEY]: { items: [] },
    [LATEST_KEY]: { items: [] },
    [TOP10_KEY]: { items: [] },
    [APEX_KEY]: { items: [] },
    [FEED_MANIFEST_KEY]: [],
  });
  const found = await findItemBySlug(env, "genuinely-nonexistent");
  assert.equal(found, null);
});

test("findItemBySlug: a feed_manifest.json fetch/parse failure does not crash resolution, just falls through to null", async () => {
  const env = {
    INTEL_R2: {
      async get(key) {
        if (key === FEED_MANIFEST_KEY) throw new Error("R2 outage");
        return null;
      },
    },
  };
  const found = await findItemBySlug(env, "abc123");
  assert.equal(found, null, "an errored fallback source must degrade to unresolvable, not throw");
});
