import assert from "node:assert/strict";
import { test } from "node:test";
import { GatewayContext } from "../gateway-context.js";

test("constructor requires a non-empty string capability", () => {
  assert.throws(() => new GatewayContext({}), /requires a non-empty string 'capability'/);
  assert.throws(() => new GatewayContext({ capability: "" }), /requires a non-empty string 'capability'/);
});

test("fields are frozen and defaults are applied", () => {
  const context = new GatewayContext({ capability: "evidence.lookup" });
  assert.equal(context.capability, "evidence.lookup");
  assert.equal(context.environment, "production");
  assert.deepEqual(context.grantedCapabilities, []);
  assert.ok(context.correlationId);
  assert.ok(Object.isFrozen(context));
  assert.throws(() => {
    context.capability = "x";
  }, TypeError);
});

test("correlation id is auto-generated when omitted, honored when supplied", () => {
  const auto = new GatewayContext({ capability: "evidence.lookup" });
  const explicit = new GatewayContext({ capability: "evidence.lookup", correlationId: "corr-123" });
  assert.notEqual(auto.correlationId, "");
  assert.equal(explicit.correlationId, "corr-123");
});

test("hasCapability() reflects grantedCapabilities", () => {
  const context = new GatewayContext({
    capability: "evidence.lookup",
    grantedCapabilities: ["evidence.lookup", "intelligence.query"],
  });
  assert.equal(context.hasCapability("evidence.lookup"), true);
  assert.equal(context.hasCapability("evidence.relationships"), false);
});

test("with() returns a NEW frozen instance and never mutates the original", () => {
  const original = new GatewayContext({ capability: "evidence.lookup", environment: "testing" });
  const patched = original.with({ featureFlags: { EIG_ENABLED: true } });
  assert.notEqual(patched, original);
  assert.deepEqual(original.featureFlags, {});
  assert.deepEqual(patched.featureFlags, { EIG_ENABLED: true });
  assert.equal(patched.correlationId, original.correlationId, "correlationId carries forward by default");
  assert.equal(patched.startedAt, original.startedAt, "startedAt carries forward by default");
  assert.ok(Object.isFrozen(patched));
});
