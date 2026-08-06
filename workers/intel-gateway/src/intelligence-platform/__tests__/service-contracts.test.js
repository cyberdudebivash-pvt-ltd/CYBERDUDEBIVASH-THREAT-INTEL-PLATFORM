import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ALL_EIPS_CONTRACTS,
  IntelligenceServiceContract,
  QueryContract,
  CorrelationContract,
  ProvenanceContract,
  ValidationContract,
  MetricsContract,
  isContractForwardCompatible,
  checkContractCompatibility,
} from "../service-contracts.js";
import { isContractForwardCompatible as evidenceRegistryVersion } from "../../evidence-registry/service-contracts.js";

test("all six named contracts are present in ALL_EIPS_CONTRACTS, no duplicates", () => {
  assert.equal(ALL_EIPS_CONTRACTS.length, 6);
  const names = ALL_EIPS_CONTRACTS.map((c) => c.name);
  assert.equal(new Set(names).size, 6, "no duplicate contract names");
  assert.deepEqual(
    new Set(names),
    new Set(["IntelligenceServiceContract", "QueryContract", "CorrelationContract", "ProvenanceContract", "ValidationContract", "MetricsContract"])
  );
});

test("every contract is frozen (immutable) at every level -- name, methods, history", () => {
  for (const contract of ALL_EIPS_CONTRACTS) {
    assert.ok(Object.isFrozen(contract), `${contract.name} itself must be frozen`);
    assert.ok(Object.isFrozen(contract.methods), `${contract.name}.methods must be frozen`);
    assert.ok(Object.isFrozen(contract.history), `${contract.name}.history must be frozen`);
  }
});

test("QueryContract documents all 12 brief dimensions, including the 3 gap-only methods", () => {
  assert.equal(QueryContract.methods.length, 12);
  assert.ok(QueryContract.methods.includes("EnterpriseQueryService.queryByVendor"));
  assert.ok(QueryContract.methods.includes("EnterpriseQueryService.queryByProduct"));
  assert.ok(QueryContract.methods.includes("EnterpriseQueryService.queryByMalware"));
});

test("ProvenanceContract's method surface is identical to Stage 12's, by design (Phase 4 fully satisfied via reuse)", () => {
  assert.equal(ProvenanceContract.methods.length, 6);
  assert.ok(ProvenanceContract.source.includes("evidence-registry/provenance-engine.js"));
});

test("CorrelationContract and IntelligenceServiceContract declare non-empty method lists", () => {
  assert.ok(CorrelationContract.methods.length > 0);
  assert.ok(IntelligenceServiceContract.methods.length > 0);
  assert.ok(ValidationContract.methods.includes("IntelligenceValidationService.validateIntelligenceBundle"));
  assert.ok(MetricsContract.methods.includes("ServicePlatformMetrics.snapshot"));
});

test("this module's exported compatibility functions are Stage 12's own, re-exported (identity check -- proves reuse, not a parallel reimplementation)", () => {
  assert.equal(isContractForwardCompatible, evidenceRegistryVersion);
});

test("checkContractCompatibility reports the current version and whether the caller's expectation holds", () => {
  const result = checkContractCompatibility(QueryContract, "1.0.0");
  assert.equal(result.compatible, true);
  assert.equal(result.currentVersion, "1.0.0");

  const stale = checkContractCompatibility(QueryContract, "0.1.0");
  assert.equal(stale.compatible, false);
});
