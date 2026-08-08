/**
 * workers/intel-gateway/src/p40-handlers.js
 * P40.0 Global Intelligence Source Fabric — Source Registry & Health API
 *
 * ARCHITECTURE NOTE: this layer composes over the canonical Source Registry
 * and Source Health artifacts produced Python-side
 * (scripts/build_source_registry.py, scripts/source_fabric_health.py) and
 * bridged into R2 by scripts/r2_upload.py — the same "Python pipeline
 * writes JSON → R2 → Worker reads via env.INTEL_R2.get()" pattern already
 * used by p21-handlers.js:_loadFeed and every other P-layer that reads
 * feed data, replicated here rather than introducing a new access pattern.
 *
 * This file computes NO per-item scoring logic and reuses none of
 * computeP20QualityScore / computeEnterpriseTrustScore / computeP26Grade:
 * those score individual intelligence ITEMS, which is a different problem
 * from source-level registry/health data. There is no existing P-layer
 * engine for "is this SOURCE healthy and what does it cost to use" — that
 * gap is exactly what the Global Intelligence Source Fabric mission adds.
 * See the P40 Reuse Report in the implementation's final deliverables for
 * why this is a genuine gap, not a missed reuse opportunity.
 *
 * 10 exported handlers / 10 API routes:
 *   /api/v1/p40/source-registry   - full registry listing (filterable by
 *                                   ?status=, ?wave=, ?domain=)
 *   /api/v1/p40/source-detail     - single source by ?id= + its live health
 *   /api/v1/p40/source-health     - full health/observability report
 *   /api/v1/p40/licensing         - licensing governance rollup (Section 23)
 *   /api/v1/p40/coverage          - intelligence-domain coverage matrix
 *   /api/v1/p40/waves             - Wave 1-5 rollout status (Section 39)
 *   /api/v1/p40/certification     - P40 certification chain status
 *   /api/v1/p40/metrics           - platform-wide source-fabric KPIs
 *   /api/v1/p40/dashboard         - dashboard-ready composite payload
 *   /api/v1/p40/observability     - observability health endpoint
 */

const P40_VERSION   = '40.0';
const REGISTRY_KEY  = 'intel/source_registry.json';
const HEALTH_KEY    = 'intel/source_fabric_health.json';
const CERT_KEY      = 'intel/p40_certification_report.json';

// ---------------------------------------------------------------------------
// R2 loaders — mirrors p21-handlers.js:_loadFeed's env.INTEL_R2?.get() +
// optional-chaining-safe pattern, scoped to this layer's own R2 keys.
// ---------------------------------------------------------------------------

async function _loadR2Json(env, key) {
  try {
    const obj = await env.INTEL_R2?.get(key);
    if (!obj) return null;
    const text = await obj.text();
    if (!text || !text.trim()) return null;
    return JSON.parse(text);
  } catch (_) {
    return null;
  }
}

async function _loadRegistry(env) {
  return await _loadR2Json(env, REGISTRY_KEY);
}

async function _loadHealth(env) {
  return await _loadR2Json(env, HEALTH_KEY);
}

function _json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-P40-Version': P40_VERSION },
  });
}

function _registryUnavailable() {
  return _json({
    error: 'Source registry not yet synced to R2',
    hint: 'Run scripts/build_source_registry.py then scripts/r2_upload.py, or check the '
        + 'sentinel-blogger.yml P40 CI stage for the last sync attempt.',
    version: P40_VERSION,
  }, 503);
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export async function handleP40SourceRegistry(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();

  const url = new URL(request.url);
  const status = url.searchParams.get('status');
  const wave = url.searchParams.get('wave');
  const domain = url.searchParams.get('domain');

  let sources = registry.sources;
  if (status) sources = sources.filter(s => s.implementation_status === status.toUpperCase());
  if (wave) sources = sources.filter(s => String(s.wave) === wave);
  if (domain) sources = sources.filter(s => (s.intelligence_domains || []).includes(domain));

  return _json({
    schema_version: 'p40.0',
    registry_version: registry.registry_version,
    generated_at: registry.generated_at,
    total: sources.length,
    filters_applied: { status: status || null, wave: wave || null, domain: domain || null },
    status_breakdown: registry.status_breakdown,
    wave_breakdown: registry.wave_breakdown,
    sources,
  });
}

export async function handleP40SourceDetail(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();

  const url = new URL(request.url);
  const id = url.searchParams.get('id');
  if (!id) return _json({ error: "Missing required query param 'id'", version: P40_VERSION }, 400);

  const source = registry.sources.find(s => s.source_id === id);
  if (!source) return _json({ error: `Unknown source_id: ${id}`, version: P40_VERSION }, 404);

  const health = await _loadHealth(env);
  const healthEntry = health ? (health.sources || []).find(h => h.source_id === id) : null;

  return _json({ schema_version: 'p40.0', source, health: healthEntry || null });
}

export async function handleP40SourceHealth(request, env) {
  const health = await _loadHealth(env);
  if (!health) {
    return _json({
      error: 'Source health report not yet synced to R2',
      hint: 'Run scripts/source_fabric_health.py then scripts/r2_upload.py.',
      version: P40_VERSION,
    }, 503);
  }
  return _json({ schema_version: 'p40.0', ...health });
}

export async function handleP40Licensing(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();

  const sources = registry.sources;
  const byClass = {};
  for (const s of sources) byClass[s.licensing_class] = (byClass[s.licensing_class] || 0) + 1;

  return _json({
    schema_version: 'p40.0',
    total: sources.length,
    redistribution_allowed: sources.filter(s => s.redistribution_allowed).length,
    redistribution_restricted: sources.filter(s => !s.redistribution_allowed).length,
    commercial_use_allowed: sources.filter(s => s.commercial_use_allowed).length,
    attribution_required: sources.filter(s => s.attribution_required).length,
    by_licensing_class: byClass,
    // Governance surface for Section 23 — "the system must prevent
    // accidental redistribution of restricted data": every non-
    // redistributable source, explicitly enumerated.
    restricted_sources: sources
      .filter(s => !s.redistribution_allowed)
      .map(s => ({
        source_id: s.source_id,
        canonical_name: s.canonical_name,
        licensing_class: s.licensing_class,
        implementation_status: s.implementation_status,
      })),
  });
}

export async function handleP40Coverage(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();

  const coverage = {};
  for (const s of registry.sources) {
    for (const d of (s.intelligence_domains || [])) {
      coverage[d] = coverage[d] || { total: 0, by_status: {} };
      coverage[d].total += 1;
      coverage[d].by_status[s.implementation_status] = (coverage[d].by_status[s.implementation_status] || 0) + 1;
    }
  }
  return _json({ schema_version: 'p40.0', domain_coverage: coverage });
}

export async function handleP40Waves(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();

  const waves = {};
  for (const s of registry.sources) {
    const w = `wave_${s.wave}`;
    waves[w] = waves[w] || { total: 0, by_status: {} };
    waves[w].total += 1;
    waves[w].by_status[s.implementation_status] = (waves[w].by_status[s.implementation_status] || 0) + 1;
  }
  return _json({ schema_version: 'p40.0', waves });
}

// sentinel-blogger.yml — the pipeline that regenerates and R2-syncs this
// report — runs 3x/day (cron '0 0,8,16 * * *', ~8h cadence). This threshold
// is a generous 2x that cadence, matching source_fabric_health.py's
// staleness philosophy: flag genuine silence, not a run landing a bit late.
const CERT_FRESHNESS_STALE_SECONDS = 16 * 3600;

export async function handleP40Certification(request, env) {
  const cert = await _loadR2Json(env, CERT_KEY);
  if (!cert) {
    return _json({
      error: 'P40 certification report not yet synced to R2',
      hint: 'Run scripts/p40_production_certification.py then scripts/r2_upload.py.',
      version: P40_VERSION,
    }, 503);
  }

  const generatedAtMs = cert.generated_at ? Date.parse(cert.generated_at) : NaN;
  const ageSeconds = Number.isFinite(generatedAtMs)
    ? Math.max(0, Math.floor((Date.now() - generatedAtMs) / 1000))
    : null;
  const freshness = ageSeconds === null
    ? 'UNKNOWN'
    : (ageSeconds > CERT_FRESHNESS_STALE_SECONDS ? 'STALE' : 'FRESH');

  return _json({
    schema_version: 'p40.0',
    ...cert,
    status: cert.release_tier ?? null,
    age_seconds: ageSeconds,
    freshness,
    sync_status: freshness === 'STALE' ? 'LAGGING' : 'SYNCED',
  });
}

export async function handleP40Metrics(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();
  const health = await _loadHealth(env);

  return _json({
    schema_version: 'p40.0',
    total_sources: registry.total_sources,
    status_breakdown: registry.status_breakdown,
    wave_breakdown: registry.wave_breakdown,
    domain_breakdown: registry.domain_breakdown,
    health_breakdown: health ? health.health_breakdown : null,
    live_or_implemented_sources: health ? health.live_or_implemented_sources : null,
    manifest_total_entries: health ? health.manifest_total_entries : null,
  });
}

export async function handleP40Dashboard(request, env) {
  const registry = await _loadRegistry(env);
  if (!registry) return _registryUnavailable();
  const health = await _loadHealth(env);

  return _json({
    schema_version: 'p40.0',
    generated_at: new Date().toISOString(),
    registry_version: registry.registry_version,
    total_sources: registry.total_sources,
    status_breakdown: registry.status_breakdown,
    wave_breakdown: registry.wave_breakdown,
    domain_breakdown: registry.domain_breakdown,
    health: health ? {
      health_breakdown: health.health_breakdown,
      generated_at: health.generated_at,
      sources: health.sources,
    } : null,
    active_sources: registry.sources
      .filter(s => s.implementation_status === 'ACTIVE')
      .sort((a, b) => a.priority - b.priority)
      .map(s => ({
        source_id: s.source_id, canonical_name: s.canonical_name,
        priority: s.priority, criticality: s.criticality,
        integration_mode: s.integration_mode,
      })),
  });
}

export async function handleP40Observability(request, env) {
  return _json({
    schema_version: 'p40.0',
    layer: 'P40',
    status: 'OPERATIONAL',
    endpoints: [
      '/api/v1/p40/source-registry',
      '/api/v1/p40/source-detail',
      '/api/v1/p40/source-health',
      '/api/v1/p40/licensing',
      '/api/v1/p40/coverage',
      '/api/v1/p40/waves',
      '/api/v1/p40/certification',
      '/api/v1/p40/metrics',
      '/api/v1/p40/dashboard',
      '/api/v1/p40/observability',
    ],
    data_sources: {
      registry: 'data/registry/source_registry.json (R2 key: intel/source_registry.json)',
      health: 'data/quality/source_fabric_health.json (R2 key: intel/source_fabric_health.json)',
      certification: 'data/quality/p40_certification_report.json (R2 key: intel/p40_certification_report.json)',
    },
    generators: [
      'scripts/build_source_registry.py',
      'scripts/source_fabric_health.py',
      'scripts/p40_production_certification.py',
    ],
    engines_reused: [],
    engines_reused_note: 'P40 is source-level (not item-level) — see file header for why P20/P25/P26 do not apply here.',
  });
}
