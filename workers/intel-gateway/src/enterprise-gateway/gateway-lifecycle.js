/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Lifecycle (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Three-state lifecycle (INIT -> READY -> STOPPED) for one EnterpriseGateway instance, mirroring
 * evidence-registry/lifecycle.js's pure-transition-table pattern at gateway-instance scale.
 * Unlike lifecycle.js (which deliberately holds no state itself -- registry-service.js is the
 * one authority on any given evidence record's current state), GatewayLifecycle DOES hold state
 * directly: there is exactly one lifecycle per gateway instance, constructed and owned by
 * gateway-service.js, so there is no separate registry for it to defer to.
 *
 *   INIT -> READY -> STOPPED
 *     \-------------------/
 */

export const GATEWAY_LIFECYCLE_STATES = Object.freeze(["INIT", "READY", "STOPPED"]);

const GATEWAY_LIFECYCLE_TRANSITIONS = Object.freeze({
  INIT: Object.freeze(["READY", "STOPPED"]),
  READY: Object.freeze(["STOPPED"]),
  STOPPED: Object.freeze([]),
});

export class IllegalGatewayLifecycleTransitionError extends Error {
  constructor(fromState, toState) {
    const legal = GATEWAY_LIFECYCLE_TRANSITIONS[fromState];
    super(
      `Illegal gateway lifecycle transition: ${fromState} -> ${toState}. Legal transitions ` +
        `from ${fromState}: [${legal && legal.length ? legal.join(", ") : "none (terminal state)"}]`
    );
    this.name = "IllegalGatewayLifecycleTransitionError";
    this.fromState = fromState;
    this.toState = toState;
  }
}

/** @param {string} fromState @param {string} toState @returns {boolean} */
export function canTransitionGatewayLifecycle(fromState, toState) {
  return Boolean(
    GATEWAY_LIFECYCLE_TRANSITIONS[fromState] && GATEWAY_LIFECYCLE_TRANSITIONS[fromState].includes(toState)
  );
}

export class GatewayLifecycle {
  constructor() {
    this._state = "INIT";
    this._transitionedAt = { INIT: Date.now() };
  }

  get state() {
    return this._state;
  }

  _transitionTo(toState) {
    if (!canTransitionGatewayLifecycle(this._state, toState)) {
      throw new IllegalGatewayLifecycleTransitionError(this._state, toState);
    }
    this._state = toState;
    this._transitionedAt[toState] = Date.now();
  }

  /** INIT -> READY. */
  markReady() {
    this._transitionTo("READY");
  }

  /** READY -> STOPPED (or INIT -> STOPPED, e.g. an aborted startup). */
  stop() {
    this._transitionTo("STOPPED");
  }

  isReady() {
    return this._state === "READY";
  }

  healthCheck() {
    return {
      state: this._state,
      ready: this.isReady(),
      transitionedAt: { ...this._transitionedAt },
    };
  }
}
