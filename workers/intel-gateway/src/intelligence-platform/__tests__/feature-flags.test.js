import assert from "node:assert/strict";
import { test } from "node:test";
import { EIPS_FLAGS, resolveEipsFlags, rollbackEipsFlags, DEPLOYMENT_ENVIRONMENTS } from "../feature-flags.js";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

test("EIPS_FLAGS defines all four deployment environments with development/testing enabled, canary/production disabled", () => {
  assert.deepEqual(Object.keys(EIPS_FLAGS).sort(), [...DEPLOYMENT_ENVIRONMENTS].sort());
  assert.equal(EIPS_FLAGS.development.EIPS_ENABLED, true);
  assert.equal(EIPS_FLAGS.testing.EIPS_ENABLED, true);
  assert.equal(EIPS_FLAGS.canary.EIPS_ENABLED, false);
  assert.equal(EIPS_FLAGS.production.EIPS_ENABLED, false);
});

test("INTERNAL_ADOPTION_ENABLED mirrors EIPS_ENABLED's own shape: enabled in development/testing, disabled in canary/production", () => {
  assert.equal(EIPS_FLAGS.development.INTERNAL_ADOPTION_ENABLED, true);
  assert.equal(EIPS_FLAGS.testing.INTERNAL_ADOPTION_ENABLED, true);
  assert.equal(EIPS_FLAGS.canary.INTERNAL_ADOPTION_ENABLED, false);
  assert.equal(EIPS_FLAGS.production.INTERNAL_ADOPTION_ENABLED, false);
});

test("resolveEipsFlags falls back to the production (all-disabled) state for an unknown environment -- secure by default", () => {
  assert.deepEqual(resolveEipsFlags("not-a-real-environment"), EIPS_FLAGS.production);
  assert.deepEqual(resolveEipsFlags(undefined), EIPS_FLAGS.production);
});

test("rollbackEipsFlags always returns the all-disabled production state", () => {
  assert.deepEqual(rollbackEipsFlags(), EIPS_FLAGS.production);
});

test("every EIPS_FLAGS entry is frozen (immutable)", () => {
  assert.ok(Object.isFrozen(EIPS_FLAGS));
  for (const env of DEPLOYMENT_ENVIRONMENTS) assert.ok(Object.isFrozen(EIPS_FLAGS[env]));
});

test("INTERNAL_ADOPTION_ENABLED remains hardcoded (not read from an env var that could be flipped without code review), and stays false for canary/production specifically", () => {
  const text = readFileSync(join(HERE, "..", "feature-flags.js"), "utf-8");
  assert.doesNotMatch(text, /INTERNAL_ADOPTION_ENABLED:\s*process\.env/, "must not be sourced from an environment variable");
  assert.match(text, /canary:\s*Object\.freeze\(\{\s*EIPS_ENABLED:\s*false,\s*INTERNAL_ADOPTION_ENABLED:\s*false\s*\}\)/);
  assert.match(text, /production:\s*Object\.freeze\(\{\s*EIPS_ENABLED:\s*false,\s*INTERNAL_ADOPTION_ENABLED:\s*false\s*\}\)/);
});
