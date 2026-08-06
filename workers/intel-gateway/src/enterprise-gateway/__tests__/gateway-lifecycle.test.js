import assert from "node:assert/strict";
import { test } from "node:test";
import {
  GatewayLifecycle,
  canTransitionGatewayLifecycle,
  IllegalGatewayLifecycleTransitionError,
  GATEWAY_LIFECYCLE_STATES,
} from "../gateway-lifecycle.js";

test("starts at INIT, not ready", () => {
  const lifecycle = new GatewayLifecycle();
  assert.equal(lifecycle.state, "INIT");
  assert.equal(lifecycle.isReady(), false);
});

test("markReady() transitions INIT -> READY", () => {
  const lifecycle = new GatewayLifecycle();
  lifecycle.markReady();
  assert.equal(lifecycle.state, "READY");
  assert.equal(lifecycle.isReady(), true);
});

test("stop() transitions READY -> STOPPED, and STOPPED is terminal", () => {
  const lifecycle = new GatewayLifecycle();
  lifecycle.markReady();
  lifecycle.stop();
  assert.equal(lifecycle.state, "STOPPED");
  assert.equal(lifecycle.isReady(), false);
  assert.throws(() => lifecycle.markReady(), IllegalGatewayLifecycleTransitionError);
});

test("an illegal transition throws IllegalGatewayLifecycleTransitionError, not a generic Error", () => {
  const lifecycle = new GatewayLifecycle();
  lifecycle.markReady();
  lifecycle.stop();
  try {
    lifecycle.markReady();
    assert.fail("expected a throw");
  } catch (error) {
    assert.ok(error instanceof IllegalGatewayLifecycleTransitionError);
    assert.equal(error.fromState, "STOPPED");
    assert.equal(error.toState, "READY");
  }
});

test("canTransitionGatewayLifecycle() matches every state in GATEWAY_LIFECYCLE_STATES", () => {
  assert.equal(canTransitionGatewayLifecycle("INIT", "READY"), true);
  assert.equal(canTransitionGatewayLifecycle("INIT", "STOPPED"), true);
  assert.equal(canTransitionGatewayLifecycle("READY", "STOPPED"), true);
  assert.equal(canTransitionGatewayLifecycle("READY", "INIT"), false);
  assert.equal(canTransitionGatewayLifecycle("STOPPED", "READY"), false);
  assert.deepEqual(GATEWAY_LIFECYCLE_STATES, ["INIT", "READY", "STOPPED"]);
});

test("healthCheck() reports state, readiness, and transition timestamps", () => {
  const lifecycle = new GatewayLifecycle();
  lifecycle.markReady();
  const health = lifecycle.healthCheck();
  assert.equal(health.state, "READY");
  assert.equal(health.ready, true);
  assert.ok(health.transitionedAt.INIT);
  assert.ok(health.transitionedAt.READY);
});
