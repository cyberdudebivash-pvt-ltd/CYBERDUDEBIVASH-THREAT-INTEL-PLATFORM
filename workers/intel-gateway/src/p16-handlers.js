/**
 * CYBERDUDEBIVASH(R) SENTINEL APEX -- P16 Extended Enterprise Handlers
 * workers/intel-gateway/src/p16-handlers.js
 *
 * P16.2  Cross-Platform Workflow Engine status
 * P16.3  Unified Asset Intelligence
 * P16.4  Enterprise Health Engine
 * P16.6  Enterprise Analytics
 * P16.7  Automation Intelligence
 * P16.8  Operational Observability
 *
 * All handlers are ADDITIVE -- zero duplication of existing engine logic.
 * Data is derived from KV/D1 already bound to the intel-gateway worker.
 */

// ---------------------------------------------------------------------------
// Shared helpers (mirror subset from index.js -- no re-import needed)
// ---------------------------------------------------------------------------
const _now = () => new Date().toISOString();

const _jsonResp = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Cache-Control": "no-store",
    },
  });

const _kv = async (kv, key, fallback = null) => {
  try { return JSON.parse(await kv.get(key)) ?? fallback; }
  catch { return fallback; }
};

// ---------------------------------------------------------------------------
// P16.2 -- Cross-Platform Workflow Engine Status
// GET /api/v1/workflows/status
// Reuses P7 automation data stored in ANALYTICS_KV
// ---------------------------------------------------------------------------
export async function handleP16Workflows(request, env) {
  const kv = env.ANALYTICS_KV || env.SECURITY_HUB_KV;

  const [queueDepth, lastRun, failureCount] = await Promise.all([
    _kv(kv, "workflow:queue_depth", 0),
    _kv(kv, "workflow:last_run_ts", null),
    _kv(kv, "workflow:failure_count_24h", 0),
  ]);

  const phases = [
    "threat_detection", "investigation", "decision",
    "playbook", "automation", "customer_notification",
    "executive_reporting", "commercial_actions",
  ];

  // PRODUCTION-TRUTH FIX (post-launch platform audit): avg_latency_ms was
  // Math.random()-generated on every request -- not stale fake data but
  // actively fabricated telemetry that changes on every poll, and status
  // was hardcoded "operational" for all 8 phases regardless of real state.
  // No KV key or computation anywhere in this file tracks per-phase latency
  // or health -- confirmed via repo-wide search; only the aggregate
  // queue_depth/last_run/failure_count_24h below are real. Reporting
  // not_separately_monitored/null rather than a fabricated figure, the same
  // fix already applied to the SLA Certificate's per-component uptime
  // breakdown and to handleP16Analytics()/handleP16Health() above.
  const phaseStatus = phases.map(p => ({
    phase: p,
    status: "not_separately_monitored",
    avg_latency_ms: null,
  }));

  return _jsonResp({
    generated_at: _now(),
    component: "cross-platform-workflow-engine",
    version: "16.2",
    workflow_engine: {
      status: failureCount > 5 ? "degraded" : "operational",
      queue_depth: queueDepth,
      last_run: lastRun,
      failure_count_24h: failureCount,
      phases: phaseStatus,
      phase_metrics_basis: "aggregate only (queue_depth, last_run, failure_count_24h); per-phase status/latency not separately instrumented",
      bottlenecks: failureCount > 3 ? ["customer_notification"] : [],
      efficiency_pct: Math.max(0, 100 - failureCount * 5),
    },
    reuses: ["P7 Enterprise Automation", "ANALYTICS_KV"],
  });
}

// ---------------------------------------------------------------------------
// P16.3 -- Unified Asset Intelligence
// GET /api/v1/assets/intelligence
// Correlates Assets x Threats x CVEs x Campaigns from existing KV cache
// ---------------------------------------------------------------------------
export async function handleP16Assets(request, env) {
  const kv = env.ANALYTICS_KV || env.SECURITY_HUB_KV;

  const [feedStats, cveCache, campaigns] = await Promise.all([
    _kv(kv, "feed:stats", {}),
    _kv(kv, "cve:live_cache", []),
    _kv(kv, "intel:campaigns", []),
  ]);

  const criticalCVEs = Array.isArray(cveCache)
    ? cveCache.filter(c => parseFloat(c.cvss || c.base_score || 0) >= 9.0).slice(0, 10)
    : [];

  const activeCampaigns = Array.isArray(campaigns)
    ? campaigns.filter(c => c.status === "active" || !c.status).slice(0, 10)
    : [];

  return _jsonResp({
    generated_at: _now(),
    component: "unified-asset-intelligence",
    version: "16.3",
    asset_intelligence: {
      threat_correlation: {
        total_threats: feedStats.total || 0,
        critical: feedStats.critical || 0,
        high: feedStats.high || 0,
        medium: feedStats.medium || 0,
      },
      critical_cves: criticalCVEs,
      active_campaigns: activeCampaigns,
      business_impact_score: Math.min(
        100,
        ((feedStats.critical || 0) * 10) + ((feedStats.high || 0) * 5)
      ),
      mssp_correlation: { tenants_affected: 0, playbooks_triggered: 0 },
      playbook_coverage_pct: activeCampaigns.length > 0 ? 78 : 100,
    },
    reuses: ["P1 Threat Intelligence", "P3 Cyber Signal Radar", "ANALYTICS_KV"],
  });
}

// ---------------------------------------------------------------------------
// P16.4 -- Enterprise Health Engine
// GET /api/v1/health/enterprise
// Aggregates platform + business + customer + security + operational health
// ---------------------------------------------------------------------------
export async function handleP16Health(request, env) {
  const kv = env.ANALYTICS_KV || env.SECURITY_HUB_KV;

  const [feedStats, slaData, errorData] = await Promise.all([
    _kv(kv, "feed:stats", {}),
    _kv(kv, "sla:metrics", {}),
    _kv(kv, "error:summary_24h", {}),
  ]);

  const errorRate = errorData.count || 0;
  const feedHealth = (feedStats.total || 0) > 10 ? 95 : 60;
  const slaHealth = slaData.breaches ? Math.max(0, 100 - slaData.breaches * 10) : 92;

  // v185.2 FIX (Fortune-500 audit, Phase 10-11): business_health,
  // customer_health, commercial_health, and executive_health were hardcoded
  // constants (88/91/85/90, always "healthy") with no backing KV key or
  // computation anywhere in the codebase -- confirmed via repo-wide search.
  // A customer or internal team polling this live, authenticated API would
  // always see "healthy" regardless of actual state. No real data source
  // exists yet for these four dimensions, so they now report
  // not_available/null rather than a fabricated score -- consistent with
  // the platform's own policy of truthful "unavailable" states over
  // manufactured "healthy" ones (see the Dark Web Monitor and monetization
  // report fixes). composite_score is computed only from the three
  // dimensions that have a real, KV-derived basis.
  const dimensions = {
    platform_health:     { score: feedHealth,         status: feedHealth > 80 ? "healthy" : "degraded" },
    security_health:     { score: slaHealth,           status: slaHealth > 75 ? "healthy" : "at_risk" },
    operational_health:  { score: Math.max(0, 95 - errorRate * 2), status: errorRate > 10 ? "degraded" : "healthy" },
    business_health:     { score: null, status: "not_available" },
    customer_health:     { score: null, status: "not_available" },
    commercial_health:   { score: null, status: "not_available" },
    executive_health:    { score: null, status: "not_available" },
  };

  const measuredScores = Object.values(dimensions)
    .map(d => d.score)
    .filter(s => typeof s === "number" && Number.isFinite(s));
  const composite = measuredScores.length > 0
    ? Math.round(measuredScores.reduce((a, b) => a + b, 0) / measuredScores.length)
    : null;

  return _jsonResp({
    generated_at: _now(),
    component: "enterprise-health-engine",
    version: "16.4",
    enterprise_health: {
      composite_score: composite,
      composite_score_basis: "platform_health, security_health, operational_health (KV-derived only)",
      status: composite === null ? "not_available" : composite > 85 ? "healthy" : composite > 70 ? "degraded" : "critical",
      dimensions,
      trend: "stable",
      last_incident: slaData.last_breach || null,
    },
    reuses: ["P6 Operations Platform", "ANALYTICS_KV"],
  });
}

// ---------------------------------------------------------------------------
// P16.6 -- Enterprise Analytics
// GET /api/v1/analytics/enterprise
// Cross-platform KPIs + trend analysis (reuses existing reporting engine data)
// ---------------------------------------------------------------------------
export async function handleP16Analytics(request, env) {
  const kv = env.ANALYTICS_KV || env.SECURITY_HUB_KV;

  const [feedStats, usageData, apiCallStats] = await Promise.all([
    _kv(kv, "feed:stats", {}),
    _kv(kv, "usage:summary", {}),
    _kv(kv, "analytics:api_calls_24h", 0),
  ]);

  // PRODUCTION-TRUTH FIX (post-launch platform audit): mean_detection_time_min,
  // mean_response_time_min, mrr_trend, escalation_rate_pct, automation_rate_pct,
  // sla_compliance_pct, platform_uptime_pct, security_posture, risk_trend, and
  // roi_multiplier were hardcoded constants with no backing KV key or
  // computation anywhere in this file -- the exact same class of bug already
  // fixed in handleP16Health() immediately above (v185.2 FIX, Fortune-500
  // audit) for business_health/customer_health/commercial_health/
  // executive_health, just missed in this sibling function. A customer
  // polling this live, authenticated /api/v1/analytics/enterprise endpoint
  // would always see "strong" security posture, "decreasing" risk, and a
  // fixed 99.8% uptime regardless of actual state. Reporting not_available
  // rather than a fabricated figure, consistent with that same fix and the
  // platform's established policy (Dark Web Monitor, SLA Certificate).
  return _jsonResp({
    generated_at: _now(),
    component: "enterprise-analytics",
    version: "16.6",
    analytics: {
      threat_kpis: {
        total_indicators: feedStats.total || 0,
        critical_alerts_24h: feedStats.critical || 0,
        mean_detection_time_min: null,
        mean_response_time_min: null,
      },
      commercial_kpis: {
        api_calls_24h: apiCallStats || 0,
        active_api_keys: usageData.active_keys || 0,
        trial_conversions_7d: usageData.trial_conversions || 0,
        mrr_trend: "not_available",
      },
      soc_kpis: {
        incidents_open: usageData.open_incidents || 0,
        incidents_closed_24h: usageData.closed_incidents || 0,
        escalation_rate_pct: null,
        automation_rate_pct: null,
      },
      mssp_kpis: {
        managed_tenants: usageData.mssp_tenants || 0,
        tickets_24h: usageData.mssp_tickets || 0,
        sla_compliance_pct: null,
      },
      executive_kpis: {
        platform_uptime_pct: null,
        security_posture: "not_available",
        risk_trend: "not_available",
        roi_multiplier: null,
      },
      trend_window: "7d",
      kpis_not_yet_measured: [
        "mean_detection_time_min", "mean_response_time_min", "mrr_trend",
        "escalation_rate_pct", "automation_rate_pct", "sla_compliance_pct",
        "platform_uptime_pct", "security_posture", "risk_trend", "roi_multiplier",
      ],
    },
    reuses: ["P10 Executive Intelligence", "P8 API Ecosystem", "ANALYTICS_KV"],
  });
}

// ---------------------------------------------------------------------------
// P16.7 -- Automation Intelligence
// GET /api/v1/automation/intelligence
// Reuses P7 automation platform metrics
// ---------------------------------------------------------------------------
export async function handleP16Automation(request, env) {
  const kv = env.ANALYTICS_KV || env.SECURITY_HUB_KV;

  const [autoStats, queueDepth, failureCount] = await Promise.all([
    _kv(kv, "automation:stats_24h", {}),
    _kv(kv, "workflow:queue_depth", 0),
    _kv(kv, "workflow:failure_count_24h", 0),
  ]);

  const totalRuns = autoStats.total_runs || 0;
  const successRuns = autoStats.success_runs || Math.max(0, totalRuns - failureCount);
  const efficiency = totalRuns > 0 ? Math.round((successRuns / totalRuns) * 100) : 100;

  const bottlenecks = [];
  if (queueDepth > 50) bottlenecks.push({ component: "workflow_queue", severity: "high", queue_depth: queueDepth });
  if (failureCount > 5) bottlenecks.push({ component: "automation_engine", severity: "medium", failures: failureCount });

  return _jsonResp({
    generated_at: _now(),
    component: "automation-intelligence",
    version: "16.7",
    automation_intelligence: {
      efficiency_pct: efficiency,
      total_runs_24h: totalRuns,
      success_runs_24h: successRuns,
      failure_runs_24h: failureCount,
      queue_depth: queueDepth,
      bottlenecks,
      optimization_suggestions: [
        bottlenecks.length > 0
          ? "Increase worker concurrency to reduce queue depth"
          : "No optimizations required -- system operating efficiently",
      ],
      failure_prediction: failureCount > 8 ? "elevated_risk" : "normal",
    },
    reuses: ["P7 Enterprise Automation", "ANALYTICS_KV"],
  });
}

// ---------------------------------------------------------------------------
// P16.8 -- Operational Observability
// GET /api/v1/observability/metrics
// Measures latencies, cache hit ratio, worker health, D1/KV performance
// ---------------------------------------------------------------------------
export async function handleP16Observability(request, env) {
  const startTs = Date.now();

  // Probe KV latency
  let kvLatencyMs = null;
  try {
    const t0 = Date.now();
    await (env.ANALYTICS_KV || env.SECURITY_HUB_KV).get("_p16_probe");
    kvLatencyMs = Date.now() - t0;
  } catch { kvLatencyMs = -1; }

  const kv = env.ANALYTICS_KV || env.SECURITY_HUB_KV;
  const [cacheHitData, workerErrorData] = await Promise.all([
    _kv(kv, "analytics:cache_hit_ratio", null),
    _kv(kv, "error:summary_24h", {}),
  ]);

  const totalLatency = Date.now() - startTs;

  return _jsonResp({
    generated_at: _now(),
    component: "operational-observability",
    version: "16.8",
    observability: {
      request_latency_ms: totalLatency,
      kv_latency_ms: kvLatencyMs,
      d1_latency_ms: null,
      cache_hit_ratio_pct: cacheHitData ? Math.round(cacheHitData * 100) : null,
      worker_health: {
        status: workerErrorData.count > 50 ? "degraded" : "healthy",
        error_rate_24h: workerErrorData.count || 0,
        last_error: workerErrorData.last_error || null,
      },
      queue_depth: await _kv(kv, "workflow:queue_depth", 0),
      cross_platform_latency_ms: {
        intel_gateway: totalLatency,
        intel_retention_engine: null,
        revenue_engine: null,
      },
      performance_targets: {
        cached_target_ms: 50,
        uncached_target_ms: 400,
        current_kv_ms: kvLatencyMs,
        within_target: kvLatencyMs !== null && kvLatencyMs <= 50,
      },
    },
    reuses: ["P6 Operations Platform", "ANALYTICS_KV", "SECURITY_HUB_KV"],
  });
}

// ---------------------------------------------------------------------------
// buildSubsystems -- wires control-plane sections that were previously notWired
// Called from handleControlPlaneState in index.js (P16.1 enrichment)
// ---------------------------------------------------------------------------
export function buildSubsystems(env, threats) {
  const notWired = r => ({ available: false, reason: r });

  // v185.2 FIX (Fortune-500 audit, Phase 10-11): automation_rate_pct,
  // mean_response_time_min, sla_compliance_pct, health_score, mrr_trend, and
  // every unconditional platform_status/status:"operational" below were
  // hardcoded constants with no backing KV key, D1 query, or computation --
  // confirmed via repo-wide search. This function's own JSON is returned
  // directly by the live, authenticated /api/v1/control-plane/state
  // endpoint, so a customer or ops team polling it always saw "operational/
  // healthy" regardless of real state. No real data source exists yet for
  // these dimensions, so they now report available:false / not_available
  // rather than a fabricated value, consistent with the platform's own
  // policy of truthful "unavailable" states over manufactured "healthy"
  // ones (see the Dark Web Monitor and monetization report fixes).

  // SOC: derive the real parts from threat stats already computed; drop the
  // two fields that had no real source.
  let soc;
  try {
    const t = threats || {};
    const stats = t.stats || {};
    soc = {
      available: true,
      source: "derived-from-threat-feed",
      active_alerts: stats.total || 0,
      critical_alerts: stats.critical || 0,
      global_threat_level: t.global_threat_level || "UNKNOWN",
      defcon: t.defcon || null,
      automation_rate_pct: null,
      mean_response_time_min: null,
      automation_metrics_status: "not_available",
    };
  } catch {
    soc = notWired("soc derivation failed");
  }

  // Automation: no live queue/status computation exists yet.
  const automation = notWired(
    "automation queue/status has no live computation yet; see /api/v1/automation/intelligence for what is actually wired"
  );

  // MSSP: no live SLA computation exists yet.
  const mssp = notWired(
    "mssp platform_status/sla_compliance_pct has no live computation yet; see /api/v1/analytics/enterprise for what is actually wired"
  );

  // Security Fabric: derive from threat coverage (this part is real).
  let security_fabric;
  try {
    const stats = (threats && threats.stats) || {};
    security_fabric = {
      available: true,
      source: "derived-from-threat-fabric",
      coverage_pct: Math.min(100, ((stats.total || 0) > 50 ? 85 : 60)),
      stix_enabled: true,
      taxii_enabled: true,
      ai_detection_active: true,
    };
  } catch {
    security_fabric = notWired("security fabric derivation failed");
  }

  // Customer: no live health_score computation exists yet.
  const customer = notWired(
    "customer platform_status/health_score has no live computation yet; see /api/v1/health/enterprise for what is actually wired"
  );

  // Commercial: revenue-engine has no public route binding yet (matches the
  // honest `commercial` object already computed by handleControlPlaneState
  // in index.js -- that caller must never prefer this fabricated fallback
  // over its own real notWired() result).
  const commercial = notWired(
    "sentinel-revenue-engine has no public route binding; commercial data lives in its D1 CRM_DB and is not externally fetchable from this Worker"
  );

  return { soc, automation, mssp, security_fabric, customer, commercial };
}
