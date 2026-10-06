const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function harness() {
 const source = fs.readFileSync(require('node:path').join(__dirname, '../js/homepage-dashboard-engine.js'), 'utf8');
 const nodes = {};
 for (const id of ['ts-incident-count','ts-incident-feed','tipsoar-badge','ts-response-count','ts-response-feed','ts-hunt-count','ts-playbook-count','ts-hunt-feed','ts-campaign-feed']) {
  let html = '', text = '';
  nodes[id] = {style:{}, get innerHTML(){return html;}, set innerHTML(v){html=v; text='';}, get textContent(){return text;}, set textContent(v){text=v;html='';}};
 }
 const ctx = {document:{getElementById:id=>nodes[id]}, console:{warn:(...args)=>{throw new Error(String(args));}}};
 vm.runInNewContext(source.slice(source.indexOf('function tipText('), source.indexOf('// ── AI EXECUTION LAYER v103')), ctx);
 return {nodes, ctx};
}
test('all incident, response, hunt and campaign fields escape injected markup',()=>{
 const {nodes,ctx}=harness(); const x='<img src=x onerror="alert(1)">';
 ctx.renderIncidentEngine({total_incidents:1, incidents:[{severity:x,title:x,threat_actor:x}]});
 ctx.renderResponseEngine({total_actions:1,response_actions:[{action_type:x}]});
 ctx.renderHuntEngine({total_hunts:1,hunt_hypotheses:[{priority:x,technique:x,hypothesis:x,confidence:x}],campaign_intelligence:[{campaign_name:x,campaign_id:x,actors_involved:[x],incident_count:x,avg_risk:x,techniques_observed:[x]}]});
 for (const id of ['ts-incident-feed','ts-response-feed','ts-hunt-feed','ts-campaign-feed']) {
  assert.ok(!nodes[id].innerHTML.includes('<img'),id);
  assert.ok(nodes[id].innerHTML.includes('&lt;'),id);
 }
});
test('prototype-named action types remain ordinary safe text with numeric counts',()=>{
 const {nodes,ctx}=harness();ctx.renderResponseEngine({response_actions:[{action_type:'__proto__'},{action_type:'constructor'},{action_type:'toString'},{action_type:'__proto__'}]});
 assert.ok(nodes['ts-response-feed'].innerHTML.includes('CONSTRUCTOR'));
 assert.ok(nodes['ts-response-feed'].innerHTML.includes('>2</span>'));
 assert.ok(!nodes['ts-response-feed'].innerHTML.includes('[object'));
});
test('malformed records are isolated and render work is bounded',()=>{
 const {nodes,ctx}=harness();
 ctx.renderIncidentEngine({incidents:Array.from({length:1000},()=>({title:'safe'}))});
 assert.equal((nodes['ts-incident-feed'].innerHTML.match(/<div /g)||[]).length,12);
 ctx.renderResponseEngine({response_actions:[null,42,[],{}, {action_type:'block_ip'}]});
 assert.ok(nodes['ts-response-feed'].innerHTML.includes('BLOCK IP'));
 ctx.renderHuntEngine({hunt_hypotheses:[null,{}, {hypothesis:44}],campaign_intelligence:[null,{}, {campaign_name:42,actors_involved:42,techniques_observed:{}}]});
 assert.ok(nodes['ts-campaign-feed'].innerHTML.includes('Awaiting attribution'));
});
test('empty refresh clears old records rather than retaining stale customer evidence',()=>{
 const {nodes,ctx}=harness();ctx.renderIncidentEngine({incidents:[{title:'old'}]});ctx.renderIncidentEngine({incidents:{}});
 assert.equal(nodes['ts-incident-feed'].innerHTML,'');
 assert.equal(nodes['ts-incident-feed'].textContent,'Awaiting validated records.');
 ctx.renderResponseEngine({response_actions:[{action_type:'block_ip'}]});ctx.renderResponseEngine({response_actions:[]});
 assert.equal(nodes['ts-response-feed'].innerHTML,'');
 ctx.renderHuntEngine({hunt_hypotheses:[{hypothesis:'old'}]});ctx.renderHuntEngine({hunt_hypotheses:'bad'});
 assert.equal(nodes['ts-hunt-feed'].innerHTML,'');
});
