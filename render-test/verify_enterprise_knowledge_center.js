#!/usr/bin/env node
/**
 * SENTINEL APEX — Knowledge Center Playwright Verification (PR-9)
 * =================================================================
 * Real-browser (headless Chromium) verification of
 * enterprise-knowledge-center.html, mirroring
 * render-test/verify_developer_portal.js (PR-8). Adds checks specific
 * to this page: the Search Hub filter actually hides/shows cards and
 * updates its live count, all 5 real data tables render with rows,
 * and the unified nav renders identically to the other 4
 * enterprise-family pages when loaded live.
 *
 * Usage:
 *   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NODE_PATH="$(npm root -g)" \
 *     node render-test/verify_enterprise_knowledge_center.js
 *
 * Exit code 0 = all checks passed. Exit code 1 = at least one failed.
 */
'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { chromium } = require('playwright');

const { startStaticServer } = require('./lib/static-server');
const REPO_ROOT = path.resolve(__dirname, '..');
const PORT = 8953;
const PAGE_URL = `http://127.0.0.1:${PORT}/enterprise-knowledge-center.html`;
const FAMILY_PAGES = [
  'enterprise-homepage.html',
  'enterprise-pricing.html',
  'enterprise-compliance.html',
  'developer-portal.html',
  'enterprise-knowledge-center.html',
];

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.json': 'application/json', '.txt': 'text/plain', '.ico': 'image/x-icon',
  '.md': 'text/markdown', '.yaml': 'text/yaml', '.xml': 'application/xml',
};

const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`);
}

function relativeLuminance([r, g, b]) {
  const chan = [r, g, b].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2];
}
function parseRgb(str) {
  const m = str.match(/rgba?\(([^)]+)\)/);
  return m ? m[1].split(',').slice(0, 3).map((v) => parseFloat(v.trim())) : null;
}
function contrastRatio(fg, bg) {
  const l1 = relativeLuminance(fg), l2 = relativeLuminance(bg);
  const [lighter, darker] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

async function main() {
  const server = await startStaticServer(REPO_ROOT, PORT, MIME);
  let browser;
  try {
    browser = await chromium.launch();

    const consoleErrors = [];
    const ctxErr = await browser.newContext();
    const pageErr = await ctxErr.newPage();
    pageErr.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    pageErr.on('pageerror', (err) => consoleErrors.push(String(err)));
    await pageErr.goto(PAGE_URL, { waitUntil: 'networkidle' });
    record('No console/page errors on load', consoleErrors.length === 0, consoleErrors.join(' | '));
    await ctxErr.close();

    const ctx1 = await browser.newContext();
    const page1 = await ctx1.newPage();
    await page1.goto(PAGE_URL, { waitUntil: 'networkidle' });

    const headingLevels = await page1.$$eval('h1,h2,h3,h4,h5,h6', (els) => els.map((e) => Number(e.tagName[1])));
    const h1Count = headingLevels.filter((l) => l === 1).length;
    record('Exactly one <h1> in rendered DOM', h1Count === 1, `found ${h1Count}`);
    let noSkips = true;
    let maxSeen = 0;
    for (const level of headingLevels) {
      if (level > maxSeen + 1) { noSkips = false; break; }
      maxSeen = Math.max(maxSeen, level);
    }
    record('No skipped heading levels in rendered DOM', noSkips, headingLevels.join(','));

    await page1.keyboard.press('Tab');
    const firstFocusedClass = await page1.evaluate(() => document.activeElement && document.activeElement.className);
    record('Skip link is the first keyboard Tab stop', firstFocusedClass === 'sapx-skip-link', `activeElement.class="${firstFocusedClass}"`);

    const tableInfo = await page1.evaluate(() => {
      const tables = Array.from(document.querySelectorAll('.sapx-table'));
      return {
        count: tables.length,
        rowCounts: tables.map((t) => t.querySelectorAll('tbody tr').length),
        allWrapped: tables.every((t) => t.closest('.sapx-table-wrap') !== null),
      };
    });
    record('All 5 real data tables render with rows', tableInfo.count === 5 && tableInfo.rowCounts.every((n) => n > 0), `count=${tableInfo.count} rows=${tableInfo.rowCounts.join(',')}`);
    record('Every table is wrapped for horizontal-scroll safety', tableInfo.allWrapped, `allWrapped=${tableInfo.allWrapped}`);

    // Search Hub: type a real, distinctive query and confirm the DOM
    // actually filters -- not just that the input/JS exists statically.
    const initialCount = await page1.$eval('#pr9-search-count', (el) => el.textContent);
    await page1.fill('#pr9-search-input', 'changelog');
    await page1.waitForTimeout(50);
    const filteredState = await page1.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.pr9-search-card'));
      const visible = cards.filter((c) => c.style.display !== 'none');
      return {
        visibleCount: visible.length,
        totalCount: cards.length,
        countText: document.getElementById('pr9-search-count').textContent,
        allVisibleMatch: visible.every((c) => (c.getAttribute('data-text') + c.textContent).toLowerCase().includes('changelog')),
      };
    });
    record('Search filter narrows visible cards for a real query', filteredState.visibleCount > 0 && filteredState.visibleCount < filteredState.totalCount, `visible=${filteredState.visibleCount}/${filteredState.totalCount}`);
    record('Search filter only shows cards actually matching the query', filteredState.allVisibleMatch, `allVisibleMatch=${filteredState.allVisibleMatch}`);
    record('Search live-region count text updates on filter', filteredState.countText !== initialCount, `before="${initialCount}" after="${filteredState.countText}"`);

    await page1.fill('#pr9-search-input', 'zzz-no-such-resource-zzz');
    await page1.waitForTimeout(50);
    const emptyState = await page1.evaluate(() => ({
      emptyVisible: getComputedStyle(document.getElementById('pr9-search-empty')).display !== 'none',
    }));
    record('Empty-results message appears for a query matching nothing', emptyState.emptyVisible, `emptyVisible=${emptyState.emptyVisible}`);

    await page1.fill('#pr9-search-input', '');
    await page1.waitForTimeout(50);
    const resetState = await page1.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.pr9-search-card'));
      return cards.filter((c) => c.style.display !== 'none').length;
    });
    record('Clearing the search restores all cards', resetState === filteredState.totalCount, `visible=${resetState} total=${filteredState.totalCount}`);

    await ctx1.close();

    // Cross-page nav consistency, verified live in the browser (not
    // just statically) for every page in the family.
    const ctxNav = await browser.newContext();
    const pageNav = await ctxNav.newPage();
    const navSets = {};
    for (const file of FAMILY_PAGES) {
      await pageNav.goto(`http://127.0.0.1:${PORT}/${file}`, { waitUntil: 'networkidle' });
      navSets[file] = await pageNav.$$eval('nav[aria-label="Primary"] a', (as) => as.map((a) => a.getAttribute('href')).sort());
    }
    const reference = JSON.stringify(navSets[FAMILY_PAGES[0]]);
    const allMatch = FAMILY_PAGES.every((f) => JSON.stringify(navSets[f]) === reference);
    record('Live-rendered nav is identical across all 5 enterprise-family pages', allMatch, JSON.stringify(navSets));
    await ctxNav.close();

    for (const [label, width, height] of [['mobile 375px', 375, 812], ['tablet 768px', 768, 1024], ['desktop 1440px', 1440, 900]]) {
      const ctx = await browser.newContext({ viewport: { width, height } });
      const page = await ctx.newPage();
      await page.goto(PAGE_URL, { waitUntil: 'networkidle' });
      const { scrollWidth, innerWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      }));
      record(`No horizontal overflow at ${label}`, scrollWidth <= innerWidth + 1, `scrollWidth=${scrollWidth} innerWidth=${innerWidth}`);
      await ctx.close();
    }

    const ctxReduced = await browser.newContext();
    const pageReduced = await ctxReduced.newPage();
    await pageReduced.emulateMedia({ reducedMotion: 'reduce' });
    await pageReduced.goto(PAGE_URL, { waitUntil: 'networkidle' });
    const animNameReduced = await pageReduced.evaluate(() => {
      const el = document.querySelector('.sapx-status-dot-live');
      return el ? getComputedStyle(el).animationName : null;
    });
    record('Status-dot pulse animation is absent under prefers-reduced-motion: reduce', animNameReduced === 'none', `animation-name="${animNameReduced}"`);
    await ctxReduced.close();

    for (const scheme of ['light', 'dark']) {
      const ctx = await browser.newContext({ colorScheme: scheme });
      const page = await ctx.newPage();
      await page.goto(PAGE_URL, { waitUntil: 'networkidle' });
      const { color, bg } = await page.evaluate(() => {
        const el = document.querySelector('.sapx-cta-banner .sapx-btn-primary');
        const cs = getComputedStyle(el);
        return { color: cs.color, bg: cs.backgroundColor };
      });
      const ratio = contrastRatio(parseRgb(color), parseRgb(bg));
      record(`Final CTA primary button contrast >= 4.5:1 in ${scheme} theme`, ratio >= 4.5, `${ratio.toFixed(2)}:1 (color=${color}, bg=${bg})`);
      await ctx.close();
    }

    const ctxShot = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const pageShot = await ctxShot.newPage();
    await pageShot.goto(PAGE_URL, { waitUntil: 'networkidle' });
    const shotPath = path.join(process.env.PR9_SCREENSHOT_DIR || '/tmp', 'enterprise-knowledge-center-desktop.png');
    await pageShot.screenshot({ path: shotPath, fullPage: true });
    console.log(`[INFO] Full-page screenshot saved to ${shotPath}`);
    await ctxShot.close();

  } finally {
    if (browser) await browser.close();
    server.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log('\n' + '='.repeat(64));
  console.log(`SUMMARY: ${results.length - failed.length}/${results.length} checks passed`);
  console.log('='.repeat(64));
  if (failed.length) {
    process.exitCode = 1;
    console.log('FAILED CHECKS:');
    for (const f of failed) console.log(`  - ${f.name}: ${f.detail}`);
  }
}

main().catch((err) => {
  console.error('[FATAL]', err);
  process.exitCode = 1;
});
