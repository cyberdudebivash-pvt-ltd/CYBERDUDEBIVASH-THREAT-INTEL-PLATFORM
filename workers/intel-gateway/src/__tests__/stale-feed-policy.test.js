import test from "node:test";
import assert from "node:assert/strict";
import { denyNonFreshLiveFeed, liveFreshCacheControl } from "../stale-feed-policy.js";

const NOW = Date.parse("2026-10-10T05:00:00Z");
const item = { id: "verified-1", title: "Original advisory", source_url: "https://publisher.example/advisory" };
const feed = (generated_at) => ({ generated_at, count: 1, items: [item] });

test("fresh authoritative feed is not denied", () => {
  assert.equal(denyNonFreshLiveFeed(feed("2026-10-10T04:59:00Z"), NOW), null);
});

test("stale feed is HTTP 503, no-store, and has zero exposed items", () => {
  const original = feed("2026-10-09T05:38:01Z");
  const before = JSON.stringify(original);
  const denial = denyNonFreshLiveFeed(original, NOW);
  assert.equal(denial.status, 503);
  assert.equal(denial.body.freshness_status, "STALE");
  assert.deepEqual(denial.body.items, []);
  assert.equal(denial.body.live_data_available, false);
  assert.match(denial.headers["Cache-Control"], /no-store/);
  assert.equal(JSON.stringify(original), before, "historical archive data must not be mutated");
});

test("missing, malformed, future, and empty input never exposes items", () => {
  for (const input of [null, { items: [item] }, { generated_at: "not-a-date", items: [item] }, feed("2026-10-11T05:00:00Z"), { generated_at: "2026-10-10T04:59:00Z", count: 0, items: [] }]) {
    const denial = denyNonFreshLiveFeed(input, NOW);
    assert.equal(denial.status, 503);
    assert.deepEqual(denial.body.items, []);
  }
});

test("inclusive freshness boundary does not cache stale intelligence", () => {
  assert.equal(denyNonFreshLiveFeed(feed("2026-10-09T23:00:00Z"), NOW), null);
  assert.equal(denyNonFreshLiveFeed(feed("2026-10-09T22:59:59Z"), NOW).status, 503);
});

test("fresh response cache expires strictly before the six-hour boundary", () => {
  const generated = "2026-10-09T23:00:00Z";
  const atNinetySec = Date.parse("2026-10-10T04:58:30.250Z");
  const ctl = liveFreshCacheControl(feed(generated), 120, atNinetySec);
  assert.equal(ctl, "public, max-age=89, must-revalidate");
  assert.equal(liveFreshCacheControl(feed(generated), 120, Date.parse("2026-10-10T04:59:59.750Z")),
    "public, max-age=0, must-revalidate");
  assert.equal(liveFreshCacheControl(feed(generated), 120, Date.parse("2026-10-10T05:00:00.001Z")), "no-store");
});
