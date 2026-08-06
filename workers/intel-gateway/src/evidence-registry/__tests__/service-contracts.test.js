import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ALL_SERVICE_CONTRACTS,
  EvidenceServiceContract,
  RelationshipContract,
  ProvenanceContract,
  ValidationContract,
  MetricsContract,
  isContractForwardCompatible,
  checkContractCompatibility,
} from "../service-contracts.js";

test("all five named contracts are present in ALL_SERVICE_CONTRACTS, no duplicates", () => {
  assert.equal(ALL_SERVICE_CONTRACTS.length, 5);
  const names = ALL_SERVICE_CONTRACTS.map((c) => c.name);
  assert.deepEqual(new Set(names).size, 5, "no duplicate contract names");
  assert.deepEqual(
    new Set(names),
    new Set(["EvidenceServiceContract", "RelationshipContract", "ProvenanceContract", "ValidationContract", "MetricsContract"])
  );
});

test("every contract is frozen (immutable) at every level -- name, methods, history", () => {
  for (const contract of ALL_SERVICE_CONTRACTS) {
    assert.ok(Object.isFrozen(contract), `${contract.name} itself must be frozen`);
    assert.ok(Object.isFrozen(contract.methods), `${contract.name}.methods must be frozen`);
    assert.ok(Object.isFrozen(contract.history), `${contract.name}.history must be frozen`);
  }
});

test("every contract declares a non-empty method list matching its documented source file", () => {
  assert.ok(EvidenceServiceContract.methods.length > 0);
  assert.equal(RelationshipContract.methods.includes("RelationshipResolutionService.resolveRelationships"), true);
  assert.equal(ProvenanceContract.methods.length, 6, "six lineage kinds, per Phase 3");
  assert.ok(ValidationContract.methods.includes("EvidenceValidationService.validateBatch"));
  assert.ok(MetricsContract.methods.includes("ServicePlatformMetrics.snapshot"));
});

test("isContractForwardCompatible: a version is always compatible with itself", () => {
  assert.equal(isContractForwardCompatible(EvidenceServiceContract.history, "1.0.0", "1.0.0"), true);
});

test("isContractForwardCompatible: an unknown version is never compatible with anything", () => {
  assert.equal(isContractForwardCompatible(EvidenceServiceContract.history, "9.9.9", "1.0.0"), false);
  assert.equal(isContractForwardCompatible(EvidenceServiceContract.history, "1.0.0", "9.9.9"), false);
});

test("isContractForwardCompatible: a later fromVersion than toVersion is never forward-compatible", () => {
  const history = [
    { version: "1.0.0", change: "initial", backwardCompatibleWithPrevious: null },
    { version: "1.1.0", change: "additive", backwardCompatibleWithPrevious: true },
  ];
  assert.equal(isContractForwardCompatible(history, "1.1.0", "1.0.0"), false);
});

test("isContractForwardCompatible: a non-additive step in the walk breaks compatibility", () => {
  const history = [
    { version: "1.0.0", change: "initial", backwardCompatibleWithPrevious: null },
    { version: "2.0.0", change: "breaking rename", backwardCompatibleWithPrevious: false },
  ];
  assert.equal(isContractForwardCompatible(history, "1.0.0", "2.0.0"), false);
});

test("checkContractCompatibility reports the current version and whether the caller's expectation holds", () => {
  const result = checkContractCompatibility(EvidenceServiceContract, "1.0.0");
  assert.equal(result.compatible, true);
  assert.equal(result.currentVersion, "1.0.0");
  assert.equal(result.callerExpectedVersion, "1.0.0");

  const stale = checkContractCompatibility(EvidenceServiceContract, "0.9.0");
  assert.equal(stale.compatible, false);
});
