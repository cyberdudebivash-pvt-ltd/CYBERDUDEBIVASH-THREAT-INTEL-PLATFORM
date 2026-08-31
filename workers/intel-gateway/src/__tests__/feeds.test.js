import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildC2IpList,
  buildRansomwareDomainList,
  buildCveExploitedSummary,
  renderConversionBanner,
  renderPlaintextFeed,
} from "../feeds.js";

// ---------------------------------------------------------------------------
// Public lead-magnet feeds (GET /feeds/*). Pure functions, no KV/network --
// index.js passes in the same feed items loadFeedItems() already loads for
// every other endpoint. See feeds.js's header comment for why CVE ids are
// read from iocs_by_type.cve rather than a top-level cve_ids field.
// ---------------------------------------------------------------------------

function item(overrides = {}) {
  return {
    title: "Test item",
    severity: "HIGH",
    risk_score: 5.0,
    threat_type: "Malware",
    source: "TestFeed",
    published: "2026-01-01T00:00:00Z",
    iocs_by_type: {},
    kev_present: false,
    ...overrides,
  };
}

test("buildC2IpList only pulls IPs from active-infrastructure threat types", () => {
  const items = [
    item({ threat_type: "Malware", iocs_by_type: { ipv4: ["1.1.1.1"] } }),
    item({ threat_type: "Vulnerability", iocs_by_type: { ipv4: ["2.2.2.2"] } }), // must be excluded
    item({ threat_type: "Ransomware", iocs_by_type: { ipv4: ["3.3.3.3"] } }),
  ];
  const ips = buildC2IpList(items, 100);
  assert.deepEqual(ips.sort(), ["1.1.1.1", "3.3.3.3"]);
});

test("buildC2IpList deduplicates and respects the limit", () => {
  const items = [
    item({ threat_type: "Malware", iocs_by_type: { ipv4: ["1.1.1.1", "1.1.1.1"] } }),
    item({ threat_type: "APT", iocs_by_type: { ipv4: ["2.2.2.2"] } }),
  ];
  assert.deepEqual(buildC2IpList(items, 100).sort(), ["1.1.1.1", "2.2.2.2"]);
  assert.equal(buildC2IpList(items, 1).length, 1);
});

test("buildRansomwareDomainList only pulls domains from Ransomware-typed items", () => {
  const items = [
    item({ threat_type: "Ransomware", iocs_by_type: { domain: ["evil.example"] } }),
    item({ threat_type: "Malware", iocs_by_type: { domain: ["other.example"] } }), // must be excluded
  ];
  assert.deepEqual(buildRansomwareDomainList(items, 100), ["evil.example"]);
});

test("buildCveExploitedSummary ranks KEV-confirmed CVEs first, then by EPSS", () => {
  const items = [
    item({ title: "low epss", iocs_by_type: { cve: ["CVE-2026-0001"] }, epss_score: 0.1, kev_present: false, risk_score: 9.0 }),
    item({ title: "kev item", iocs_by_type: { cve: ["CVE-2026-0002"] }, epss_score: 0.05, kev_present: true, risk_score: 1.0 }),
    item({ title: "high epss", iocs_by_type: { cve: ["CVE-2026-0003"] }, epss_score: 0.9, kev_present: false, risk_score: 2.0 }),
  ];
  const result = buildCveExploitedSummary(items, 25);
  assert.equal(result.cves[0].cve_id, "CVE-2026-0002", "KEV-confirmed must rank first regardless of EPSS/risk");
  assert.equal(result.cves[1].cve_id, "CVE-2026-0003", "higher EPSS ranks above lower EPSS among non-KEV");
  assert.equal(result.cves[2].cve_id, "CVE-2026-0001");
  assert.equal(result.total_candidates, 3);
  assert.equal(result.kev_confirmed_count, 1);
});

test("buildCveExploitedSummary reads CVE ids from iocs_by_type.cve, not a top-level cve_ids field", () => {
  const items = [item({ iocs_by_type: { cve: ["CVE-2026-9999"] } })];
  const result = buildCveExploitedSummary(items, 25);
  assert.equal(result.cves.length, 1);
  assert.equal(result.cves[0].cve_id, "CVE-2026-9999");
});

test("buildCveExploitedSummary falls back to a top-level cve_ids field if present", () => {
  const items = [item({ cve_ids: ["CVE-2026-8888"], iocs_by_type: {} })];
  const result = buildCveExploitedSummary(items, 25);
  assert.equal(result.cves[0].cve_id, "CVE-2026-8888");
});

test("buildCveExploitedSummary deduplicates by CVE id and respects the limit", () => {
  const items = Array.from({ length: 30 }, (_, i) =>
    item({ iocs_by_type: { cve: [`CVE-2026-${1000 + i}`] }, risk_score: i })
  );
  const result = buildCveExploitedSummary(items, 25);
  assert.equal(result.cves.length, 25);
  assert.equal(result.total_candidates, 30);
});

test("buildCveExploitedSummary skips items with no CVE id at all", () => {
  const items = [item({ iocs_by_type: {} }), item({ iocs_by_type: { cve: [] } })];
  const result = buildCveExploitedSummary(items, 25);
  assert.equal(result.cves.length, 0);
  assert.equal(result.total_candidates, 0);
});

test("renderConversionBanner truthfully states the real count when under the cap", () => {
  const banner = renderConversionBanner("Active C2 IP", 4, 100, "c2_feed");
  assert.match(banner, /every active c2 ip indicator currently tracked \(4\)/i);
  assert.doesNotMatch(banner, /Top 100 indicators/);
});

test("renderConversionBanner claims 'Top N' only when the cap was actually hit", () => {
  const banner = renderConversionBanner("Active C2 IP", 100, 100, "c2_feed");
  assert.match(banner, /Top 100 indicators/);
});

test("renderConversionBanner always points at the real .html pricing URL, not a bare dead link", () => {
  const banner = renderConversionBanner("Active C2 IP", 4, 100, "c2_feed");
  assert.match(banner, /\/pricing\.html\?ref=c2_feed/);
});

test("renderPlaintextFeed places every indicator on its own line after the banner", () => {
  const body = renderPlaintextFeed("Active C2 IP", ["1.1.1.1", "2.2.2.2"], 100, "c2_feed");
  const lines = body.trim().split("\n");
  assert.equal(lines[lines.length - 2], "1.1.1.1");
  assert.equal(lines[lines.length - 1], "2.2.2.2");
});

test("renderPlaintextFeed with zero indicators still renders a valid banner and no stray lines", () => {
  const body = renderPlaintextFeed("Active C2 IP", [], 100, "c2_feed");
  assert.ok(body.includes("Sentinel APEX"));
  assert.ok(!body.trim().endsWith("undefined"));
});
