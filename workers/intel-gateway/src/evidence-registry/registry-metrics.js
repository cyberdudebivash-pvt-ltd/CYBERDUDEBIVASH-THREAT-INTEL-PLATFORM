/**
 * Evidence Registry Observability  -  Stage 11 Phase 9 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Plain in-memory counters, exposed via snapshot(). "No external telemetry changes"  -  nothing
 * here calls fetch(), an Analytics Engine binding, or any other external sink; this is a
 * passive accumulator a future, separately-authorized integration could read from (e.g. to
 * populate a data/quality/ report, matching this platform's existing convention), not a live
 * telemetry pipeline itself.
 */

const EMPTY_COUNTS = () => ({});

export class EvidenceRegistryMetrics {
  constructor() {
    this._evidenceCount = 0;
    this._lifecycleTransitions = 0;
    this._lifecycleTransitionsByType = EMPTY_COUNTS();
    this._validationFailures = 0;
    this._versionUpdates = 0;
    this._migrationEvents = 0;
    this._adapterUsage = EMPTY_COUNTS();
    this._featureFlagActivations = EMPTY_COUNTS();
  }

  _increment(bag, key) {
    bag[key] = (bag[key] || 0) + 1;
  }

  /** @param {1 | -1} delta */
  recordEvidenceCountDelta(delta) {
    this._evidenceCount += delta;
  }

  /** @param {string} fromState @param {string} toState */
  recordLifecycleTransition(fromState, toState) {
    this._lifecycleTransitions += 1;
    this._increment(this._lifecycleTransitionsByType, `${fromState}->${toState}`);
  }

  recordValidationFailure() {
    this._validationFailures += 1;
  }

  recordVersionUpdate() {
    this._versionUpdates += 1;
  }

  /** @param {string} adapterName */
  recordMigrationEvent(adapterName) {
    this._migrationEvents += 1;
    this._increment(this._adapterUsage, adapterName || "unknown");
  }

  /** @param {string} flagName */
  recordFeatureFlagActivation(flagName) {
    this._increment(this._featureFlagActivations, flagName || "unknown");
  }

  /**
   * Point-in-time copy of every counter. A plain object (not `this`) so callers can't mutate
   * live counters through the returned reference.
   */
  snapshot() {
    return {
      evidence_count: this._evidenceCount,
      lifecycle_transitions: this._lifecycleTransitions,
      lifecycle_transitions_by_type: { ...this._lifecycleTransitionsByType },
      validation_failures: this._validationFailures,
      version_updates: this._versionUpdates,
      migration_events: this._migrationEvents,
      adapter_usage: { ...this._adapterUsage },
      feature_flag_activations: { ...this._featureFlagActivations },
    };
  }
}
