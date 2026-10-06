import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ALL_EIG_CONTRACTS,
  GatewayServiceContract,
  MiddlewareContract,
  CapabilityRegistryContract,
  GatewayMetricsContract,
  isContractForwardCompatible,
  checkContractCompatibility,
} from "../service-contracts.js";

test("all 4 contracts are present, frozen, and their declared version matches their history's last entry", () => {
  assert.equal(ALL_EIG_CONTRACTS.length, 4);
  for (const contract of ALL_EIG_CONTRACTS) {
    assert.ok(Object.isFrozen(contract), `${contract.name} is not frozen`);
    const lastEntry = contract.history[contract.history.length - 1];
    assert.equal(contract.version, lastEntry.version, `${contract.name}'s version drifted from its own history`);
  }
});

test("contract names are unique across the 4 contracts", () => {
  const names = ALL_EIG_CONTRACTS.map((c) => c.name);
  assert.equal(new Set(names).size, names.length);
});

test("checkContractCompatibility() is the reused Stage 12/13 function, not a reimplementation", () => {
  // GatewayServiceContract is 1.1.0 as of Stage 21 Phase 4 (describeCapability/
  // describeAllCapabilities/annotateCapability, additive) -- a caller that still expects the
  // Stage 14 Phase 1 baseline (1.0.0) must remain forward-compatible with the current version.
  const result = checkContractCompatibility(GatewayServiceContract, "1.0.0");
  assert.equal(result.compatible, true);
  assert.equal(result.currentVersion, "1.1.0");
});

test("isContractForwardCompatible() rejects an unknown version", () => {
  assert.equal(isContractForwardCompatible(GatewayServiceContract.history, "0.9.0", "1.0.0"), false);
});

test("Stage 21: CapabilityRegistryContract 1.2.0 remains forward-compatible with a caller still expecting 1.0.0", () => {
  const result = checkContractCompatibility(CapabilityRegistryContract, "1.0.0");
  assert.equal(result.compatible, true);
  assert.equal(result.currentVersion, "1.2.0");
});

test("each contract's source names the expected module", () => {
  assert.match(GatewayServiceContract.source, /gateway-service\.js/);
  assert.match(MiddlewareContract.source, /gateway-middleware\.js/);
  assert.match(CapabilityRegistryContract.source, /gateway-registry\.js/);
  assert.match(GatewayMetricsContract.source, /gateway-metrics\.js/);
});
