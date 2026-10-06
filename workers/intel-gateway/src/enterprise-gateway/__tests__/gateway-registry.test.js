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

test("describe() returns safe metadata without the handler function", () => {
  const registry = new GatewayRegistry();
  const handler = async () => "ok";
  registry.register("evidence.lookup", handler, {
    description: "test capability",
    version: "2.0.0",
    requiredCapabilities: ["evidence.lookup", "extra.scope"],
  });
  const described = registry.describe("evidence.lookup");
  assert.deepEqual(described, {
    name: "evidence.lookup",
    version: "2.0.0",
    description: "test capability",
    requiredCapabilities: ["evidence.lookup", "extra.scope"],
    // Stage 21 Phase 4: commercial-classification metadata, secure-by-default when not supplied.
    owner: null,
    consumers: [],
    securityClassification: "internal",
    visibility: "internal",
    lifecycle: "internal-only",
  });
  assert.equal("handler" in described, false);
});

test("Stage 21: register() accepts commercial-classification options and describe() surfaces them", () => {
  const registry = new GatewayRegistry();
  registry.register("commercial.readinessSummary", async () => "ok", {
    owner: "Commercial Quality Orchestrator (Stage 20A)",
    consumers: ["commercial-catalog/platform.js"],
    securityClassification: "standard",
    visibility: "commercial",
    lifecycle: "beta",
  });
  const described = registry.describe("commercial.readinessSummary");
  assert.equal(described.owner, "Commercial Quality Orchestrator (Stage 20A)");
  assert.deepEqual(described.consumers, ["commercial-catalog/platform.js"]);
  assert.equal(described.securityClassification, "standard");
  assert.equal(described.visibility, "commercial");
  assert.equal(described.lifecycle, "beta");
});

test("Stage 21: annotate() merges commercial-classification metadata onto an already-registered capability without re-registering it", () => {
  const registry = new GatewayRegistry();
  registry.register("evidence.lookup", async () => "ok", { description: "unchanged" });
  registry.annotate("evidence.lookup", { visibility: "commercial", lifecycle: "ga", owner: "Intelligence Platform (Stage 13)" });
  const described = registry.describe("evidence.lookup");
  assert.equal(described.visibility, "commercial");
  assert.equal(described.lifecycle, "ga");
  assert.equal(described.owner, "Intelligence Platform (Stage 13)");
  // annotate() must not touch the fields it doesn't own.
  assert.equal(described.description, "unchanged");
});

test("Stage 21: annotate() rejects an unsupported field name", () => {
  const registry = new GatewayRegistry();
  registry.register("evidence.lookup", async () => "ok");
  assert.throws(() => registry.annotate("evidence.lookup", { version: "9.9.9" }), /unsupported field "version"/);
});

test("Stage 21: annotate() of an unregistered capability throws CapabilityNotRegisteredError, same as get()/describe()", () => {
  const registry = new GatewayRegistry();
  assert.throws(() => registry.annotate("nope", { owner: "x" }), CapabilityNotRegisteredError);
});

test("describe() of an unregistered capability throws CapabilityNotRegisteredError, same as get()", () => {
  const registry = new GatewayRegistry();
  assert.throws(() => registry.describe("nope"), CapabilityNotRegisteredError);
});

test("describeAll() returns safe metadata for every registered capability, in registration order", () => {
  const registry = new GatewayRegistry();
  registry.register("a", async () => {}, { description: "first" });
  registry.register("b", async () => {}, { description: "second" });
  const described = registry.describeAll();
  assert.deepEqual(
    described.map((entry) => entry.name),
    ["a", "b"]
  );
  assert.ok(described.every((entry) => !("handler" in entry)));
});

test("describeAll() on an empty registry returns an empty array", () => {
  const registry = new GatewayRegistry();
  assert.deepEqual(registry.describeAll(), []);
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
