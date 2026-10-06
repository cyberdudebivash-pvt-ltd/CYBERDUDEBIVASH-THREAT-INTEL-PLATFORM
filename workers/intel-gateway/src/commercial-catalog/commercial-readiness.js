/**
 * Commercial Catalog (Project TITAN Stage 21 Phase 7) -- Commercial Readiness Publisher.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md.
 *
 * Publishes, per catalog entry: description, owner, dependencies, commercial value, internal
 * consumers, security level, expected latency, documentation status (catalog.js, static) plus
 * observed registration state and, when available, measured latency against the declared budget
 * (CommercialMetrics, live). Read-only composition over catalog.js + commercial-metrics.js -- no
 * new scoring/grading logic; this is presentation over already-computed/already-declared data, the
 * same "no new scorer" discipline the P39 Commercial Quality Orchestrator holds itself to
 * (check_commercial_orchestrator_no_new_scorer(), mirrored by this stage's own governance check --
 * see Phase 6).
 *
 * Distinct from scripts/commercial_readiness_auditor.py / commercial_readiness_governor.py /
 * p24_commercial_certification.py -- those score/govern DATA ITEMS or the release as a whole;
 * this module describes GATEWAY SERVICES. See audit doc Sec 2.4 for the verified non-duplication
 * rationale.
 */

import { COMMERCIAL_SERVICE_CATALOG } from "./catalog.js";

/**
 * @param {import('./catalog.js').CommercialCatalogEntry} entry
 * @param {import('./commercial-metrics.js').CommercialMetrics|null} metrics
 * @returns {object}
 */
export function buildCommercialReadinessEntry(entry, metrics = null) {
  const capabilityId = entry.newAdapter ? entry.id : entry.gatewayCapability;
  let observed = null;
  if (metrics) {
    const snapshot = metrics.sharedServiceMetrics.snapshot();
    const stats = snapshot.call_latency_stats[`gateway.${capabilityId}`];
    if (stats) {
      observed = {
        invocationCount: stats.count,
        p50Ms: stats.p50_ms,
        p95Ms: stats.p95_ms,
        withinLatencyBudget: stats.p95_ms <= entry.expectedLatencyMs,
      };
    }
  }
  return {
    id: entry.id,
    name: entry.name,
    description: entry.description,
    owner: entry.owner,
    dependencies: entry.dependencies,
    commercialValue: entry.commercialValue,
    internalConsumers: entry.internalConsumers,
    securityLevel: entry.securityClassification,
    visibility: entry.visibility,
    lifecycle: entry.lifecycle,
    expectedLatencyMs: entry.expectedLatencyMs,
    documentationStatus: entry.documentationStatus,
    classification: entry.classification,
    observed,
  };
}

/**
 * @param {{gateway?: import('../enterprise-gateway/gateway-service.js').EnterpriseGateway,
 *   metrics?: import('./commercial-metrics.js').CommercialMetrics}} [options]
 * @returns {{generatedAt: string, catalogSize: number, gaCount: number, betaCount: number,
 *   blockedCount: number, entries: object[], serviceHealth: object[]|null}}
 */
export function buildCommercialReadinessReport({ gateway = null, metrics = null } = {}) {
  const entries = COMMERCIAL_SERVICE_CATALOG.map((entry) => buildCommercialReadinessEntry(entry, metrics));
  const countByLifecycle = (lifecycle) => entries.filter((entry) => entry.lifecycle === lifecycle).length;
  return {
    generatedAt: new Date().toISOString(),
    catalogSize: entries.length,
    gaCount: countByLifecycle("ga"),
    betaCount: countByLifecycle("beta"),
    blockedCount: countByLifecycle("blocked-pending-wiring"),
    entries,
    serviceHealth: metrics && gateway ? metrics.commercialServiceHealth(gateway) : null,
  };
}
