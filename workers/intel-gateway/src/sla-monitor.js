// ==============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- SLA Monitor Engine v201.0
// Real-time uptime tracking + SLA compliance proof for Enterprise subscribers
//
// Endpoints:
//   GET  /api/sla/status      -- public: current uptime + SLA health
//   GET  /api/sla/report      -- Enterprise: 30-day SLA compliance report
//   GET  /api/sla/incidents   -- Enterprise: incident log
//   POST /api/sla/ping        -- internal: heartbeat recorder (external prober: .github/workflows/sla-heartbeat.yml)
//   GET  /api/sla/certificate -- Enterprise: downloadable SLA compliance cert data
//
// SLA Targets:
//   Enterprise: 99.9% uptime / month (~44 min downtime allowed)
//   Pro:        99.5% uptime / month (~3.6 hrs downtime allowed)
//   Free:       best-effort (no SLA)
// ==============================================================================

const safe    = (v, fb = "UNKNOWN") => (v == null ? fb : String(v));
const safeNum = (v, fb = 0)        => (typeof v === "number" && isFinite(v) ? v : Number(v) || fb);
const safeArr = (v)                => (Array.isArray(v) ? v : []);

// Constant-time string comparison for shared-secret checks -- same
// implementation as index.js's timingSafeEqual; duplicated locally (rather
// than imported) because index.js imports from this module, so an
// index.js -> this file -> index.js import would be circular. Same pattern
// already used in revenue-enforcement.js.
function timingSafeEqual(a, b) {
  const bufA = new TextEncoder().encode(String(a ?? ""));
  const bufB = new TextEncoder().encode(String(b ?? ""));
  const len  = Math.max(bufA.length, bufB.length);
  let diff   = bufA.length ^ bufB.length;
  for (let i = 0; i < len; i++) {
    diff |= (bufA[i] ?? 0) ^ (bufB[i] ?? 0);
  }
  return diff === 0;
}

// PRODUCTION-VERIFICATION FIX (2026-08-24): this file was never reachable
// from index.js's router (confirmed: no import of sla-monitor.js existed),
// and even if wired it would have crashed/misbehaved for every real caller:
//   - `auth.valid`, `auth.key_id`, `auth.email` do not exist on the real
//     resolveAuth() return shape ({tier, key, sub, jwt?, kv?, error?} --
//     index.js:324). Every "if (!auth.valid)" check here was always true,
//     so real Enterprise customers with a genuine key would still get 401.
//   - Tier values compared here ("enterprise") are lowercase; the real
//     auth.tier is always uppercase (TIERS.ENTERPRISE = "ENTERPRISE"),
//     confirmed by index.js:317 and documented as the exact same class of
//     bug already fixed once in revenue-enforcement.js (see that file's
//     REVENUE_CONFIG comment). The comparison could never match.
//   - env.KV is not a bound namespace (wrangler.toml binds API_KEYS_KV,
//     RATE_LIMIT_KV, ANALYTICS_KV, SECURITY_HUB_KV only) -- every ping/
//     incident read or write was silently a no-op against `undefined`.
// Fixed to the real contract; storage moved to the existing SECURITY_HUB_KV
// binding (same "reuse an existing binding, no new infra" pattern already
// used by credit-system.js and api-extensions.js's abuse/webhook state).
const SLA_PING_KEY      = "sla:pings";
const SLA_INCIDENT_KEY  = "sla:incidents";
const SLA_WINDOW_DAYS   = 30;
const PING_TTL          = 60 * 60 * 24 * 35; // 35-day retention
const ENTERPRISE_SLA    = 99.9;
const PRO_SLA           = 99.5;
// The external heartbeat probes every 10 minutes; GitHub's scheduler can run
// late, so a ping counts as current for 45 minutes.
const HEARTBEAT_STALE_S = 45 * 60;
const SLA_MAX_BATCH     = 500;

/* ===========================================================================
   handleSLAStatus  -- GET /api/sla/status  (public)
   =========================================================================== */
export async function handleSLAStatus(request, env, rid) {
  const pings = await _loadPings(env);
  const now   = Date.now();
  const windowMs = SLA_WINDOW_DAYS * 24 * 60 * 60 * 1000;

  const recent = pings.filter(p => (now - p.ts) <= windowMs);
  const upPings = recent.filter(p => p.ok).length;
  const total   = recent.length;
  const uptimePct = total > 0 ? ((upPings / total) * 100) : 100;

  // Check last ping freshness (stale = potential outage)
  const lastPing = pings[pings.length - 1];
  const lastPingAge = lastPing ? Math.round((now - lastPing.ts) / 1000) : null;
  // "operational" = the latest heartbeat succeeded and is current.
  // "degraded"    = the latest heartbeat FAILED (a real signal).
  // "monitoring_delayed" = the latest heartbeat succeeded but is older than
  //   HEARTBEAT_STALE_S. GitHub's scheduler is best-effort and can skip or
  //   delay runs; missing data is not evidence of an outage, so it is not
  //   reported as one (it was "degraded" on 2026-09-27 with the site up).
  const heartbeatFresh = lastPingAge !== null && lastPingAge < HEARTBEAT_STALE_S;
  const liveStatus = !lastPing ? "insufficient_data"
    : lastPing.ok === false ? "degraded"
    : heartbeatFresh ? "operational" : "monitoring_delayed";

  const incidents = await _loadIncidents(env);
  const recentIncidents = incidents.filter(i => (now - new Date(i.start).getTime()) <= windowMs);

  const totalDownMs = recentIncidents.reduce((acc, i) => {
    const dur = i.duration_ms || 0;
    return acc + dur;
  }, 0);
  const windowTotalMs    = SLA_WINDOW_DAYS * 24 * 60 * 60 * 1000;
  const calculatedUptime = Math.min(100, ((windowTotalMs - totalDownMs) / windowTotalMs) * 100);

  // CodeRabbit review finding (PR #237): this previously defaulted to a
  // fabricated 100% uptime whenever total <= 10 -- including total === 0,
  // i.e. a Worker that has never received a single /api/sla/ping heartbeat
  // would still report "operational" / 100% / sla_met_enterprise: true to
  // paying Enterprise customers with zero actual monitoring evidence behind
  // it. This endpoint has never been reachable before this PR (no prior
  // customer integration to stay compatible with), so there is no cost to
  // reporting real absence-of-data honestly instead.
  const hasData = total > 0;
  // The more conservative of the two real signals (was Math.max, the less
  // conservative one, despite this pairing being documented as conservative).
  const displayUptime = hasData ? Math.min(uptimePct, calculatedUptime) : null;

  return _json(200, {
    status:           !hasData ? "insufficient_data" : liveStatus,
    heartbeat_stale_after_seconds: HEARTBEAT_STALE_S,
    uptime_pct_30d:   hasData ? parseFloat(displayUptime.toFixed(4)) : null,
    sla_target_enterprise: ENTERPRISE_SLA,
    sla_target_pro:        PRO_SLA,
    // A historical ratio is not a current SLA verdict while the external
    // monitor itself is stale. Keep the measured historical uptime visible,
    // but fail closed on the compliance boolean until monitoring resumes.
    monitoring_current:    heartbeatFresh,
    sla_met_enterprise:    hasData && heartbeatFresh ? displayUptime >= ENTERPRISE_SLA : null,
    sla_met_pro:           hasData && heartbeatFresh ? displayUptime >= PRO_SLA : null,
    total_pings_30d:       total,
    successful_pings_30d:  upPings,
    last_ping_age_seconds: lastPingAge,
    incidents_30d:         recentIncidents.length,
    total_downtime_seconds: Math.round(totalDownMs / 1000),
    // PRODUCTION-TRUTH FIX (post-launch platform audit): the 4 entries below
    // "intel-gateway" were hardcoded operational/99.9x%+ uptime figures with
    // no ping mechanism ever recording per-component data for any of them --
    // nothing calls POST /api/sla/ping with component "stix-feed"/"ai-engine"/
    // "dark-web-monitor"/"premium-reports" anywhere in this codebase (checked:
    // no cron, no workflow, no admin script). "intel-gateway" alone reflects
    // real measured data (displayUptime, computed above from actual pings/
    // incidents). "dark-web-monitor" specifically claimed 99.95% uptime for a
    // feature whose routes return 503 unavailable on every call (see index.js
    // dark-web-monitor.js route registration) -- reported honestly as disabled
    // rather than fabricated-operational.
    components: {
      "intel-gateway":    { status: !hasData ? "insufficient_data" : liveStatus, uptime: displayUptime },
      "stix-feed":        { status: "not_separately_monitored", uptime: null },
      "ai-engine":        { status: "not_separately_monitored", uptime: null },
      "dark-web-monitor": { status: "disabled", uptime: null, note: "Simulated-data endpoints intentionally disabled pending real data-source integration -- see dark-web-monitor.js" },
      "premium-reports":  { status: "not_separately_monitored", uptime: null },
    },
    version: "201.0",
    ts:      new Date().toISOString(),
    rid,
  });
}

/* ===========================================================================
   handleSLAReport  -- GET /api/sla/report  (Enterprise)
   =========================================================================== */
// v185.2 FIX (Fortune-500 audit, entitlement inventory): all three gates in
// this file checked only auth.tier !== "ENTERPRISE", excluding MSSP -- every
// other Enterprise-tier gate in the codebase (enforceTierGate's isEnt,
// requireEnterprise in enterprise-endpoints.js, the ~6 inline
// TIERS.ENTERPRISE||TIERS.MSSP checks in index.js) treats MSSP as
// Enterprise-or-above. This denied the platform's top-paying tier access to
// SLA reports, incidents, and certificates that ENTERPRISE customers get.
export async function handleSLAReport(request, env, auth, rid) {
  if (!auth || (!auth.key && !auth.jwt)) return _jsonErr(401, "Authentication required.", rid);
  if (auth.tier !== "ENTERPRISE" && auth.tier !== "MSSP") {
    return _jsonErr(403, "SLA compliance reports require Enterprise tier. Upgrade at /upgrade.html", rid);
  }

  const pings    = await _loadPings(env);
  const incidents = await _loadIncidents(env);
  const now      = Date.now();
  const windowMs = SLA_WINDOW_DAYS * 24 * 60 * 60 * 1000;

  // Build daily uptime breakdown (last 30 days)
  const dailyStats = [];
  for (let d = 0; d < SLA_WINDOW_DAYS; d++) {
    const dayStart = now - (d + 1) * 86400000;
    const dayEnd   = now - d * 86400000;
    const dayPings = pings.filter(p => p.ts >= dayStart && p.ts < dayEnd);
    const dayUp    = dayPings.filter(p => p.ok).length;
    const dayTotal = dayPings.length;
    const dayDate  = new Date(dayStart).toISOString().split("T")[0];
    dailyStats.unshift({
      date:       dayDate,
      // Missing checks are missing evidence, never a synthetic 100% day.
      uptime_pct: dayTotal > 0 ? parseFloat(((dayUp / dayTotal) * 100).toFixed(2)) : null,
      pings:      dayTotal,
      incidents:  incidents.filter(i => {
        const iStart = new Date(i.start).getTime();
        return iStart >= dayStart && iStart < dayEnd;
      }).length,
    });
  }

  const recentPings    = pings.filter(p => (now - p.ts) <= windowMs);
  const upCount        = recentPings.filter(p => p.ok).length;
  const hasData        = recentPings.length > 0;
  const uptimePct      = hasData ? ((upCount / recentPings.length) * 100) : null;
  const lastPing       = pings[pings.length - 1];
  const lastPingAgeS   = lastPing ? Math.round((now - lastPing.ts) / 1000) : null;
  const monitoringCurrent = lastPingAgeS !== null && lastPingAgeS < HEARTBEAT_STALE_S;
  const recentIncidents = incidents.filter(i => (now - new Date(i.start).getTime()) <= windowMs);
  const totalDownMs    = recentIncidents.reduce((acc, i) => acc + (i.duration_ms || 0), 0);

  return _json(200, {
    report_type:         "enterprise_sla_30d",
    account:             safe(auth.sub, ""),
    generated_at:        new Date().toISOString(),
    period:              `${new Date(now - windowMs).toISOString().split("T")[0]} to ${new Date().toISOString().split("T")[0]}`,
    sla_target:          ENTERPRISE_SLA,
    // CodeRabbit review finding (PR #237): previously defaulted to a
    // fabricated 100%/"MET" when there was zero ping data. See
    // handleSLAStatus's matching fix note above for full rationale.
    actual_uptime_pct:   hasData ? parseFloat(uptimePct.toFixed(4)) : null,
    sla_status:          !hasData ? "INSUFFICIENT_DATA"
      : !monitoringCurrent ? "MONITORING_DELAYED"
      : (uptimePct >= ENTERPRISE_SLA ? "MET" : "BREACHED"),
    monitoring_current:  monitoringCurrent,
    last_ping_age_seconds: lastPingAgeS,
    total_downtime_min:  parseFloat((totalDownMs / 60000).toFixed(2)),
    allowed_downtime_min: parseFloat(((100 - ENTERPRISE_SLA) / 100 * SLA_WINDOW_DAYS * 24 * 60).toFixed(2)),
    incidents_count:     recentIncidents.length,
    incidents:           recentIncidents.slice(-20),
    daily_breakdown:     dailyStats,
    // PRODUCTION-TRUTH FIX: same fabricated-per-component-uptime issue as
    // handleSLAStatus above (see that function's matching comment) -- no
    // real per-component ping data exists for these 4 entries.
    components: {
      "intel-gateway":    { sla: ENTERPRISE_SLA, actual: hasData ? Math.min(100, uptimePct) : null },
      "stix-feed":        { sla: ENTERPRISE_SLA, actual: null, status: "not_separately_monitored" },
      "ai-engine":        { sla: ENTERPRISE_SLA, actual: null, status: "not_separately_monitored" },
      "dark-web-monitor": { sla: 99.5,           actual: null, status: "disabled" },
      "premium-reports":  { sla: ENTERPRISE_SLA, actual: null, status: "not_separately_monitored" },
    },
    credit_policy: "SLA credit of 10% per day of breach, up to 30% of monthly fee. Contact bivash@cyberdudebivash.com with this report to claim.",
    certifier:     "CYBERDUDEBIVASH SENTINEL APEX -- v201.0 GOD-MODE",
    gstin:         "21ARKPN8270G1ZP",
    rid,
  });
}

/* ===========================================================================
   handleSLAIncidents  -- GET /api/sla/incidents  (Enterprise)
   =========================================================================== */
export async function handleSLAIncidents(request, env, auth, rid) {
  if (!auth || (!auth.key && !auth.jwt)) return _jsonErr(401, "Authentication required.", rid);
  if (auth.tier !== "ENTERPRISE" && auth.tier !== "MSSP") return _jsonErr(403, "Enterprise tier required.", rid);

  const incidents = await _loadIncidents(env);
  const url = new URL(request.url);
  const limit = Math.min(100, safeNum(parseInt(url.searchParams.get("limit") || "50"), 50));

  return _json(200, {
    incidents: incidents.slice(-limit),
    total:     incidents.length,
    rid,
  });
}

/* ===========================================================================
   handleSLAPing  -- POST /api/sla/ping  (internal cron/admin)
   Records heartbeats from the external prober (scripts/sla_heartbeat.py,
   every 10 minutes via .github/workflows/sla-heartbeat.yml).
   =========================================================================== */
export async function handleSLAPing(request, env, rid) {
  const secret = request.headers.get("X-Admin-Secret") || "";
  const envSecret = env.WORKER_ADMIN_SECRET || "";
  if (!envSecret || !timingSafeEqual(secret, envSecret)) {
    return _jsonErr(403, "Admin secret required for SLA ping.", rid);
  }

  let body;
  try { body = await request.json(); } catch { body = {}; }

  // 2026-09-26: the heartbeat is an external prober (.github/workflows/
  // sla-heartbeat.yml via scripts/sla_heartbeat.py). A failed probe is often
  // observed while this Worker is unreachable, so the prober replays it later:
  // it sends observed_at (when the probe ran) and a probe_id (so a replay that
  // already landed is not counted twice), several at once via `pings`.
  // A body without them records one ping at the Worker's clock, as before.
  const now   = Date.now();
  const batch = Array.isArray(body.pings) ? body.pings.slice(0, SLA_MAX_BATCH) : [body];
  const cutoff = now - 35 * 86400000;

  const pings = await _loadPings(env);
  const seen  = new Set(pings.map(p => p.probe_id).filter(Boolean));
  const added = [];
  for (const b of batch) {
    const ping = _pingFromBody(b || {}, request, now);
    if (ping.ts <= cutoff) continue;
    if (ping.probe_id && seen.has(ping.probe_id)) continue;
    if (ping.probe_id) seen.add(ping.probe_id);
    pings.push(ping);
    added.push(ping);
  }

  // Keep only last 35 days of pings, in time order (replays arrive late).
  pings.sort((a, b) => a.ts - b.ts);
  const trimmed = pings.filter(p => p.ts > cutoff).slice(-10000);

  // Incident = 3+ consecutive failures. One incident per failure streak,
  // extended while the streak lasts (previously every further failure
  // recorded another overlapping incident).
  if (added.some(p => !p.ok)) {
    await _syncIncidents(env, trimmed);
  }

  if (env.SECURITY_HUB_KV && added.length) {
    await env.SECURITY_HUB_KV.put(SLA_PING_KEY, JSON.stringify(trimmed), { expirationTtl: PING_TTL });
  }

  const last = added[added.length - 1];
  return _json(200, {
    recorded: added.length > 0,
    recorded_count: added.length,
    duplicates_skipped: batch.length - added.length,
    ts: last ? new Date(last.ts).toISOString() : null,
    ok: last ? last.ok : null,
    rid,
  });
}

// One ping from an untrusted-shape body (the caller is authenticated, but the
// fields are still bounded). observed_at is honoured only within the retention
// window and not more than a minute ahead of this Worker's clock.
function _pingFromBody(b, request, now) {
  let ts = now;
  if (typeof b.observed_at === "string") {
    const t = Date.parse(b.observed_at);
    if (Number.isFinite(t) && t <= now + 60000) ts = Math.min(t, now);
  }
  const probeId = typeof b.probe_id === "string" && /^[A-Za-z0-9._:-]{1,64}$/.test(b.probe_id) ? b.probe_id : null;
  const ping = {
    ts,
    ok:        b.ok !== false,
    latency:   safeNum(b.latency_ms, 0),
    component: safe(b.component, "intel-gateway").slice(0, 64),
    region:    safe(b.region || (request.cf?.colo) || "unknown").slice(0, 64),
    note:      safe(b.note || "", "").slice(0, 200),
  };
  if (probeId) ping.probe_id = probeId;
  return ping;
}

// Failure streaks of 3+ in the (time-ordered) ping list, per component.
export function _failureStreaks(pings) {
  const byComp = new Map();
  for (const p of pings) {
    if (!byComp.has(p.component)) byComp.set(p.component, []);
    byComp.get(p.component).push(p);
  }
  const streaks = [];
  for (const [component, list] of byComp) {
    let run = [];
    const flush = () => {
      if (run.length >= 3) streaks.push({ component, start: run[0].ts, end: run[run.length - 1].ts, count: run.length });
      run = [];
    };
    for (const p of list) { if (p.ok) flush(); else run.push(p); }
    flush();
  }
  return streaks;
}

async function _syncIncidents(env, pings) {
  if (!env.SECURITY_HUB_KV) return;
  try {
    const incidents = await _loadIncidents(env);
    let changed = false;
    for (const s of _failureStreaks(pings)) {
      const startIso = new Date(s.start).toISOString();
      const existing = incidents.find(i => i.auto_detected && i.component === s.component && i.start === startIso);
      const duration = s.end - s.start;
      if (existing) {
        if (existing.duration_ms !== duration) {
          existing.duration_ms = duration;
          existing.failed_checks = s.count;
          changed = true;
        }
      } else {
        incidents.push({
          start:         startIso,
          component:     s.component,
          severity:      "P2",
          description:   "3+ consecutive health check failures detected.",
          duration_ms:   duration,
          failed_checks: s.count,
          auto_detected: true,
          id:            `INC-${s.start.toString(36).toUpperCase()}`,
        });
        changed = true;
      }
    }
    if (changed) {
      incidents.sort((a, b) => new Date(a.start) - new Date(b.start));
      await env.SECURITY_HUB_KV.put(SLA_INCIDENT_KEY, JSON.stringify(incidents.slice(-500)), { expirationTtl: PING_TTL });
    }
  } catch {}
}

/* ===========================================================================
   handleSLACertificate  -- GET /api/sla/certificate  (Enterprise)
   Returns SLA compliance certificate as JSON (can be rendered to PDF)
   =========================================================================== */
// PRODUCTION-TRUTH FIX (post-launch platform audit): this certificate --
// the one formal document an Enterprise customer can hand to their OWN
// auditors as compliance evidence -- hardcoded sla_status: "COMPLIANT"
// unconditionally. It never called _loadPings/_loadIncidents, the same real
// data handleSLAStatus and handleSLAReport (both fixed for this exact class
// of bug in PR #237 -- "previously defaulted to a fabricated 100%/'MET'
// when there was zero ping data") already load two functions above. A
// customer requesting this certificate during a real outage, or before any
// monitoring history existed at all, still received a signed-looking
// "COMPLIANT" document. Fixed to compute the same real uptime/incident
// data as its siblings and report INSUFFICIENT_DATA honestly, matching
// their established precedent, rather than issue a certificate with no
// verification behind it.
export async function handleSLACertificate(request, env, auth, rid) {
  if (!auth || (!auth.key && !auth.jwt)) return _jsonErr(401, "Authentication required.", rid);
  if (auth.tier !== "ENTERPRISE" && auth.tier !== "MSSP") return _jsonErr(403, "Enterprise tier required.", rid);

  const now = new Date();
  const periodEnd   = now.toISOString().split("T")[0];
  const periodStart = new Date(now - SLA_WINDOW_DAYS * 86400000).toISOString().split("T")[0];

  const pings    = await _loadPings(env);
  const incidents = await _loadIncidents(env);
  const nowMs    = now.getTime();
  const windowMs = SLA_WINDOW_DAYS * 24 * 60 * 60 * 1000;

  const recentPings = pings.filter(p => (nowMs - p.ts) <= windowMs);
  const upCount      = recentPings.filter(p => p.ok).length;
  const hasData      = recentPings.length > 0;
  const pingUptime   = hasData ? (upCount / recentPings.length) * 100 : null;
  const lastPing     = pings[pings.length - 1];
  const lastPingAgeS = lastPing ? Math.round((nowMs - lastPing.ts) / 1000) : null;
  const monitoringCurrent = lastPingAgeS !== null && lastPingAgeS < HEARTBEAT_STALE_S;

  const recentIncidents = incidents.filter(i => (nowMs - new Date(i.start).getTime()) <= windowMs);
  const totalDownMs     = recentIncidents.reduce((acc, i) => acc + (i.duration_ms || 0), 0);
  const incidentUptime  = Math.min(100, ((windowMs - totalDownMs) / windowMs) * 100);

  // Same "take the more conservative real signal" combination handleSLAStatus
  // uses -- an incident can be recorded (and thus count against uptime) even
  // in a window with sparse ping coverage.
  const actualUptime = hasData ? Math.min(pingUptime, incidentUptime) : null;
  const slaStatus = !hasData
    ? "INSUFFICIENT_DATA"
    : !monitoringCurrent
      ? "MONITORING_DELAYED"
      : (actualUptime >= ENTERPRISE_SLA ? "COMPLIANT" : "BREACHED");

  return _json(200, {
    certificate: {
      title:          "SENTINEL APEX Enterprise SLA Compliance Certificate",
      issued_to:      safe(auth.sub, "Enterprise Subscriber"),
      issued_by:      "CYBERDUDEBIVASH SENTINEL APEX",
      gstin:          "21ARKPN8270G1ZP",
      period:         `${periodStart} to ${periodEnd}`,
      sla_target:     `${ENTERPRISE_SLA}% uptime`,
      sla_status:     slaStatus,
      measured_uptime_pct: hasData ? parseFloat(actualUptime.toFixed(4)) : null,
      incidents_in_period: recentIncidents.length,
      monitoring_current:  monitoringCurrent,
      last_ping_age_seconds: lastPingAgeS,
      monitoring_basis:    !hasData
        ? "No monitoring data recorded for this period -- compliance cannot be verified."
        : !monitoringCurrent
          ? `Historical data exists (${recentPings.length} health check(s)), but the external heartbeat is stale; current compliance cannot be verified.`
          : `${recentPings.length} health check(s) + ${recentIncidents.length} recorded incident(s) over the period`,
      platform_url:   "https://intel.cyberdudebivash.com",
      support_email:  "bivash@cyberdudebivash.com",
      version:        "201.0 GOD-MODE",
      issued_at:      now.toISOString(),
      cert_id:        `APEX-CERT-${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${Date.now().toString(36).toUpperCase()}`,
    },
    rid,
  });
}

/* -- Internal helpers --------------------------------------------------------- */
async function _loadPings(env) {
  if (!env.SECURITY_HUB_KV) return [];
  try { return JSON.parse(await env.SECURITY_HUB_KV.get(SLA_PING_KEY) || "[]"); } catch { return []; }
}

async function _loadIncidents(env) {
  if (!env.SECURITY_HUB_KV) return [];
  try { return JSON.parse(await env.SECURITY_HUB_KV.get(SLA_INCIDENT_KEY) || "[]"); } catch { return []; }
}

function _json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "X-Sentinel-Version": "201.0" },
  });
}

function _jsonErr(status, message, rid) {
  return _json(status, { error: true, message, rid, version: "201.0" });
}
