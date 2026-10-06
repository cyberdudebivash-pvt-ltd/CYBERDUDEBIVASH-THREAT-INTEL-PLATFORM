const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../js/homepage-dashboard-engine.js'), 'utf8');
const start = source.indexOf('        function _cdbRenderAIResult(');
const end = source.indexOf('\n        function ', start + 30);
assert.ok(start >= 0 && end > start);
const context = {window: {}, _cdbEsc: value => String(value), console};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
function render(ai) {
 const container = {};
 context._cdbRenderAIResult({risk_score: 9}, ai, [], container);
 return container.innerHTML;
}
test('missing AI measurements show pending without borrowed scores or fabricated confidence', () => {
 const html = render({});
 assert.match(html, /Assessment pending/);
 assert.match(html, /ASSESSMENT PENDING/);
 assert.doesNotMatch(html, /CONF 50%|cdb-agent-risk-fill/);
});
test('verified zero remains measured', () => {
 const html = render({ai_risk_score: 0, ai_confidence: 0});
 assert.match(html, /CONF 0%/);
 assert.match(html, />0\.0<\/div>/);
 assert.match(html, /width:0%/);
 assert.doesNotMatch(html, /Assessment pending/);
});
test('invalid measurements remain pending', () => {
 for (const value of [null, '', ' ', false, {}, 'invalid', Infinity, -1]) {
  const html = render({ai_risk_score: value, ai_confidence: value});
  assert.match(html, /Assessment pending/);
  assert.doesNotMatch(html, /cdb-agent-risk-fill|CONF NaN|CONF null/);
 }
 const html = render({ai_risk_score: 11, ai_confidence: 1.1});
 assert.doesNotMatch(html, /cdb-agent-risk-fill/);
});
test('valid bounds and numeric strings render measurements', () => {
 const html = render({ai_risk_score: '10', ai_confidence: '1'});
 assert.match(html, /CONF 100%/);
 assert.match(html, /width:100%/);
 assert.doesNotMatch(html, /Assessment pending/);
});
