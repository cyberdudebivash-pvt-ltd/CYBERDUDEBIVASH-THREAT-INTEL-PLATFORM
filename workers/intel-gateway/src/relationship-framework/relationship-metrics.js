/**
 * Relationship Metrics Service -- Stage 16 Phase 1 + Phase 7 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Plain in-memory counters, exposed via snapshot() -- mirrors evidence-registry/service-metrics.js
 * and registry-metrics.js's exact pattern and "no external telemetry" discipline: nothing here
 * calls fetch(), an Analytics Engine binding, or any other external sink. This is Phase 7's own
 * observability requirement (traversal latency, correlation metrics, validation failures,
 * confidence propagation metrics) implemented as the same passive-accumulator idiom every prior
 * TITAN stage in this repository used, not a new telemetry mechanism.
 */

const EMPTY_COUNTS = () => ({});

export class RelationshipMetricsService {
  constructor() {
    this._traversalLatenciesMs = EMPTY_COUNTS(); // operation name -> array of durations
    this._correlationCounts = EMPTY_COUNTS(); // dimension -> count
    this._validationFailures = 0;
    this._validationFailuresByReason = EMPTY_COUNTS();
    this._confidencePropagations = 0;
    this._confidencePropagationSum = 0;
    this._resolutionsViaProvider = 0;
  }

  _increment(bag, key) {
    bag[key] = (bag[key] || 0) + 1;
  }

  /** @param {string} operation @param {number} durationMs */
  recordTraversalLatency(operation, durationMs) {
    if (!this._traversalLatenciesMs[operation]) this._traversalLatenciesMs[operation] = [];
    this._traversalLatenciesMs[operation].push(durationMs);
  }

  /** @param {string} dimension - e.g. "evidence", "relationship", "ioc" */
  recordCorrelation(dimension) {
    this._increment(this._correlationCounts, dimension);
  }

  /** @param {string} [reason] */
  recordValidationFailure(reason) {
    this._validationFailures += 1;
    if (reason) this._increment(this._validationFailuresByReason, reason);
  }

  /**
   * Confidence propagation: recorded every time a relationship's confidence is carried forward
   * into a derived result (e.g. traversal aggregating edge confidences, correlation attaching a
   * relationship's confidence to a correlated record) -- Phase 7's own named metric.
   * @param {number} confidenceValue
   */
  recordConfidencePropagation(confidenceValue) {
    this._confidencePropagations += 1;
    this._confidencePropagationSum += confidenceValue;
  }

  recordResolutionViaProvider() {
    this._resolutionsViaProvider += 1;
  }

  _latencyStats() {
    const stats = {};
    for (const [name, samples] of Object.entries(this._traversalLatenciesMs)) {
      if (samples.length === 0) continue;
      const sorted = [...samples].sort((a, b) => a - b);
      const sum = sorted.reduce((total, value) => total + value, 0);
      stats[name] = {
        count: sorted.length,
        mean_ms: Number((sum / sorted.length).toFixed(3)),
        p50_ms: Number(sorted[Math.floor(sorted.length * 0.5)].toFixed(3)),
        p95_ms: Number(sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))].toFixed(3)),
        max_ms: Number(sorted[sorted.length - 1].toFixed(3)),
      };
    }
    return stats;
  }

  /** Point-in-time copy of every counter. A plain object, not `this`, per this platform's established convention. */
  snapshot() {
    return {
      traversal_latency_stats: this._latencyStats(),
      correlation_counts: { ...this._correlationCounts },
      validation_failures: this._validationFailures,
      validation_failures_by_reason: { ...this._validationFailuresByReason },
      confidence_propagations: this._confidencePropagations,
      average_propagated_confidence:
        this._confidencePropagations > 0
          ? Number((this._confidencePropagationSum / this._confidencePropagations).toFixed(4))
          : null,
      resolutions_via_provider: this._resolutionsViaProvider,
    };
  }
}
