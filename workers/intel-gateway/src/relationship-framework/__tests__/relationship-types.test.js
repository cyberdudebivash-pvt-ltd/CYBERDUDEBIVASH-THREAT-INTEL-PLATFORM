import assert from "node:assert/strict";
import { test } from "node:test";
import { RELATIONSHIP_TYPE_DEFINITIONS, RELATIONSHIP_CATALOG_VERSION } from "../relationship-types.js";

test("catalog has no duplicate type names", () => {
  const names = RELATIONSHIP_TYPE_DEFINITIONS.map((d) => d.name);
  assert.equal(new Set(names).size, names.length);
});

test("catalog has no duplicate aliases, including across different types", () => {
  const aliases = RELATIONSHIP_TYPE_DEFINITIONS.flatMap((d) => d.aliases);
  assert.equal(new Set(aliases).size, aliases.length, "an alias must resolve to exactly one canonical type");
});

test("every definition is frozen (including nested arrays)", () => {
  for (const def of RELATIONSHIP_TYPE_DEFINITIONS) {
    assert.ok(Object.isFrozen(def), `${def.name} should be frozen`);
    assert.ok(Object.isFrozen(def.aliases));
    assert.ok(Object.isFrozen(def.validSourceTypes));
    assert.ok(Object.isFrozen(def.validTargetTypes));
  }
});

test("every definition has the five Phase 2 category values covered across the catalog", () => {
  const categories = new Set(RELATIONSHIP_TYPE_DEFINITIONS.map((d) => d.category));
  for (const expected of ["evidence", "threat", "ioc", "campaign", "attack"]) {
    assert.ok(categories.has(expected), `no relationship type registered for category "${expected}"`);
  }
});

test("every definition cites a source", () => {
  for (const def of RELATIONSHIP_TYPE_DEFINITIONS) {
    assert.ok(def.source && def.source.length > 0, `${def.name} must cite where its vocabulary came from`);
  }
});

test("RELATIONSHIP_CATALOG_VERSION is a semver-shaped string", () => {
  assert.match(RELATIONSHIP_CATALOG_VERSION, /^\d+\.\d+\.\d+$/);
});
