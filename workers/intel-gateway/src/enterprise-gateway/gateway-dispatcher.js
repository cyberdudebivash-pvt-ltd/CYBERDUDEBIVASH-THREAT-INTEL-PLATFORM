/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Dispatcher (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Owns the full internal dispatch path: build context -> registry lookup -> capability
 * authorization -> middleware chain -> resolved handler, the whole call wrapped in the SHARED
 * ServicePlatformMetrics.timed() under a "gateway.<capability>" operation name. No knowledge of
 * GatewayLifecycle (gateway-service.js checks readiness before calling in) and no knowledge of
 * any concrete service -- it only knows GatewayRegistry entries and GatewayContext.
 */

import { GatewayContext } from "./gateway-context.js";
import { composeGatewayMiddleware, defaultGatewayMiddleware } from "./gateway-middleware.js";
import { resolveEigFlags } from "./feature-flags.js";

export class CapabilityAuthorizationError extends Error {
  constructor(capability, missing) {
    super(
      `Capability "${capability}" denied -- caller is missing required capabilit` +
        `${missing.length === 1 ? "y" : "ies"}: ${missing.join(", ")}`
    );
    this.name = "CapabilityAuthorizationError";
    this.capability = capability;
    this.missing = missing;
  }
}

export class GatewayDispatcher {
  /**
   * @param {{registry: import('./gateway-registry.js').GatewayRegistry,
   *   serviceMetrics: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics,
   *   gatewayMetrics: import('./gateway-metrics.js').GatewayMetrics,
   *   middleware?: Array<Function>}} deps
   */
  constructor(deps = {}) {
    if (!deps.registry) throw new Error("GatewayDispatcher requires a registry dependency");
    if (!deps.serviceMetrics) throw new Error("GatewayDispatcher requires a serviceMetrics dependency");
    if (!deps.gatewayMetrics) throw new Error("GatewayDispatcher requires a gatewayMetrics dependency");
    this._registry = deps.registry;
    this._serviceMetrics = deps.serviceMetrics;
    this._gatewayMetrics = deps.gatewayMetrics;
    this._middleware =
      deps.middleware ||
      defaultGatewayMiddleware({
        resolveFlags: resolveEigFlags,
        serviceMetrics: deps.serviceMetrics,
        gatewayMetrics: deps.gatewayMetrics,
      });
    this._runMiddleware = composeGatewayMiddleware(this._middleware);
  }

  /**
   * @param {{capability: string, method: string, args?: any[], caller?: {id: string, kind?: string},
   *   grantedCapabilities?: string[], environment?: string, correlationId?: string,
   *   metadata?: object}} request
   * @returns {Promise<any>}
   */
  async dispatch(request = {}) {
    const entry = this._registry.get(request.capability); // throws CapabilityNotRegisteredError

    const context = new GatewayContext({
      correlationId: request.correlationId,
      caller: request.caller,
      capability: request.capability,
      grantedCapabilities: request.grantedCapabilities,
      environment: request.environment,
      metadata: { ...(request.metadata || {}), request: { method: request.method, args: request.args } },
    });

    const missing = entry.requiredCapabilities.filter((required) => !context.hasCapability(required));
    if (missing.length > 0) {
      this._gatewayMetrics.recordCapabilityAuthorizationDenial(request.capability);
      throw new CapabilityAuthorizationError(request.capability, missing);
    }

    const args = request.args || [];
    const runHandler = (finalContext) => entry.handler(finalContext, request.method, ...args);

    return this._serviceMetrics.timed(`gateway.${request.capability}`, () => this._runMiddleware(context, runHandler));
  }
}
