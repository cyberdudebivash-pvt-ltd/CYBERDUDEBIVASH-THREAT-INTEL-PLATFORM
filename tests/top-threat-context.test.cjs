'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=process.env.SENTINEL_UI_TEST_ROOT||path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'js/homepage-dashboard-engine.js'),'utf8');
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a,`missing ${start}`);return source.slice(a,b);}
const container={innerHTML:''};
const context={window:{CDB_NORMALIZE:{epss:()=>({percent:0})}},document:{getElementById:id=>id==='top-threats-section'?container:null},
 getTopThreats:data=>data,cdbBuildReportUrl:item=>item.report_url||'',Date};
vm.createContext(context);
vm.runInContext(section('function _cdbSocThreatContext(item)','function getTopThreats(data)')+
 section('function renderTopThreats(data)','        window.onerror ='),context);
const view=context._cdbSocThreatContext;
test('all generic actor variants produce factual source context, never an attributed actor',()=>{
 for(const actor of ['UNC-UNKNOWN','UNC-CDB-99','CDB-UNATTR-CVE','CDB-UNATTR-APT','Unattributed APT Cluster','Unknown Threat Actor',' N/A ','']){
  const value=view({actor_tag:actor,source:'Security Affairs',cve_ids:['CVE-2026-86360']});
  assert.equal(value.actor,'');assert.equal(value.label,'SOURCE · Security Affairs');assert.equal(value.cves[0],'CVE-2026-86360');
 }
});
test('reported actor fields are preserved and entitlement restrictions remain authoritative',()=>{
 assert.equal(view({actor_display_name:'APT29',actor_tag:'UNC-UNKNOWN'}).label,'ACTOR · APT29');
 assert.equal(view({actor:'Lazarus'}).actor,'Lazarus');
 assert.equal(view({actor_tag:'APT29',actor_paywall:{allowed:false},source:'Source'}).actor,'');
 assert.ok(view({actor_tag:'APT29',actor_paywall:{allowed:false}}).description.includes('restricted'));
});
test('CVE/source fallback never labels the vendor, risk or CVE as the attacker',()=>{
 assert.equal(view({title:'Microsoft CVE-2026-96940',risk_score:10}).label,'VULNERABILITY ADVISORY');
 assert.equal(view({title:'Dell vulnerability',threat_type:'Vulnerability'}).actor,'');
 assert.equal(view({}).label,'THREAT ADVISORY');
 assert.deepEqual(Array.from(view({cve_ids:['cve-2026-86360','not-a-cve'],cve_id:'CVE-2026-86360'}).cves),['CVE-2026-86360']);
});
test('report pool keeps actual actor/source/CVE evidence and original source URL',()=>{
 const r={id:'report',title:'Dell DSU flaw',url:'/reports/report.html',source_url:'https://example.com/advisory',
  cve:['CVE-2026-86360'],actor_display_name:'APT29',source:'Publisher',actor_paywall:{allowed:false}};
 const pool=context._cdbReportPoolItem(r);
 assert.equal(pool.actor_display_name,r.actor_display_name);assert.equal(pool.source,r.source);assert.equal(pool.source_url,r.source_url);
 assert.equal(view(pool).cves[0],'CVE-2026-86360');assert.equal(view(pool).actor,'');
});
test('actual SOC renderer shows safe useful context and structured CVEs on the visible cards',()=>{
 const title='Dell DSU <img src=x onerror=alert(1)>';
 context.renderTopThreats([{title,source:'Publisher <script>',actor:'CDB-UNATTR-CVE',cve_ids:['CVE-2026-86360'],risk_score:9.6,
  cvss_score:9.6,report_url:'/reports/fixture.html',timestamp:new Date().toISOString(),mitre_tactics:[]}]);
 assert.ok(container.innerHTML.includes('SOURCE · Publisher &lt;script&gt;'));
 assert.ok(container.innerHTML.includes('CVE-2026-86360'));assert.ok(!container.innerHTML.includes('UNATTRIBUTED'));
 assert.ok(!container.innerHTML.includes('<script>'));assert.ok(!container.innerHTML.includes('<img'));
 assert.ok(container.innerHTML.includes('FULL INTEL'));assert.ok(container.innerHTML.includes('/reports/fixture.html'));
});
test('recon snapshots never present stale, future or incomplete scans as current results',()=>{
 vm.runInContext(section('            function bugHunterScanView(data, nowMs)','            function renderBugHunterEngine(data)'),context);
 const now=Date.parse('2026-10-07T05:00:00Z'),view=context.bugHunterScanView;
 assert.equal(view({timestamp:'2026-08-25T18:02:45.017Z',status:'COMPLETED'},now).recent,false);
 assert.ok(view({timestamp:'2026-08-25T18:02:45.017Z',status:'COMPLETED'},now).label.includes('HISTORICAL'));
 assert.equal(view({timestamp:'2026-10-07T04:00:00Z',status:'COMPLETED'},now).recent,true);
 assert.equal(view({timestamp:'2026-10-07T04:00:00Z',status:'RUNNING'},now).recent,false);
 assert.equal(view({timestamp:'2026-10-08T04:00:00Z',status:'COMPLETED'},now).timestamp,'');
 assert.equal(view({},now).recent,false);
});
