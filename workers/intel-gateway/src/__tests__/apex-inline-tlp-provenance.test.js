/**
 * P0 #725 after merge of #731: inline Apex/AI summary builders must
 * preserve source TLP metadata and reject any unverified source record.
 * Exercises the real gateway router with R2 summary objects absent.
 * No network calls or production storage; harness uses fake in-memory R2.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { harness, feedObject, PRO_KEY } from "./watchdog-harness.js";

const PUBLIC = Object.freeze({
  id: "intel--apex-tlp-public-1",
  title: "Synthetic approved public advisory",
  severity: "CRITICAL",
  risk_score: 8.1,
  tlp: "TLP:CLEAR",
  classification: "TLP:CLEAR",
  source: "test-only",
  cve_ids: ["CVE-2026-1000"],
  iocs: [{ value: "198.51.100.33" }],
});

const cases = [
  "/api/v1/intel/apex.json",
  "/api/v1/intel/ai_summary.json",
];

test("derived Apex and AI-summary advisory rows retain the explicitly approved source TLP", async () => {
  const h = harness({ feed: feedObject([PUBLIC]) });
  for (const path of cases) {
    const res = await h.call("GET", path);
    assert.equal(res.status, 200, path + ": " + JSON.stringify(res.body));
    const rows = path.includes("apex") ? res.body.top_advisories : res.body.top_critical_advisories;
    assert.ok(Array.isArray(rows) && rows.length > 0, path);
    assert.equal(rows[0].tlp, "TLP:CLEAR");
    assert.equal(rows[0].classification, "TLP:CLEAR");
    // FREE remains FREE, regardless of the approved TLP label.
    assert.equal(res.body._tier, "FREE");
  }
});

test("derived Apex/summary remains usable for paid keys without relaxing anonymous TLP checks", async () => {
  const h = harness({ feed: feedObject([PUBLIC]) });
  for (const path of cases) {
    const res = await h.call("GET", path, { key: PRO_KEY });
    assert.equal(res.status, 200, path);
    const rows = path.includes("apex") ? res.body.top_advisories : res.body.top_critical_advisories;
    assert.equal(rows[0].tlp, "TLP:CLEAR");
  }
});

test("both derived endpoints fail closed on missing, restricted, conflicting or nested restriction", async () => {
  const scenarios = [
    { name: "unlabelled", item: (({ tlp, classification, ...rest }) => rest)(PUBLIC) },
    { name: "RED", item: { ...PUBLIC, tlp: "TLP:RED" } },
    { name: "conflicting document", item: { ...PUBLIC, classification: "TLP:CLEAR; TLP:AMBER" } },
    { name: "nested upstream", item: { ...PUBLIC, evidence: { tlp: "TLP:GREEN", private_blob: "secret-sentinel" } } },
  ];
  for (const { name, item } of scenarios) {
    const h = harness({ feed: feedObject([item]) });
    for (const path of cases) {
      const res = await h.call("GET", path);
      assert.equal(res.status, 503, name + ": " + path);
      assert.equal(res.headers.get("cache-control"), "no-store");
      assert.ok(!JSON.stringify(res.body).includes(item.title), "unapproved source text reached response");
      assert.ok(!JSON.stringify(res.body).includes("secret-sentinel"));
    }
  }
});

test("summary top-N selection cannot hide an unapproved off-window input", async () => {
  const feed = Array.from({ length: 22 }, (_, i) => ({
    ...PUBLIC,
    id: "intel--approved-" + i,
    title: "Public advisory " + i,
  }));
  feed.push({ ...PUBLIC, id: "intel--unapproved", tlp: "TLP:RED", title: "Private advisory" });
  const h = harness({ feed: feedObject(feed) });
  for (const path of cases) {
    const res = await h.call("GET", path);
    assert.equal(res.status, 503, path);
    assert.ok(!JSON.stringify(res.body).includes("Private advisory"));
  }
});
