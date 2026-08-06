import assert from "node:assert/strict";
import { test } from "node:test";
import { EIG_FLAGS, resolveEigFlags, rollbackEigFlags, DEPLOYMENT_ENVIRONMENTS } from "../feature-flags.js";

test("all 4 deployment environments are present with the conservative default shape", () => {
  for (const environment of DEPLOYMENT_ENVIRONMENTS) {
    assert.ok(Object.hasOwn(EIG_FLAGS, environment), `EIG_FLAGS is missing environment "${environment}"`);
  }
  assert.equal(EIG_FLAGS.development.EIG_ENABLED, true);
  assert.equal(EIG_FLAGS.testing.EIG_ENABLED, true);
  assert.equal(EIG_FLAGS.canary.EIG_ENABLED, false);
  assert.equal(EIG_FLAGS.production.EIG_ENABLED, false);
  assert.equal(EIG_FLAGS.development.INTERNAL_ADOPTION_ENABLED, true);
  assert.equal(EIG_FLAGS.testing.INTERNAL_ADOPTION_ENABLED, true);
  assert.equal(EIG_FLAGS.canary.INTERNAL_ADOPTION_ENABLED, false);
  assert.equal(EIG_FLAGS.production.INTERNAL_ADOPTION_ENABLED, false);
});

test("EIG_FLAGS and each environment entry are frozen", () => {
  assert.ok(Object.isFrozen(EIG_FLAGS));
  assert.ok(Object.isFrozen(EIG_FLAGS.production));
});

test("resolveEigFlags() falls back to production for an unrecognized environment", () => {
  assert.deepEqual(resolveEigFlags("staging-typo"), EIG_FLAGS.production);
  assert.deepEqual(resolveEigFlags(undefined), EIG_FLAGS.production);
});

test("resolveEigFlags() uses Object.hasOwn(), not a bare [] || fallback -- an Object.prototype member name does not leak through", () => {
  assert.deepEqual(resolveEigFlags("constructor"), EIG_FLAGS.production);
  assert.deepEqual(resolveEigFlags("toString"), EIG_FLAGS.production);
  assert.deepEqual(resolveEigFlags("hasOwnProperty"), EIG_FLAGS.production);
});

test("resolveEigFlags() returns the exact matching environment entry when recognized", () => {
  assert.equal(resolveEigFlags("development"), EIG_FLAGS.development);
  assert.equal(resolveEigFlags("testing"), EIG_FLAGS.testing);
});

test("rollbackEigFlags() always returns the all-disabled production state", () => {
  assert.equal(rollbackEigFlags(), EIG_FLAGS.production);
});
