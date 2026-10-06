// SOC Operations Center data model (js/soc-ops-model.js): every figure is
// counted from the live feed; missing fields are unknown, never zero; the
// freshness authority decides what may be shown.
import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const M = createRequire(import.meta.url)(path.resolve(HERE, "../../../../js/soc-ops-model.js"));

const NOW = Date.parse("2026-09-28T12:30:00Z");
const iso = (msAgo) => new Date(NOW - msAgo).toISOString();
const FEED = {
  generated_at: iso(600e3),
  items: [
    { id: "a", title: "Citrix NetScaler RCE exploited", severity: "CRITICAL", source: "BleepingComputer", published_at: iso(30 * 60e3),
      cve_ids: ["CVE-2026-88771", "cve-2026-88772"], kev_present: true, exploit_maturity: "POC", source_url: "https://example.org/a",
      mitre_tactics: [{ id: "T1190", tactic: "Initial Access" }, "T1059"] },
    { id: "b", title: "Roundcube SQLi", severity: "high", source: "SecurityAffairs", published_at: iso(5 * 3600e3),
      kev_present: "NO", metasploit_available: true, source_url: "javascript:alert(1)",
      mitre_tactics: [{ id: "T1059", tactic: "Execution" }, { id: "T1059.001", tactic: "Execution" }] },
    { id: "c", title: "Old advisory", severity: "MEDIUM", source: "BleepingComputer", published_at: iso(3 * 86400e3) },
    { id: "d", title: "Undated advisory", severity: "weird", source: "" },
    { id: "e", title: "   " },
  ],
};

test("publication: FRESH is live, STALE <= 48h is labelled NOT LIVE, anything else withholds", () => {
  assert.equal(M.publication({ freshness_status: "FRESH", feed_age_seconds: 60, feed_generated_at: "x" }).mode, "live");
  const stale = M.publication({ freshness_status: "STALE", feed_age_seconds: 9 * 3600 });
  assert.equal(stale.mode, "stale");
  assert.match(stale.label, /NOT LIVE/);
  assert.equal(M.publication({ freshness_status: "STALE", feed_age_seconds: 49 * 3600 }).mode, "down");
  assert.equal(M.publication({ freshness_status: "STALE", feed_age_seconds: "n/a" }).mode, "down");
  assert.equal(M.publication({ freshness_status: "EMPTY" }).mode, "down");
  assert.equal(M.publication(null).mode, "down");
  assert.match(M.publication(null, true).label, /UNAVAILABLE/);
});

test("KPIs are counted from the feed; KEV unknown is not counted as 'not listed'", () => {
  const m = M.model(FEED, NOW);
  assert.equal(m.kpis.advisories, 4, "a blank title is not an advisory");
  assert.deepEqual(m.kpis.by_severity, { CRITICAL: 1, HIGH: 1, MEDIUM: 1, LOW: 0, INFO: 0, UNKNOWN: 1 });
  assert.equal(m.kpis.kev_listed, 1);
  assert.equal(m.kpis.kev_stated_on, 2, "only items whose feed states KEV either way");
  assert.equal(m.kpis.exploit_evidence, 2, "exploit_maturity POC and metasploit_available");
  assert.equal(m.feed_generated_at, FEED.generated_at);
});

test("24h intake buckets by publication hour; older and undated items are counted apart", () => {
  const h = M.model(FEED, NOW).hourly;
  assert.equal(h.buckets.length, 24);
  assert.equal(h.last_24h, 2);
  assert.equal(h.older, 1);
  assert.equal(h.undated, 1);
  assert.equal(h.buckets[23].count, 1, "30 minutes ago lands in the current hour");
  assert.equal(h.buckets[23].critical, 1);
  assert.equal(h.buckets.reduce((n, b) => n + b.count, 0), 2);
});

test("sources and ATT&CK tactics come from the items; technique ids are not tactics", () => {
  const m = M.model(FEED, NOW);
  assert.deepEqual(m.sources, [{ name: "BleepingComputer", count: 2 }, { name: "SecurityAffairs", count: 1 }]);
  assert.deepEqual(m.attack.tactics, [{ name: "Execution", advisories: 1 }, { name: "Initial Access", advisories: 1 }], "one count per advisory per tactic");
  assert.deepEqual(m.attack.techniques, ["T1059", "T1059.001", "T1190"]);
});

test("stream: newest first, undated last, only https source links", () => {
  const s = M.model(FEED, NOW).stream;
  assert.deepEqual(s.map((r) => r.id), ["a", "b", "c", "d"]);
  assert.equal(s[0].url, "https://example.org/a");
  assert.equal(s[1].url, null, "a javascript: URL is never rendered as a link");
  assert.deepEqual(s[0].cves, ["CVE-2026-88771", "CVE-2026-88772"]);
  assert.equal(s[1].kev, false);
  assert.equal(s[2].kev, null);
  assert.equal(s[3].severity, "UNKNOWN");
  assert.equal(s[3].published, null);
});

test("empty or malformed feed yields zeros from counting nothing, never invented figures", () => {
  for (const feed of [null, {}, { items: "x" }, { items: [null, 7, {}] }]) {
    const m = M.model(feed, NOW);
    assert.equal(m.kpis.advisories, 0);
    assert.equal(m.hourly.last_24h, 0);
    assert.deepEqual(m.sources, []);
    assert.deepEqual(m.stream, []);
  }
});
