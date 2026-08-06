import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CEC_FLAGS,
  EVIDENCE_REGISTRY_FLAGS,
  resolveCecFlags,
  rollbackCecFlags,
} from "../feature-flags.js";

test("Stage 8 backward compatibility: EVIDENCE_REGISTRY_FLAGS still all false", () => {
  assert.equal(EVIDENCE_REGISTRY_FLAGS.SCAFFOLDING_ENABLED, false);
  assert.equal(EVIDENCE_REGISTRY_FLAGS.REGISTRY_SERVICE_ENABLED, false);
  assert.equal(EVIDENCE_REGISTRY_FLAGS.EVIDENCE_API_ENABLED, false);
  assert.ok(Object.isFrozen(EVIDENCE_REGISTRY_FLAGS));
});

test("resolveCecFlags: production and canary default to disabled", () => {
  assert.equal(resolveCecFlags("production").CEC_ENABLED, false);
  assert.equal(resolveCecFlags("canary").CEC_ENABLED, false);
});

test("resolveCecFlags: development and testing default to enabled (for exercising this directory's own code only)", () => {
  assert.equal(resolveCecFlags("development").CEC_ENABLED, true);
  assert.equal(resolveCecFlags("testing").CEC_ENABLED, true);
});

test("resolveCecFlags: unrecognized/missing environment fails closed to production (secure by default)", () => {
  assert.equal(resolveCecFlags("staging-typo").CEC_ENABLED, false);
  assert.equal(resolveCecFlags(undefined).CEC_ENABLED, false);
  assert.equal(resolveCecFlags("").CEC_ENABLED, false);
});

test("rollbackCecFlags: always returns the disabled state regardless of current environment", () => {
  assert.deepEqual(rollbackCecFlags(), CEC_FLAGS.production);
  assert.equal(rollbackCecFlags().CEC_ENABLED, false);
});

test("CEC_FLAGS entries are frozen (cannot be mutated at runtime)", () => {
  assert.ok(Object.isFrozen(CEC_FLAGS));
  assert.ok(Object.isFrozen(CEC_FLAGS.production));
  assert.throws(() => {
    "use strict";
    CEC_FLAGS.production.CEC_ENABLED = true;
  }, TypeError);
});
