import assert from "node:assert/strict";
import { test } from "node:test";
import { routeExports } from "../exports.js";
import { INDICATORS_R2_KEY } from "../../ingestion/cron_worker.js";

// ---------------------------------------------------------------------------
// Task 4: rule-syntax validation for Suricata/Snort/YARA/Splunk/STIX export
// routes + access-control enforcement (FREE = truncated sample, PRO+ = full
// payload). Exercises the real routeExports() public contract exactly as
// index.js calls it (auth already resolved, items already loaded), so this
// is a black-box test of what actually ships, not a reimplementation of it.
// ---------------------------------------------------------------------------

function fakeR2WithIndicators(indicators) {
  const store = new Map();
  store.set(INDICATORS_R2_KEY, JSON.stringify({ items: indicators }));
  return {
    async get(key) {
      if (!store.has(key)) return null;
      const text = store.get(key);
      return { text: async () => text };
    },
    async put(key, value) { store.set(key, value); },
  };
}

function manyItems(n, withRules = true) {
  return Array.from({ length: n }, (_, i) => ({
    id: `intel--item${i}`, stix_id: `indicator--item${i}`, title: `Advisory ${i}`,
    severity: "HIGH", risk_score: 50 + (i % 40), source: "test-source",
    cve_ids: [`CVE-2026-${10000 + i}`], tags: ["test"],
    published_at: new Date().toISOString(),
    suricata_rule: withRules ? `alert ip any any -> any any (msg:"item ${i}"; sid:${8000000 + i}; rev:1;)` : undefined,
    yara_rule: withRules ? `rule item_${i} { condition: true }` : undefined,
  }));
}

function liveIndicatorFixtures() {
  return [
    { indicator: "5.6.7.8", type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6, risk_score: 45, first_seen: new Date().toISOString(), last_seen: new Date().toISOString(), tags: ["tor"], meta: {} },
    { indicator: "http://evil.example.com/x", type: "url", source: "URLHAUS", source_confidence: 0.85, risk_score: 80, first_seen: new Date().toISOString(), last_seen: new Date().toISOString(), tags: ["malware"], meta: { host: "evil.example.com", threat: "malware_download" } },
  ];
}

const REQ = {}; // routeExports does not currently read anything off `req`
const CTX = {};

// --- routing ------------------------------------------------------------------

test("routeExports returns null for a path outside /api/v1/export/", async () => {
  const res = await routeExports("/api/v1/intel/latest.json", REQ, {}, CTX, "FREE", [], "req-1", {});
  assert.equal(res, null);
});

test("routeExports returns null for an unrecognized export format", async () => {
  const res = await routeExports("/api/v1/export/unknown.format", REQ, {}, CTX, "FREE", [], "req-1", {});
  assert.equal(res, null);
});

// --- FREE vs PRO tiering --------------------------------------------------------

test("FREE tier suricata export is capped at the 25-rule sample and says so", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/suricata.rules", REQ, env, CTX, "FREE", manyItems(40), "req-2", {});
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("X-Sentinel-Rule-Count"), "25");
  assert.equal(res.headers.get("X-Sentinel-Rule-Total"), "40");
  const body = await res.text();
  assert.match(body, /FREE tier sample/);
  assert.match(body, /upgrade\.html/);
});

test("PRO tier suricata export returns the full rule set with no sample notice", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/suricata.rules", REQ, env, CTX, "PRO", manyItems(40), "req-3", {});
  assert.equal(res.headers.get("X-Sentinel-Rule-Count"), "40");
  const body = await res.text();
  assert.doesNotMatch(body, /FREE tier sample/);
});

test("ENTERPRISE and MSSP both count as paid (full export, not sampled)", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  for (const tier of ["ENTERPRISE", "MSSP"]) {
    const res = await routeExports("/api/v1/export/yara.yar", REQ, env, CTX, tier, manyItems(30), "req-4", {});
    assert.equal(res.headers.get("X-Sentinel-Rule-Count"), "30", `tier ${tier} should get the full set`);
  }
});

test("no API key at all (auth.tier defaults to FREE) still gets a 200 sample, never a hard 403", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/yara.yar", REQ, env, CTX, "FREE", manyItems(30), "req-5", { tier: "FREE", key: null });
  assert.equal(res.status, 200);
});

// --- Suricata: reuses item.suricata_rule verbatim + synthesizes from live indicators ---

test("suricata export reuses item.suricata_rule content verbatim and adds live-indicator rules", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators(liveIndicatorFixtures()) };
  const items = manyItems(2);
  const res = await routeExports("/api/v1/export/suricata.rules", REQ, env, CTX, "PRO", items, "req-6", {});
  const body = await res.text();
  assert.match(body, /alert ip any any -> any any \(msg:"item 0"; sid:8000000; rev:1;\)/);
  assert.match(body, /5\.6\.7\.8/); // live Tor IP indicator rule present
  assert.match(body, /evil\.example\.com/); // live URLhaus domain rule present
  // Live-indicator SIDs must fall in the reserved 9500000-9589999 block, never
  // colliding with the CI-generated 915xxxx range or this test's own 8000000+ sids.
  const liveSidMatches = [...body.matchAll(/sid:(\d+)/g)].map(m => Number(m[1])).filter(s => s >= 9500000);
  assert.ok(liveSidMatches.length >= 2);
  assert.ok(liveSidMatches.every(s => s >= 9500000 && s < 9590000));
});

test("suricata export is syntactically valid: every rule line starts with a valid action keyword and has a sid", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators(liveIndicatorFixtures()) };
  const res = await routeExports("/api/v1/export/suricata.rules", REQ, env, CTX, "PRO", manyItems(3), "req-7", {});
  const body = await res.text();
  const ruleLines = body.split("\n").filter(l => l.startsWith("alert "));
  assert.ok(ruleLines.length >= 5);
  for (const line of ruleLines) {
    assert.match(line, /^(alert)\s(ip|dns|http|tcp)\s/, `malformed action/protocol: ${line}`);
    assert.match(line, /sid:\d+;/, `missing sid: ${line}`);
    assert.match(line, /rev:\d+;/, `missing rev: ${line}`);
  }
});

// --- Snort: new generator, IP + HTTP-header-content subset only ---

test("snort export generates valid rules from live indicators, in the reserved SID block", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators(liveIndicatorFixtures()) };
  const res = await routeExports("/api/v1/export/snort.rules", REQ, env, CTX, "PRO", [], "req-8", {});
  const body = await res.text();
  const ruleLines = body.split("\n").filter(l => l.startsWith("alert "));
  assert.equal(ruleLines.length, 2); // one ip rule (Tor), one content rule (URLhaus host)
  for (const line of ruleLines) {
    assert.match(line, /^alert (ip|tcp) any any -> /);
    assert.match(line, /sid:(\d+);/);
    const sid = Number(line.match(/sid:(\d+);/)[1]);
    assert.ok(sid >= 9600000 && sid < 9690000, `snort sid ${sid} outside reserved block`);
  }
  assert.match(body, /5\.6\.7\.8/);
  assert.match(body, /evil\.example\.com/);
});

test("FREE tier snort export is capped at 25 and PRO is not", async () => {
  const manyLive = Array.from({ length: 40 }, (_, i) => ({
    indicator: `10.0.0.${i}`, type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6,
    risk_score: 50, first_seen: new Date().toISOString(), last_seen: new Date().toISOString(), tags: [], meta: {},
  }));
  const env = { INTEL_R2: fakeR2WithIndicators(manyLive) };
  const free = await routeExports("/api/v1/export/snort.rules", REQ, env, CTX, "FREE", [], "req-9", {});
  const pro  = await routeExports("/api/v1/export/snort.rules", REQ, env, CTX, "PRO",  [], "req-10", {});
  assert.equal(free.headers.get("X-Sentinel-Rule-Count"), "25");
  assert.equal(pro.headers.get("X-Sentinel-Rule-Count"), "40");
});

// --- YARA: reuses item.yara_rule verbatim ---

test("yara export reuses item.yara_rule content verbatim", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/yara.yar", REQ, env, CTX, "PRO", manyItems(2), "req-11", {});
  assert.equal(res.headers.get("Content-Type"), "text/plain; charset=utf-8");
  const body = await res.text();
  assert.match(body, /rule item_0 \{ condition: true \}/);
  assert.match(body, /rule item_1 \{ condition: true \}/);
});

// --- Splunk CSV: valid CSV shape + OWASP CSV-injection guard ---

test("splunk export produces a valid CSV with the documented header row", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators(liveIndicatorFixtures()) };
  const res = await routeExports("/api/v1/export/splunk.csv", REQ, env, CTX, "PRO", manyItems(3), "req-12", {});
  assert.equal(res.headers.get("Content-Type"), "text/csv; charset=utf-8");
  const lines = (await res.text()).trim().split("\n");
  assert.equal(lines[0], "indicator,type,severity,risk_score,source,confidence,first_seen,last_seen,tags,cve_ids");
  assert.equal(lines.length, 1 + 3 + 2); // header + 3 items + 2 live indicators
});

test("splunk export neutralizes formula-injection-shaped indicator values", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([
    { indicator: "=cmd|'/bin/calc'!A1", type: "url", source: "URLHAUS", source_confidence: 0.5, risk_score: 10, first_seen: "", last_seen: "", tags: [], meta: {} },
  ]) };
  const res = await routeExports("/api/v1/export/splunk.csv", REQ, env, CTX, "PRO", [], "req-13", {});
  const body = await res.text();
  const dataLine = body.trim().split("\n")[1];
  assert.match(dataLine, /^"'=cmd/, "a leading = must be neutralized with a leading single-quote");
});

test("FREE tier splunk export is capped at 25 rows and signals it via headers, not corrupted CSV", async () => {
  const many = manyItems(40, false);
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/splunk.csv", REQ, env, CTX, "FREE", many, "req-14", {});
  const lines = (await res.text()).trim().split("\n");
  assert.equal(lines.length, 1 + 25); // header + 25 sampled rows, still strictly valid CSV
  assert.equal(res.headers.get("X-Sentinel-Upgrade-Url"), "https://intel.cyberdudebivash.com/upgrade.html?plan=pro");
});

// --- TAXII / STIX 2.1 bundle ---

test("taxii export produces a well-formed STIX 2.1 bundle and uses the injected buildStixPatternFn", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators(liveIndicatorFixtures()) };
  const stixPatternCalls = [];
  const fakeBuildStixPattern = (item) => { stixPatternCalls.push(item.id); return `[vulnerability:name = '${item.cve_ids[0]}']`; };

  const res = await routeExports("/api/v1/export/taxii.json", REQ, env, CTX, "PRO", manyItems(2), "req-15", {}, fakeBuildStixPattern);
  assert.equal(res.headers.get("Content-Type"), "application/stix+json;version=2.1");
  const bundle = JSON.parse(await res.text());
  assert.equal(bundle.type, "bundle");
  assert.equal(bundle.spec_version, "2.1");
  assert.equal(bundle.objects.length, 4); // 2 items + 2 live indicators
  assert.equal(stixPatternCalls.length, 2);
  assert.ok(bundle.objects.every(o => o.type === "indicator" && o.pattern));
  assert.equal(bundle.x_sentinel_tier_notice, undefined); // PRO: no truncation notice
});

test("taxii export falls back to a default pattern builder when none is injected", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/taxii.json", REQ, env, CTX, "PRO", manyItems(1), "req-16", {});
  const bundle = JSON.parse(await res.text());
  assert.equal(bundle.objects.length, 1);
  assert.match(bundle.objects[0].pattern, /threat-actor:name/);
});

test("FREE tier taxii export is truncated to 25 objects and carries an upgrade notice field", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/taxii.json", REQ, env, CTX, "FREE", manyItems(40), "req-17", {});
  const bundle = JSON.parse(await res.text());
  assert.equal(bundle.objects.length, 25);
  assert.match(bundle.x_sentinel_tier_notice, /FREE tier sample/);
  assert.equal(bundle.x_sentinel_upgrade_url, "https://intel.cyberdudebivash.com/upgrade.html?plan=pro");
});

// --- entitlement engine wiring ---

test("routeExports honors an injected resolveEntitlement() that denies access", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const denyingResolver = () => ({ allowed: false, enforced: true });
  const res = await routeExports("/api/v1/export/suricata.rules", REQ, env, CTX, "PRO", manyItems(5), "req-18", {}, null, denyingResolver);
  assert.equal(res.status, 503);
  const body = JSON.parse(await res.text());
  assert.equal(body.error, "export_disabled");
});

test("routeExports proceeds normally when resolveEntitlement is not supplied (index.js's own optionality contract)", async () => {
  const env = { INTEL_R2: fakeR2WithIndicators([]) };
  const res = await routeExports("/api/v1/export/suricata.rules", REQ, env, CTX, "PRO", manyItems(5), "req-19", {});
  assert.equal(res.status, 200);
});
