import assert from "node:assert/strict";
import { test } from "node:test";
import {
  handleP40SourceRegistry,
  handleP40SourceDetail,
  handleP40SourceHealth,
  handleP40Licensing,
  handleP40Coverage,
  handleP40Waves,
  handleP40Certification,
  handleP40Metrics,
  handleP40Dashboard,
  handleP40Observability,
} from "../p40-handlers.js";

// ---------------------------------------------------------------------------
// Mock R2 environment — env.INTEL_R2.get(key) returns an object with a
// text() method, matching the real Cloudflare R2Object contract used by
// every other P-layer's _loadFeed(env) helper (e.g. p21-handlers.js).
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
  registry_version: "1.0.0",
  generated_at: "2026-08-08T00:00:00Z",
  total_sources: 3,
  status_breakdown: { ACTIVE: 1, PLANNED: 1, REQUIRES_CREDENTIALS: 1 },
  wave_breakdown: { "1": 3 },
  domain_breakdown: { vulnerability: 2, ioc: 1 },
  sources: [
    {
      source_id: "cisa_kev", canonical_name: "CISA KEV", wave: 1, priority: 1,
      criticality: "CRITICAL", implementation_status: "ACTIVE", intelligence_domains: ["vulnerability"],
      licensing_class: "PUBLIC_DOMAIN", redistribution_allowed: true, commercial_use_allowed: true,
      attribution_required: false, integration_mode: "EVENT_STREAM",
    },
    {
      source_id: "openphish", canonical_name: "OpenPhish", wave: 1, priority: 2,
      criticality: "HIGH", implementation_status: "ACTIVE", intelligence_domains: ["phishing"],
      licensing_class: "FREE_NONCOMMERCIAL", redistribution_allowed: true, commercial_use_allowed: false,
      attribution_required: true, integration_mode: "EVENT_STREAM",
    },
    {
      source_id: "microsoft_msrc", canonical_name: "Microsoft MSRC", wave: 2, priority: 3,
      criticality: "MEDIUM", implementation_status: "PLANNED", intelligence_domains: ["vulnerability"],
      licensing_class: "PUBLIC_DOMAIN", redistribution_allowed: true, commercial_use_allowed: true,
      attribution_required: false, integration_mode: "NOT_INTEGRATED",
    },
  ],
};

const FAKE_HEALTH = {
  generated_at: "2026-08-08T12:00:00Z",
  total_sources: 3,
  health_breakdown: { HEALTHY: 1, NO_DATA: 1, NOT_APPLICABLE: 1 },
  sources: [{ source_id: "cisa_kev", health_status: "HEALTHY" }],
};

// ---------------------------------------------------------------------------
// handleP40SourceRegistry
// ---------------------------------------------------------------------------

test("handleP40SourceRegistry: returns 503 with a helpful hint when R2 is empty", async () => {
  const res = await handleP40SourceRegistry(new Request("https://x/api/v1/p40/source-registry"), mockEnv({}));
  assert.equal(res.status, 503);
  const body = await res.json();
  assert.match(body.error, /not yet synced/);
});

test("handleP40SourceRegistry: returns full listing when R2 has data", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceRegistry(new Request("https://x/api/v1/p40/source-registry"), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.total, 3);
  assert.equal(body.sources.length, 3);
});

test("handleP40SourceRegistry: ?status= filters correctly", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceRegistry(new Request("https://x/api/v1/p40/source-registry?status=active"), env);
  const body = await res.json();
  assert.equal(body.total, 2);
  assert.ok(body.sources.every(s => s.implementation_status === "ACTIVE"));
});

test("handleP40SourceRegistry: ?wave= filters correctly", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceRegistry(new Request("https://x/api/v1/p40/source-registry?wave=2"), env);
  const body = await res.json();
  assert.equal(body.total, 1);
  assert.equal(body.sources[0].source_id, "microsoft_msrc");
});

test("handleP40SourceRegistry: ?domain= filters correctly", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceRegistry(new Request("https://x/api/v1/p40/source-registry?domain=phishing"), env);
  const body = await res.json();
  assert.equal(body.total, 1);
  assert.equal(body.sources[0].source_id, "openphish");
});

// ---------------------------------------------------------------------------
// handleP40SourceDetail
// ---------------------------------------------------------------------------

test("handleP40SourceDetail: 400 when id missing", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceDetail(new Request("https://x/api/v1/p40/source-detail"), env);
  assert.equal(res.status, 400);
});

test("handleP40SourceDetail: 404 for unknown source_id", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceDetail(new Request("https://x/api/v1/p40/source-detail?id=nope"), env);
  assert.equal(res.status, 404);
});

test("handleP40SourceDetail: returns source + joined health for known id", async () => {
  const env = mockEnv({
    "intel/source_registry.json": FAKE_REGISTRY,
    "intel/source_fabric_health.json": FAKE_HEALTH,
  });
  const res = await handleP40SourceDetail(new Request("https://x/api/v1/p40/source-detail?id=cisa_kev"), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.source.source_id, "cisa_kev");
  assert.equal(body.health.health_status, "HEALTHY");
});

test("handleP40SourceDetail: health is null (not an error) when health report unavailable", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40SourceDetail(new Request("https://x/api/v1/p40/source-detail?id=cisa_kev"), env);
  const body = await res.json();
  assert.equal(body.health, null);
});

// ---------------------------------------------------------------------------
// handleP40Licensing — Section 23 governance surface
// ---------------------------------------------------------------------------

test("handleP40Licensing: computes redistribution/commercial rollups correctly", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40Licensing(new Request("https://x/api/v1/p40/licensing"), env);
  const body = await res.json();
  assert.equal(body.total, 3);
  assert.equal(body.commercial_use_allowed, 2);
  assert.equal(body.attribution_required, 1);
  assert.equal(body.restricted_sources.length, 0); // all 3 fixtures allow redistribution
});

// ---------------------------------------------------------------------------
// handleP40Coverage / handleP40Waves
// ---------------------------------------------------------------------------

test("handleP40Coverage: builds per-domain status breakdown", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40Coverage(new Request("https://x/api/v1/p40/coverage"), env);
  const body = await res.json();
  assert.equal(body.domain_coverage.vulnerability.total, 2);
  assert.equal(body.domain_coverage.phishing.total, 1);
});

test("handleP40Waves: buckets sources by wave", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40Waves(new Request("https://x/api/v1/p40/waves"), env);
  const body = await res.json();
  assert.equal(body.waves.wave_1.total, 2);
  assert.equal(body.waves.wave_2.total, 1);
});

// ---------------------------------------------------------------------------
// handleP40SourceHealth / handleP40Certification / handleP40Metrics / handleP40Dashboard
// ---------------------------------------------------------------------------

test("handleP40SourceHealth: 503 when unavailable, 200 with data otherwise", async () => {
  const resMissing = await handleP40SourceHealth(new Request("https://x/api/v1/p40/source-health"), mockEnv({}));
  assert.equal(resMissing.status, 503);

  const env = mockEnv({ "intel/source_fabric_health.json": FAKE_HEALTH });
  const res = await handleP40SourceHealth(new Request("https://x/api/v1/p40/source-health"), env);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.total_sources, 3);
});

test("handleP40Certification: 503 when unavailable", async () => {
  const res = await handleP40Certification(new Request("https://x/api/v1/p40/certification"), mockEnv({}));
  assert.equal(res.status, 503);
});

test("handleP40Metrics: composes registry + health breakdowns", async () => {
  const env = mockEnv({
    "intel/source_registry.json": FAKE_REGISTRY,
    "intel/source_fabric_health.json": FAKE_HEALTH,
  });
  const res = await handleP40Metrics(new Request("https://x/api/v1/p40/metrics"), env);
  const body = await res.json();
  assert.equal(body.total_sources, 3);
  assert.deepEqual(body.health_breakdown, FAKE_HEALTH.health_breakdown);
});

test("handleP40Metrics: health fields are null (not a crash) when health report unavailable", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40Metrics(new Request("https://x/api/v1/p40/metrics"), env);
  const body = await res.json();
  assert.equal(body.health_breakdown, null);
});

test("handleP40Dashboard: lists only ACTIVE sources sorted by priority", async () => {
  const env = mockEnv({ "intel/source_registry.json": FAKE_REGISTRY });
  const res = await handleP40Dashboard(new Request("https://x/api/v1/p40/dashboard"), env);
  const body = await res.json();
  assert.equal(body.active_sources.length, 2);
  assert.equal(body.active_sources[0].source_id, "cisa_kev"); // priority 1 before priority 2
});

// ---------------------------------------------------------------------------
// handleP40Observability — no R2 dependency, must always succeed
// ---------------------------------------------------------------------------

test("handleP40Observability: lists all 10 endpoints and never depends on R2", async () => {
  const res = await handleP40Observability(new Request("https://x/api/v1/p40/observability"), mockEnv({}));
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.endpoints.length, 10);
  assert.equal(body.status, "OPERATIONAL");
});
