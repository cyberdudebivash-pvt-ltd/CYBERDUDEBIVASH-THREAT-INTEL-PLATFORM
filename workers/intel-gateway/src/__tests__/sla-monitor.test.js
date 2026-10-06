import assert from "node:assert/strict";
import { test } from "node:test";
import {
  handleSLAPing,
  handleSLAStatus,
  handleSLAReport,
  handleSLACertificate,
  _failureStreaks,
} from "../sla-monitor.js";

// ---------------------------------------------------------------------------
// 2026-09-26: /api/sla/* had no data source -- nothing ever called
// POST /api/sla/ping, so /api/sla/status was permanently insufficient_data.
// The heartbeat is now an external prober (scripts/sla_heartbeat.py, every
// 10 min from .github/workflows/sla-heartbeat.yml). It replays probes it could
// not deliver during an outage, so the ping handler accepts observed_at +
// probe_id and batches; incidents are one-per-failure-streak.
// sla-monitor.js has no imports, so it runs under plain `node --test`.
// ---------------------------------------------------------------------------

const SECRET = "test-admin-secret";
const MIN = 60 * 1000;

function kv() {
  const m = new Map();
  return {
    m,
    get: async (k) => (m.has(k) ? m.get(k) : null),
    put: async (k, v) => { m.set(k, v); },
  };
}
const envWith = () => ({ WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: kv() });

function pingReq(body, secret = SECRET) {
  return new Request("https://x/api/sla/ping", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Secret": secret },
    body: JSON.stringify(body),
  });
}
const pings = (env) => JSON.parse(env.SECURITY_HUB_KV.m.get("sla:pings") || "[]");
const incidents = (env) => JSON.parse(env.SECURITY_HUB_KV.m.get("sla:incidents") || "[]");
const status = async (env) => (await handleSLAStatus(new Request("https://x/api/sla/status"), env, "r")).json();
const iso = (msAgo) => new Date(Date.now() - msAgo).toISOString();

test("ping without the admin secret is rejected (unchanged)", async () => {
  const env = envWith();
  const r = await handleSLAPing(pingReq({ ok: true }, "wrong"), env, "r");
  assert.equal(r.status, 403);
  assert.equal(pings(env).length, 0);
});

test("a plain ping body still records one ping at the Worker's clock", async () => {
  const env = envWith();
  const before = Date.now();
  const r = await handleSLAPing(pingReq({ ok: true, latency_ms: 42 }), env, "r");
  assert.equal(r.status, 200);
  const [p] = pings(env);
  assert.equal(pings(env).length, 1);
  assert.ok(p.ts >= before && p.ts <= Date.now());
  assert.equal(p.ok, true);
  assert.equal(p.latency, 42);
});

test("replayed probes keep their observed_at, are time-ordered, and are not double-counted", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: true, observed_at: iso(5 * MIN), probe_id: "p3" }), env, "r");
  const batch = { pings: [
    { ok: false, observed_at: iso(25 * MIN), probe_id: "p1" },
    { ok: false, observed_at: iso(15 * MIN), probe_id: "p2" },
    { ok: true,  observed_at: iso(5 * MIN),  probe_id: "p3" },
  ] };
  const body = await (await handleSLAPing(pingReq(batch), env, "r")).json();
  assert.equal(body.recorded_count, 2);
  assert.equal(body.duplicates_skipped, 1);
  const ids = pings(env).map((p) => p.probe_id);
  assert.deepEqual(ids, ["p1", "p2", "p3"]);
  const again = await (await handleSLAPing(pingReq(batch), env, "r")).json();
  assert.equal(again.recorded_count, 0);
  assert.equal(pings(env).length, 3);
});

test("observed_at is bounded: future is clamped to now, beyond retention is dropped", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ pings: [
    { ok: true, observed_at: new Date(Date.now() + 3600 * 1000).toISOString(), probe_id: "future" },
    { ok: true, observed_at: iso(40 * 24 * 60 * MIN), probe_id: "ancient" },
    { ok: true, observed_at: "not-a-date", probe_id: "bad" },
  ] }), env, "r");
  const ps = pings(env);
  assert.deepEqual(ps.map((p) => p.probe_id).sort(), ["bad", "future"]);
  for (const p of ps) assert.ok(p.ts <= Date.now());
});

test("unsafe probe_id and oversized fields are not stored verbatim", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: true, probe_id: "<script>", note: "x".repeat(5000) }), env, "r");
  const [p] = pings(env);
  assert.equal(p.probe_id, undefined);
  assert.equal(p.note.length, 200);
});

test("a batch is capped at 500 pings", async () => {
  const env = envWith();
  const many = Array.from({ length: 700 }, (_, i) => ({ ok: true, observed_at: iso((700 - i) * MIN), probe_id: `b${i}` }));
  const body = await (await handleSLAPing(pingReq({ pings: many }), env, "r")).json();
  assert.equal(body.recorded_count, 500);
  assert.equal(pings(env).length, 500);
});

test("one outage = one incident, extended while it lasts (not one per failed probe)", async () => {
  const env = envWith();
  // Use one clock anchor for the whole synthetic outage. Calling Date.now()
  // once per observation makes the expected 40-minute interval drift by
  // 1+ ms under CI scheduling and turns a correct production result into a
  // flaky strict-equality failure.
  const anchor = Date.now();
  const fails = [50, 40, 30, 20, 10].map((m, i) => ({
    ok: false,
    observed_at: new Date(anchor - m * MIN).toISOString(),
    probe_id: `f${i}`,
  }));
  for (const f of fails) await handleSLAPing(pingReq(f), env, "r");
  let inc = incidents(env);
  assert.equal(inc.length, 1);
  assert.equal(inc[0].failed_checks, 5);
  assert.equal(inc[0].duration_ms, 40 * MIN);
  await handleSLAPing(
    pingReq({ ok: true, observed_at: new Date(anchor).toISOString(), probe_id: "rec" }),
    env,
    "r",
  );
  inc = incidents(env);
  assert.equal(inc.length, 1);
});

test("two failures are not an incident", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ pings: [
    { ok: false, observed_at: iso(20 * MIN), probe_id: "a" },
    { ok: false, observed_at: iso(10 * MIN), probe_id: "b" },
    { ok: true,  observed_at: iso(0), probe_id: "c" },
  ] }), env, "r");
  assert.equal(incidents(env).length, 0);
});

test("_failureStreaks separates components", () => {
  const t = Date.now();
  const s = _failureStreaks([
    { ts: t, ok: false, component: "a" }, { ts: t + 1, ok: false, component: "b" },
    { ts: t + 2, ok: false, component: "a" }, { ts: t + 3, ok: false, component: "a" },
  ]);
  assert.deepEqual(s.map((x) => [x.component, x.count]), [["a", 3]]);
});

test("status: no heartbeats -> insufficient_data, no figure (unchanged)", async () => {
  const d = await status(envWith());
  assert.equal(d.status, "insufficient_data");
  assert.equal(d.uptime_pct_30d, null);
});

test("status: a current successful heartbeat -> operational", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: true, observed_at: iso(8 * MIN), probe_id: "ok1" }), env, "r");
  const d = await status(env);
  assert.equal(d.status, "operational");
  assert.equal(d.monitoring_current, true);
  assert.equal(d.uptime_pct_30d, 100);
  assert.equal(d.sla_met_enterprise, true);
});

test("status: a failed latest heartbeat -> degraded (was operational if recent)", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ pings: [
    { ok: true,  observed_at: iso(20 * MIN), probe_id: "u" },
    { ok: false, observed_at: iso(2 * MIN), probe_id: "d" },
  ] }), env, "r");
  const d = await status(env);
  assert.equal(d.status, "degraded");
  assert.equal(d.uptime_pct_30d, 50);
});

test("status: last heartbeat OK but stale -> monitoring_delayed, not an outage", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: true, observed_at: iso(60 * MIN), probe_id: "old" }), env, "r");
  const d = await status(env);
  assert.equal(d.status, "monitoring_delayed");
  assert.equal(d.monitoring_current, false);
  assert.equal(d.components["intel-gateway"].status, "monitoring_delayed");
  assert.equal(d.heartbeat_stale_after_seconds, 45 * 60);
  assert.equal(d.uptime_pct_30d, 100); // historical measurement is still visible
  assert.equal(d.sla_met_enterprise, null); // but current compliance is not asserted
  assert.equal(d.sla_met_pro, null);
});

test("status: last heartbeat FAILED, even if stale -> degraded", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: false, observed_at: iso(90 * MIN), probe_id: "down" }), env, "r");
  assert.equal((await status(env)).status, "degraded");
});

test("status: uptime is the more conservative of ping ratio and incident time", async () => {
  const env = envWith();
  const ps = [];
  for (let i = 0; i < 100; i++) ps.push({ ok: i < 3 ? false : true, observed_at: iso((100 - i) * 10 * MIN), probe_id: `c${i}` });
  await handleSLAPing(pingReq({ pings: ps }), env, "r");
  const d = await status(env);
  // 97/100 pings ok -> 97%; one 20-minute incident over 30 days -> ~99.95%.
  assert.equal(d.uptime_pct_30d, 97);
  assert.equal(d.incidents_30d, 1);
});


test("enterprise SLA report: stale monitor cannot report MET and empty days are null", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: true, observed_at: iso(60 * MIN), probe_id: "stale-report" }), env, "r");
  const auth = { tier: "ENTERPRISE", key: "k", sub: "acct" };
  const d = await (await handleSLAReport(new Request("https://x/api/sla/report"), env, auth, "r")).json();
  assert.equal(d.sla_status, "MONITORING_DELAYED");
  assert.equal(d.monitoring_current, false);
  assert.equal(typeof d.last_ping_age_seconds, "number");
  assert.ok(d.daily_breakdown.some((day) => day.pings === 0 && day.uptime_pct === null));
});

test("enterprise SLA certificate: stale monitor cannot issue COMPLIANT evidence", async () => {
  const env = envWith();
  await handleSLAPing(pingReq({ ok: true, observed_at: iso(60 * MIN), probe_id: "stale-cert" }), env, "r");
  const auth = { tier: "ENTERPRISE", key: "k", sub: "acct" };
  const d = await (await handleSLACertificate(new Request("https://x/api/sla/certificate"), env, auth, "r")).json();
  assert.equal(d.certificate.sla_status, "MONITORING_DELAYED");
  assert.equal(d.certificate.monitoring_current, false);
  assert.match(d.certificate.monitoring_basis, /external heartbeat is stale/i);
});
