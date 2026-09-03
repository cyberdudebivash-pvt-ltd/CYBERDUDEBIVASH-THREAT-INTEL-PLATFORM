import assert from "node:assert/strict";
import { test } from "node:test";
import {
  handleP41Capabilities,
  handleP41CapabilityDetail,
  handleP41Observability,
} from "../p41-handlers.js";

// ---------------------------------------------------------------------------
// Mock R2 environment -- env.INTEL_R2.get(key) returns an object with a
// text() method, matching the real Cloudflare R2Object contract used by
// every other P-layer's loader (see p40-handlers.test.js for the identical
// pattern this file follows).
// ---------------------------------------------------------------------------

function mockEnv(files) {
  return {
    INTEL_R2: {
      async get(key) {
        if (!(key in files)) return null;
        return { async text() { return JSON.stringify(files[key]); } };
      },
    },
  };
}

const FAKE_REGISTRY = {
  schema_version: 1,
  generated_at: "2026-09-01T00:00:00Z",
  entries: [
    { id: "cves.html", frontend_route: "/cves.html", category: "CUSTOMER_UI", status: "live", notes: "internal audit note that must never leak" },
    { id: "ransomware.html", frontend_route: "/ransomware.html", category: "CUSTOMER_UI", status: "live", notes: "another internal note" },
    { id: "privacy-policy.html", frontend_route: "/privacy-policy.html", category: "CUSTOMER_UI", status: "static_content", notes: "legal page" },
    { id: "api-management-center.html", frontend_route: "/api-management-center.html", category: "CUSTOMER_UI", status: "orphan", notes: "hardcoded stat counters, zero fetch" },
    { id: "admin.html", frontend_route: "/admin.html", category: "ADMIN", notes: "internal admin console" },
    { id: "GODMODE-REVENUE-AUDIT-REPORT.html", frontend_route: "/GODMODE-REVENUE-AUDIT-REPORT.html", category: "INTERNAL", notes: "one-off internal artifact" },
  ],
};

// ---------------------------------------------------------------------------
// handleP41Capabilities
// ---------------------------------------------------------------------------

test("handleP41Capabilities: returns 503 with a helpful hint when R2 is empty", async () => {
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities"), mockEnv({}));
  assert.equal(res.status, 503);
  const body = await res.json();
  assert.match(body.error, /not yet synced/);
});

test("handleP41Capabilities: returns only CUSTOMER_UI entries -- ADMIN/INTERNAL never leak", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities"), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.total, 4);
  const ids = body.capabilities.map((c) => c.id);
  assert.ok(!ids.includes("admin.html"), "ADMIN entry must never appear in the public response");
  assert.ok(!ids.includes("GODMODE-REVENUE-AUDIT-REPORT.html"), "INTERNAL entry must never appear in the public response");
});

test("handleP41Capabilities: never includes the registry's internal `notes` field", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities"), env);
  const body = await res.json();
  for (const c of body.capabilities) {
    assert.equal(Object.prototype.hasOwnProperty.call(c, "notes"), false, `capability ${c.id} must not carry a notes field`);
  }
  const raw = JSON.stringify(body);
  assert.ok(!raw.includes("internal audit note"), "internal note text must never appear anywhere in the response");
  assert.ok(!raw.includes("hardcoded stat counters"), "internal note text must never appear anywhere in the response");
});

test("handleP41Capabilities: derives a human-readable title from the filename without fabricating content", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities"), env);
  const body = await res.json();
  const cves = body.capabilities.find((c) => c.id === "cves.html");
  assert.equal(cves.title, "Cves");
  const ransomware = body.capabilities.find((c) => c.id === "ransomware.html");
  assert.equal(ransomware.title, "Ransomware");
});

test("handleP41Capabilities: ?status= filters correctly and is still scoped to CUSTOMER_UI only", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities?status=live"), env);
  const body = await res.json();
  assert.equal(body.total, 2);
  assert.deepEqual(body.capabilities.map((c) => c.id).sort(), ["cves.html", "ransomware.html"]);
});

test("handleP41Capabilities: a query param cannot be used to smuggle ADMIN/INTERNAL entries through", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  // No "category" override exists on this endpoint by design -- confirm the
  // handler ignores an attempted category override rather than trusting it.
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities?category=ADMIN&status=live"), env);
  const body = await res.json();
  assert.ok(body.capabilities.every((c) => c.id !== "admin.html"));
});

test("handleP41Capabilities: one malformed entry does not break the whole listing", async () => {
  const registryWithGarbage = {
    ...FAKE_REGISTRY,
    entries: [...FAKE_REGISTRY.entries, { category: "CUSTOMER_UI" /* missing id/frontend_route */ }, null, "not-an-object"],
  };
  const env = mockEnv({ "intel/frontend_capability_registry.json": registryWithGarbage });
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities"), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.total, 4);
});

test("handleP41Capabilities: passes through registry_generated_at honestly instead of fabricating freshness", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41Capabilities(new Request("https://x/api/v1/p41/capabilities"), env);
  const body = await res.json();
  assert.equal(body.registry_generated_at, "2026-09-01T00:00:00Z");
});

// ---------------------------------------------------------------------------
// handleP41CapabilityDetail
// ---------------------------------------------------------------------------

test("handleP41CapabilityDetail: 400 when id is missing", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41CapabilityDetail(new Request("https://x/api/v1/p41/capability"), env);
  assert.equal(res.status, 400);
});

test("handleP41CapabilityDetail: 404 for an ADMIN id -- never resolvable through this public endpoint", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41CapabilityDetail(new Request("https://x/api/v1/p41/capability?id=admin.html"), env);
  assert.equal(res.status, 404);
});

test("handleP41CapabilityDetail: 200 with the public shape for a real CUSTOMER_UI id", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41CapabilityDetail(new Request("https://x/api/v1/p41/capability?id=cves.html"), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.capability.id, "cves.html");
  assert.equal(body.capability.status, "live");
  assert.equal(Object.prototype.hasOwnProperty.call(body.capability, "notes"), false);
});

// ---------------------------------------------------------------------------
// handleP41Observability
// ---------------------------------------------------------------------------

test("handleP41Observability: reports OPERATIONAL when the registry is present", async () => {
  const env = mockEnv({ "intel/frontend_capability_registry.json": FAKE_REGISTRY });
  const res = await handleP41Observability(new Request("https://x/api/v1/p41/observability"), env);
  const body = await res.json();
  assert.equal(body.status, "OPERATIONAL");
  assert.equal(body.layer, "P41");
});

test("handleP41Observability: reports DEGRADED (not a crash, not a silent 200-as-healthy) when R2 is empty", async () => {
  const res = await handleP41Observability(new Request("https://x/api/v1/p41/observability"), mockEnv({}));
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.status, "DEGRADED");
  assert.ok(body.degradation_reason);
});
