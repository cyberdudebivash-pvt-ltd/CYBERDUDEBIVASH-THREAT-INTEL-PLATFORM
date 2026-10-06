const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../js/homepage-dashboard-engine.js'), 'utf8');
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
