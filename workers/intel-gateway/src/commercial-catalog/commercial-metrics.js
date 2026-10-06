/**
 * Commercial Catalog (Project TITAN Stage 21 Phase 5) -- Commercial Observability.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md.
 *
 * Reuse-first, mirroring gateway-metrics.js's own precedent exactly: most of what Phase 5 asks
 * for already exists and is reused unchanged, not rebuilt --
 *   - Tracing: gateway-middleware.js's tracingMiddleware (correlation-id span logging) already
 *     wraps every dispatched capability, commercial ones included. Not touched.
 *   - Latency + invocation counters: GatewayDispatcher.dispatch() already wraps every call in the
 *     SHARED ServicePlatformMetrics.timed("gateway.<capability>", ...) (gateway-dispatcher.js:79)
 *     -- every commercial adapter, once registered via registerCapability(), gets per-capability
 *     count/mean/p50/p95/max latency for free under that same key. CommercialMetrics.snapshot()
 *     below reads that data back rather than re-counting it a second time (which would violate
 *     "exactly one shared instance", the same property GatewayMetrics/EIPS metrics already
 *     guard).
 *   - Gateway health: EnterpriseGateway.healthCheck() already exists, reused unchanged.
 *
 * The one genuinely new concern Phase 5 asks for with no existing home: FAILURE CLASSIFICATION.
 * ServicePlatformMetrics.timed() records that a call failed and how long it took, but nothing
 * classifies WHY. CommercialMetrics owns exactly that one new counter set, plus a Service Health
 * rollup cross-referencing the catalog against what's actually registered -- the same "exactly
 * the genuinely-new part, nothing more" discipline gateway-metrics.js's own module docstring
 * documents for itself.
 */

import { COMMERCIAL_SERVICE_CATALOG } from "./catalog.js";
import { CommercialAdapterValidationError } from "./commercial-adapters.js";

export const FAILURE_CLASSIFICATIONS = Object.freeze([
  "validation",
  "not_wired",
  "upstream_unavailable",
  "unexpected",
]);

/**
 * Pure classification function -- no side effects, easy to unit test independently of any
 * metrics instance.
 * @param {unknown} error
 * @returns {"validation"|"not_wired"|"upstream_unavailable"|"unexpected"}
 */
export function classifyCommercialAdapterError(error) {
  if (error instanceof CommercialAdapterValidationError) return "validation";
  const message = error && typeof error === "object" && "message" in error ? String(error.message) : "";
  if (/NOT_WIRED/i.test(message)) return "not_wired";
  if (/unavailable|ECONNREFUSED|timeout/i.test(message)) return "upstream_unavailable";
  return "unexpected";
}

export class CommercialMetrics {
  /** @param {{gatewayMetrics: import('../enterprise-gateway/gateway-metrics.js').GatewayMetrics}} deps */
  constructor({ gatewayMetrics } = {}) {
    if (!gatewayMetrics) {
      throw new Error("CommercialMetrics requires a gatewayMetrics dependency");
    }
    this._gatewayMetrics = gatewayMetrics;
    this._failuresByCapability = {}; // capabilityId -> {validation: n, not_wired: n, upstream_unavailable: n, unexpected: n}
  }

  /** @returns {import('../evidence-registry/service-metrics.js').ServicePlatformMetrics} the single shared instance */
  get sharedServiceMetrics() {
    return this._gatewayMetrics.sharedServiceMetrics;
  }

  /**
   * @param {string} capabilityId
   * @param {"validation"|"not_wired"|"upstream_unavailable"|"unexpected"} classification
   */
  recordFailure(capabilityId, classification) {
    if (!this._failuresByCapability[capabilityId]) {
      this._failuresByCapability[capabilityId] = Object.fromEntries(FAILURE_CLASSIFICATIONS.map((c) => [c, 0]));
    }
    this._failuresByCapability[capabilityId][classification] += 1;
  }

  /**
   * Wraps a commercial adapter handler with failure classification -- catches, classifies,
   * records, and always re-throws (mirroring ServicePlatformMetrics.timed()'s own "record then
   * rethrow" contract, so callers still see the real error). Composition over the adapter, not a
   * modification to it -- commercial-adapters.js has no knowledge this wrapper exists.
   * @param {string} capabilityId
   * @param {import('../enterprise-gateway/gateway-registry.js').GatewayCapabilityHandler} handler
   * @returns {import('../enterprise-gateway/gateway-registry.js').GatewayCapabilityHandler}
   */
  wrapWithFailureClassification(capabilityId, handler) {
    const metrics = this;
    return async function classifiedHandler(context, method, ...args) {
      try {
        return await handler(context, method, ...args);
      } catch (error) {
        metrics.recordFailure(capabilityId, classifyCommercialAdapterError(error));
        throw error;
      }
    };
  }

  /**
   * Service Health rollup: for every catalog entry, is its Gateway capability actually
   * registered? Cross-references the catalog (documentation-as-data) against the live registry
   * (describeAllCapabilities(), Stage 21 Phase 4) rather than trusting the catalog's own claims --
   * catches a catalog entry whose registration was forgotten or failed silently.
   * @param {import('../enterprise-gateway/gateway-service.js').EnterpriseGateway} gateway
   */
  commercialServiceHealth(gateway) {
    const registered = new Set(gateway.listCapabilities());
    return COMMERCIAL_SERVICE_CATALOG.map((entry) => {
      const capabilityId = entry.newAdapter ? entry.id : entry.gatewayCapability;
      return {
        id: entry.id,
        name: entry.name,
        lifecycle: entry.lifecycle,
        registered: registered.has(capabilityId),
      };
    });
  }

  /** Merged snapshot: {registry, service, gateway} (Stages 11-14) + commercial (this stage). */
  snapshot() {
    return {
      ...this._gatewayMetrics.snapshot(),
      commercial: {
        catalog_size: COMMERCIAL_SERVICE_CATALOG.length,
        failures_by_capability: { ...this._failuresByCapability },
      },
    };
  }
}
