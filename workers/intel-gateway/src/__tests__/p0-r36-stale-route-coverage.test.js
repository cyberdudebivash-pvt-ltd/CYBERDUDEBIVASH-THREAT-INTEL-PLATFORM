import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = new URL("../index.js", import.meta.url);
const source = readFileSync(fileURLToPath(root), "utf8");
const aliases = [
  "/api/feed", "/api/feed.json", "/api/preview", "/api/v1/intel/latest.json",
  "/api/v1/intel/top10.json", "/api/platform/stats", "/api/v1/intel/stats",
  "/api/metrics", "/api/v1/intel/campaigns", "/api/v1/intel/ransomware",
  "/api/v1/intel/apt", "/api/v1/intel/epss", "/api/v1/intel/pulse",
  "/api/v1/intel/darkweb", "/api/v1/intel/cybermap",
];

test("live routes dispatch to fail-closed policy before projecting old data", () => {
  assert.ok(source.includes("import { denyNonFreshLiveFeed, liveFreshCacheControl } from"), "both runtime policy helpers imported");
  for (const route of aliases) {
    assert.ok(source.includes(route), route + " route missing");
  }
  for (const route of [
    "/api/feed", "/api/preview", "/api/v1/intel/latest.json", "/api/v1/intel/top10.json",
    "/api/platform/stats", "/api/v1/intel/stats", "/api/metrics", "/api/v1/intel/campaigns",
    "/api/v1/intel/ransomware", "/api/v1/intel/apt", "/api/v1/intel/epss",
    "/api/v1/intel/pulse", "/api/v1/intel/darkweb", "/api/v1/intel/cybermap",
  ]) {
    const start = source.indexOf('if (path === "' + route + '"');
    assert.ok(start > 0, route + " dispatch missing");
    const next = source.indexOf("  // ---", start + 10);
    const block = source.slice(start, next > start ? next : start + 7000);
    assert.ok(block.includes("denyNonFreshLiveFeed("), route + " must deny stale");
  }
});

test("response policy preserves 503; never sends stored stale items in denial", () => {
  const helper = readFileSync(fileURLToPath(new URL("../stale-feed-policy.js", import.meta.url)), "utf8");
  assert.match(helper, /status: 503/);
  assert.match(helper, /items: \[\]/);
  assert.match(helper, /no-store/);
  assert.doesNotMatch(helper, /generated_at: new Date\(/);
});

test("legacy GitHub Pages snapshot URLs are Worker-routed through the same live guards", () => {
  assert.ok(source.includes('path === "/feed.json"'));
  assert.ok(source.includes('path === "/latest.json"'));
  const wrangler = readFileSync(fileURLToPath(new URL("../../wrangler.toml", import.meta.url)), "utf8");
  assert.ok(wrangler.includes('pattern = "intel.cyberdudebivash.com/feed.json"'));
  assert.ok(wrangler.includes('pattern = "intel.cyberdudebivash.com/latest.json"'));
});
