/**
 * Black-box test of scripts/intelligence_platform_snapshot.mjs -- Stage 13 Phase 10's one
 * authorized internal consumer. Spawns it as a real child process (the same way CI or a human
 * operator would invoke it), rather than importing its internals, so this test exercises the
 * actual entry point, not a proxy for it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(HERE, "..", "..", "..", "..", "..", "scripts", "intelligence_platform_snapshot.mjs");

function run(env) {
  return execFileSync("node", [SCRIPT, env], { encoding: "utf-8" });
}

test("production (default): INTERNAL_ADOPTION_ENABLED is false -- documented no-op, zero platform construction", () => {
  const output = run("production");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=false/);
  assert.match(output, /documented no-op/);
  assert.doesNotMatch(output, /"contracts":/, "must not have constructed or exercised the platform at all");
});

test("canary: INTERNAL_ADOPTION_ENABLED is false -- same documented no-op as production", () => {
  const output = run("canary");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=false/);
  assert.match(output, /documented no-op/);
});

test("development: INTERNAL_ADOPTION_ENABLED is true -- the platform actually runs and produces a real snapshot", () => {
  const output = run("development");
  assert.match(output, /INTERNAL_ADOPTION_ENABLED=true/);
  assert.match(output, /"contracts":/);
  assert.match(output, /IntelligenceServiceContract/);
  const jsonStart = output.indexOf("{");
  const jsonEnd = output.lastIndexOf("}") + 1;
  const snapshot = JSON.parse(output.slice(jsonStart, jsonEnd));
  assert.equal(snapshot.contracts.length, 6);
  assert.ok(snapshot.metrics.registry, "snapshot must include a real registry metrics view");
  assert.equal(snapshot.metrics.registry.evidence_count, 1, "the one sample record must have been registered");
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

test("every run documents the required Stage 14 follow-up rather than silently doing less than the brief asked", () => {
  const output = run("development");
  assert.match(output, /Required follow-up/);
  assert.match(output, /Stage 14/);
});
