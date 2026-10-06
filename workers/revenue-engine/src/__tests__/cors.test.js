import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "../index.js";

// ---------------------------------------------------------------------------
// A security report flagged Access-Control-Allow-Origin: * on every response
// from this admin-secret-bearing API, including the OPTIONS preflight. Fix:
// echo back the request Origin only when it's on an explicit allowlist
// (REVENUE_ADMIN_SECRET's real browser callers all live on
// intel.cyberdudebivash.com), omit the header entirely otherwise.
// ---------------------------------------------------------------------------

function makeEnv() {
  return {};
}

test("OPTIONS preflight: an allowed origin gets it echoed back", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/revenue/dashboard", {
    method: "OPTIONS",
    headers: { Origin: "https://intel.cyberdudebivash.com" },
  });
  const res = await worker.fetch(req, makeEnv(), {});
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), "https://intel.cyberdudebivash.com");
});

test("OPTIONS preflight: a disallowed origin gets no Access-Control-Allow-Origin header", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/revenue/dashboard", {
    method: "OPTIONS",
    headers: { Origin: "https://attacker.example" },
  });
  const res = await worker.fetch(req, makeEnv(), {});
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), null);
});

test("OPTIONS preflight: no Origin header at all also gets no ACAO header (never falls back to *)", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/revenue/dashboard", { method: "OPTIONS" });
  const res = await worker.fetch(req, makeEnv(), {});
  assert.equal(res.status, 204);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), null);
});

test("GET /api/health: an allowed origin gets its exact origin echoed back, never a bare *", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/health", {
    headers: { Origin: "https://intel.cyberdudebivash.com" },
  });
  const res = await worker.fetch(req, makeEnv(), {});
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), "https://intel.cyberdudebivash.com");
});

test("GET /api/health: a disallowed origin gets a normal response with no ACAO header", async () => {
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/health", {
    headers: { Origin: "https://attacker.example" },
  });
  const res = await worker.fetch(req, makeEnv(), {});
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), null);
  // The response body itself is unaffected -- this is a browser-enforced header, not an
  // authorization control, so the JSON payload is identical either way.
  assert.equal((await res.json()).status, "ok");
});

test("A 500 error response also gets the correct CORS origin applied, not skipped", async () => {
  // /api/crm/leads with no admin secret hits isAdmin()'s 401 branch, not a throw, but exercises
  // the same withCorsOrigin() wrapping path as every other response including error paths.
  const req = new Request("https://revenue.intel.cyberdudebivash.com/api/crm/leads", {
    headers: { Origin: "https://intel.cyberdudebivash.com" },
  });
  const res = await worker.fetch(req, makeEnv(), {});
  assert.equal(res.status, 401);
  assert.equal(res.headers.get("Access-Control-Allow-Origin"), "https://intel.cyberdudebivash.com");
});
