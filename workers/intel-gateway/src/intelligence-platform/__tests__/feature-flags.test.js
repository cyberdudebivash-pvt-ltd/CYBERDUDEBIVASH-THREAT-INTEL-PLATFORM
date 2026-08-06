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

test("INTERNAL_ADOPTION_ENABLED defaults false in every environment, including development/testing", () => {
  for (const env of DEPLOYMENT_ENVIRONMENTS) {
    assert.equal(EIPS_FLAGS[env].INTERNAL_ADOPTION_ENABLED, false, `${env} must default INTERNAL_ADOPTION_ENABLED to false`);
  }
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

test("INTERNAL_ADOPTION_ENABLED remains hardcoded false in source for every environment (not read from an env var that could be flipped without code review)", () => {
  const text = readFileSync(join(HERE, "..", "feature-flags.js"), "utf-8");
  const matches = text.match(/INTERNAL_ADOPTION_ENABLED:\s*false/g) || [];
  assert.equal(matches.length, 4, "all four environments must hardcode INTERNAL_ADOPTION_ENABLED: false");
});
