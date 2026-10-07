/** Offline pre-deploy regression: shipped layout and real rendering functions.
 * No production requests, credentials, payments, telemetry fabrication or new
 * refresh intervals. Fixtures are explicitly test-only and all networking aborts.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const engine = fs.readFileSync(path.join(root, 'js/homepage-dashboard-engine.js'), 'utf8');
const feeds = fs.readFileSync(path.join(root, 'js/sentinel-live-feeds.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'css/homepage-design-system.css'), 'utf8');
function section(source, start, end) {
  const a = source.indexOf(start), b = source.indexOf(end, a);
  assert.ok(a >= 0 && b > a, `Missing shipped function ${start}`);
  return source.slice(a, b);
}
const shipped = [
  section(engine, '        function renderMapTicker(data)', '\n        // ── MISP Export'),
  section(html, '            var lastTickerSignature', '            // ── Metrics + Last Sync'),
  section(engine, 'function _cdbSocThreatContext(item)', 'function getTopThreats(data)'),
  section(engine, 'function renderTopThreats(data)', '        window.onerror ='),
  section(engine, '            function bugHunterScanView(data, nowMs)', '            // ── TIP+SOAR RENDERERS'),
  section(engine, '            function renderGenesisEngine(data)', '            // ── CORTEX RENDERER'),
  section(feeds, '  async function loadAPT()', '  // ── 8. EPSS'),
].join('\n');
const safeHtml = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
  .replace(/<link\b[^>]*>/gi, tag => tag.includes('css/homepage-design-system.css') ? `<style>${css}</style>` : '')
  .replace(/<iframe\b[^>]*>[\s\S]*?<\/iframe>/gi, '');
const fixture = Array.from({ length: 54 }, (_, i) => ({
  title: `CVE-2026-${10000+i} complete advisory ${i} with a long readable description beyond sixty characters <img src=x onerror=alert(1)>`,
  severity: 'HIGH', risk_score: 8, cve_ids: [`CVE-2026-${10000+i}`],
  actor: 'CDB-UNATTR-CVE', source: 'Test-only publisher',
  report_url: '/reports/test-only.html', timestamp: new Date().toISOString(), mitre_tactics: [],
}));
const bootstrap = `
const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const _cdbEsc = esc;
const el = id => document.getElementById(id);
const setText = (id, value) => { if (el(id)) el(id).textContent = value; };
const setUnavailable = setText;
const safeUrl = value => /^https?:\\/\\//i.test(String(value || '')) ? String(value) : '';
const fmtRelTime = () => 'Test timestamp';
const getSeverity = (_, item) => item.severity || 'HIGH';
const extractCVEs = title => String(title).match(/CVE-\\d{4}-\\d{4,}/g) || [];
const clear = target => target.replaceChildren();
const node = (tag, text, style) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (style) n.style.cssText = style; return n; };
const sevOf = item => item.severity || 'INFO';
const SEV_COLOR = {};
const SNAP = { tickerView: (state, limit) => ({ mode: state.mode || 'live', message: state.message || '', count: state.feed.items.length, items: state.feed.items.slice(0, limit) }) };
const getTopThreats = data => data.slice(0, 10);
const cdbBuildReportUrl = item => item.report_url || '';
window.CDB_NORMALIZE = { epss: () => ({percent: 0}) };
window.testAPT = {};
const apiFetch = async () => window.testAPT;
${shipped}
window.renderP0Fixture = items => { renderMapTicker(items); buildTicker({feed:{items}}); renderTopThreats(items.slice(0,3)); };
window.renderReconFixture = renderBugHunterEngine;
window.renderGenesisFixture = renderGenesisEngine;
window.renderAPTFixture = async data => { window.testAPT=data; await loadAPT(); };
`;
function luminance(rgb) {
  const values = rgb.match(/[\d.]+/g).slice(0,3).map(Number).map(n => n/255)
    .map(n => n <= .04045 ? n/12.92 : ((n+.055)/1.055)**2.4);
  return values[0]*.2126 + values[1]*.7152 + values[2]*.0722;
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  let cases = 0;
  try {
    const page = await browser.newPage({ viewport: {width:1366, height:900} });
    await page.route('**/*', route => route.abort());
    await page.setContent(safeHtml, { waitUntil: 'domcontentloaded' });
    await page.addScriptTag({ content: bootstrap });
    await page.evaluate(items => window.renderP0Fixture(items), fixture);
    await page.evaluate(()=>window.renderGenesisFixture({engines:{G11_GlobalAttackMap:{summary:{flows:[{source:'Test-only fabricated corridor',target:'Not observed'}]}}},generated_at:new Date().toISOString()}));
    for (const width of [1920,1366,1024,768,641,640,390,320]) {
      await page.setViewportSize({width,height:900});
      await page.mouse.move(0,0);
      const layout = await page.evaluate(() => {
        const rect = e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,right:r.right,bottom:r.bottom}; };
        const shell=document.querySelector('.apex-shell'), row=document.getElementById('cdb-map-attack-ticker');
        const shellStyle=getComputedStyle(shell), eicc=document.getElementById('eicc-ticker-strip');
        return { shellContent:shell.clientWidth-parseFloat(shellStyle.paddingLeft)-parseFloat(shellStyle.paddingRight),
          row:rect(row), label:rect(document.getElementById('cdb-advisory-label')),
          viewport:rect(row.querySelector('.cdb-advisory-viewport')), pause:rect(row.querySelector('button')),
          eicc:rect(eicc), eiccViewport:rect(eicc.querySelector('.eicc-ticker-viewport')),
          count:rect(eicc.querySelector('.eicc-ticker-count')), labelText:row.innerText,
          genesisGrid:rect(document.getElementById('genesis-grid')),
          mapTile:rect(document.querySelector('[data-engine-value="G11"]')),
          firstCopyCount:document.querySelectorAll('.eicc-ticker-copy:not([aria-hidden]) [data-ticker-item]').length,
          unsafe:document.querySelectorAll('#top-threats-section img,#top-threats-section script,#eicc-ticker-inner img').length,
          soc:document.getElementById('top-threats-section').innerText };
      });
      assert.ok(Math.abs(layout.row.width-layout.shellContent)<=1, `LATEST row cuts off at ${width}px: ${JSON.stringify(layout)}`);
      assert.ok(layout.viewport.width>50 && layout.eiccViewport.width>50, `Empty ticker viewport at ${width}`);
      for (const r of [layout.label,layout.pause,layout.viewport]) assert.ok(r.x>=layout.row.x-1 && r.right<=layout.row.right+1, `Advisory control clips at ${width}`);
      assert.ok(layout.count.right<=layout.eicc.right+1, `LIVE INTEL count clips at ${width}`);
      assert.ok(layout.mapTile.right<=layout.genesisGrid.right+1 && layout.genesisGrid.right<=width, `G11 tile clips at ${width}`);
      if(width<=640) assert.ok(layout.viewport.y>=layout.label.bottom && layout.eiccViewport.y>layout.eicc.y, `Mobile ticker needs its own row at ${width}`);
      assert.equal(layout.firstCopyCount,54); assert.equal(layout.unsafe,0);
      assert.ok(layout.soc.includes('SOURCE · Test-only publisher') && !layout.soc.includes('UNATTRIBUTED'));
      cases++;
    }
    await page.setViewportSize({width:1366,height:900});
    await page.mouse.move(0,0);
    const motion = () => page.evaluate(() => ['cdb-ticker-text','eicc-ticker-inner'].map(id => {
      const e=document.getElementById(id), s=getComputedStyle(e);
      return {name:s.animationName,duration:parseFloat(s.animationDuration),state:s.animationPlayState,transform:s.transform,width:e.scrollWidth};
    }));
    const before=await motion();
    await page.waitForTimeout(300); // bounded local animation test, no network
    const after=await motion();
    for(let i=0;i<2;i++) {
      assert.notEqual(after[i].name,'none'); assert.equal(after[i].state,'running');
      assert.notEqual(before[i].transform,after[i].transform,'Loaded ticker is stationary');
      assert.ok(after[i].duration>=160 && after[i].width/2/after[i].duration<=18.05,'Ticker exceeds readable pace');
    }
    for(const strip of ['#cdb-map-attack-ticker','#eicc-ticker-strip']) {
      const button=page.locator(`${strip} button`);
      await button.click(); assert.equal(await button.getAttribute('aria-pressed'),'true');
      assert.equal(await page.locator(`${strip} [id$="inner"],${strip} #cdb-ticker-text`).evaluate(e=>getComputedStyle(e).animationPlayState),'paused');
      await button.click(); assert.equal(await button.getAttribute('aria-pressed'),'false');
      await page.evaluate(()=>document.activeElement.blur()); await page.mouse.move(0,0);
    }
    cases++;
    assert.equal(await page.locator('[data-engine-value="G11"]').innerText(),'TELEMETRY REQUIRED');
    assert.ok(!(await page.locator('#genesis-attack-flows').innerText()).includes('Test-only fabricated corridor'));
    await page.emulateMedia({reducedMotion:'reduce'});
    const reduced=await page.evaluate(()=>({
      states:['cdb-ticker-text','eicc-ticker-inner'].map(id=>getComputedStyle(document.getElementById(id)).animationName),
      overflow:['.cdb-advisory-viewport','.eicc-ticker-viewport'].map(s=>getComputedStyle(document.querySelector(s)).overflowX),
      clones:[...document.querySelectorAll('.cdb-advisory-copy[aria-hidden],.eicc-ticker-copy[aria-hidden]')].map(e=>getComputedStyle(e).display)
    }));
    assert.deepEqual(reduced.states,['none','none']);assert.deepEqual(reduced.overflow,['auto','auto']);
    assert.ok(reduced.clones.every(s=>s==='none'));cases++;
    await page.evaluate(()=>window.renderReconFixture({status:'COMPLETED',timestamp:'2026-08-25T18:02:45.017Z',domain:'test-only.example',metrics:{api_endpoints:0,critical_findings:0},findings_summary:[]}));
    assert.equal(await page.locator('#bh-api-count').innerText(),'Re-scan required');
    assert.equal(await page.locator('#bh-critical-count').innerText(),'Re-scan required');
    assert.ok((await page.locator('#bh-health-badge').innerText()).includes('HISTORICAL'));cases++;
    await page.evaluate(()=>window.renderReconFixture({status:'COMPLETED',timestamp:new Date().toISOString(),metrics:{api_endpoints:0,critical_findings:2},findings_summary:[]}));
    assert.equal(await page.locator('#bh-api-count').innerText(),'No observations in scan');
    assert.equal(await page.locator('#bh-critical-count').innerText(),'2');cases++;
    await page.evaluate(()=>window.renderAPTFixture({apt_advisories:6,sources_reporting:3,total_ttps:0,top_actors:[],recent_activity:[{title:'APT source report <img src=x>',source:'Test-only source',source_url:'javascript:alert(1)',published:'2026-10-07T04:00:00Z'}]}));
    assert.equal(await page.locator('#cdb-apt-count').innerText(),'6');
    assert.equal(await page.locator('#cdb-apt-sectors').innerText(),'3');
    assert.ok((await page.locator('#cdb-apt-list').innerText()).includes('named attribution is not provided'));
    assert.equal(await page.locator('#cdb-apt-list img,#cdb-apt-list a').count(),0);cases++;
    await page.evaluate(()=>window.renderAPTFixture({apt_advisories:6,sources_reporting:3,top_actors:[null],recent_activity:[null],publication:{fresh:false,status:'stale'}}));
    assert.equal(await page.locator('#cdb-apt-status').innerText(),'SAVED FEED · NOT LIVE');cases++;
    const footer=await page.evaluate(()=>[...document.querySelectorAll('.cdb-customer-footer *, .cdb-payment-footer *')]
      .filter(e=>[...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())&&e.getBoundingClientRect().width>0)
      .map(e=>({text:e.innerText,font:parseFloat(getComputedStyle(e).fontSize),color:getComputedStyle(e).color})));
    assert.ok(footer.length>20,'Footer content missing');
    for(const e of footer) {
      assert.ok(e.font>=12,`Unreadable footer microtype ${e.font}: ${e.text}`);
      if(e.color!=='rgb(2, 10, 20)') assert.ok((luminance(e.color)+.05)/(luminance('rgb(8,12,20)')+.05)>=4.5,`Low footer contrast: ${e.text}`);
    }
    assert.ok(footer.some(e=>e.text.includes('bivash@cyberdudebivash.com')),'Official support contact lost');cases++;
    console.log(`PASS: ${cases} offline dashboard browser cases; 8 viewports, complete slow tickers, SOC/APT evidence, recon provenance and footer readability.`);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
