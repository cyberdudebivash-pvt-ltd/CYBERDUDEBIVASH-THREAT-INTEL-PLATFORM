const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(){
 const s=fs.readFileSync(require('node:path').join(__dirname,'../js/homepage-dashboard-engine.js'),'utf8');
 const children=[];const parent={querySelector:sel=>children.find(c=>'.'+c.className===sel),appendChild:n=>children.push(n)};
 const el={textContent:'',style:{},parentNode:parent};
 const ctx={document:{getElementById:()=>el,createElement:()=>({style:{},remove(){children.splice(children.indexOf(this),1)}})},console:{warn:e=>{throw e}}};
 vm.runInNewContext(s.slice(s.indexOf('function renderSovereignEngine('),s.indexOf('// ── BUG HUNTER ENGINE',s.indexOf('function renderSovereignEngine('))),ctx);
 return {el,children,render:ctx.renderSovereignEngine};
}
test('legacy compliance and tenant assertions cannot become governance evidence',()=>{
 const {el,children,render}=harness();render({compliance:{soc2_score:100,nist_score:100},tenants:{total:2260}});
 assert.equal(el.textContent,'Coverage pending');assert.equal(children.length,0);
});
test('valid feed coverage shows source counts and refresh replaces old evidence',()=>{
 const {el,children,render}=harness();const d={evidence_type:'feed_coverage',feed_coverage:{total_records:25,executive_summary_records:20,nvd_confirmed_records:8}};
 render(d);render(d);assert.equal(el.textContent,'25 records');assert.equal(children.length,1);
 assert.ok(children[0].textContent.includes('not a compliance assessment'));
 render({});assert.equal(children.length,0);assert.equal(el.textContent,'Coverage pending');
});
test('coverage rejects malformed or impossible values and preserves real zero',()=>{
 const {el,render}=harness();for(const v of ['<img>',-1,Infinity,26]){
 render({evidence_type:'feed_coverage',feed_coverage:{total_records:25,executive_summary_records:v,nvd_confirmed_records:1}});assert.equal(el.textContent,'Coverage pending');}
 render({evidence_type:'feed_coverage',feed_coverage:{total_records:0,executive_summary_records:0,nvd_confirmed_records:0}});assert.equal(el.textContent,'0 records');
});
