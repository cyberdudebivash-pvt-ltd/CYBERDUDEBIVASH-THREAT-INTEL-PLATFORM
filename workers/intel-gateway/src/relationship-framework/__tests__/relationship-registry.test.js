import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipRegistry, UnknownRelationshipTypeError } from "../relationship-registry.js";
import { RELATIONSHIP_TYPE_DEFINITIONS } from "../relationship-types.js";

test("registry auto-seeds every catalog definition on construction", () => {
  const registry = new RelationshipRegistry();
  assert.equal(registry.list().length, RELATIONSHIP_TYPE_DEFINITIONS.length);
});

test("normalizeTypeName resolves both canonical and lowercase alias forms", () => {
  const registry = new RelationshipRegistry();
  assert.equal(registry.normalizeTypeName("ATTRIBUTED_TO"), "ATTRIBUTED_TO");
  assert.equal(registry.normalizeTypeName("attributed_to"), "ATTRIBUTED_TO");
  assert.equal(registry.normalizeTypeName("Attributed_To"), "ATTRIBUTED_TO");
});

test("normalizeTypeName returns null (not throw) for an unknown type", () => {
  const registry = new RelationshipRegistry();
  assert.equal(registry.normalizeTypeName("NOT_A_REAL_TYPE"), null);
  assert.equal(registry.isKnownType("NOT_A_REAL_TYPE"), false);
});

test("get() throws UnknownRelationshipTypeError for an unregistered type", () => {
  const registry = new RelationshipRegistry();
  assert.throws(() => registry.get("NOT_A_REAL_TYPE"), UnknownRelationshipTypeError);
});

test("get() returns the full definition for a known type", () => {
  const registry = new RelationshipRegistry();
  const def = registry.get("attributed_to");
  assert.equal(def.name, "ATTRIBUTED_TO");
  assert.equal(def.category, "threat");
});

test("list(category) filters correctly", () => {
  const registry = new RelationshipRegistry();
  const attackTypes = registry.list("attack");
  assert.ok(attackTypes.length > 0);
  assert.ok(attackTypes.every((d) => d.category === "attack"));
});

test("register() rejects a duplicate name (Single Source of Truth)", () => {
  const registry = new RelationshipRegistry();
  assert.throws(
    () => registry.register({ name: "ATTRIBUTED_TO", aliases: [], validSourceTypes: [], validTargetTypes: [] }),
    /already registered/
  );
});

test("register() accepts a genuinely new type and it becomes immediately queryable", () => {
  const registry = new RelationshipRegistry();
  registry.register({
    name: "TEST_ONLY_TYPE",
    aliases: ["test_only_type"],
    category: "evidence",
    validSourceTypes: ["Evidence"],
    validTargetTypes: ["Evidence"],
    requiresConfidence: false,
    description: "test fixture",
    version: "1.0.0",
    source: "test",
  });
  assert.equal(registry.isKnownType("test_only_type"), true);
});

test("validateEntityPair flags an invalid source entity class with a specific reason", () => {
  const registry = new RelationshipRegistry();
  const result = registry.validateEntityPair("ATTRIBUTED_TO", "IOC", "ThreatActor");
  assert.equal(result.valid, false);
  assert.match(result.reason, /does not permit source entity class "IOC"/);
});

test("validateEntityPair flags an invalid target entity class", () => {
  const registry = new RelationshipRegistry();
  const result = registry.validateEntityPair("ATTRIBUTED_TO", "Advisory", "CVE");
  assert.equal(result.valid, false);
  assert.match(result.reason, /does not permit target entity class "CVE"/);
});

test("validateEntityPair passes for a genuinely valid pairing", () => {
  const registry = new RelationshipRegistry();
  const result = registry.validateEntityPair("ATTRIBUTED_TO", "Advisory", "ThreatActor");
  assert.equal(result.valid, true);
  assert.equal(result.canonicalType, "ATTRIBUTED_TO");
});

test("validateEntityPair on an unknown type reports unknown, not a false pass", () => {
  const registry = new RelationshipRegistry();
  const result = registry.validateEntityPair("NOT_A_REAL_TYPE", "Advisory", "ThreatActor");
  assert.equal(result.valid, false);
  assert.match(result.reason, /Unknown relationship type/);
});

test("catalogVersion() reflects the seeded catalog version", () => {
  const registry = new RelationshipRegistry();
  assert.equal(registry.catalogVersion(), "1.0.0");
});
