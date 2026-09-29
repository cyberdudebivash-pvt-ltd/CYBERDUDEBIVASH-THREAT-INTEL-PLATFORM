import test from "node:test";
import assert from "node:assert/strict";
import { routeEnterpriseEndpoint } from "../enterprise-endpoints.js";

const req = new Request("https://intel.cyberdudebivash.com/api/export/misp");
const items = [{
  id:"intel-1",
  title:"Authorized malware finding",
  severity:"HIGH",
  confidence:90,
  published_at:"2026-09-29T00:00:00.000Z",
  tags:["malware"],
  iocs:[{type:"domain",value:"example.invalid"}],
}];

function normalizeVolatileMispFields(payload) {
  const copy = structuredClone(payload);
  if (copy?._meta) delete copy._meta.exported_at;
  for (const wrapper of copy?.response || []) {
    if (wrapper?.Event) delete wrapper.Event.timestamp;
  }
  return copy;
}

test("legacy MISP URL uses canonical enterprise entitlement resource", async () => {
  const calls=[];
  const resolveEntitlement=(ctx,env,resource,auth,legacyAllowed)=>{ calls.push({resource,legacyAllowed}); return {allowed:false}; };
  const res=await routeEnterpriseEndpoint("/api/export/misp",req,{},{},"enterprise",items,"req-misp",{tier:"enterprise"},resolveEntitlement);
  assert.equal(res.status,403);
  assert.deepEqual(calls.map(x=>x.resource),["misp_export"]);
});

test("canonical and legacy MISP URLs return the same payload contract", async () => {
  const allow=(ctx,env,resource,auth,legacyAllowed)=>({allowed:legacyAllowed});
  const args=[req,{},{},"enterprise",items,"req-misp",{tier:"enterprise"},allow];
  const canonical=await routeEnterpriseEndpoint("/api/misp/export",...args);
  const legacy=await routeEnterpriseEndpoint("/api/export/misp",...args);
  assert.equal(canonical.status,200); assert.equal(legacy.status,200);
  assert.equal(canonical.headers.get("Content-Type"),legacy.headers.get("Content-Type"));
  const canonicalBody = await canonical.json();
  const legacyBody = await legacy.json();

  // The alias contract is semantic, not clock identity. Each handler call
  // legitimately stamps its own export time and event epoch, so those two
  // volatile fields can differ by milliseconds/seconds without changing the
  // MISP customer contract. Everything else must remain byte-for-byte
  // equivalent after JSON parsing.
  assert.deepEqual(
    normalizeVolatileMispFields(canonicalBody),
    normalizeVolatileMispFields(legacyBody),
  );
});

test("FREE cannot use either MISP route", async () => {
  const allow=(ctx,env,resource,auth,legacyAllowed)=>({allowed:legacyAllowed});
  for (const path of ["/api/misp/export","/api/export/misp"]) {
    const res=await routeEnterpriseEndpoint(path,req,{},{},"free",items,"req-free",{tier:"free"},allow);
    assert.equal(res.status,403);
  }
});
