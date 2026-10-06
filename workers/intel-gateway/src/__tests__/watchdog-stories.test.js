// Cyber Watchdog story grouping: one brief row per story, evidence-only.
// Pins the production case (2026-09-28, Citrix NetScaler reported by several
// outlets) and the negative controls that keep distinct threats apart.
import assert from "node:assert/strict";
import { test } from "node:test";
import { groupStories, storyMatch, corroboration, sourceKey } from "../watchdog-stories.js";
import { sourceKey as aiFeedSourceKey } from "../ai-threat-feed.js";
import { buildWatchdogBrief, routeWatchdog } from "../cyber-watchdog.js";

const KEV_ARTICLE = {
  id: "bc", title: "Citrix confirms two NetScaler RCE zero-days exploited in attacks", source: "BleepingComputer",
  source_url: "https://www.bleepingcomputer.com/news/security/citrix-netscaler", cve_ids: ["CVE-2026-88771", "CVE-2026-88772"],
  kev_product: "Citrix NetScaler", kev_present: true, cvss_score: 9.8, severity: "CRITICAL", published_at: "2026-09-27T12:00:00Z",
};
const SA_ARTICLE = {
  id: "sa", title: "Citrix Confirmed Two New NetScaler Flaws Exploited as Zero-Day", source: "SecurityAffairs",
  source_url: "https://securityaffairs.com/199873/citrix", cve_ids: [], severity: "HIGH", published_at: "2026-09-27T09:00:00Z",
};
const CISA_ORDER = {
  id: "cisa", title: "CISA orders feds to patch exploited Citrix flaws by Wednesday", source: "BleepingComputer",
  source_url: "https://www.bleepingcomputer.com/news/security/cisa-orders", cve_ids: [], severity: "HIGH", published_at: "2026-09-27T15:00:00Z",
};

test("production case: the NetScaler articles form one story led by the KEV report, with cited evidence", () => {
  const stories = groupStories([KEV_ARTICLE, SA_ARTICLE, CISA_ORDER]);
  assert.equal(stories.length, 2);
  assert.equal(stories[0].lead.id, "bc");
  const c = corroboration(stories[0]);
  assert.equal(c.reports, 2);
  assert.deepEqual(c.sources, ["BleepingComputer", "SecurityAffairs"]);
  assert.equal(c.related[0].id, "sa");
  assert.equal(c.related[0].rule, "kev_product_in_title");
  assert.match(c.related[0].evidence, /^citrix netscaler \+ /);
  assert.equal(stories[1].lead.id, "cisa", "a title naming only the vendor is not enough to merge");
});

test("shared CVE and same source article merge; different CVEs never do", () => {
  const a = { id: "a", title: "Roundcube SQL injection exploited", cve_ids: ["CVE-2026-48842"] };
  const b = { id: "b", title: "Webmail bug under attack", cve_id: "cve-2026-48842" };
  assert.deepEqual(storyMatch(a, b), { rule: "shared_cve", evidence: "CVE-2026-48842" });
  const c = { id: "c", title: "Different story", source_url: "https://x.org/p?utm_source=rss" };
  const d = { id: "d", title: "Retitled copy", source_url: "https://X.org/p/" };
  assert.equal(storyMatch(c, d).rule, "same_source_article");
  const e = { ...KEV_ARTICLE, id: "e", cve_ids: ["CVE-2026-99999"], source_url: "https://other.example/e" };
  assert.equal(storyMatch(KEV_ARTICLE, e), null, "same product, different CVEs: two threats");
});

test("negative controls for the title rule", () => {
  // Bare vendor as the KEV product is too broad.
  assert.equal(storyMatch({ ...KEV_ARTICLE, kev_product: "Citrix" }, SA_ARTICLE), null);
  // Only one shared specific word beyond the product.
  assert.equal(storyMatch(KEV_ARTICLE, { ...SA_ARTICLE, title: "Citrix NetScaler appliance hit by botnet" }), null);
  // Outside the 7-day window.
  assert.equal(storyMatch(KEV_ARTICLE, { ...SA_ARTICLE, published_at: "2026-09-10T00:00:00Z" }), null);
  // No date: never merged on title evidence.
  assert.equal(storyMatch(KEV_ARTICLE, { ...SA_ARTICLE, published_at: undefined }), null);
  // The candidate names its own CVE: only the CVE rule may merge it.
  assert.equal(storyMatch(KEV_ARTICLE, { ...SA_ARTICLE, cve_ids: ["CVE-2026-11111"] }), null);
  // Symmetric: the CVE-less report may come first.
  assert.equal(storyMatch(SA_ARTICLE, KEV_ARTICLE).rule, "kev_product_in_title");
});

test("sourceKey has one implementation, re-exported by the AI feed", () => {
  assert.equal(aiFeedSourceKey, sourceKey);
});

const NOW_MS = Date.parse("2026-09-28T06:00:00Z");
const feed = (items) => ({ generated_at: "2026-09-28T05:00:00Z", count: items.length, items });

test("brief 3.2.0: one row per story by default, ?group=none keeps one row per item", async () => {
  const items = [CISA_ORDER, SA_ARTICLE, KEV_ARTICLE];
  const b = buildWatchdogBrief(feed(items), { tier: "FREE", nowMs: NOW_MS });
  assert.equal(b.body.group, "story");
  assert.equal(b.body.count, 2);
  assert.equal(b.body.stories, 2);
  assert.equal(b.body.feed_items_seen, 3, "feed counts are not reduced");
  assert.equal(b.body.items[0].id, "bc", "the story is led by its highest-priority report");
  assert.equal(b.body.items[0].corroboration.reports, 2);
  assert.equal(b.body.items[1].corroboration.reports, 1);
  const capped = buildWatchdogBrief(feed(items), { tier: "FREE", nowMs: NOW_MS, limit: 1 });
  assert.equal(capped.body.truncated, true);
  const flat = buildWatchdogBrief(feed(items), { tier: "FREE", nowMs: NOW_MS, group: "none" });
  assert.equal(flat.body.count, 3);
  assert.equal(flat.body.items[0].corroboration, undefined);
  const byFeed = buildWatchdogBrief(feed(items), { tier: "FREE", nowMs: NOW_MS, sort: "feed" });
  assert.equal(byFeed.body.items[1].id, "sa", "feed order: the first report in the feed leads");
  assert.equal(byFeed.body.items[1].corroboration.related[0].id, "bc");
  const run = (qs) => routeWatchdog({ path: "/api/watchdog/brief", method: "GET", auth: { tier: "FREE" }, feed: feed(items), nowMs: NOW_MS, searchParams: new URLSearchParams(qs) });
  assert.equal((await run("")).body.count, 2);
  assert.equal((await run("group=none")).body.count, 3);
  assert.equal((await run("group=bogus")).body.group, "story");
});
