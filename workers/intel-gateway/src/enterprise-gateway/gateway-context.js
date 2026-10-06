/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Context (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * GatewayContext is the immutable, per-call value threaded through GatewayDispatcher's
 * middleware chain and into the resolved capability handler. Frozen at construction and by
 * every subsequent with() call, matching this codebase's existing freeze-heavy convention
 * (CanonicalEvidence version records, every *_FLAGS table, every service-contracts.js entry) --
 * a middleware stage that wants to enrich context for stages downstream of it calls with({...})
 * and passes the RETURNED instance to next(), it never mutates the one it received.
 */

function generateCorrelationId() {
  return crypto.randomUUID();
}

export class GatewayContext {
  /**
   * @param {{correlationId?: string, caller?: {id: string, kind?: string}, capability: string,
   *   grantedCapabilities?: string[], environment?: string, featureFlags?: object,
   *   metadata?: object, startedAt?: number}} input
   */
  constructor(input = {}) {
    if (!input.capability || typeof input.capability !== "string") {
      throw new Error("GatewayContext requires a non-empty string 'capability'");
    }
    this.correlationId = input.correlationId || generateCorrelationId();
    this.caller = Object.freeze({ id: "unknown", kind: "unknown", ...(input.caller || {}) });
    this.capability = input.capability;
    this.grantedCapabilities = Object.freeze([...(input.grantedCapabilities || [])]);
    this.environment = input.environment || "production";
    this.featureFlags = Object.freeze({ ...(input.featureFlags || {}) });
    this.metadata = Object.freeze({ ...(input.metadata || {}) });
    this.startedAt = input.startedAt || Date.now();
    Object.freeze(this);
  }

  /** @param {string} name @returns {boolean} */
  hasCapability(name) {
    return this.grantedCapabilities.includes(name);
  }

  /**
   * Returns a NEW frozen GatewayContext with `patch` merged in -- never mutates `this`.
   * `correlationId` and `startedAt` always carry forward unless explicitly overridden, so a
   * middleware stage enriching context can never accidentally split a call's correlation id or
   * reset its elapsed-time origin partway through the chain.
   * @param {object} patch
   * @returns {GatewayContext}
   */
  with(patch = {}) {
    return new GatewayContext({
      correlationId: this.correlationId,
      caller: this.caller,
      capability: this.capability,
      grantedCapabilities: this.grantedCapabilities,
      environment: this.environment,
      featureFlags: this.featureFlags,
      metadata: this.metadata,
      startedAt: this.startedAt,
      ...patch,
    });
  }
}
