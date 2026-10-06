const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function renderer() {
 const source = fs.readFileSync(path.join(__dirname,'../js/homepage-dashboard-engine.js'),'utf8');
 const start = source.indexOf('function renderBugHunterEngine(data)');
 const end = source.indexOf('// ── TIP+SOAR RENDERERS',start);
 const nodes = {};
 for (const id of ['bh-findings-feed','bh-risk-exposure','bh-mitigated','bh-rosi','bh-subdomain-count','bh-livehost-count'])
  nodes[id] = {style:{},innerHTML:'',textContent:''};
 const context={document:{getElementById:id=>nodes[id]||null,querySelector:()=>null},console};
 vm.runInNewContext(source.slice(start,end)+';this.render=renderBugHunterEngine;',context);
 return {nodes,render:context.render};
}
test('recon findings render hostile strings as text and cap DOM work',()=>{
 const {nodes,render}=renderer();
 const hostile='<img src=x onerror=alert(1)>';
 render({metrics:{},findings_summary:Array.from({length:1000},()=>({severity:hostile,type:hostile,target:hostile}))});
 const html=nodes['bh-findings-feed'].innerHTML;
 assert.ok(!html.includes('<img'));
 assert.ok(html.includes('&lt;img'));
 assert.equal((html.match(/<div /g)||[]).length,50);
});
test('recon panel shows scope and scan evidence, never assumed financial returns',()=>{
 const {nodes,render}=renderer();
 render({domain:'example.test',timestamp:'2026-10-06T12:00:00Z',metrics:{risk_exposure:12000,rosi:95,total_findings:1}});
 assert.equal(nodes['bh-risk-exposure'].textContent,'example.test');
 assert.equal(nodes['bh-mitigated'].textContent,'2026-10-06T12:00:00.000Z');
 assert.equal(nodes['bh-rosi'].textContent,'1');
 assert.equal(nodes['bh-subdomain-count'].textContent,'Awaiting scan');
});
test('empty and malformed findings produce different operational states',()=>{
 const {nodes,render}=renderer();
 render({status:'COMPLETED',metrics:{},findings_summary:[]});
 assert.equal(nodes['bh-findings-feed'].textContent,'No findings recorded in this scan snapshot.');
 render({status:'COMPLETED',metrics:{},findings_summary:'malformed'});
 assert.equal(nodes['bh-findings-feed'].textContent,'Awaiting validated scan findings.');
 render({metrics:{},findings_summary:[null,4,'bad',{}]});
 assert.ok(nodes['bh-findings-feed'].innerHTML.includes('UNCLASSIFIED'));
});

