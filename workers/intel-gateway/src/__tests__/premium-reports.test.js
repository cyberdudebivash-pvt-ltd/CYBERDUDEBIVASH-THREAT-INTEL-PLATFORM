// Premium Threat Report builders and handler: accuracy of a paid deliverable.
// Each case pins a defect verified against the production feed on 2026-09-28.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  analyseMitreCoverage, buildCVESummary, itemCveIds, handlePremiumReport, handleReportList, handleReportCsv,
  buildReportCsv, periodCoverage,
} from "../premium-reports.js";
import { planPrice } from "../cyber-watchdog.js";

const CITRIX = {
  id: "adv-citrix", title: "Citrix confirms two NetScaler RCE zero-days exploited in attacks", severity: "CRITICAL",
  cve_id: "CVE-2026-88771", cve_ids: ["CVE-2026-88771", "CVE-2026-88772"], kev_present: true, cvss_score: 9.8,
  exploit_maturity: "POC", source: "BleepingComputer",
  mitre_tactics: [{ id: "T1190", name: "Exploit Public-Facing Application", tactic: "Initial Access" }, "T1059"],
};
const ROLLER = {
  id: "adv-roller", title: "Apache Roller stored XSS", severity: "MEDIUM", cve_id: "CVE-2026-82381", cve_ids: ["CVE-2026-82381"],
  cvss_score: 10, kev_present: false, exploit_maturity: "UNPROVEN",
  mitre_tactics: [{ id: "T1059", name: "Command and Scripting Interpreter", tactic: "Execution" }],
};
const DUP = { ...CITRIX, id: "adv-citrix-2", title: "CISA orders feds to patch exploited Citrix flaws", cve_ids: ["CVE-2026-88771"] };

test("MITRE tactics stored as objects are named, never \"[object Object]\"; technique ids are techniques", () => {
  const m = analyseMitreCoverage([CITRIX, ROLLER]);
  assert.doesNotMatch(JSON.stringify(m), /object Object/);
  assert.deepEqual(m.top_tactics.map((t) => t.tactic).sort(), ["Execution", "Initial Access"]);
  assert.deepEqual(m.techniques_list.sort(), ["T1059", "T1190"]);
  assert.equal(m.unique_techniques, 2);
});

test("CVE summary: every CVE of a multi-CVE advisory, counted once, KEV first, real exploit evidence", () => {
  assert.deepEqual(itemCveIds(CITRIX), ["CVE-2026-88771", "CVE-2026-88772"]);
  assert.deepEqual(itemCveIds({ cve_id: "not-a-cve", cve_ids: ["cve-2026-1234", null, 7] }), ["CVE-2026-1234"]);
  const c = buildCVESummary([CITRIX, DUP, ROLLER]);
  assert.equal(c.total_cves, 3);
  assert.equal(c.kev_count, 2, "per unique CVE: the duplicate report does not double count");
  assert.deepEqual(c.top_cves.map((x) => x.id), ["CVE-2026-88771", "CVE-2026-88772", "CVE-2026-82381"], "KEV outranks a higher CVSS");
  assert.equal(c.top_cves[0].exploit_available, true, "exploit_maturity POC is exploit evidence");
  assert.equal(c.top_cves[2].exploit_available, false);
  assert.equal(c.exploit_available_count, 2);
});

const isoAgo = (sec) => new Date(Date.now() - sec * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");

// In-memory R2: the live feed key plus stored reports with customMetadata,
// listed in pages like the real binding.
function envWith(items, { generatedAt = isoAgo(600), feed, pageSize = 1000 } = {}) {
  const puts = [];
  const store = new Map();
  const analytics = [];
  return {
    puts, store, analytics,
    ANALYTICS_KV: { async get() { return null; }, async put(k, v) { analytics.push(k); } },
    INTEL_R2: {
      async get(key) {
        if (key === "api/v1/intel/latest.json") {
          if (feed === null) return null;
          const body = feed !== undefined ? feed : { generated_at: generatedAt, count: items.length, items };
          return { json: async () => body };
        }
        const o = store.get(key);
        return o ? { customMetadata: o.meta, json: async () => JSON.parse(o.body) } : null;
      },
      async put(key, body, opts) { puts.push({ key, opts }); store.set(key, { body, meta: opts.customMetadata }); },
      async list({ prefix, limit, cursor }) {
        const keys = [...store.keys()].filter((k) => k.startsWith(prefix)).sort();
        const start = cursor ? Number(cursor) : 0;
        const size = Math.min(limit, pageSize);
        const page = keys.slice(start, start + size);
        const truncated = start + size < keys.length;
        return {
          objects: page.map((k) => ({ key: k, size: 1, uploaded: new Date(), customMetadata: store.get(k).meta })),
          truncated, cursor: truncated ? String(start + size) : undefined,
        };
      },
    },
  };
}
const post = (body) => new Request("https://intel.example/api/reports/premium", { method: "POST", body: JSON.stringify(body || {}) });

test("free tier upsell quotes the Pro price Razorpay charges", async () => {
  const res = await handlePremiumReport(post(), envWith([]), { tier: "FREE" }, "rid");
  assert.equal(res.status, 403);
  const body = await res.json();
  assert.match(body.message, new RegExp("\\$" + planPrice("PRO").usd_monthly + "/mo"));
  assert.doesNotMatch(body.message, /\$29/);
});

test("reports rank advisories by priority, carry cve_ids and act-first guidance; MSSP gets full-tier caps", async () => {
  const filler = Array.from({ length: 60 }, (_, i) => ({ id: "low-" + i, title: "Low note " + i, severity: "LOW" }));
  const env = envWith([...filler, ROLLER, CITRIX]);
  const pro = await (await handlePremiumReport(post(), env, { tier: "PRO", sub: "cust_1" }, "rid")).json();
  assert.equal(pro.advisories_count, 50);
  assert.equal(pro.advisories[0].id, "adv-citrix", "the KEV zero-day survives the Pro cap although it is last in the feed");
  assert.deepEqual(pro.advisories[0].cve_ids, ["CVE-2026-88771", "CVE-2026-88772"]);
  assert.equal(pro.advisories[0].priority.band, "CRITICAL");
  assert.equal(pro.executive_summary.priority_actions[0].id, "adv-citrix");
  assert.ok(pro.executive_summary.priority_actions[0].evidence.some((e) => /CISA KEV/.test(e)));
  assert.ok(pro.executive_summary.key_recommendations.some((r) => /Patch 2 CISA KEV/.test(r)));
  const mssp = await (await handlePremiumReport(post(), env, { tier: "MSSP", sub: "cust_2" }, "rid")).json();
  assert.equal(mssp.advisories_count, 62, "MSSP is not capped at the Pro limit");
  assert.equal(env.puts[1].opts.customMetadata.key_id, "cust_2", "ownership still recorded");
});

test("cve_focused reports keep advisories that carry only cve_ids", async () => {
  const onlyIds = { id: "ids-only", title: "Multi CVE advisory", severity: "HIGH", cve_ids: ["CVE-2026-5555"] };
  const r = await (await handlePremiumReport(post({ type: "cve_focused" }), envWith([onlyIds, { id: "n", title: "No CVE", severity: "LOW" }]), { tier: "PRO", sub: "c" }, "rid")).json();
  assert.deepEqual(r.advisories.map((a) => a.id), ["ids-only"]);
});

const getReq = (url) => new Request("https://intel.example" + url);

test("no readable feed: 503, nothing stored, nothing counted", async () => {
  const env = envWith([], { feed: null });
  const res = await handlePremiumReport(post(), env, { tier: "PRO", sub: "c" }, "rid");
  assert.equal(res.status, 503);
  assert.equal((await res.json()).error, "intelligence_unavailable");
  assert.equal(env.puts.length, 0);
  assert.equal(env.analytics.length, 0);
});

test("stale feed: labelled NOT LIVE within 48h, refused beyond it", async () => {
  const stale = await handlePremiumReport(post(), envWith([CITRIX], { generatedAt: isoAgo(9 * 3600) }), { tier: "PRO", sub: "c" }, "rid");
  assert.equal(stale.status, 201);
  const body = await stale.json();
  assert.equal(body.intelligence_freshness.live, false);
  assert.match(body.intelligence_freshness.label, /NOT LIVE/);
  const ancient = envWith([CITRIX], { generatedAt: isoAgo(49 * 3600) });
  const res = await handlePremiumReport(post(), ancient, { tier: "PRO", sub: "c" }, "rid");
  assert.equal(res.status, 503);
  assert.equal((await res.json()).error, "intelligence_degraded");
  assert.equal(ancient.puts.length, 0);
  const fresh = await (await handlePremiumReport(post(), envWith([CITRIX]), { tier: "PRO", sub: "c" }, "rid")).json();
  assert.equal(fresh.intelligence_freshness.live, true);
});

test("the report period filters advisories and reports what it actually covers", async () => {
  const recent = { ...CITRIX, id: "recent", published_at: isoAgo(2 * 86400) };
  const old = { ...ROLLER, id: "old", published_at: isoAgo(20 * 86400) };
  const undated = { id: "undated", title: "Undated advisory", severity: "HIGH" };
  const weekly = await (await handlePremiumReport(post({ type: "weekly" }), envWith([recent, old, undated]), { tier: "PRO", sub: "c" }, "rid")).json();
  assert.deepEqual(weekly.advisories.map((a) => a.id).sort(), ["recent", "undated"]);
  assert.equal(weekly.coverage.excluded_outside_period, 1);
  assert.equal(weekly.coverage.undated_advisories, 1);
  assert.equal(weekly.coverage.earliest_published, recent.published_at.replace("Z", ".000Z"));
  assert.deepEqual(periodCoverage([], "2026-09-01", "2026-09-28", 0).earliest_published, null);
});

test("report list walks every R2 page, so an owner's reports never drop out", async () => {
  const env = envWith([CITRIX], { pageSize: 2 });
  for (let i = 0; i < 5; i++) await handlePremiumReport(post(), env, { tier: "PRO", sub: "other" }, "rid");
  await handlePremiumReport(post(), env, { tier: "PRO", sub: "owner" }, "rid");
  const list = await (await handleReportList(getReq("/api/reports/list"), env, { tier: "PRO", sub: "owner" }, "rid")).json();
  assert.equal(list.count, 1, "found beyond the first page");
  assert.equal(list.truncated, false);
  assert.match(list.reports[0].csv_url, /\/csv$/);
});

test("CSV export: owner only, per section, formula-safe", async () => {
  const hostile = { id: "evil", title: "=HYPERLINK(\"http://x\",\"click\")", severity: "HIGH", cve_ids: ["CVE-2026-1"], published_at: isoAgo(3600) };
  const env = envWith([CITRIX, hostile]);
  const made = await (await handlePremiumReport(post(), env, { tier: "PRO", sub: "owner" }, "rid")).json();
  const id = made.report_id;
  const res = await handleReportCsv(getReq(`/api/reports/${id}/csv`), env, { tier: "PRO", sub: "owner" }, "rid", id);
  assert.equal(res.status, 200);
  assert.match(res.headers.get("Content-Type"), /text\/csv/);
  assert.match(res.headers.get("Content-Disposition"), new RegExp(id + "-advisories\\.csv"));
  const csv = await res.text();
  const lines = csv.trim().split("\r\n");
  assert.equal(lines[0], "report_id,id,title,severity,priority_band,priority_score,risk_score,cve_ids,kev_present,actor_tag,source,processed_at");
  assert.equal(lines.length, 3);
  assert.match(lines[1], /CVE-2026-88771;CVE-2026-88772/);
  assert.ok(csv.includes("\"'=HYPERLINK("), "formula neutralised and quoted");
  const cves = await (await handleReportCsv(getReq(`/api/reports/${id}/csv?section=cves`), env, { tier: "PRO", sub: "owner" }, "rid", id)).text();
  assert.match(cves.split("\r\n")[1], /^rpt_[a-f0-9]{16},CVE-2026-88771,/);
  assert.equal((await handleReportCsv(getReq(`/api/reports/${id}/csv?section=bogus`), env, { tier: "PRO", sub: "owner" }, "rid", id)).status, 400);
  assert.equal((await handleReportCsv(getReq(`/api/reports/${id}/csv`), env, { tier: "PRO", sub: "intruder" }, "rid", id)).status, 404);
  assert.equal((await handleReportCsv(getReq(`/api/reports/${id}/csv`), env, { tier: "FREE" }, "rid", id)).status, 403);
  assert.equal(buildReportCsv({ report_id: "r", advisories: [{ id: "a", title: "-1 day", risk_score: -1 }] }).split("\r\n")[1].split(",")[2], "'-1 day");
});
