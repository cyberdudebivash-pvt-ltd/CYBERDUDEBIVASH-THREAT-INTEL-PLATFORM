/**
 * Enterprise Evidence Service Platform  -  Stage 12 Phase 6, Service Observability
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Service-layer metrics, distinct from Stage 11's EvidenceRegistryMetrics (registry-metrics.js,
 * unmodified, unduplicated): that class counts registry-level events (evidence count, lifecycle
 * transitions, validation failures, version updates, migration events, feature-flag
 * activations). This class counts SERVICE-layer concerns Stage 11 has no equivalent for  -  call
 * latency, query statistics, relationship-resolution outcomes  -  and does not re-count anything
 * EvidenceRegistryMetrics already tracks. EvidenceMetricsService (evidence-service.js) merges
 * both into one snapshot rather than this class duplicating the registry's counters itself.
 *
 * "No customer telemetry"  -  same passive-accumulator design as registry-metrics.js: nothing
 * here calls fetch(), an Analytics Engine binding, or any external sink.
 */

const EMPTY_COUNTS = () => ({});

export class ServicePlatformMetrics {
  constructor() {
    this._callCounts = EMPTY_COUNTS();
    this._callLatenciesMs = EMPTY_COUNTS(); // operation -> array of durations (ms)
    this._queryCounts = EMPTY_COUNTS(); // dimension -> count (Phase 2 query engine)
    this._relationshipResolutions = 0;
    this._relationshipResolutionFailures = 0;
    this._provenanceLookups = EMPTY_COUNTS(); // lineage kind -> count (Phase 3)
    this._validationFailures = 0;
    this._contractVersionMismatches = 0;
  }

  _increment(bag, key) {
    bag[key] = (bag[key] || 0) + 1;
  }

  /**
   * Wraps an operation, recording its call count and latency under `name`. Returns whatever the
   * operation returns (or rethrows whatever it throws, after still recording latency  -  a failed
   * call still took time and is still worth observing).
   * @template T
   * @param {string} name
   * @param {() => Promise<T> | T} operation
   * @returns {Promise<T>}
   */
  async timed(name, operation) {
    this._increment(this._callCounts, name);
    const start = performance.now();
    try {
      return await operation();
    } finally {
      const elapsed = performance.now() - start;
      if (!this._callLatenciesMs[name]) this._callLatenciesMs[name] = [];
      this._callLatenciesMs[name].push(elapsed);
    }
  }

  /** @param {string} dimension - e.g. "cve", "threatActor", "uuid" */
  recordQuery(dimension) {
    this._increment(this._queryCounts, dimension);
  }

  /** @param {boolean} succeeded */
  recordRelationshipResolution(succeeded) {
    this._relationshipResolutions += 1;
    if (!succeeded) this._relationshipResolutionFailures += 1;
  }

  /** @param {string} lineageKind - e.g. "version", "relationship", "confidence", "source", "audit", "evidence" */
  recordProvenanceLookup(lineageKind) {
    this._increment(this._provenanceLookups, lineageKind);
  }

  recordValidationFailure() {
    this._validationFailures += 1;
  }

  recordContractVersionMismatch() {
    this._contractVersionMismatches += 1;
  }

  /**
   * Summary statistics (count, mean, p50, p95, max) per recorded operation name. Computed from
   * `this._callLatenciesMs` on demand rather than maintained incrementally  -  this is an
   * in-memory diagnostic aggregate, not a hot path; recomputing on snapshot() keeps the
   * recording side (`timed()`) trivially cheap.
   */
  _latencyStats() {
    const stats = {};
    for (const [name, samples] of Object.entries(this._callLatenciesMs)) {
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

  /** Point-in-time copy of every counter. A plain object, not `this`, per registry-metrics.js's precedent. */
  snapshot() {
    return {
      call_counts: { ...this._callCounts },
      call_latency_stats: this._latencyStats(),
      query_counts: { ...this._queryCounts },
      relationship_resolutions: this._relationshipResolutions,
      relationship_resolution_failures: this._relationshipResolutionFailures,
      provenance_lookups: { ...this._provenanceLookups },
      validation_failures: this._validationFailures,
      contract_version_mismatches: this._contractVersionMismatches,
    };
  }
}
