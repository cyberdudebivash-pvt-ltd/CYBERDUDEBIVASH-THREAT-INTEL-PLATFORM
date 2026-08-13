import assert from "node:assert/strict";
import { test } from "node:test";
import {
  handleRxPubA0ReportsIdentity,
  handleRxPubA0Observability,
} from "../rx-pub-a0-handlers.js";

// ---------------------------------------------------------------------------
// Mock R2 environment  -  mirrors p40-handlers.test.js's mockEnv, matching
// the real Cloudflare R2Object contract (env.INTEL_R2.get(key).text()).
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

const MANIFEST_KEY = "intel/rx_pub_a0_reports_artifact_manifest.json";

const FAKE_MANIFEST = {
  schema_version: "2",
  generated_at: "2026-08-13T15:50:30Z",
  pipeline_run_id: "31713054946",
  release_sha: "51ff48f0",
  bucket: "sentinel-apex-reports",
  public_base_url: "https://intel.cyberdudebivash.com",
  reports: {
    "intel--abc123": {
      r2_key: "reports/2026/08/intel--abc123.html",
      publication_state: "REMOTE_VERIFIED",
      live_state: "LIVE_VERIFIED",
    },
  },
  summary: {
    total_in_window: 1,
    remote_verified: 1,
    stale_or_divergent_or_failed: 0,
    unknown: 0,
    live_verified: 1,
    live_stale_or_divergent_or_missing: 0,
    live_unknown: 0,
    run_deadline_exceeded: false,
  },
};

// ---------------------------------------------------------------------------
// handleRxPubA0ReportsIdentity
// ---------------------------------------------------------------------------

test("handleRxPubA0ReportsIdentity: returns 503 with a helpful hint when R2 is empty", async () => {
  const res = await handleRxPubA0ReportsIdentity(
    new Request("https://x/api/v1/rx-pub-a0/reports-identity"), mockEnv({}),
  );
  assert.equal(res.status, 503);
  const body = await res.json();
  assert.match(body.error, /not yet synced/);
});

test("handleRxPubA0ReportsIdentity: returns summary (not per-report detail) by default", async () => {
  const env = mockEnv({ [MANIFEST_KEY]: FAKE_MANIFEST });
  const res = await handleRxPubA0ReportsIdentity(
    new Request("https://x/api/v1/rx-pub-a0/reports-identity"), env,
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.summary.remote_verified, 1);
  assert.equal(body.summary.live_verified, 1);
  assert.equal(body.pipeline_run_id, "31713054946");
  assert.equal(
    "reports" in body, false,
    "per-report detail must be omitted unless ?full=1 is passed",
  );
});

test("handleRxPubA0ReportsIdentity: ?full=1 includes per-report detail", async () => {
  const env = mockEnv({ [MANIFEST_KEY]: FAKE_MANIFEST });
  const res = await handleRxPubA0ReportsIdentity(
    new Request("https://x/api/v1/rx-pub-a0/reports-identity?full=1"), env,
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.ok(body.reports["intel--abc123"]);
  assert.equal(body.reports["intel--abc123"].live_state, "LIVE_VERIFIED");
});

test("handleRxPubA0ReportsIdentity: never claims enforcement is active", async () => {
  const env = mockEnv({ [MANIFEST_KEY]: FAKE_MANIFEST });
  const res = await handleRxPubA0ReportsIdentity(
    new Request("https://x/api/v1/rx-pub-a0/reports-identity"), env,
  );
  const body = await res.json();
  assert.equal(
    body.enforced, false,
    "this observability endpoint must never claim STAGE 3.6a enforces anything -- "
    + "that remains gated by --enforce per docs/RX_PUB_A0_R2_VERIFIER_BAKEIN.md",
  );
});

// ---------------------------------------------------------------------------
// handleRxPubA0Observability
// ---------------------------------------------------------------------------

test("handleRxPubA0Observability: lists both routes and its own generator script", async () => {
  const res = await handleRxPubA0Observability(
    new Request("https://x/api/v1/rx-pub-a0/observability"), mockEnv({}),
  );
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.deepEqual(body.endpoints, [
    "/api/v1/rx-pub-a0/reports-identity",
    "/api/v1/rx-pub-a0/observability",
  ]);
  assert.match(body.generators[0], /r2_reports_verifier\.py/);
});
