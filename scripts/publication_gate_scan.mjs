#!/usr/bin/env node
/**
 * scripts/publication_gate_scan.mjs
 * CYBERDUDEBIVASH(R) SENTINEL APEX — P0 Publication Gate Production Scan
 *
 * Section 34's audit: for every item currently resolvable via the same feed
 * sources workers/intel-gateway/src/index.js's findItemBySlug() searches,
 * evaluate the SAME authoritative gate (publication-gate.js) the /reports/**
 * route now enforces, and report which are CUSTOMER_READY vs BLOCKED/REJECTED.
 *
 * Reuses the real evaluatePublicationGate() function unchanged (imported
 * directly, not re-implemented in Python or duplicated here) so this scan
 * can never disagree with what the Worker actually does.
 *
 * SCOPE (documented, not silent): covers the "latest"/"top10"/"apex" feed
 * windows — the same bounded, currently-resolvable population the
 * /reports/** gate itself can verify. This is NOT a scan of the full
 * 43,000+ historical report archive; older archived reports outside these
 * windows are a separate, larger undertaking (see the incident report's
 * Residual Risk section).
 *
 * Run: node scripts/publication_gate_scan.mjs [--base-url=https://intel.cyberdudebivash.com]
 */
import { evaluatePublicationGate } from '../workers/intel-gateway/src/publication-gate.js';

const args = process.argv.slice(2);
const baseUrlArg = args.find(a => a.startsWith('--base-url='));
const BASE_URL = baseUrlArg ? baseUrlArg.split('=')[1] : 'https://intel.cyberdudebivash.com';

// Public API endpoints that mirror the R2 keys findItemBySlug() searches
// (LATEST_PRO_JSON_KEY requires auth this scan doesn't have -- latest.json,
// top10.json, and apex.json are the publicly-fetchable subset).
const FEED_ENDPOINTS = [
  '/api/v1/intel/latest.json',
  '/api/v1/intel/top10.json',
  '/api/v1/intel/apex.json',
];

async function fetchJson(url) {
  try {
    const res = await fetch(url, { headers: { 'User-Agent': 'SentinelApex-PublicationGateScan/1.0' } });
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}

async function main() {
  const byId = new Map();
  for (const endpoint of FEED_ENDPOINTS) {
    const data = await fetchJson(BASE_URL + endpoint);
    if (!data) {
      console.error(`[scan] WARNING: could not fetch ${endpoint} — skipping`);
      continue;
    }
    const items = Array.isArray(data) ? data : (data.items || data.data || []);
    for (const item of items) {
      const id = (item.stix_id || item.id || '').replace(/\.html?$/, '');
      if (id && !byId.has(id)) byId.set(id, item);
    }
  }

  const total = byId.size;
  const results = [];
  let customerReady = 0, blocked = 0, rejected = 0;

  for (const [id, item] of byId) {
    const gate = evaluatePublicationGate(item);
    if (gate.customer_ready) customerReady++;
    else if (gate.publication_state === 'REJECTED') rejected++;
    else blocked++;

    results.push({
      report_id: id,
      publicly_accessible_url: `${BASE_URL}/reports/${id}.html`,
      publication_state: gate.publication_state,
      customer_ready: gate.customer_ready,
      P21: gate.P21_CERTIFICATION,
      P25: gate.P25_TRUST_TIER,
      P26: gate.P26_CERT_TIER,
      blocking_gates: gate.blocking_gates,
    });
  }

  const nonCertifiedPublic = results.filter(r => !r.customer_ready);

  const report = {
    schema_version: 'publication_gate_scan.1.0',
    scanned_at: new Date().toISOString(),
    scope_note: 'Covers only items resolvable via latest/top10/apex feed windows -- see script header.',
    total_scanned: total,
    customer_ready_reports: customerReady,
    blocked_reports: blocked,
    rejected_reports: rejected,
    non_certified_public_reports: nonCertifiedPublic.length,
    non_certified_report_ids: nonCertifiedPublic.map(r => r.report_id),
    quarantine_list: nonCertifiedPublic,
  };

  console.log(JSON.stringify(report, null, 2));
  console.error(`\n[scan] total=${total} customer_ready=${customerReady} blocked=${blocked} rejected=${rejected}`);
  console.error(`[scan] non_certified_public_reports = ${nonCertifiedPublic.length}`);

  process.exit(nonCertifiedPublic.length > 0 ? 1 : 0);
}

main();
