import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildAPTPayload} from '../apt-contract.js';
const profiles=[{id:'APT29',alias:'Cozy Bear',nation:'RU',sector:'Government',ttps:21}];
const build=items=>buildAPTPayload(items,profiles,'2026-10-07T05:00:00Z');
test('structured APT-topic classifications produce real activity without fabricated identities',()=>{
 const p=build([{title:'Infrastructure investigation',actor:'CDB-UNATTR-APT',source:'Publisher',source_url:'https://example.com/intel'},
  {title:'Second report',actor:'Unattributed APT Cluster',source:'Source'}]);
 assert.equal(p.apt_advisories,2);assert.equal(p.tracked_apts,0);assert.equal(p.sources_reporting,2);
 assert.equal(p.recent_activity.length,2);assert.equal(p.attribution_status,'NAMED_ATTRIBUTION_NOT_PROVIDED');
});
test('adapter/capture substrings and arbitrary CVEs are not APT activity',()=>{
 const p=build([{title:'Task capture adapter flaw',threat_type:'Vulnerability',tags:['Capture']},
  {title:'Hackers exploit 32 zero-days on first day of Pwn2Own Ireland',threat_type:'Vulnerability'},
  {title:'APT report',actor:'CDB-UNATTR-CVE'}]);
 assert.equal(p.apt_advisories,1);assert.equal(p.tracked_apts,0);
});
test('source title mentions are reporting, not attributed actors, nations or catalog sector counts',()=>{
 const p=build([{title:'New report mentions Cozy Bear',source:'Publisher'}]);
 assert.equal(p.apt_advisories,1);assert.equal(p.tracked_apts,0);assert.equal(p.active_sectors,0);assert.equal(p.total_ttps,0);
});
test('explicit reported actors are deduplicated and only supplied countries/sectors/techniques count',()=>{
 const p=build([{title:'Report',actor_display_name:'Cozy Bear',actor_sectors:['Energy'],actor_country:'RU',
  mitre_techniques:[{id:'T1059'},'T1059','garbage'],source_url:'https://example.com/report'},
  {title:'Report 2',actor_tag:'APT29',attck_technique_ids:['T1059','T1190']}]);
 assert.equal(p.tracked_apts,1);assert.equal(p.active_sectors,1);assert.equal(p.total_ttps,2);
 assert.equal(p.top_actors[0].nation,'RU');assert.equal(p.top_actors[0].source_urls.length,1);
 assert.equal(p.top_actors[0].attribution_basis,'reported_actor_field');
});
test('catalog country is not used when source actor country is absent or unknown',()=>{
 for(const actor_country of [undefined,'Unknown','N/A','']){
  const p=build([{actor:'APT29',title:'Report',actor_country}]);assert.equal(p.tracked_apts,1);assert.ok(!('nation' in p.top_actors[0]));
 }
});
test('actor entitlement restriction cannot be bypassed by alternate identity fields',()=>{
 const p=build([{actor:'APT29',actor_tag:'APT29',actor_display_name:'Cozy Bear',title:'Report',actor_paywall:{allowed:false}}]);
 assert.equal(p.tracked_apts,0);assert.equal(p.apt_advisories,1);
});
test('public aggregation never discloses raw legacy identities, actor sectors or private actor techniques',()=>{
 const p=buildAPTPayload([{actor:'APT29',title:'Report',actor_country:'RU',actor_sectors:['Energy'],
  actor_ttps:['T1190'],mitre_techniques:['T1059'],source:'Publisher'}],profiles,'now',{includeAttribution:false});
 assert.equal(p.apt_advisories,1);assert.equal(p.tracked_apts,0);assert.equal(p.active_sectors,0);
 assert.equal(p.total_ttps,1);assert.deepEqual(p.top_actors,[]);
 assert.ok(!JSON.stringify(p).includes('APT29'));assert.ok(!JSON.stringify(p).includes('Energy'));
});
test('bounded newest activity, malformed inputs and unsafe source links fail safely',()=>{
 assert.equal(build(null).items_evaluated,0);
 const p=build(Array.from({length:12},(_,i)=>({title:'APT reporting '+i,published:`2026-10-${String(i+1).padStart(2,'0')}T00:00:00Z`,tags:{},source_url:'javascript:alert(1)'})));
 assert.equal(p.recent_activity.length,5);assert.equal(p.recent_activity[0].title,'APT reporting 11');
 assert.equal(p.recent_activity[0].source_url,'');
});
