const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function harness(){
 const s=fs.readFileSync(require('node:path').join(__dirname,'../js/homepage-dashboard-engine.js'),'utf8');
 const nodes={};for(const id of ['ai-summary-grid','ai-top-threats','ai-response-queue','ai-correlate-summary']){
  let html='',text='';nodes[id]={get innerHTML(){return html},set innerHTML(v){html=v;text=''},get textContent(){return text},set textContent(v){text=v;html=''}};
 }
 const ctx={document:{getElementById:id=>nodes[id]},window:{},console:{warn:(...a)=>{throw Error(String(a))}}};
 const helper=s.slice(s.indexOf('function tipText('),s.indexOf('function renderIncidentEngine('));
 vm.runInNewContext(helper+s.slice(s.indexOf('function aiMetric('),s.indexOf('// ── ORCHESTRATOR',s.indexOf('function aiMetric('))),ctx);
 return {ctx,nodes};
}
test('AI fields remain text across threats, responses and correlation',()=>{
 const {ctx,nodes}=harness(),x='<img src=x onerror="alert(1)">';
 ctx.renderAIAnalysis({summary:{total_analyzed:x,critical_count:x,avg_risk_score:x},top_threats:[{title:x,actor:x,priority:x,risk_score:x,ttps:[x]}]},
 {response_queue:[{incident_title:x,playbook:x,priority:x,sla_hours:x}]},
 {summary:{threat_clusters:x},threat_clusters:[{actor:x,incident_count:x,avg_risk:x,ttps:[x]}]});
 for(const id of ['ai-top-threats','ai-response-queue','ai-correlate-summary']){
  assert.ok(!nodes[id].innerHTML.includes('<img'),id);assert.ok(nodes[id].innerHTML.includes('&lt;'),id);
 }
 assert.ok(nodes['ai-summary-grid'].innerHTML.includes('Assessment pending'));
});
test('invalid metrics never become fabricated zero while real zeros survive',()=>{
 const {ctx}=harness();for(const v of [null,undefined,'',true,{},'bad',-1,Infinity])assert.equal(ctx.aiMetric(v),'Assessment pending');
 assert.equal(ctx.aiMetric(0),'0');assert.equal(ctx.aiMetric('0'),'0');assert.equal(ctx.aiMetric(0,1),'0.0');
 assert.equal(ctx.aiMetric('7.3',1),'7.3');assert.equal(ctx.aiMetric(1.5),'Assessment pending');
});
test('malformed nested arrays and mixed records cannot abort AI rendering',()=>{
 const {ctx,nodes}=harness();
 ctx.renderAIAnalysis({summary:{avg_risk_score:'bad'},top_threats:[null,5,{}, {title:42,ttps:{}}]},
 {response_queue:[null,{}, {playbook:42}]},{summary:{},threat_clusters:[null,{}, {ttps:'bad'}]});
 assert.ok(nodes['ai-top-threats'].innerHTML.includes('42'));
 ctx.renderAIAnalysis({top_threats:{}},{response_queue:'bad'},{summary:{},threat_clusters:'bad'});
 assert.ok(!nodes['ai-top-threats'].innerHTML.includes('42'));
});
test('bounded AI rows and partial refreshes remove stale evidence',()=>{
 const {ctx,nodes}=harness();ctx.renderAIAnalysis({top_threats:Array.from({length:10000},()=>({title:'old'}))},null,null);
 assert.equal((nodes['ai-top-threats'].innerHTML.match(/display:flex;align-items:flex-start/g)||[]).length,8);
 ctx.renderAIAnalysis(null,null,null);assert.equal(nodes['ai-top-threats'].innerHTML,'');assert.equal(nodes['ai-top-threats'].textContent,'Assessment pending');
});
