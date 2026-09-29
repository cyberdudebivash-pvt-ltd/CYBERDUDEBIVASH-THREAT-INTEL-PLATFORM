import test from "node:test";
import assert from "node:assert/strict";
import { routeEnterpriseEndpoint } from "../enterprise-endpoints.js";

const req = new Request("https://intel.cyberdudebivash.com/api/export/misp");
const items = [{ id:"intel-1", title:"Authorized malware finding", severity:"HIGH", confidence:90, tags:["malware"], iocs:[{type:"domain",value:"example.invalid"}] }];

test("legacy MISP URL uses canonical enterprise entitlement resource", async () => {
  const calls=[];
  const resolveEntitlement=(ctx,env,resource,auth,legacyAllowed)=>{ calls.push({resource,legacyAllowed}); return {allowed:false}; };
  const res=await routeEnterpriseEndpoint("/api/export/misp",req,{},{},"ENTERPRISE",items,"req-misp",{tier:"ENTERPRISE"},resolveEntitlement);
  assert.equal(res.status,403);
  assert.deepEqual(calls.map(x=>x.resource),["misp_export"]);
});

test("canonical and legacy MISP URLs return the same payload contract", async () => {
  const allow=(ctx,env,resource,auth,legacyAllowed)=>({allowed:legacyAllowed});
  // routeEnterpriseEndpoint receives normalizeTierForEE(auth.tier) from the
  // production dispatcher, so its tier argument is lowercase even though
  // resolveAuth() itself uses uppercase wire values.
  const args=[req,{},{},"enterprise",items,"req-misp",{tier:"ENTERPRISE"},allow];
  const canonical=await routeEnterpriseEndpoint("/api/misp/export",...args);
  const legacy=await routeEnterpriseEndpoint("/api/export/misp",...args);
  assert.equal(canonical.status,200); assert.equal(legacy.status,200);
  assert.equal(canonical.headers.get("Content-Type"),legacy.headers.get("Content-Type"));
  assert.deepEqual(await canonical.json(),await legacy.json());
});

test("FREE cannot use either MISP route", async () => {
  const allow=(ctx,env,resource,auth,legacyAllowed)=>({allowed:legacyAllowed});
  for (const path of ["/api/misp/export","/api/export/misp"]) {
    const res=await routeEnterpriseEndpoint(path,req,{},{},"FREE",items,"req-free",{tier:"FREE"},allow);
    assert.equal(res.status,403);
  }
});
