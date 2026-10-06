/**
 * FREE / anonymous responses carry no IOC values (F15, 2026-10-01).
 *
 * enforceTierGate("ioc_full") says "Full IOC arrays require Pro or
 * Enterprise", /api/v1/ioc/enriched answers FREE with 402, and the
 * commercial contract gives FREE no IOC visibility. applyTierGateV2() -- the
 * one FREE mask behind /api/feed.json, /api/v1/intel/latest.json,
 * /api/preview and the report fallbacks -- cleared `iocs` but copied
 * `iocs_by_type` through, so the same values reached anonymous callers
 * grouped by type. Live on c14dbae11 (2026-10-01T07:01Z): 55 of 57 items in
 * anonymous /api/feed.json and 29 of 57 in /api/v1/intel/latest.json carried
 * IOC values in iocs_by_type.
 *
 * Contract: for FREE, every IOC value carrier is emptied (keys kept, so the
 * shape is unchanged) and the paywall count reflects what was withheld;
 * PRO, ENTERPRISE and MSSP see the item unchanged. Through the real router,
 * no withheld value appears anywhere in an anonymous response body.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { applyTierGateV2 } from "../revenue-enforcement.js";
import { harness, feedObject, PRO_KEY, ENT_KEY } from "./watchdog-harness.js";

const IOC_VALUES = {
  domain: ["c2-relay.f15-ioc.test", "stage2.f15-ioc.test"],
  ipv4: ["198.51.100.77"],
  sha256: ["f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f15f"],
};
const ALL_VALUES = Object.values(IOC_VALUES).flat();

function item(overrides = {}) {
  return {
    id: "intel--f15-1", title: "Loader campaign with C2 relays", severity: "HIGH", source: "Vendor",
    processed_at: "2026-09-30T05:00:00Z",
    iocs: ALL_VALUES.map((value) => ({ value })),
    iocs_by_type: JSON.parse(JSON.stringify(IOC_VALUES)),
    ioc_counts: { domain: 2, ipv4: 1, sha256: 1 },
    ...overrides,
  };
}

test("FREE: iocs_by_type is emptied with iocs; keys, counts and paywall stay", () => {
  const gated = applyTierGateV2(item(), "free", null);
  assert.deepEqual(gated.iocs, []);
  assert.deepEqual(gated.iocs_by_type, { domain: [], ipv4: [], sha256: [] }, "IOC values leaked through iocs_by_type");
  assert.deepEqual(gated.ioc_counts, { domain: 2, ipv4: 1, sha256: 1 }, "counts are not values; they stay visible");
  assert.equal(gated.ioc_paywall.count, ALL_VALUES.length);
  assert.equal(gated.ioc_paywall.allowed, false);
  for (const v of ALL_VALUES) assert.ok(!JSON.stringify(gated).includes(v), `${v} survived the FREE mask`);
});

test("FREE: values only in iocs_by_type (iocs empty) are still withheld", () => {
  const gated = applyTierGateV2(item({ iocs: [] }), "free", null);
  assert.deepEqual(gated.iocs_by_type, { domain: [], ipv4: [], sha256: [] });
  assert.equal(gated.ioc_paywall.count, ALL_VALUES.length);
  for (const v of ALL_VALUES) assert.ok(!JSON.stringify(gated).includes(v), `${v} survived the FREE mask`);
});

test("FREE: an item with no IOCs gets no paywall block", () => {
  const gated = applyTierGateV2(item({ iocs: [], iocs_by_type: { domain: [] }, ioc_counts: {} }), "free", null);
  assert.equal(gated.ioc_paywall, undefined);
  assert.deepEqual(gated.iocs_by_type, { domain: [] });
});

test("negative control: paid tiers keep every IOC value", () => {
  for (const tier of ["pro", "enterprise", "mssp"]) {
    const gated = applyTierGateV2(item(), tier, null);
    assert.deepEqual(gated.iocs_by_type, IOC_VALUES, `${tier} lost entitled IOC values`);
    assert.equal(gated.iocs.length, ALL_VALUES.length);
    assert.equal(gated.ioc_paywall, undefined);
  }
});

test("router: no anonymous surface returns a withheld IOC value", async () => {
  const hx = harness({ feed: feedObject([item(), item({ id: "intel--f15-2", iocs: [] })]) });
  for (const path of ["/api/v1/intel/latest.json", "/api/feed.json", "/api/preview/", "/api/v1/intel/apex.json", "/api/v1/intel/top10.json"]) {
    const res = await hx.call("GET", path);
    assert.equal(res.status, 200, `${path}: HTTP ${res.status} ${res.text.slice(0, 120)}`);
    for (const v of ALL_VALUES) assert.ok(!res.text.includes(v), `${path} leaked ${v} to an anonymous caller`);
  }
});

test("router negative control: PRO and ENTERPRISE keys still receive the values", async () => {
  const hx = harness({ feed: feedObject([item()]) });
  for (const key of [PRO_KEY, ENT_KEY]) {
    const res = await hx.call("GET", "/api/v1/intel/latest.json", { key });
    assert.equal(res.status, 200);
    for (const v of ALL_VALUES) assert.ok(res.text.includes(v), `entitled caller lost ${v}`);
  }
});
