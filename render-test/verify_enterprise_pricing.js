#!/usr/bin/env node
/**
 * SENTINEL APEX — Enterprise Pricing Playwright Verification (PR-6)
 * ====================================================================
 * Real-browser (headless Chromium) verification of enterprise-pricing.html,
 * mirroring render-test/verify_enterprise_homepage.js (PR-5). Adds two
 * checks specific to this page: the feature-comparison table scrolls
 * rather than overflows on mobile, and the 7-column customer-journey
 * grid collapses correctly at both responsive breakpoints.
 *
 * Self-contained: starts a local static file server rooted at the repo
 * root so root-relative hrefs resolve exactly as they do in production.
 *
 * Usage:
 *   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NODE_PATH="$(npm root -g)" \
 *     node render-test/verify_enterprise_pricing.js
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
const PORT = 8946;
const PAGE_URL = `http://127.0.0.1:${PORT}/enterprise-pricing.html`;

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.json': 'application/json', '.txt': 'text/plain', '.ico': 'image/x-icon',
};

const results = [];
function record(name, pass, detail) {
  results.push({ name, pass, detail });
  const tag = pass ? 'PASS' : 'FAIL';
  console.log(`[${tag}] ${name}${detail ? ' — ' + detail : ''}`);
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
  if (!m) return null;
  return m[1].split(',').slice(0, 3).map((v) => parseFloat(v.trim()));
}
function contrastRatio(fg, bg) {
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
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
    let noSkips = true, maxSeen = 0;
    for (const level of headingLevels) {
      if (level > maxSeen + 1) { noSkips = false; break; }
      maxSeen = Math.max(maxSeen, level);
    }
    record('No skipped heading levels in rendered DOM', noSkips, headingLevels.join(','));

    await page1.keyboard.press('Tab');
    const firstFocusedClass = await page1.evaluate(() => document.activeElement && document.activeElement.className);
    record('Skip link is the first keyboard Tab stop', firstFocusedClass === 'sapx-skip-link', `activeElement.class="${firstFocusedClass}"`);

    // Comparison table has real rows and is inside a horizontal-scroll wrapper.
    const tableInfo = await page1.evaluate(() => {
      const table = document.querySelector('.pr6-compare-table');
      const wrapper = document.querySelector('.pr6-compare-scroll');
      return {
        rowCount: table ? table.querySelectorAll('tbody tr').length : 0,
        wrapperOverflowX: wrapper ? getComputedStyle(wrapper).overflowX : null,
      };
    });
    record('Comparison table has real rows', tableInfo.rowCount >= 5, `rows=${tableInfo.rowCount}`);
    record('Comparison table wrapper allows horizontal scroll (not clipped)', tableInfo.wrapperOverflowX === 'auto', `overflow-x=${tableInfo.wrapperOverflowX}`);
    await ctx1.close();

    for (const [label, width, height] of [['mobile 375px', 375, 812], ['tablet 768px', 768, 1024], ['desktop 1440px', 1440, 900]]) {
      const ctx = await browser.newContext({ viewport: { width, height } });
      const page = await ctx.newPage();
      await page.goto(PAGE_URL, { waitUntil: 'networkidle' });
      const { scrollWidth, innerWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      }));
      record(`No horizontal overflow at ${label}`, scrollWidth <= innerWidth + 1, `scrollWidth=${scrollWidth} innerWidth=${innerWidth}`);

      const journeyCols = await page.evaluate(() => {
        const grid = document.querySelector('.pr6-journey-grid');
        return grid ? getComputedStyle(grid).gridTemplateColumns.split(' ').length : null;
      });
      const expectedCols = width <= 560 ? 1 : width <= 900 ? 2 : 7;
      record(`Customer journey grid has ${expectedCols} column(s) at ${label}`, journeyCols === expectedCols, `actual=${journeyCols}`);
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
        const el = document.querySelector('.sapx-pricing-card-featured .sapx-btn-primary');
        const cs = getComputedStyle(el);
        return { color: cs.color, bg: cs.backgroundColor };
      });
      const ratio = contrastRatio(parseRgb(color), parseRgb(bg));
      record(`Featured plan's primary CTA contrast >= 4.5:1 in ${scheme} theme`, ratio >= 4.5, `${ratio.toFixed(2)}:1 (color=${color}, bg=${bg})`);
      await ctx.close();
    }

    const ctxShot = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const pageShot = await ctxShot.newPage();
    await pageShot.goto(PAGE_URL, { waitUntil: 'networkidle' });
    const shotPath = path.join(process.env.PR6_SCREENSHOT_DIR || '/tmp', 'enterprise-pricing-desktop.png');
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
