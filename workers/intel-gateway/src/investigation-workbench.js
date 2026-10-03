// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Read-Only Analyst Investigation Workbench
// =============================================================================
// Customer-release goals:
//   * compose existing P30/P31/P32 engines into one analyst-ready read surface;
//   * expose evidence, MITRE context, correlation, timeline and playbook together;
//   * provide a public, clearly-labelled synthetic replay for product evaluation;
//   * remain read-only: no incident mutation, no IOC execution, no customer data;
//   * preserve existing entitlement boundaries and Cloudflare cost discipline.
//
// Reuse-before-build:
//   - timeline: P30 canonical timeline computation
//   - graph/correlation/copilot/playbook: P31 canonical computations
//   - per-claim evidence transparency: P32 canonical evidence computation
//   - authorization scopes: api-extensions.js
//   - paid graph entitlement: revenue-enforcement.js
//
// This module deliberately does NOT introduce a second graph engine, confidence
// model, report generator, RBAC store, or persistence layer.
// =============================================================================

import { computeP30Timeline } from './p30-handlers.js';
import {
  computeP31CampaignContext,
  computeP31Copilot,
  computeP31EntityNormalization,
  computeP31Graph,
  computeP31Playbook,
} from './p31-handlers.js';
import { computeP32EvidenceClaims } from './p32-handlers.js';
import { enforceTierGate } from './revenue-enforcement.js';
import { enforceScopeMiddleware } from './api-extensions.js';
import { extractDetectionArtifacts } from './detection-registry.js';

export const INVESTIGATION_WORKBENCH_VERSION = '1.1.0';
const PAID_INVESTIGATION_TIERS = new Set(['PRO', 'ENTERPRISE', 'MSSP']);

const MAX_RELATED_ITEMS = 6;
const MAX_GRAPH_NODES = 120;
const MAX_GRAPH_EDGES = 180;

function jsonResp(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'X-Sentinel-Investigation-Version': INVESTIGATION_WORKBENCH_VERSION,
      ...headers,
    },
  });
}

function methodNotAllowed() {
  return jsonResp(
    { error: 'method_not_allowed', message: 'This investigation surface is read-only. Use GET.' },
    405,
    { Allow: 'GET' },
  );
}

function normalizeTier(tier) {
  return String(tier || 'FREE').toUpperCase();
}

function stringOrNull(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function finiteNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function safeArray(value, limit = 50) {
  return Array.isArray(value) ? value.slice(0, limit) : [];
}

function iocCountOf(item) {
  const declared = Number.parseInt(item?.ioc_count || 0, 10);
  if (Number.isFinite(declared) && declared > 0) return declared;
  const counts = item?.ioc_counts || item?.iocs_by_type;
  if (!counts || typeof counts !== 'object' || Array.isArray(counts)) return 0;
  return Object.values(counts).reduce((sum, value) => {
    const n = Number.parseInt(value || 0, 10);
    return sum + (Number.isFinite(n) && n > 0 ? n : 0);
  }, 0);
}

function stableGraphItem(item, fallbackIndex = 0) {
  if (stringOrNull(item?.id)) return item;
  const stable = stringOrNull(item?.stix_id) || stringOrNull(item?.slug) || stringOrNull(item?.cve_id);
  return stable ? { ...item, id: stable } : { ...item, id: `workbench-item-${fallbackIndex}` };
}

function safeReportPath(value) {
  const v = stringOrNull(value);
  if (!v || !v.startsWith('/reports/') || v.includes('..')) return null;
  return /^\/reports\/[A-Za-z0-9._\/-]+$/.test(v) ? v : null;
}

async function loadFeed(env) {
  if (!env?.INTEL_R2 || typeof env.INTEL_R2.get !== 'function') {
    throw new Error('intel_store_unavailable');
  }
  const object = await env.INTEL_R2.get('api/v1/intel/latest.json');
  if (!object) return [];
  const parsed = await object.json();
  if (Array.isArray(parsed)) return parsed;
  if (Array.isArray(parsed?.items)) return parsed.items;
  if (Array.isArray(parsed?.data)) return parsed.data;
  return [];
}

function itemIdentity(item) {
  const direct = [item?.id, item?.stix_id, item?.slug, item?.cve_id]
    .map(stringOrNull).filter(Boolean);
  const cves = safeArray(item?.cve_ids || item?.cves, 20)
    .map(stringOrNull).filter(Boolean);
  return [...new Set([...direct, ...cves])];
}

function findItem(items, id) {
  const wanted = String(id || '').trim().toLowerCase();
  if (!wanted) return null;
  return items.find(item => itemIdentity(item).some(v => v.toLowerCase() === wanted)) || null;
}

function sanitizeItem(item) {
  const apex = item?.apex && typeof item.apex === 'object' ? item.apex : {};
  return {
    id: stringOrNull(item?.id) || stringOrNull(item?.stix_id),
    stix_id: stringOrNull(item?.stix_id),
    title: stringOrNull(item?.title) || 'Untitled intelligence item',
    description: stringOrNull(item?.description),
    severity: stringOrNull(item?.severity),
    risk_score: finiteNumber(item?.risk_score ?? item?.cvss_score),
    cvss_score: finiteNumber(item?.cvss_score ?? item?.risk_score),
    epss_score: finiteNumber(item?.epss_score),
    kev_present: Boolean(item?.kev_present || apex.kev_listed),
    source: stringOrNull(item?.source || item?.source_domain),
    source_url: stringOrNull(item?.source_url),
    published_at: stringOrNull(item?.published_at || item?.published || item?.timestamp),
    processed_at: stringOrNull(item?.processed_at || item?.processed_ts),
    threat_type: stringOrNull(item?.threat_type),
    threat_actor: stringOrNull(item?.actor_tag || item?.threat_actor),
    confidence: finiteNumber(item?.confidence),
    tlp: stringOrNull(item?.tlp || item?.tlp_marking),
    cve_ids: safeArray(item?.cve_ids || item?.cves, 20),
    ttps: safeArray(item?.ttps, 30),
    mitre_tactics: safeArray(item?.mitre_tactics, 20),
    ioc_count: iocCountOf(item),
  };
}

function detectionAvailability(item) {
  // Canonical source: detection-registry.js, which reads the live per-item
  // fields written by detection_bundle_injector.py and applies structural
  // validation before an artifact is considered customer-available.
  let artifacts = [];
  try { artifacts = extractDetectionArtifacts(item); } catch (_) { artifacts = []; }
  const formats = new Set(artifacts.map(a => a.artifact_type));
  return {
    sigma: formats.has('sigma'),
    yara: formats.has('yara'),
    kql: formats.has('kql'),
    spl: formats.has('spl'),
    suricata: formats.has('suricata'),
    artifact_count: artifacts.length,
    validation: 'canonical_detection_registry',
  };
}

function itemScopedOutputs(item) {
  const id = stringOrNull(item?.id) || stringOrNull(item?.stix_id);
  if (!id) return { detections: null, stix: null };
  const encoded = encodeURIComponent(id);
  return {
    detections: `/api/v1/detections?intel_id=${encoded}`,
    stix: `/api/stix?id=${encoded}`,
  };
}

function boundedGraph(graph) {
  const nodes = safeArray(graph?.nodes, MAX_GRAPH_NODES);
  const nodeIds = new Set(nodes.map(n => n.id));
  const edges = safeArray(graph?.edges, MAX_GRAPH_EDGES)
    .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
  return {
    nodes,
    edges,
    stats: {
      ...(graph?.stats || {}),
      returned_nodes: nodes.length,
      returned_edges: edges.length,
      truncated: (graph?.nodes?.length || 0) > nodes.length || (graph?.edges?.length || 0) > edges.length,
    },
  };
}

function itemLimitations(item, graph, claims) {
  const limitations = [];
  const apex = item?.apex && typeof item.apex === 'object' ? item.apex : {};
  if (!item?.source_url) limitations.push('Primary source URL is not present on this intelligence record.');
  if (!(item?.kev_present || apex.kev_listed)) limitations.push('No CISA KEV evidence is attached to this record.');
  if (!(Number(item?.epss_score) > 0)) limitations.push('No positive EPSS score is attached to this record.');
  if (!stringOrNull(item?.actor_tag || item?.threat_actor)) limitations.push('No threat-actor attribution is attached to this record.');
  if (!Array.isArray(item?.ttps) || item.ttps.length === 0) limitations.push('No MITRE ATT&CK technique mapping is attached to this record.');
  if (iocCountOf(item) === 0) limitations.push('No IOC inventory is attached to this record.');
  if (!claims?.length) limitations.push('No structured evidence claims are available for this record.');
  if (graph?.stats?.truncated) limitations.push('Graph response is bounded for edge-runtime safety; use the canonical P31 graph API for wider exploration.');
  limitations.push('This read-only view composes existing intelligence; it does not detonate binaries or execute indicators.');
  return limitations;
}

function relatedSummary(context) {
  return safeArray(context?.related, MAX_RELATED_ITEMS).map(item => ({
    id: stringOrNull(item?.id) || stringOrNull(item?.stix_id),
    title: stringOrNull(item?.title) || 'Untitled intelligence item',
    severity: stringOrNull(item?.severity),
    source: stringOrNull(item?.source || item?.source_domain),
    published_at: stringOrNull(item?.published_at || item?.published || item?.timestamp),
    shared_actor: stringOrNull(item?.actor_tag || item?.threat_actor),
    ttps: safeArray(item?.ttps, 12),
  }));
}

function buildInvestigation(item, allItems) {
  const campaign = computeP31CampaignContext(item, allItems);
  const relatedItems = safeArray(campaign?.related, MAX_RELATED_ITEMS)
    .filter(candidate => itemIdentity(candidate).length > 0);
  const graphItems = [item, ...relatedItems].map((candidate, index) => stableGraphItem(candidate, index));
  const graph = boundedGraph(computeP31Graph(graphItems));
  const copilot = computeP31Copilot(item);
  const evidenceClaims = computeP32EvidenceClaims(item);
  const entityContext = computeP31EntityNormalization(item);
  const timeline = computeP30Timeline(item);
  const playbook = computeP31Playbook(item);
  const sanitized = sanitizeItem(item);
  const reports = {
    html: safeReportPath(item?.report_url || item?.internal_report_url),
    pdf: safeReportPath(item?.pdf_url || item?.pdf_report_url),
  };

  return {
    schema_version: 'sentinel-apex.investigation.v1',
    workbench_version: INVESTIGATION_WORKBENCH_VERSION,
    generated_at: new Date().toISOString(),
    read_only: true,
    intelligence: sanitized,
    risk_explanation: {
      why_this_matters: safeArray(copilot?.whyParts, 12),
      what_changed: safeArray(copilot?.whatChanged, 12),
      investigate_first: safeArray(copilot?.whatFirst, 12),
      recommended_log_sources: safeArray(copilot?.logList, 12),
      next_actions: safeArray(copilot?.whatNext, 12),
    },
    evidence_claims: evidenceClaims,
    mitre: {
      techniques: safeArray(entityContext?.ttps, 30),
      tactics: safeArray(entityContext?.tactics, 20),
    },
    entities: {
      actor: entityContext?.actor || null,
      cves: safeArray(entityContext?.cves, 20),
      ioc_types: safeArray(entityContext?.iocTypes, 20),
    },
    correlation: {
      campaign_name: campaign?.campaignName || null,
      related_items: relatedSummary(campaign),
      graph,
    },
    evidence_timeline: timeline,
    investigation_playbook: playbook,
    detection_availability: detectionAvailability(item),
    customer_outputs: {
      report: reports,
      browser_print_to_pdf: true,
      item_scoped: itemScopedOutputs(item),
      global_feed_exports: [
        { format: 'STIX 2.1', path: '/api/v1/export/taxii.json' },
        { format: 'YARA', path: '/api/v1/export/yara.yar' },
        { format: 'Suricata', path: '/api/v1/export/suricata.rules' },
        { format: 'Snort', path: '/api/v1/export/snort.rules' },
        { format: 'Splunk CSV', path: '/api/v1/export/splunk.csv' },
      ],
      note: 'item_scoped links resolve this intelligence record; global_feed_exports are existing tier-gated feed outputs and are not represented as item-specific.',
    },
    limitations: itemLimitations(item, graph, evidenceClaims),
  };
}

const REPLAY_SCENARIOS = Object.freeze({
  ransomware: {
    name: 'Synthetic Ransomware Intrusion',
    description: 'A deterministic, fictional SOC replay showing detection and correlation from reconnaissance through encryption impact.',
    events: [
      ['00:00', 'Reconnaissance', 'TA0043', 'T1595', 'Network scan observed against TEST-NET service range', 'MEDIUM', 'Recon activity'],
      ['00:18', 'Credential Access', 'TA0006', 'T1110', 'Synthetic password-spray pattern crosses detection threshold', 'HIGH', 'Credential spray'],
      ['00:41', 'Initial Access', 'TA0001', 'T1133', 'Synthetic remote-access authentication from 203.0.113.10', 'HIGH', 'External remote service'],
      ['01:12', 'Privilege Escalation', 'TA0004', 'T1068', 'Synthetic privilege-escalation evidence recorded', 'CRITICAL', 'Privilege escalation'],
      ['02:06', 'Command and Control', 'TA0011', 'T1071.001', 'Synthetic HTTPS beacon to c2.example', 'HIGH', 'C2 beacon'],
      ['03:24', 'Exfiltration', 'TA0010', 'T1041', 'Synthetic outbound transfer pattern to 198.51.100.24', 'CRITICAL', 'Exfiltration over C2'],
      ['04:05', 'Impact', 'TA0040', 'T1486', 'Synthetic file-encryption behavior detected', 'CRITICAL', 'Data encrypted for impact'],
    ],
  },
  credential: {
    name: 'Synthetic Identity Compromise',
    description: 'A fictional replay of credential abuse, suspicious sign-in and persistence signals.',
    events: [
      ['00:00', 'Credential Access', 'TA0006', 'T1110', 'Synthetic authentication failures increase across test identities', 'MEDIUM', 'Password spray'],
      ['00:26', 'Initial Access', 'TA0001', 'T1078', 'Synthetic valid-account sign-in from 203.0.113.42', 'HIGH', 'Valid accounts'],
      ['00:49', 'Discovery', 'TA0007', 'T1087', 'Synthetic account-discovery telemetry observed', 'MEDIUM', 'Account discovery'],
      ['01:14', 'Persistence', 'TA0003', 'T1098', 'Synthetic account-modification event creates persistence signal', 'HIGH', 'Account manipulation'],
      ['01:51', 'Collection', 'TA0009', 'T1114', 'Synthetic mailbox collection pattern crosses threshold', 'HIGH', 'Email collection'],
    ],
  },
  cloud: {
    name: 'Synthetic Cloud Key Abuse',
    description: 'A fictional replay showing cloud identity misuse, key creation and suspicious data access.',
    events: [
      ['00:00', 'Initial Access', 'TA0001', 'T1078.004', 'Synthetic cloud account sign-in from 198.51.100.60', 'HIGH', 'Cloud accounts'],
      ['00:20', 'Discovery', 'TA0007', 'T1526', 'Synthetic cloud-service discovery activity observed', 'MEDIUM', 'Cloud service discovery'],
      ['00:47', 'Persistence', 'TA0003', 'T1098.001', 'Synthetic additional cloud credential created', 'CRITICAL', 'Additional cloud credentials'],
      ['01:23', 'Collection', 'TA0009', 'T1530', 'Synthetic object-storage read burst detected', 'HIGH', 'Data from cloud storage'],
      ['02:02', 'Exfiltration', 'TA0010', 'T1567.002', 'Synthetic transfer to storage.example detected', 'CRITICAL', 'Exfiltration to cloud storage'],
    ],
  },
});

function replayGraph(events) {
  const nodes = [{ id: 'asset:synthetic-enterprise', type: 'asset', label: 'Synthetic Enterprise Environment' }];
  const edges = [];
  events.forEach((event, index) => {
    const eventId = `event:${index + 1}`;
    const techniqueId = `technique:${event.technique}`;
    nodes.push({ id: eventId, type: 'event', label: `${event.stage}: ${event.rule}` });
    if (!nodes.some(n => n.id === techniqueId)) {
      nodes.push({ id: techniqueId, type: 'technique', label: event.technique });
    }
    edges.push({ source: 'asset:synthetic-enterprise', target: eventId, relation: 'observed_event', evidence: event.evidence });
    edges.push({ source: eventId, target: techniqueId, relation: 'mapped_to_technique', evidence: 'Synthetic MITRE ATT&CK mapping' });
    if (index > 0) edges.push({ source: `event:${index}`, target: eventId, relation: 'precedes', evidence: 'Synthetic replay order' });
  });
  return { nodes, edges };
}

function buildReplay(scenarioId) {
  const source = REPLAY_SCENARIOS[scenarioId];
  const events = source.events.map((row, index) => ({
    sequence: index + 1,
    offset: row[0],
    stage: row[1],
    tactic: row[2],
    technique: row[3],
    evidence: row[4],
    severity: row[5],
    rule: row[6],
  }));
  const graph = replayGraph(events);
  return {
    schema_version: 'sentinel-apex.synthetic-replay.v1',
    workbench_version: INVESTIGATION_WORKBENCH_VERSION,
    generated_at: new Date().toISOString(),
    scenario_id: scenarioId,
    name: source.name,
    description: source.description,
    synthetic: true,
    read_only: true,
    customer_data: false,
    network_actions: false,
    malware_execution: false,
    workflow: ['ingest', 'validate', 'correlate', 'map ATT&CK', 'explain evidence', 'prepare detections', 'report'],
    events,
    graph: { ...graph, stats: { total_nodes: graph.nodes.length, total_edges: graph.edges.length } },
    summary: {
      event_count: events.length,
      critical_events: events.filter(e => e.severity === 'CRITICAL').length,
      high_events: events.filter(e => e.severity === 'HIGH').length,
      techniques: [...new Set(events.map(e => e.technique))],
      tactics: [...new Set(events.map(e => e.tactic))],
    },
    limitations: [
      'All entities, addresses and domains are synthetic examples reserved for documentation/testing.',
      'The replay does not execute malware, scan external systems, send authentication attempts, or perform network actions.',
      'Replay detections demonstrate workflow semantics only and are not measurements of a customer environment.',
      'Use authenticated live investigation mode for current SENTINEL APEX intelligence.',
    ],
  };
}

function capabilities() {
  return {
    schema_version: 'sentinel-apex.investigation-capabilities.v1',
    workbench_version: INVESTIGATION_WORKBENCH_VERSION,
    mode: 'read_only',
    live_investigation: {
      path: '/api/v1/investigation/item?id=<intelligence-id>',
      authentication: 'API key or customer JWT',
      entitlement: 'PRO, ENTERPRISE or MSSP with read:intel scope',
      outputs: ['risk explanation', 'evidence claims', 'MITRE context', 'correlation graph', 'timeline', 'playbook', 'report links when present', 'export links'],
    },
    synthetic_replay: {
      path: '/api/v1/demo/replay?scenario=ransomware',
      authentication: 'none',
      scenarios: Object.keys(REPLAY_SCENARIOS),
      data: 'synthetic only',
    },
    safety: {
      mutations: false,
      binary_detonation: false,
      external_scanning: false,
      raw_ioc_arrays_in_workbench_response: false,
    },
  };
}

export async function routeInvestigationWorkbench({ path, request, env, auth, requestId = '' }) {
  if (request.method !== 'GET') return methodNotAllowed();

  if (path === '/api/v1/investigation/capabilities') {
    return jsonResp(capabilities(), 200, { 'Cache-Control': 'public, max-age=300' });
  }

  if (path === '/api/v1/demo/replay') {
    const scenario = (new URL(request.url).searchParams.get('scenario') || 'ransomware').toLowerCase();
    if (!Object.hasOwn(REPLAY_SCENARIOS, scenario)) {
      return jsonResp({
        error: 'invalid_scenario',
        valid_scenarios: Object.keys(REPLAY_SCENARIOS),
      }, 400, { 'Cache-Control': 'no-store' });
    }
    return jsonResp(buildReplay(scenario), 200, { 'Cache-Control': 'public, max-age=3600, stale-while-revalidate=86400' });
  }

  if (path !== '/api/v1/investigation/item') return null;

  if (!auth?.key && !auth?.jwt) {
    return jsonResp({
      error: 'authentication_required',
      message: 'Provide X-API-Key or Authorization: Bearer <JWT>.',
    }, 401, { 'Cache-Control': 'no-store' });
  }

  const tier = normalizeTier(auth.tier);
  // Fail closed on every tier except the three commercial identities this
  // endpoint explicitly promises. Unknown/legacy tier strings must never
  // inherit paid access merely because they are "not FREE".
  if (!PAID_INVESTIGATION_TIERS.has(tier)) {
    const gate = enforceTierGate('intel_graph', tier);
    return jsonResp({
      status: 'locked',
      error: gate.reason || 'pro_required',
      message: gate.message || 'Analyst Investigation Workbench requires PRO, ENTERPRISE or MSSP.',
      upgrade: gate.upgrade || null,
      workbench_version: INVESTIGATION_WORKBENCH_VERSION,
    }, 402, { 'Cache-Control': 'no-store' });
  }

  const scopeError = enforceScopeMiddleware(auth, 'read:intel', requestId);
  if (scopeError) return scopeError;

  const id = (new URL(request.url).searchParams.get('id') || '').trim();
  if (!id) {
    return jsonResp({ error: 'missing_id', message: 'Query parameter ?id=<intelligence-id> is required.' }, 400, { 'Cache-Control': 'no-store' });
  }
  if (id.length > 256) {
    return jsonResp({ error: 'invalid_id', message: 'Investigation id exceeds the 256-character limit.' }, 400, { 'Cache-Control': 'no-store' });
  }

  let items;
  try {
    items = await loadFeed(env);
  } catch (error) {
    return jsonResp({
      error: 'intelligence_store_unavailable',
      message: 'The current intelligence manifest could not be read.',
    }, 503, { 'Cache-Control': 'no-store', 'Retry-After': '30' });
  }

  if (!items.length) {
    return jsonResp({ error: 'no_feed_data', message: 'No current intelligence records are available.' }, 503, { 'Cache-Control': 'no-store', 'Retry-After': '30' });
  }

  const item = findItem(items, id);
  if (!item) {
    return jsonResp({ error: 'not_found', message: 'No current intelligence item matched the requested id.' }, 404, { 'Cache-Control': 'no-store' });
  }

  try {
    return jsonResp(buildInvestigation(item, items), 200, {
      'Cache-Control': 'private, no-store, max-age=0',
      'X-Sentinel-Read-Only': 'true',
    });
  } catch (error) {
    return jsonResp({
      error: 'investigation_projection_failed',
      message: 'The intelligence item exists, but its analyst projection could not be composed.',
    }, 500, { 'Cache-Control': 'no-store' });
  }
}

export const __test = Object.freeze({
  buildInvestigation,
  buildReplay,
  capabilities,
  findItem,
  safeReportPath,
});
