import assert from "node:assert/strict";
import { test } from "node:test";
import { GatewayDispatcher, CapabilityAuthorizationError } from "../gateway-dispatcher.js";
import { GatewayRegistry, CapabilityNotRegisteredError } from "../gateway-registry.js";
import { GatewayMetrics } from "../gateway-metrics.js";
import { testPlatform } from "./test-helpers.js";

function buildDispatcher({ middleware } = {}) {
  const platform = testPlatform();
  const serviceMetrics = platform.metrics.sharedServiceMetrics;
  const gatewayMetrics = new GatewayMetrics(platform.metrics);
  const registry = new GatewayRegistry();
  const dispatcher = new GatewayDispatcher({ registry, serviceMetrics, gatewayMetrics, middleware });
  return { dispatcher, registry, serviceMetrics, gatewayMetrics };
}

test("constructor requires registry, serviceMetrics, and gatewayMetrics", () => {
  assert.throws(() => new GatewayDispatcher({}), /requires a registry/);
});

test("dispatch() of an unregistered capability throws CapabilityNotRegisteredError", async () => {
  const { dispatcher } = buildDispatcher();
  await assert.rejects(
    () => dispatcher.dispatch({ capability: "nope", method: "x", grantedCapabilities: ["nope"] }),
    CapabilityNotRegisteredError
  );
});

test("dispatch() of a capability the caller lacks throws CapabilityAuthorizationError naming what's missing, and records a denial", async () => {
  const { dispatcher, registry, gatewayMetrics } = buildDispatcher();
  registry.register("secret.capability", async () => "should not run");
  try {
    await dispatcher.dispatch({ capability: "secret.capability", method: "x", grantedCapabilities: [] });
    assert.fail("expected a throw");
  } catch (error) {
    assert.ok(error instanceof CapabilityAuthorizationError);
    assert.deepEqual(error.missing, ["secret.capability"]);
  }
  assert.equal(gatewayMetrics.snapshot().gateway.capability_authorization_denials["secret.capability"], 1);
});

test("dispatch() happy path: the middleware chain runs in the documented order, then the resolved handler", async () => {
  const seen = [];
  const testMiddleware = [
    async (context, next) => {
      seen.push("outer-in");
      const r = await next();
      seen.push("outer-out");
      return r;
    },
    async (context, next) => {
      seen.push("inner-in");
      const r = await next();
      seen.push("inner-out");
      return r;
    },
  ];
  const { dispatcher, registry } = buildDispatcher({ middleware: testMiddleware });
  registry.register("greet", async (context, method, name) => {
    seen.push("handler");
    return `hello ${name} via ${method}`;
  });

  const result = await dispatcher.dispatch({
    capability: "greet",
    method: "sayHi",
    args: ["world"],
    grantedCapabilities: ["greet"],
  });
  assert.equal(result, "hello world via sayHi");
  assert.deepEqual(seen, ["outer-in", "inner-in", "handler", "inner-out", "outer-out"]);
});

test("dispatch() wraps the call in the shared serviceMetrics.timed() under a gateway-prefixed name", async () => {
  const { dispatcher, registry, serviceMetrics } = buildDispatcher({ middleware: [] });
  registry.register("counted", async () => "ok");
  await dispatcher.dispatch({ capability: "counted", method: "run", grantedCapabilities: ["counted"] });
  const snapshot = serviceMetrics.snapshot();
  assert.equal(snapshot.call_counts["gateway.counted"], 1);
});

test("dispatch() propagates a handler's thrown error, still recorded by the outer timed() wrap", async () => {
  const { dispatcher, registry, serviceMetrics } = buildDispatcher({ middleware: [] });
  registry.register("failer", async () => {
    throw new Error("handler exploded");
  });
  await assert.rejects(
    () => dispatcher.dispatch({ capability: "failer", method: "run", grantedCapabilities: ["failer"] }),
    /handler exploded/
  );
  assert.equal(serviceMetrics.snapshot().call_counts["gateway.failer"], 1, "a failed call is still timed/counted");
});
