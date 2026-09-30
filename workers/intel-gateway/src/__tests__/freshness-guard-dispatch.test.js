/**
 * R01 freshness self-heal trigger (freshness-guard-dispatch.js): dormant by
 * default, and when enabled exactly one workflow_dispatch of
 * intel-freshness-guard.yml per :00/:30 tick of the EXISTING 15-minute cron,
 * through the REAL scheduled() handler. No network: fetch is stubbed.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import worker from "../index.js";
import { harness } from "./watchdog-harness.js";
import {
  dispatchFreshnessGuard, freshnessGuardDispatchEnabled, isGuardDispatchTick,
  FRESHNESS_GUARD_DISPATCH_URL, FRESHNESS_GUARD_WORKFLOW,
} from "../freshness-guard-dispatch.js";

const TOKEN = "github_pat_test_0123456789abcdefghijklmnopqrstuvwxyz";
const CRON = "*" + "/15 * * * *";
const at = (hh, mm) => Date.UTC(2026, 8, 30, hh, mm, 0);

// Runs the real scheduled() handler with every GitHub API call recorded.
async function runCron(env, scheduledTime, githubAnswer = () => new Response(null, { status: 204 })) {
  const calls = [];
  const logs = [];
  const realFetch = globalThis.fetch;
  const realLog = console.log;
  globalThis.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input.url;
    if (url.startsWith("https://api.github.com/")) {
      calls.push({ url, init });
      return githubAnswer(url, init);
    }
    return realFetch(input, init);
  };
  console.log = (...a) => { logs.push(a.join(" ")); };
  const waits = [];
  try {
    await worker.scheduled({ cron: CRON, scheduledTime }, env, { waitUntil: (p) => waits.push(p) });
    const settled = await Promise.allSettled(waits);
    return { calls, logs, rejected: settled.filter((s) => s.status === "rejected") };
  } finally {
    globalThis.fetch = realFetch;
    console.log = realLog;
  }
}

test("pure: enabled only with the exact flag AND a non-blank token", () => {
  assert.equal(freshnessGuardDispatchEnabled({}), false);
  assert.equal(freshnessGuardDispatchEnabled({ FRESHNESS_GUARD_DISPATCH_ENABLED: "true" }), false);
  assert.equal(freshnessGuardDispatchEnabled({ FRESHNESS_GUARD_DISPATCH_ENABLED: "true", FRESHNESS_GUARD_DISPATCH_TOKEN: "   " }), false);
  assert.equal(freshnessGuardDispatchEnabled({ FRESHNESS_GUARD_DISPATCH_ENABLED: "TRUE", FRESHNESS_GUARD_DISPATCH_TOKEN: TOKEN }), false);
  assert.equal(freshnessGuardDispatchEnabled({ FRESHNESS_GUARD_DISPATCH_ENABLED: "false", FRESHNESS_GUARD_DISPATCH_TOKEN: TOKEN }), false);
  assert.equal(freshnessGuardDispatchEnabled({ FRESHNESS_GUARD_DISPATCH_ENABLED: "true", FRESHNESS_GUARD_DISPATCH_TOKEN: TOKEN }), true);
});

test("pure: dispatch ticks are :00 and :30 of the 15-minute cron", () => {
  assert.equal(isGuardDispatchTick(at(15, 0)), true);
  assert.equal(isGuardDispatchTick(at(15, 15)), false);
  assert.equal(isGuardDispatchTick(at(15, 30)), true);
  assert.equal(isGuardDispatchTick(at(15, 45)), false);
  assert.equal(isGuardDispatchTick(NaN), false);
});

test("pure: targets the guard workflow by FILE name on this repository", () => {
  assert.equal(FRESHNESS_GUARD_WORKFLOW, "intel-freshness-guard.yml");
  assert.equal(
    FRESHNESS_GUARD_DISPATCH_URL,
    "https://api.github.com/repos/cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/workflows/intel-freshness-guard.yml/dispatches",
  );
});

test("dormant: the production configuration (flag absent/false, no token) never calls GitHub", async () => {
  for (const extra of [{}, { FRESHNESS_GUARD_DISPATCH_ENABLED: "false" }, { FRESHNESS_GUARD_DISPATCH_ENABLED: "true" }, { FRESHNESS_GUARD_DISPATCH_TOKEN: TOKEN }]) {
    const hx = harness();
    Object.assign(hx.env, extra);
    const out = await runCron(hx.env, at(15, 0));
    assert.equal(out.calls.length, 0, JSON.stringify(extra));
    assert.equal(out.logs.filter((l) => l.includes("freshness_guard_dispatch")).length, 0);
  }
});

test("enabled: one workflow_dispatch on :00 and :30, none on :15 and :45", async () => {
  const hx = harness();
  Object.assign(hx.env, { FRESHNESS_GUARD_DISPATCH_ENABLED: "true", FRESHNESS_GUARD_DISPATCH_TOKEN: TOKEN });
  for (const [mm, expected] of [[0, 1], [15, 0], [30, 1], [45, 0]]) {
    const out = await runCron(hx.env, at(16, mm));
    assert.equal(out.calls.length, expected, "minute " + mm);
    assert.equal(out.rejected.length, 0);
    if (expected) {
      const { url, init } = out.calls[0];
      assert.equal(url, FRESHNESS_GUARD_DISPATCH_URL);
      assert.equal(init.method, "POST");
      assert.deepEqual(JSON.parse(init.body), { ref: "main" });
      assert.equal(init.headers.Authorization, "Bearer " + TOKEN);
      assert.equal(init.headers.Accept, "application/vnd.github+json");
      const log = out.logs.find((l) => l.includes("freshness_guard_dispatch"));
      assert.ok(log && log.includes('"status":"dispatched"'), String(log));
    }
  }
});

test("failure isolation: GitHub down or refusing never breaks the cron, and the token is never logged", async () => {
  const hx = harness();
  Object.assign(hx.env, { FRESHNESS_GUARD_DISPATCH_ENABLED: "true", FRESHNESS_GUARD_DISPATCH_TOKEN: TOKEN });

  const down = await runCron(hx.env, at(17, 0), () => { throw new TypeError("network down"); });
  assert.equal(down.calls.length, 1);
  assert.equal(down.rejected.length, 0, "no waitUntil promise may reject");
  assert.ok(down.logs.some((l) => l.includes('"status":"error"')));

  const refused = await runCron(hx.env, at(17, 30), () => new Response('{"message":"Bad credentials"}', { status: 401 }));
  assert.equal(refused.rejected.length, 0);
  assert.ok(refused.logs.some((l) => l.includes('"status":"rejected"') && l.includes('"http_status":401')));

  for (const l of [...down.logs, ...refused.logs]) assert.ok(!l.includes(TOKEN), "token leaked to logs");
  // The Watchdog scheduler still ran on the same ticks.
  assert.ok(hx.env.WATCHDOG_SCHEDULER.requests >= 2);
});

test("direct call returns a status object and never throws", async () => {
  const env = { FRESHNESS_GUARD_DISPATCH_ENABLED: "true", FRESHNESS_GUARD_DISPATCH_TOKEN: " " + TOKEN + " " };
  let seen = null;
  const ok = await dispatchFreshnessGuard(env, at(18, 0), async (url, init) => { seen = init; return new Response(null, { status: 204 }); });
  assert.deepEqual(ok, { status: "dispatched" });
  assert.equal(seen.headers.Authorization, "Bearer " + TOKEN, "token is trimmed");
  assert.deepEqual(await dispatchFreshnessGuard(env, at(18, 15), async () => { throw new Error("must not be called"); }), { status: "not_this_tick" });
  assert.deepEqual(await dispatchFreshnessGuard({}, at(18, 0)), { status: "disabled" });
});
