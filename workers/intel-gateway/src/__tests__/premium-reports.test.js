// Premium Threat Report builders and handler: accuracy of a paid deliverable.
// Each case pins a defect verified against the production feed on 2026-09-28.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  analyseMitreCoverage, buildCVESummary, itemCveIds, handlePremiumReport,
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

function envWith(items) {
  const puts = [];
  return {
    puts,
    INTEL_R2: {
      async get(key) { return key === "api/v1/intel/latest.json" ? { json: async () => ({ items }) } : null; },
      async put(key, body, opts) { puts.push({ key, opts }); },
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
