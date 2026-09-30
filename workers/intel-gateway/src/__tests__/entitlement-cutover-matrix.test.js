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
  for (const tier of ["", "UNKNOWN", "premium", "enterprise-plus", null, undefined]) {
    for (const resource of ["sla_report", "siem", "taxii_access", "report_full", "alerts"]) {
      assert.equal(enforceTierGate(resource, tier).allowed, false, resource + " tier=" + String(tier));
    }
  }
});
