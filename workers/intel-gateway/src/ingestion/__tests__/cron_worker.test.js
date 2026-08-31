import assert from "node:assert/strict";
import { test } from "node:test";
import {
  normalizeKEV, normalizeURLhaus, normalizeTorExitNodes,
  computeSentinelRiskScore, mergeIndicators, buildIndicatorSummary,
  runScheduledIngestion, getLiveIndicatorsSummary, getLiveIndicators,
  INDICATORS_R2_KEY, SUMMARY_R2_KEY,
} from "../cron_worker.js";

// ---------------------------------------------------------------------------
// Task 4: ingestion parser validation on mocked upstream feed payloads +
// scoring/merge/TTL logic. No live network calls -- runScheduledIngestion's
// own network dependency is exercised via a monkey-patched global fetch,
// restored after each test that uses it.
// ---------------------------------------------------------------------------

// --- normalizeKEV -----------------------------------------------------------

test("normalizeKEV maps CISA KEV vulnerabilities into the common indicator shape", () => {
  const raw = {
    vulnerabilities: [
      { cveID: "cve-2026-00001", vendorProject: "Acme", product: "Widget", vulnerabilityName: "Acme RCE", dateAdded: "2026-08-01", dueDate: "2026-08-22", knownRansomwareCampaignUse: "Known" },
      { cveID: "CVE-2026-00002", vendorProject: "Foo", product: "Bar", dateAdded: "2026-08-15", knownRansomwareCampaignUse: "Unknown" },
    ],
  };
  const out = normalizeKEV(raw);
  assert.equal(out.length, 2);
  assert.equal(out[0].indicator, "CVE-2026-00001"); // uppercased
  assert.equal(out[0].type, "cve");
  assert.equal(out[0].source, "CISA_KEV");
  assert.ok(out[0].tags.includes("ransomware"));
  assert.ok(out[0].tags.includes("kev"));
  assert.equal(out[1].tags.includes("ransomware"), false);
  assert.equal(out[0].meta.vendor_project, "Acme");
});

test("normalizeKEV tolerates missing/malformed input without throwing", () => {
  assert.deepEqual(normalizeKEV(null), []);
  assert.deepEqual(normalizeKEV({}), []);
  assert.deepEqual(normalizeKEV({ vulnerabilities: [{ vendorProject: "no-cve-id" }] }), []);
});

// --- normalizeURLhaus --------------------------------------------------------

test("normalizeURLhaus handles the id-keyed-array-of-one upstream shape", () => {
  const raw = {
    "12345": [{ id: "12345", url: "http://bad.example.com/payload.exe", date_added: "2026-08-20 10:00:00", threat: "malware_download", url_status: "online", tags: ["elf", "mirai"] }],
  };
  const out = normalizeURLhaus(raw);
  assert.equal(out.length, 1);
  assert.equal(out[0].type, "url");
  assert.equal(out[0].source, "URLHAUS");
  assert.equal(out[0].meta.host, "bad.example.com");
  assert.deepEqual(out[0].tags, ["elf", "mirai"]);
});

test("normalizeURLhaus handles a plain array shape and skips entries with no url", () => {
  const raw = [{ url: "http://x.example/a" }, { id: "no-url-field" }];
  const out = normalizeURLhaus(raw);
  assert.equal(out.length, 1);
  assert.equal(out[0].indicator, "http://x.example/a");
});

test("normalizeURLhaus tolerates malformed URLs without throwing", () => {
  const out = normalizeURLhaus([{ url: "not a valid url" }]);
  assert.equal(out.length, 1);
  assert.equal(out[0].meta.host, "");
});

// --- normalizeTorExitNodes ---------------------------------------------------

test("normalizeTorExitNodes keeps only valid IPv4 lines, drops comments/blank lines", () => {
  const text = "# Tor bulk exit list\n1.2.3.4\n\n# comment\n256.1.1.1\nnot-an-ip\n8.8.8.8\n";
  const out = normalizeTorExitNodes(text);
  const ips = out.map(i => i.indicator);
  assert.deepEqual(ips, ["1.2.3.4", "8.8.8.8"]);
  assert.ok(out.every(i => i.type === "ip" && i.source === "TOR_EXIT_NODE"));
});

test("normalizeTorExitNodes tolerates empty/undefined input", () => {
  assert.deepEqual(normalizeTorExitNodes(""), []);
  assert.deepEqual(normalizeTorExitNodes(undefined), []);
});

// --- computeSentinelRiskScore -------------------------------------------------

test("computeSentinelRiskScore stays within 0-100 and ranks sources/recency sensibly", () => {
  const nowIso = new Date().toISOString();
  const oldIso = new Date(Date.now() - 29 * 86400000).toISOString();

  const freshKev = { source: "CISA_KEV", last_seen: nowIso, sighting_count: 1, tags: ["kev"] };
  const oldTor   = { source: "TOR_EXIT_NODE", last_seen: oldIso, sighting_count: 1, tags: ["tor"] };

  const kevScore = computeSentinelRiskScore(freshKev);
  const torScore = computeSentinelRiskScore(oldTor);

  assert.ok(kevScore >= 0 && kevScore <= 100);
  assert.ok(torScore >= 0 && torScore <= 100);
  assert.ok(kevScore > torScore, `fresh high-confidence KEV (${kevScore}) should outscore a stale Tor node (${torScore})`);
});

test("computeSentinelRiskScore rewards repeat sightings", () => {
  const nowIso = new Date().toISOString();
  const single = computeSentinelRiskScore({ source: "URLHAUS", last_seen: nowIso, sighting_count: 1, tags: [] });
  const repeat = computeSentinelRiskScore({ source: "URLHAUS", last_seen: nowIso, sighting_count: 20, tags: [] });
  assert.ok(repeat > single);
});

// --- mergeIndicators ----------------------------------------------------------

test("mergeIndicators upserts a repeat sighting: bumps sighting_count, refreshes last_seen", () => {
  const previous = [{
    indicator: "1.2.3.4", type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6,
    first_seen: "2026-08-01T00:00:00.000Z", last_seen: "2026-08-01T00:00:00.000Z",
    sighting_count: 1, tags: ["tor"], meta: {},
  }];
  const incoming = [{
    indicator: "1.2.3.4", type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6,
    first_seen: "2026-08-25T00:00:00.000Z", last_seen: "2026-08-25T00:00:00.000Z",
    sighting_count: 1, tags: ["tor", "anonymization"], meta: {},
  }];
  const merged = mergeIndicators(previous, incoming);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].sighting_count, 2);
  assert.equal(merged[0].last_seen, "2026-08-25T00:00:00.000Z");
  assert.deepEqual(new Set(merged[0].tags), new Set(["tor", "anonymization"]));
  assert.ok(typeof merged[0].risk_score === "number");
  assert.ok(merged[0].expires_at);
});

test("mergeIndicators drops indicators whose last_seen is older than the 30-day TTL", () => {
  const expired = {
    indicator: "9.9.9.9", type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6,
    first_seen: "2026-01-01T00:00:00.000Z", last_seen: "2026-01-01T00:00:00.000Z",
    sighting_count: 1, tags: [], meta: {},
  };
  const fresh = {
    indicator: "8.8.8.8", type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6,
    first_seen: new Date().toISOString(), last_seen: new Date().toISOString(),
    sighting_count: 1, tags: [], meta: {},
  };
  const merged = mergeIndicators([expired], [fresh]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].indicator, "8.8.8.8");
});

test("mergeIndicators sorts the result by risk_score descending", () => {
  const nowIso = new Date().toISOString();
  const items = [
    { indicator: "a-cve", type: "cve", source: "TOR_EXIT_NODE", source_confidence: 0.6, first_seen: nowIso, last_seen: nowIso, sighting_count: 1, tags: [], meta: {} },
    { indicator: "b-cve", type: "cve", source: "CISA_KEV", source_confidence: 0.95, first_seen: nowIso, last_seen: nowIso, sighting_count: 1, tags: ["ransomware"], meta: {} },
  ];
  const merged = mergeIndicators([], items);
  assert.equal(merged[0].source, "CISA_KEV");
  assert.ok(merged[0].risk_score >= merged[1].risk_score);
});

// --- buildIndicatorSummary -----------------------------------------------------

test("buildIndicatorSummary computes by_source/by_type/high_risk_count correctly", () => {
  const items = [
    { indicator: "a", type: "cve", source: "CISA_KEV", risk_score: 90 },
    { indicator: "b", type: "ip", source: "TOR_EXIT_NODE", risk_score: 50 },
    { indicator: "c", type: "url", source: "URLHAUS", risk_score: 71 },
  ];
  const summary = buildIndicatorSummary(items, [{ name: "CISA_KEV", ok: true, items: [1] }], "2026-08-31T00:00:00.000Z");
  assert.equal(summary.total_indicators, 3);
  assert.equal(summary.high_risk_count, 2); // >= 70
  assert.equal(summary.by_source.CISA_KEV, 1);
  assert.equal(summary.by_type.url, 1);
  assert.equal(summary.top_indicators.length, 3);
});

// --- runScheduledIngestion (I/O layer, fetch + R2 mocked) ----------------------

function makeFakeR2() {
  const store = new Map();
  return {
    store,
    async get(key) {
      if (!store.has(key)) return null;
      const text = store.get(key);
      return { text: async () => text };
    },
    async put(key, value) {
      store.set(key, value);
    },
  };
}

test("runScheduledIngestion writes both R2 keys and degrades gracefully when one source fails", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });

  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("cisa.gov")) {
      return { ok: true, json: async () => ({ vulnerabilities: [{ cveID: "CVE-2026-99999", dateAdded: "2026-08-01" }] }) };
    }
    if (u.includes("urlhaus")) {
      throw new Error("simulated URLhaus outage");
    }
    if (u.includes("torproject")) {
      return { ok: true, text: async () => "1.1.1.1\n2.2.2.2\n" };
    }
    throw new Error(`unexpected URL in test: ${u}`);
  };

  const env = { INTEL_R2: makeFakeR2() };
  const summary = await runScheduledIngestion(env);

  assert.equal(summary.total_indicators, 3); // 1 KEV + 0 URLhaus (failed) + 2 Tor
  assert.ok(env.INTEL_R2.store.has(INDICATORS_R2_KEY));
  assert.ok(env.INTEL_R2.store.has(SUMMARY_R2_KEY));

  const urlhausResult = summary.sources.find(s => s.name === "URLHAUS");
  assert.equal(urlhausResult.ok, false);
  assert.match(urlhausResult.error, /simulated URLhaus outage/);

  const kevResult = summary.sources.find(s => s.name === "CISA_KEV");
  assert.equal(kevResult.ok, true);
  assert.equal(kevResult.ingested, 1);
});

test("runScheduledIngestion upserts against a previous snapshot already in R2", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("cisa.gov")) return { ok: true, json: async () => ({ vulnerabilities: [] }) };
    if (u.includes("urlhaus")) return { ok: true, json: async () => ({}) };
    if (u.includes("torproject")) return { ok: true, text: async () => "3.3.3.3\n" };
    throw new Error(`unexpected URL: ${u}`);
  };

  const env = { INTEL_R2: makeFakeR2() };
  const nowIso = new Date().toISOString();
  await env.INTEL_R2.put(INDICATORS_R2_KEY, JSON.stringify({
    generated_at: nowIso, count: 1,
    items: [{ indicator: "3.3.3.3", type: "ip", source: "TOR_EXIT_NODE", source_confidence: 0.6, first_seen: nowIso, last_seen: nowIso, sighting_count: 5, tags: ["tor"], meta: {} }],
  }));

  const summary = await runScheduledIngestion(env);
  assert.equal(summary.total_indicators, 1);

  const written = JSON.parse(env.INTEL_R2.store.get(INDICATORS_R2_KEY));
  assert.equal(written.items[0].sighting_count, 6); // upserted, not duplicated
});

// --- getLiveIndicatorsSummary / getLiveIndicators (fail-soft reads) ------------

test("getLiveIndicatorsSummary and getLiveIndicators fail soft with no INTEL_R2 binding", async () => {
  assert.equal(await getLiveIndicatorsSummary({}), null);
  assert.deepEqual(await getLiveIndicators({}), []);
});

test("getLiveIndicatorsSummary fails soft on corrupt JSON in R2", async () => {
  const env = { INTEL_R2: makeFakeR2() };
  await env.INTEL_R2.put(SUMMARY_R2_KEY, "{not valid json");
  assert.equal(await getLiveIndicatorsSummary(env), null);
});

test("getLiveIndicators reads back a written snapshot and respects `limit`", async () => {
  const env = { INTEL_R2: makeFakeR2() };
  await env.INTEL_R2.put(INDICATORS_R2_KEY, JSON.stringify({ items: [{ indicator: "a" }, { indicator: "b" }, { indicator: "c" }] }));
  const limited = await getLiveIndicators(env, { limit: 2 });
  assert.equal(limited.length, 2);
});
