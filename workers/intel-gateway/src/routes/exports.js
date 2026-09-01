// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Tier-Gated Multi-Format SIEM/SOAR Exports
// =============================================================================
//   GET /api/v1/export/suricata.rules  -- Suricata IDS/IPS rules
//   GET /api/v1/export/snort.rules     -- Snort IDS rules
//   GET /api/v1/export/yara.yar        -- YARA malware detection rules
//   GET /api/v1/export/splunk.csv      -- Splunk Enterprise Security lookup table
//   GET /api/v1/export/taxii.json      -- STIX 2.1 bundle
//
// REUSE (Principle 4 -- searched before building):
//  - Suricata/YARA rule CONTENT is not regenerated here. item.suricata_rule /
//    item.yara_rule are the canonical per-item fields already written by
//    detection_bundle_injector.py (see detection-registry.js's header) and
//    already consumed the identical way by enterprise-endpoints.js's
//    handleYaraBulk()/handleSigmaBulk(). This file follows that exact
//    established pattern rather than a third reimplementation.
//  - STIX indicator shape reuses index.js's buildStixPattern(), passed in
//    as a parameter (see below) so this bundle matches /taxii/*'s own
//    inline bundle rather than drifting from it.
//  - Splunk CSV's OWASP CSV-injection guard mirrors enterprise-endpoints.js's
//    handleSiemSentinel() guard byte-for-byte (same regex, same behavior);
//    not cross-imported because it is a 1-line closure local to that
//    function, not a module export -- duplicating a well-known one-line
//    security check is lower risk than restructuring an unrelated,
//    already-hardened production file for it.
//  - Snort has no existing generator anywhere in this codebase --
//    detection-registry.js's own header documents exactly four pre-existing
//    rule generators, none of them Snort. New logic here is justified by
//    that confirmed gap, derived from the same normalized indicators the
//    Suricata path uses.
//
// WHY A NEW FILE INSTEAD OF EXTENDING enterprise-endpoints.js's
// /api/sigma|yara/bulk OR /api/siem/*: those routes hard-deny FREE tier
// (403 tier_insufficient). Task brief explicitly wants a teaser/PLG model
// instead (FREE = top 25 samples + upgrade banner, PRO/ENTERPRISE = full
// set) -- a genuinely different, additive product surface, not a
// duplicate of the existing hard-gate behavior.
//
// CIRCULAR IMPORT NOTE: index.js imports routeExports from this file, so
// this file must NOT statically import anything from index.js (mirrors
// enterprise-endpoints.js's routeEnterpriseEndpoint()'s own documented
// reason for taking resolveEntitlement as a parameter instead). All values
// index.js already computed (tier, items, buildStixPattern, resolveEntitlement)
// are passed in as parameters instead.
// =============================================================================

import { getLiveIndicators } from '../ingestion/cron_worker.js';

export const EXPORTS_VERSION = '1.0.0';

// Matches index.js's own PREVIEW_LIMIT (= 25, the platform-wide FREE
// preview size used by /api/preview) -- redeclared locally rather than
// imported to avoid the circular-import problem documented above for a
// single stable constant.
const FREE_SAMPLE_LIMIT = 25;
const UPGRADE_URL = 'https://intel.cyberdudebivash.com/upgrade.html?plan=pro';
const STIX_CT = 'application/stix+json;version=2.1';

// Reserved SID blocks, deliberately disjoint from the CI-generated Suricata
// rules' observed 915xxxx range (data/intelligence/detection_rules/suricata/
// *.rules, detection_bundle_injector.py's output) so live-ingested-indicator
// rules synthesized here can never collide with a CI-assigned SID.
const SURICATA_LIVE_SID_BASE = 9500000; // 9500000-9589999
const SNORT_SID_BASE         = 9600000; // 9600000-9689999
const SID_SPREAD             = 90000;

function isPaidTier(tier) {
  return tier === 'PRO' || tier === 'ENTERPRISE' || tier === 'MSSP';
}

/** Deterministic, collision-avoiding SID within [base, base+SID_SPREAD). */
function stableSid(key, base) {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return base + (h % SID_SPREAD);
}

// OWASP CSV Injection guard -- mirrors enterprise-endpoints.js's
// handleSiemSentinel() guard exactly (see file header note above).
function csvGuard(s) {
  return /^[=+\-@\t\r]/.test(s) ? "'" + s : s;
}
function csvCell(v) {
  return `"${csvGuard(String(v == null ? '' : v)).replace(/"/g, "'")}"`;
}

/** Network-shaped live indicators only (ip/url) -- cve entries (KEV) have no IDS-rule representation. */
function networkIndicators(liveIndicators) {
  return (liveIndicators || []).filter(i => i.type === 'ip' || i.type === 'url');
}

// -----------------------------------------------------------------------------
// SURICATA
// -----------------------------------------------------------------------------

function itemSuricataRules(items) {
  return (items || [])
    .map(i => i.suricata_rule || (i.detection_rules && i.detection_rules.suricata) || '')
    .filter(Boolean);
}

function liveSuricataRules(liveIndicators) {
  const nowIso = new Date().toISOString();
  return networkIndicators(liveIndicators).map(ind => {
    const sid = stableSid(`suricata:${ind.type}:${ind.indicator}`, SURICATA_LIVE_SID_BASE);
    if (ind.type === 'ip') {
      return `alert ip any any -> ${ind.indicator} any (msg:"CDB SENTINEL APEX - Live Threat Intel IP (${ind.source}): ${ind.indicator}"; sid:${sid}; rev:1; classtype:trojan-activity; metadata:created_at ${nowIso.slice(0, 10)}, risk_score ${ind.risk_score || 0}, source ${ind.source};)`;
    }
    const host = (ind.meta && ind.meta.host) || ind.indicator;
    return `alert dns any any -> any any (msg:"CDB SENTINEL APEX - Live Threat Intel Domain (${ind.source}): ${host}"; dns.query; content:"${host}"; nocase; sid:${sid}; rev:1; classtype:trojan-activity; metadata:created_at ${nowIso.slice(0, 10)}, risk_score ${ind.risk_score || 0}, source ${ind.source};)`;
  });
}

function buildSuricataExport(items, liveIndicators, tier) {
  const allRules = [...itemSuricataRules(items), ...liveSuricataRules(liveIndicators)];
  const paid = isPaidTier(tier);
  const rules = paid ? allRules : allRules.slice(0, FREE_SAMPLE_LIMIT);
  const header = [
    '# CYBERDUDEBIVASH(R) SENTINEL APEX -- Suricata Threat Intel Rules',
    `# Generated: ${new Date().toISOString()}`,
    `# Rules: ${rules.length}${paid ? '' : ` (FREE sample of ${allRules.length} total)`}`,
    paid ? '# License: PRO/ENTERPRISE -- full feed' : `# FREE tier sample -- upgrade for the complete, continuously-updated rule set: ${UPGRADE_URL}`,
    '',
  ].join('\n');
  return { body: header + rules.join('\n') + '\n', count: rules.length, total: allRules.length };
}

// -----------------------------------------------------------------------------
// SNORT (new -- no existing generator; classic Snort 2.9+/3 syntax, kept to
// the IP + HTTP-header-content subset that is valid across Snort versions
// without relying on a specific DNS preprocessor configuration)
// -----------------------------------------------------------------------------

function liveSnortRules(liveIndicators) {
  return networkIndicators(liveIndicators).map(ind => {
    const sid = stableSid(`snort:${ind.type}:${ind.indicator}`, SNORT_SID_BASE);
    if (ind.type === 'ip') {
      return `alert ip any any -> ${ind.indicator} any (msg:"CDB SENTINEL APEX - Threat Intel IP (${ind.source}): ${ind.indicator}"; sid:${sid}; rev:1; classtype:trojan-activity; priority:2;)`;
    }
    const host = (ind.meta && ind.meta.host) || ind.indicator;
    return `alert tcp any any -> any $HTTP_PORTS (msg:"CDB SENTINEL APEX - Threat Intel Domain (${ind.source}): ${host}"; content:"${host}"; http_header; nocase; sid:${sid}; rev:1; classtype:trojan-activity;)`;
  });
}

function buildSnortExport(liveIndicators, tier) {
  const allRules = liveSnortRules(liveIndicators);
  const paid = isPaidTier(tier);
  const rules = paid ? allRules : allRules.slice(0, FREE_SAMPLE_LIMIT);
  const header = [
    '# CYBERDUDEBIVASH(R) SENTINEL APEX -- Snort Threat Intel Rules',
    `# Generated: ${new Date().toISOString()}`,
    `# Rules: ${rules.length}${paid ? '' : ` (FREE sample of ${allRules.length} total)`}`,
    paid ? '# License: PRO/ENTERPRISE -- full feed' : `# FREE tier sample -- upgrade for the complete, continuously-updated rule set: ${UPGRADE_URL}`,
    '',
  ].join('\n');
  return { body: header + rules.join('\n') + '\n', count: rules.length, total: allRules.length };
}

// -----------------------------------------------------------------------------
// YARA -- reuses item.yara_rule exactly like handleYaraBulk()
// -----------------------------------------------------------------------------

function buildYaraExport(items, tier) {
  const allRules = (items || [])
    .map(i => i.yara_rule || (i.detection_rules && i.detection_rules.yara) || '')
    .filter(Boolean);
  const paid = isPaidTier(tier);
  const rules = paid ? allRules : allRules.slice(0, FREE_SAMPLE_LIMIT);
  const header = [
    '// CYBERDUDEBIVASH(R) SENTINEL APEX -- YARA Intelligence Rules',
    `// Generated: ${new Date().toISOString()}`,
    `// Rules: ${rules.length}${paid ? '' : ` (FREE sample of ${allRules.length} total)`}`,
    paid ? '// License: PRO/ENTERPRISE -- full feed' : `// FREE tier sample -- upgrade for the complete rule set: ${UPGRADE_URL}`,
    '',
  ].join('\n') + '\n';
  return { body: header + rules.join('\n\n'), count: rules.length, total: allRules.length };
}

// -----------------------------------------------------------------------------
// SPLUNK CSV -- flat lookup table merging per-item advisories + live
// indicators. Kept strictly valid CSV (no comment lines, which Splunk's
// lookup parser does not support) -- FREE-tier notice travels in response
// headers instead, same convention already used by handleSiemSentinel/etc.
// -----------------------------------------------------------------------------

function buildSplunkExport(items, liveIndicators, tier) {
  const header = 'indicator,type,severity,risk_score,source,confidence,first_seen,last_seen,tags,cve_ids';
  const itemRows = (items || []).map(i => [
    i.id || i.stix_id || '', 'advisory', i.severity || 'MEDIUM', i.risk_score || i.apex_score?.apex_enterprise_score || 0,
    i.source || 'sentinel-apex', '', i.published_at || i.published || '', i.published_at || i.published || '',
    (i.tags || []).slice(0, 5).join('|'), (i.cve_ids || []).slice(0, 5).join('|'),
  ]);
  const liveRows = (liveIndicators || []).map(ind => [
    ind.indicator, ind.type, ind.risk_score >= 70 ? 'HIGH' : ind.risk_score >= 40 ? 'MEDIUM' : 'LOW', ind.risk_score || 0,
    ind.source, ind.source_confidence || '', ind.first_seen || '', ind.last_seen || '',
    (ind.tags || []).join('|'), '',
  ]);
  const allRows = [...itemRows, ...liveRows];
  const paid = isPaidTier(tier);
  const rows = paid ? allRows : allRows.slice(0, FREE_SAMPLE_LIMIT);
  const csv = [header, ...rows.map(r => r.map(csvCell).join(','))].join('\n') + '\n';
  return { body: csv, count: rows.length, total: allRows.length };
}

// -----------------------------------------------------------------------------
// TAXII / STIX 2.1 bundle -- reuses buildStixPatternFn (index.js's
// buildStixPattern, passed by the caller) for item-based objects so the
// pattern shape matches /taxii/*'s own bundle exactly.
// -----------------------------------------------------------------------------

function liveIndicatorToStixPattern(ind) {
  if (ind.type === 'ip') return `[ipv4-addr:value = '${ind.indicator}']`;
  return `[url:value = '${String(ind.indicator).replace(/['"\\]/g, '')}']`;
}

// STIX 2.1 requires every object id to match `{type}--{UUID}` (RFC 4122).
// item.stix_id/item.id and the live-indicator SID are internal identifiers,
// not UUIDs -- reusing them directly here previously produced bundles that
// failed schema validation on every sampled object. Mint a fresh, valid id
// instead; the internal id is kept as a custom_property for traceability.
function stixObjectId(type) {
  return `${type}--${crypto.randomUUID()}`;
}

function buildTaxiiExport(items, liveIndicators, tier, buildStixPatternFn) {
  const nowIso = new Date().toISOString();
  const itemObjects = (items || []).map(item => ({
    type: 'indicator', spec_version: '2.1',
    id: stixObjectId('indicator'),
    created: item.published || item.published_at || nowIso, modified: item.published || item.published_at || nowIso,
    name: item.title, indicator_types: ['malicious-activity'],
    pattern: typeof buildStixPatternFn === 'function' ? buildStixPatternFn(item) : `[threat-actor:name = '${(item.source || 'unknown').replace(/['"\\]/g, '')}']`,
    pattern_type: 'stix', valid_from: item.published || item.published_at || nowIso,
    labels: (item.tags || []).slice(0, 10),
    custom_properties: { x_sentinel_severity: item.severity, x_sentinel_risk_score: item.risk_score, x_sentinel_source: item.source, x_sentinel_item_id: item.stix_id || item.id },
  }));
  const liveObjects = (liveIndicators || []).map(ind => ({
    type: 'indicator', spec_version: '2.1',
    id: stixObjectId('indicator'),
    created: ind.first_seen || nowIso, modified: ind.last_seen || nowIso,
    name: `${ind.source} ${ind.type}: ${ind.indicator}`, indicator_types: ['malicious-activity'],
    pattern: liveIndicatorToStixPattern(ind), pattern_type: 'stix', valid_from: ind.first_seen || nowIso,
    labels: ind.tags || [],
    custom_properties: { x_sentinel_risk_score: ind.risk_score, x_sentinel_source: ind.source, x_sentinel_indicator: `${ind.type}:${ind.indicator}` },
  }));

  const allObjects = [...itemObjects, ...liveObjects];
  const paid = isPaidTier(tier);
  const objects = paid ? allObjects : allObjects.slice(0, FREE_SAMPLE_LIMIT);

  const bundle = {
    type: 'bundle', id: stixObjectId('bundle'), spec_version: '2.1', objects,
  };
  return {
    bundle: paid ? bundle : {
      ...bundle,
      x_sentinel_tier_notice: `FREE tier sample: ${objects.length} of ${allObjects.length} total objects. Upgrade for the complete, continuously-updated bundle.`,
      x_sentinel_upgrade_url: UPGRADE_URL,
    },
    count: objects.length, total: allObjects.length,
  };
}

// -----------------------------------------------------------------------------
// ROUTER -- called from index.js's handleRequest(), same call convention as
// enterprise-endpoints.js's routeEnterpriseEndpoint(): auth already resolved
// by the caller, items already loaded by the caller (loadFeedItems), and
// buildStixPatternFn/resolveEntitlement passed by reference to avoid the
// circular import documented at the top of this file.
//
// @param {string} pathname
// @param {Request} req
// @param {object} env
// @param {object} ctx
// @param {string} tier              - auth.tier, e.g. 'FREE'|'PRO'|'ENTERPRISE'|'MSSP'
// @param {Array}  items             - feed items from loadFeedItems(env)
// @param {string} req_id
// @param {object} auth
// @param {Function} [buildStixPatternFn] - index.js's buildStixPattern, optional
// @param {Function} [resolveEntitlement] - index.js's canonical entitlement decision fn, optional
// @returns {Promise<Response|null>}
// -----------------------------------------------------------------------------
export async function routeExports(pathname, req, env, ctx, tier, items, req_id, auth, buildStixPatternFn, resolveEntitlement) {
  if (!pathname.startsWith('/api/v1/export/')) return null;

  const resource = 'export_' + pathname.replace('/api/v1/export/', '').replace(/\.[a-z0-9]+$/i, '');
  const adHocAllowed = true; // export routes are open to FREE (sample) + PRO/ENTERPRISE (full) -- never a hard 403
  const allowed = resolveEntitlement ? resolveEntitlement(ctx, env, resource, auth, adHocAllowed).allowed : adHocAllowed;
  if (!allowed) {
    return new Response(JSON.stringify({
      error: 'export_disabled', message: 'This export is temporarily disabled.', endpoint: pathname, request_id: req_id,
    }), { status: 503, headers: { 'Content-Type': 'application/json', 'X-Request-ID': req_id } });
  }

  const liveIndicators = await getLiveIndicators(env, { limit: 1000 });
  const paid = isPaidTier(tier);
  const baseHeaders = {
    'X-Request-ID': req_id,
    'X-Sentinel-Tier': tier || 'FREE',
    'X-Sentinel-Version': EXPORTS_VERSION,
    'Cache-Control': paid ? 'private, max-age=300' : 'public, max-age=120',
  };

  if (pathname === '/api/v1/export/suricata.rules') {
    const { body, count, total } = buildSuricataExport(items, liveIndicators, tier);
    return new Response(body, {
      status: 200,
      headers: {
        ...baseHeaders, 'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': `attachment; filename="sentinel-apex-suricata-${Date.now()}.rules"`,
        'X-Sentinel-Rule-Count': String(count), 'X-Sentinel-Rule-Total': String(total),
      },
    });
  }

  if (pathname === '/api/v1/export/snort.rules') {
    const { body, count, total } = buildSnortExport(liveIndicators, tier);
    return new Response(body, {
      status: 200,
      headers: {
        ...baseHeaders, 'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': `attachment; filename="sentinel-apex-snort-${Date.now()}.rules"`,
        'X-Sentinel-Rule-Count': String(count), 'X-Sentinel-Rule-Total': String(total),
      },
    });
  }

  if (pathname === '/api/v1/export/yara.yar') {
    const { body, count, total } = buildYaraExport(items, tier);
    return new Response(body, {
      status: 200,
      headers: {
        ...baseHeaders, 'Content-Type': 'text/plain; charset=utf-8',
        'Content-Disposition': `attachment; filename="sentinel-apex-yara-${Date.now()}.yar"`,
        'X-Sentinel-Rule-Count': String(count), 'X-Sentinel-Rule-Total': String(total),
      },
    });
  }

  if (pathname === '/api/v1/export/splunk.csv') {
    const { body, count, total } = buildSplunkExport(items, liveIndicators, tier);
    return new Response(body, {
      status: 200,
      headers: {
        ...baseHeaders, 'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': `attachment; filename="sentinel-apex-splunk-${Date.now()}.csv"`,
        'X-Sentinel-Row-Count': String(count), 'X-Sentinel-Row-Total': String(total),
        ...(paid ? {} : { 'X-Sentinel-Upgrade-Url': UPGRADE_URL, 'X-Sentinel-Sample-Notice': `FREE sample: ${count} of ${total} rows -- upgrade for the full export` }),
      },
    });
  }

  if (pathname === '/api/v1/export/taxii.json') {
    const { bundle, count, total } = buildTaxiiExport(items, liveIndicators, tier, buildStixPatternFn);
    return new Response(JSON.stringify(bundle), {
      status: 200,
      headers: {
        ...baseHeaders, 'Content-Type': STIX_CT,
        'X-Sentinel-Object-Count': String(count), 'X-Sentinel-Object-Total': String(total),
      },
    });
  }

  return null;
}
