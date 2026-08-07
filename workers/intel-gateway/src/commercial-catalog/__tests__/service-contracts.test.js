import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ALL_COMMERCIAL_CATALOG_CONTRACTS,
  CommercialCatalogContract,
  CommercialAdaptersContract,
  CommercialMetricsContract,
  CommercialReadinessContract,
  INTERNAL_V1_NAMESPACE,
  isContractForwardCompatible,
  checkContractCompatibility,
} from "../service-contracts.js";

test("all 4 contracts are present, frozen, and their declared version matches their history's last entry", () => {
  assert.equal(ALL_COMMERCIAL_CATALOG_CONTRACTS.length, 4);
  for (const contract of ALL_COMMERCIAL_CATALOG_CONTRACTS) {
    assert.ok(Object.isFrozen(contract), `${contract.name} is not frozen`);
    const lastEntry = contract.history[contract.history.length - 1];
    assert.equal(contract.version, lastEntry.version, `${contract.name}'s version drifted from its own history`);
  }
});

test("contract names are unique across the 4 contracts", () => {
  const names = ALL_COMMERCIAL_CATALOG_CONTRACTS.map((c) => c.name);
  assert.equal(new Set(names).size, names.length);
});

test("every contract is namespaced internal/v1 -- a deliberately distinct concept from ADR-0012's public /api/v1/ path versioning", () => {
  for (const contract of ALL_COMMERCIAL_CATALOG_CONTRACTS) {
    assert.equal(contract.namespace, INTERNAL_V1_NAMESPACE, `${contract.name}`);
  }
});

test("checkContractCompatibility() is the reused enterprise-gateway function, not a reimplementation", () => {
  const result = checkContractCompatibility(CommercialCatalogContract, "1.0.0");
  assert.equal(result.compatible, true);
  assert.equal(result.currentVersion, "1.0.0");
});

test("isContractForwardCompatible() rejects an unknown version", () => {
  assert.equal(isContractForwardCompatible(CommercialCatalogContract.history, "0.9.0", "1.0.0"), false);
});

test("each contract's source names the expected module", () => {
  assert.match(CommercialCatalogContract.source, /catalog\.js/);
  assert.match(CommercialAdaptersContract.source, /commercial-adapters\.js/);
  assert.match(CommercialMetricsContract.source, /commercial-metrics\.js/);
  assert.match(CommercialReadinessContract.source, /commercial-readiness\.js/);
});

test("CommercialAdaptersContract names all 10 adapter factories, one per catalog newAdapter entry", async () => {
  const { listNewAdapterEntries } = await import("../catalog.js");
  assert.equal(CommercialAdaptersContract.methods.length, listNewAdapterEntries().length);
});
