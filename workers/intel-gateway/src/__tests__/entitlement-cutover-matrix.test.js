import assert from "node:assert/strict";
import { test } from "node:test";
import { enforceTierGate } from "../revenue-enforcement.js";

const matrix = [
  ["sla_report",       { FREE:false, PRO:false, ENTERPRISE:true, MSSP:true }],
  ["sla_incidents",    { FREE:false, PRO:false, ENTERPRISE:true, MSSP:true }],
  ["sla_certificate",  { FREE:false, PRO:false, ENTERPRISE:true, MSSP:true }],
  ["siem",             { FREE:false, PRO:false, ENTERPRISE:true, MSSP:true }],
  ["taxii_access",     { FREE:false, PRO:true,  ENTERPRISE:true, MSSP:true }],
  ["taxii_kev",        { FREE:false, PRO:false, ENTERPRISE:true, MSSP:true }],
  ["report_full",      { FREE:false, PRO:true,  ENTERPRISE:true, MSSP:true }],
  ["alerts",           { FREE:false, PRO:true,  ENTERPRISE:true, MSSP:true }],
];

test("commercial entitlement matrix is explicit for cutover candidates", () => {
  for (const [resource, tiers] of matrix) {
    for (const [tier, expected] of Object.entries(tiers)) {
      const decision = enforceTierGate(resource, tier);
      assert.equal(
        decision.allowed,
        expected,
        resource + " " + tier + " expected allowed=" + expected + " got " + JSON.stringify(decision)
      );
    }
  }
});

test("unknown or malformed tiers never inherit paid access", () => {
  for (const tier of ["", "UNKNOWN", "premium", "enterprise-plus", " PRO ", null, undefined, 1, true, {}, ["PRO"], { toUpperCase: () => "ENTERPRISE" }]) {
    for (const resource of ["ioc_full", "stix_bundle", "ai_full", "report_full", "sla_report", "sla_incidents", "sla_certificate", "siem", "alerts", "api_keys", "ioc_confidence_detail", "stix_export_full", "ai_predict", "ai_campaigns", "ai_anomalies", "intel_graph", "intel_graph_full", "intel_relations", "detection_rules", "actor_attribution", "taxii_access", "taxii_kev", "misp_export", "brand_protection", "vendor_risk", "vendor_risk_bulk", "geopolitical_risk", "nlq", "incident_response", "incident_delete", "intel_manifest_full", "cve_detail_full"]) {
      assert.equal(enforceTierGate(resource, tier).allowed, false, resource + " tier=" + String(tier));
    }
  }
});
