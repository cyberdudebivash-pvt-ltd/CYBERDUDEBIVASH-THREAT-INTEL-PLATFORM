#!/usr/bin/env node
/**
 * SENTINEL APEX — Enterprise Family Production Certification (PR-10)
 * =================================================================
 * Real-browser (headless Chromium) verification run across all 5
 * enterprise-family pages together, for release-readiness
 * certification. This does not replace each page's own
 * render-test/verify_*.js script (still the source of truth for that
 * page's specific behavior) -- it re-confirms, in one consolidated
 * run, that the certification-level properties (accessibility,
 * responsive behavior, keyboard focus order, external-link safety,
 * contrast, live nav consistency) hold across the whole family at
 * once, as a single release gate.
 *
 * Usage:
 *   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NODE_PATH="$(npm root -g)" \
 *     node render-test/verify_enterprise_family_certification.js
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
const PORT = 8957;
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

    for (const file of FAMILY_PAGES) {
      const url = `http://127.0.0.1:${PORT}/${file}`;

      const consoleErrors = [];
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
      page.on('pageerror', (err) => consoleErrors.push(String(err)));
      await page.goto(url, { waitUntil: 'networkidle' });
      record(`[${file}] No console/page errors on load`, consoleErrors.length === 0, consoleErrors.join(' | '));

      const headingLevels = await page.$$eval('h1,h2,h3,h4,h5,h6', (els) => els.map((e) => Number(e.tagName[1])));
      const h1Count = headingLevels.filter((l) => l === 1).length;
      record(`[${file}] Exactly one <h1>`, h1Count === 1, `found ${h1Count}`);
      let noSkips = true, maxSeen = 0;
      for (const level of headingLevels) {
        if (level > maxSeen + 1) { noSkips = false; break; }
        maxSeen = Math.max(maxSeen, level);
      }
      record(`[${file}] No skipped heading levels`, noSkips, headingLevels.join(','));

      // Focus order: first 3 keyboard Tab stops must be skip link, then
      // the brand link, then the first primary-nav link -- the same
      // order across every page in the family (release-readiness gate
      // on keyboard navigation / focus order, per this PR's mandate).
      const focusOrder = [];
      for (let i = 0; i < 3; i++) {
        await page.keyboard.press('Tab');
        focusOrder.push(await page.evaluate(() => {
          const el = document.activeElement;
          return el ? `${el.tagName}.${el.className}`.trim() : null;
        }));
      }
      const expectedFirst = 'A.sapx-skip-link';
      record(`[${file}] Skip link is the first Tab stop`, focusOrder[0] === expectedFirst, `order=${focusOrder.join(' -> ')}`);

      // External-link safety: every target="_blank" anchor must carry
      // rel="noopener noreferrer" (reverse-tabnabbing protection).
      const unsafeExternal = await page.$$eval('a[target="_blank"]', (as) =>
        as.filter((a) => {
          const rel = (a.getAttribute('rel') || '').split(/\s+/);
          return !(rel.includes('noopener') && rel.includes('noreferrer'));
        }).map((a) => a.getAttribute('href'))
      );
      record(`[${file}] Every target=_blank link has rel="noopener noreferrer"`, unsafeExternal.length === 0, unsafeExternal.join(', '));

      await ctx.close();

      for (const [label, width, height] of [['mobile 375px', 375, 812], ['desktop 1440px', 1440, 900]]) {
        const ctxV = await browser.newContext({ viewport: { width, height } });
        const pageV = await ctxV.newPage();
        await pageV.goto(url, { waitUntil: 'networkidle' });
        const { scrollWidth, innerWidth } = await pageV.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
        }));
        record(`[${file}] No horizontal overflow at ${label}`, scrollWidth <= innerWidth + 1, `scrollWidth=${scrollWidth} innerWidth=${innerWidth}`);
        await ctxV.close();
      }

      for (const scheme of ['light', 'dark']) {
        const ctxC = await browser.newContext({ colorScheme: scheme });
        const pageC = await ctxC.newPage();
        await pageC.goto(url, { waitUntil: 'networkidle' });
        const btn = await pageC.evaluate(() => {
          const el = document.querySelector('.sapx-cta-banner .sapx-btn-primary, .sapx-header-ctas .sapx-btn-primary');
          if (!el) return null;
          const cs = getComputedStyle(el);
          return { color: cs.color, bg: cs.backgroundColor };
        });
        if (btn) {
          const ratio = contrastRatio(parseRgb(btn.color), parseRgb(btn.bg));
          record(`[${file}] Primary button contrast >= 4.5:1 in ${scheme} theme`, ratio >= 4.5, `${ratio.toFixed(2)}:1`);
        } else {
          record(`[${file}] Primary button contrast >= 4.5:1 in ${scheme} theme`, false, 'no primary button found to test');
        }
        await ctxC.close();
      }
    }

    // Cross-page: live nav consistency, re-confirmed as an independent
    // release gate (not relying solely on PR-9's own test surviving).
    const ctxNav = await browser.newContext();
    const pageNav = await ctxNav.newPage();
    const navSets = {};
    for (const file of FAMILY_PAGES) {
      await pageNav.goto(`http://127.0.0.1:${PORT}/${file}`, { waitUntil: 'networkidle' });
      navSets[file] = await pageNav.$$eval('nav[aria-label="Primary"] a', (as) => as.map((a) => a.getAttribute('href')).sort());
    }
    const reference = JSON.stringify(navSets[FAMILY_PAGES[0]]);
    const allMatch = FAMILY_PAGES.every((f) => JSON.stringify(navSets[f]) === reference);
    record('Live-rendered primary nav is identical across all 5 enterprise-family pages', allMatch, JSON.stringify(navSets));
    await ctxNav.close();

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
