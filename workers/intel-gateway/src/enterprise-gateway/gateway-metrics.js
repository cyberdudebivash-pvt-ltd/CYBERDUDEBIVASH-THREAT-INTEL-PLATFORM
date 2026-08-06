/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Metrics (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Wraps platform.metrics (IntelligenceMetricsService) for its .sharedServiceMetrics getter --
 * the ONE ServicePlatformMetrics instance threaded through evidence-registry/, intelligence-
 * platform/, and now this gateway. GatewayMetrics constructs NO ServicePlatformMetrics of its
 * own; it owns exactly three genuinely-new counters with no existing home anywhere in the
 * platform (feature-flag evaluations, capability-authorization denials, middleware validation
 * failures -- all gateway-REQUEST-level concerns, distinct from the evidence/intelligence DATA
 * validation failures ServicePlatformMetrics.recordValidationFailure() already exists for),
 * plus a bounded audit-entry ring buffer. snapshot() merges all three layers -- registry
 * (Stage 11), service (Stage 12+13, shared), gateway (this stage, genuinely new). This is
 * EvidenceMetricsService's (Stage 12) actual-merge shape, not IntelligenceMetricsService's
 * (Stage 13) pure-passthrough shape -- Stage 13 added no counters of its own so passthrough was
 * correct there; Stage 14 does add counters, so it needs the merge behavior instead.
 *
 * "No duplicate metrics instances" is verified three ways, mirroring how Stage 13 caught and
 * fixed its own version of this exact bug: structurally, by gateway-service.js's construction
 * order; behaviorally, by __tests__/metrics-sharing.test.js (identity assertion); and by
 * scripts/titan_architecture_governance_check.py's check_eig_metrics_no_duplicate_instance().
 */

const AUDIT_BUFFER_LIMIT = 100;

export class GatewayMetrics {
  /** @param {import('../intelligence-platform/intelligence-service.js').IntelligenceMetricsService} intelligenceMetrics */
  constructor(intelligenceMetrics) {
    if (!intelligenceMetrics) {
      throw new Error("GatewayMetrics requires an intelligenceMetrics (platform.metrics) dependency");
    }
    this._intelligenceMetrics = intelligenceMetrics;
    this._featureFlagEvaluations = {}; // environment -> { enabled: n, disabled: n }
    this._capabilityAuthorizationDenials = {}; // capability -> count
    this._middlewareValidationFailures = {}; // capability -> count
    this._auditEntries = [];
  }

  /** @returns {import('../evidence-registry/service-metrics.js').ServicePlatformMetrics} the single shared instance */
  get sharedServiceMetrics() {
    return this._intelligenceMetrics.sharedServiceMetrics;
  }

  /** @param {string} environment @param {boolean} enabled */
  recordFeatureFlagEvaluation(environment, enabled) {
    if (!this._featureFlagEvaluations[environment]) {
      this._featureFlagEvaluations[environment] = { enabled: 0, disabled: 0 };
    }
    this._featureFlagEvaluations[environment][enabled ? "enabled" : "disabled"] += 1;
  }

  /** @param {string} capability */
  recordCapabilityAuthorizationDenial(capability) {
    this._capabilityAuthorizationDenials[capability] = (this._capabilityAuthorizationDenials[capability] || 0) + 1;
  }

  /** @param {string} capability */
  recordMiddlewareValidationFailure(capability) {
    this._middlewareValidationFailures[capability] = (this._middlewareValidationFailures[capability] || 0) + 1;
  }

  /**
   * @param {{correlationId: string, capability: string, method: string, caller: object,
   *   outcome: "success"|"failure", elapsedMs: number, timestamp: string}} entry
   */
  recordAuditEntry(entry) {
    this._auditEntries.push(Object.freeze({ ...entry }));
    if (this._auditEntries.length > AUDIT_BUFFER_LIMIT) {
      this._auditEntries.shift();
    }
  }

  recentAuditEntries() {
    return [...this._auditEntries];
  }

  /** Merged point-in-time snapshot: {registry, service} (Stage 11 + shared Stage 12/13) + gateway (this stage). */
  snapshot() {
    return {
      ...this._intelligenceMetrics.snapshot(),
      gateway: {
        feature_flag_evaluations: { ...this._featureFlagEvaluations },
        capability_authorization_denials: { ...this._capabilityAuthorizationDenials },
        middleware_validation_failures: { ...this._middlewareValidationFailures },
        recent_audit_entries: this.recentAuditEntries(),
      },
    };
  }
}
