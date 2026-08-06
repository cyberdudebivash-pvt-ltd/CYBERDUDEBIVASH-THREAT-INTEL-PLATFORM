/**
 * Black-box test of scripts/enterprise_gateway_snapshot.mjs -- this stage's one authorized
 * internal consumer. Spawns it as a real child process (the same way CI or a human operator
 * would invoke it), rather than importing its internals, so this test exercises the actual
 * entry point, not a proxy for it. Mirrors intelligence-platform/__tests__/
 * internal-adoption.test.js's (Stage 13) exact pattern.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(HERE, "..", "..", "..", "..", "..", "scripts", "enterprise_gateway_snapshot.mjs");

function run(env) {
  // timeout: if the script ever hangs, this test fails fast instead of blocking the CI job.
  return execFileSync("node", [SCRIPT, env], { encoding: "utf-8", timeout: 30_000 });
}

test("production (default): INTERNAL_ADOPTION_ENABLED is false -- documented no-op, zero gateway construction", () => {
  const output = run("production");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=false/);
  assert.match(output, /documented no-op/);
  assert.doesNotMatch(output, /"contracts":/, "must not have constructed or exercised the gateway at all");
});

test("canary: INTERNAL_ADOPTION_ENABLED is false -- same documented no-op as production", () => {
  const output = run("canary");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=false/);
  assert.match(output, /documented no-op/);
});

test("development: INTERNAL_ADOPTION_ENABLED is true -- the gateway actually dispatches and produces a real snapshot", () => {
  const output = run("development");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=true/);
  assert.match(output, /"contracts":/);
  assert.match(output, /GatewayServiceContract/);
  // Unlike intelligence_platform_snapshot.mjs (whose only console.log with a brace is the final
  // JSON block), this script's dispatcher middleware logs [Stage 14 gateway-trace]/[gateway-
  // audit] lines with their own embedded "{...}" JSON BEFORE the snapshot -- a plain
  // indexOf("{") would grab one of those instead. Anchor on the snapshot's actual first key.
  const jsonStart = output.indexOf('{\n  "environment"');
  const jsonEnd = output.lastIndexOf("}") + 1;
  assert.ok(jsonStart >= 0, "the final snapshot JSON block must be present in stdout");
  const snapshot = JSON.parse(output.slice(jsonStart, jsonEnd));
  assert.equal(snapshot.contracts.length, 4);
  assert.equal(snapshot.capabilities.length, 8);
  assert.equal(snapshot.health.ready, true);
  assert.ok(snapshot.gatewayMetrics.registry, "snapshot must include a real registry metrics view");
  assert.equal(snapshot.gatewayMetrics.registry.evidence_count, 1, "the one sample record must have been registered");
  assert.ok(
    snapshot.gatewayMetrics.service.call_counts["gateway.evidence.lookup"] >= 1,
    "the dispatched evidence.lookup call must be recorded on the shared metrics instance"
  );
  assert.ok(snapshot.platformMetricsViaDispatch.service, "the least-privilege platform.metrics dispatch must also have succeeded");
});

test("testing: INTERNAL_ADOPTION_ENABLED is true, same as development", () => {
  const output = run("testing");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=true/);
  assert.match(output, /"contracts":/);
});

test("unrecognized environment falls back to production's disabled state -- secure by default", () => {
  const output = run("not-a-real-environment");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=false/);
});

test("every run documents the required follow-up rather than silently doing less than the brief asked", () => {
  const output = run("development");
  assert.match(output, /Required follow-up/);
  assert.match(output, /Phase 1/);
});
