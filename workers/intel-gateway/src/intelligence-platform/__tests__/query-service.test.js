import assert from "node:assert/strict";
import { test } from "node:test";
import { EnterpriseQueryService } from "../query-service.js";
import { EvidenceQueryEngine } from "../../evidence-registry/query-engine.js";
import { EvidenceRegistry } from "../../evidence-registry/registry-service.js";
import { evidence, UUID_1 } from "./test-helpers.js";

async function buildService() {
  const registry = new EvidenceRegistry();
  const queryEngine = new EvidenceQueryEngine(registry);
  const service = new EnterpriseQueryService({ queryEngine });
  await registry.registerEvidence(
    evidence(UUID_1, {
      related_cves: ["CVE-2026-1111"],
      related_threat_actors: ["APT-TEST"],
      related_campaigns: ["CAMPAIGN-TEST"],
      related_iocs: ["1.2.3.4"],
      related_reports: ["RPT-TEST"],
      related_attack_techniques: ["T1059"],
      source_id: "SRC-TEST",
    })
  );
  return { service, registry };
}

test("EnterpriseQueryService requires a queryEngine dependency", () => {
  assert.throws(() => new EnterpriseQueryService({}), /requires a shared queryEngine dependency/);
});

test("all 9 covered dimensions delegate to EvidenceQueryEngine and return the registered record", async () => {
  const { service } = await buildService();
  assert.equal((await service.queryByEvidence(UUID_1)).evidence_uuid, UUID_1);
  assert.equal((await service.queryByCVE("CVE-2026-1111"))[0].evidence_uuid, UUID_1);
  assert.equal((await service.queryByThreatActor("APT-TEST"))[0].evidence_uuid, UUID_1);
  assert.equal((await service.queryByCampaign("CAMPAIGN-TEST"))[0].evidence_uuid, UUID_1);
  assert.equal((await service.queryByIOC("1.2.3.4"))[0].evidence_uuid, UUID_1);
  assert.equal((await service.queryByReport("RPT-TEST"))[0].evidence_uuid, UUID_1);
  assert.equal((await service.queryByAttackTechnique("T1059"))[0].evidence_uuid, UUID_1);
  assert.equal((await service.queryBySource("SRC-TEST"))[0].evidence_uuid, UUID_1);
  assert.deepEqual(await service.queryByConfidence("nonexistent-tier"), []);
});

test("queryByVendor documents the confirmed platform gap and does not return a silent empty array", async () => {
  const { service } = await buildService();
  await assert.rejects(() => service.queryByVendor("Cisco"), (err) => {
    assert.match(err.message, /no canonical, composable Vendor implementation/);
    assert.match(err.message, /buildEvidenceAttribution/);
    return true;
  });
});

test("queryByProduct documents the confirmed platform gap (informal field exists elsewhere, no evidence-registry index)", async () => {
  const { service } = await buildService();
  await assert.rejects(() => service.queryByProduct("Windows Server"), (err) => {
    assert.match(err.message, /no canonical, composable Product implementation/);
    assert.match(err.message, /related_products/);
    return true;
  });
});

test("queryByMalware documents the confirmed platform gap (nested-only field, dead-code normalizer)", async () => {
  const { service } = await buildService();
  await assert.rejects(() => service.queryByMalware("Emotet"), (err) => {
    assert.match(err.message, /no canonical, composable Malware implementation/);
    assert.match(err.message, /actor_malware/);
    return true;
  });
});
