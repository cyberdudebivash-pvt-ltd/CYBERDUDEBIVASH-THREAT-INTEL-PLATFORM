import assert from "node:assert/strict";
import { test } from "node:test";
import {
  GatewayRegistry,
  DuplicateCapabilityError,
  CapabilityNotRegisteredError,
  createServiceMethodHandler,
} from "../gateway-registry.js";
import { GatewayContext } from "../gateway-context.js";

test("register/has/get/list round-trip", () => {
  const registry = new GatewayRegistry();
  const handler = async () => "ok";
  registry.register("test.capability", handler, { description: "test" });
  assert.equal(registry.has("test.capability"), true);
  const entry = registry.get("test.capability");
  assert.equal(entry.handler, handler);
  assert.equal(entry.description, "test");
  assert.deepEqual(registry.list(), ["test.capability"]);
});

test("requiredCapabilities defaults to [name] when not specified", () => {
  const registry = new GatewayRegistry();
  registry.register("evidence.lookup", async () => {});
  assert.deepEqual(registry.get("evidence.lookup").requiredCapabilities, ["evidence.lookup"]);
});

test("duplicate registration throws DuplicateCapabilityError and does not overwrite", () => {
  const registry = new GatewayRegistry();
  const first = async () => "first";
  registry.register("dup", first);
  assert.throws(() => registry.register("dup", async () => "second"), DuplicateCapabilityError);
  assert.equal(registry.get("dup").handler, first);
});

test("lookup of an unregistered capability throws CapabilityNotRegisteredError", () => {
  const registry = new GatewayRegistry();
  assert.throws(() => registry.get("nope"), CapabilityNotRegisteredError);
});

test("unregister() removes an entry and reports whether one existed", () => {
  const registry = new GatewayRegistry();
  registry.register("temp", async () => {});
  assert.equal(registry.unregister("temp"), true);
  assert.equal(registry.has("temp"), false);
  assert.equal(registry.unregister("temp"), false);
});

test("createServiceMethodHandler dispatches to the named method on the target service", async () => {
  const service = {
    async byCVE(cve) {
      return [`evidence-for-${cve}`];
    },
  };
  const handler = createServiceMethodHandler(service);
  const context = new GatewayContext({ capability: "evidence.lookup" });
  const result = await handler(context, "byCVE", "CVE-2026-1234");
  assert.deepEqual(result, ["evidence-for-CVE-2026-1234"]);
});

test("createServiceMethodHandler throws on an unknown method", async () => {
  const service = { async byCVE() {} };
  const handler = createServiceMethodHandler(service);
  const context = new GatewayContext({ capability: "evidence.lookup" });
  await assert.rejects(() => handler(context, "byVendor"), /does not exist on the target service/);
});

test("createServiceMethodHandler honors an explicit allowedMethods allowlist", async () => {
  const service = {
    async a() {
      return 1;
    },
    async b() {
      return 2;
    },
  };
  const handler = createServiceMethodHandler(service, { allowedMethods: ["a"] });
  const context = new GatewayContext({ capability: "x" });
  assert.equal(await handler(context, "a"), 1);
  await assert.rejects(() => handler(context, "b"), /not an allowed method/);
});
