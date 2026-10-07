const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = process.env.SENTINEL_UI_TEST_ROOT || path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'js/homepage-dashboard-engine.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'css/homepage-design-system.css'), 'utf8');
const start = source.indexOf('        function renderMapTicker(data)');
const end = source.indexOf('\n        // ── MISP Export', start);
assert.ok(start >= 0 && end > start);
function renderer(width = 7200) {
 const el = {innerHTML: '', textContent: '', scrollWidth: width,
  style: {animation: '', setProperty(k,v) {this[k]=v;}}};
 const context = {document: {getElementById: () => el},
  getSeverity: () => 'HIGH', extractCVEs: () => [],
  _cdbEsc: value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')};
 vm.createContext(context);
 vm.runInContext(source.slice(start, end), context);
 return {el, render: context.renderMapTicker};
}
test('complete titles are escaped and duplicate loop is hidden from assistive technology', () => {
 const {el,render} = renderer();
 const title = 'A complete advisory title beyond twenty-eight characters <script>alert(1)</script>';
 render([{title,risk_score:8}]);
 assert.ok(el.innerHTML.includes(title.replaceAll('<','&lt;').replaceAll('>','&gt;')));
 assert.ok(el.innerHTML.includes('aria-hidden="true"'));
 assert.ok(!el.innerHTML.includes('<script>'));
 assert.equal(el.style['--advisory-cycle'],'200s');
});
test('short tracks still have a slow minimum cycle', () => {
 const {el,render}=renderer(100);
 render([{title:'CVE advisory',risk_score:7}]);
 assert.equal(el.style['--advisory-cycle'],'160s');
});
test('missing feed stops movement instead of retaining prior headlines', () => {
 const {el,render}=renderer();
 render([]);
 assert.equal(el.textContent,'Waiting for the live feed…');
 assert.equal(el.style.animation,'none');
 render([{title:'Fresh advisory'}]);
 assert.equal(el.style.animation,'');
});

test('LATEST ADVISORIES is a direct full-width shell row after the header, not in the capped board', () => {
 const header = html.slice(html.indexOf('<header class="apex-header"'), html.indexOf('</header>'));
 assert.ok(!header.includes('id="cdb-map-attack-ticker"'));
 assert.match(html, /<\/header>\s*<!--[^>]+-->\s*<div id="cdb-map-attack-ticker"/);
 assert.equal((html.match(/id="cdb-map-attack-ticker"/g)||[]).length, 1);
 assert.match(css, /#cdb-map-attack-ticker\s*\{[^}]*grid-template-columns:\s*max-content minmax\(0, 1fr\) max-content/);
});
test('LIVE INTEL has a complete CSS-owned animation and accessible viewport/control', () => {
 assert.match(css, /#eicc-ticker-inner\s*\{[^}]*animation:\s*eicc-ticker-scroll var\(--eicc-cycle, 160s\) linear infinite/);
 assert.match(html, /class="eicc-ticker-viewport" tabindex="0"/);
 assert.match(html, /class="cdb-advisory-pause eicc-ticker-pause" aria-pressed="false"/);
 assert.match(css, /\.eicc-ticker-viewport\s*\{\s*overflow-x:\s*auto/);
 assert.match(css, /\.eicc-ticker-copy\[aria-hidden="true"\]/);
});

function eiccRenderer() {
 class Element {
  constructor(){this.children=[];this.attributes={};this.textContent='';this.scrollWidth=7200;this.style={animation:'',setProperty(k,v){this[k]=v;}};}
  get firstChild(){return this.children[0];}
  removeChild(e){this.children.splice(this.children.indexOf(e),1);}
  appendChild(e){this.children.push(e);return e;}
  setAttribute(k,v){this.attributes[k]=v;}
 }
 const ticker=new Element(), count=new Element();
 const context={lastTickerSignature:'',document:{getElementById:id=>id==='eicc-ticker-inner'?ticker:count},
  clear:e=>{while(e.firstChild)e.removeChild(e.firstChild);},
  node:(tag,text,style)=>{const e=new Element();if(text!=null)e.textContent=String(text);return e;},
  sevOf:i=>i.severity||'INFO',SEV_COLOR:{},
  SNAP:{tickerView:(state,limit)=>({mode:state.mode||'live',message:state.message||'',count:state.feed.items.length,items:state.feed.items.slice(0,limit)})}};
 const start=html.indexOf('            function buildTicker(state)');
 const end=html.indexOf('            // ── Metrics + Last Sync',start);
 assert.ok(start>=0&&end>start);
 vm.createContext(context);vm.runInContext(html.slice(start,end),context);
 return {ticker,count,render:context.buildTicker};
}
test('LIVE INTEL renders every feed item, complete titles and equal accessible copies',()=>{
 const {ticker,count,render}=eiccRenderer();
 const items=Array.from({length:54},(_,i)=>({severity:'LOW',title:'CVE-'+i+' '+ 'complete title '.repeat(10)}));
 render({feed:{items}});
 assert.equal(count.textContent,'54');assert.equal(ticker.children.length,2);
 assert.equal(ticker.children[0].children.length,54);
 assert.equal(ticker.children[1].attributes['aria-hidden'],'true');
 assert.equal(ticker.children[0].children[53].children[1].textContent,' '+items[53].title);
 assert.equal(ticker.style['--eicc-cycle'],'200s');
});
test('unchanged snapshot refresh does not reset a long ticker cycle',()=>{
 const {ticker,render}=eiccRenderer();const state={feed:{items:[{title:'Complete advisory'}]}};
 render(state);const first=ticker.children[0];render({...state});assert.equal(ticker.children[0],first);
 render({feed:{items:[{title:'Changed advisory'}]}});assert.notEqual(ticker.children[0],first);
});
test('LIVE INTEL stops on missing feed and resumes CSS motion on recovery; stale notices remain',()=>{
 const {ticker,render}=eiccRenderer();
 render({mode:'unavailable',message:'Unavailable',feed:{items:[]}});assert.equal(ticker.style.animation,'none');
 render({mode:'degraded',message:'LAST AUTHORITATIVE UPDATE',feed:{items:[{title:'<img src=x>'}]}});
 assert.equal(ticker.style.animation,'');assert.equal(ticker.children[0].children[0].textContent,'LAST AUTHORITATIVE UPDATE');
 assert.equal(ticker.children[0].children[1].children[1].textContent,' <img src=x>');
 assert.equal(ticker.children[1].children.length,ticker.children[0].children.length);
});
