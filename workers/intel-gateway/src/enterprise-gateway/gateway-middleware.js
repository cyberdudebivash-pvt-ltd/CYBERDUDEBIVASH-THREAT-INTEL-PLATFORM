/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Middleware Pipeline (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Six composable middleware stages plus composeGatewayMiddleware(), the onion-style runner that
 * chains them around a final handler. Default order (outermost first, closest to the handler
 * last): tracing, feature-flag evaluation, version compatibility, gateway-request validation,
 * audit logging, metrics-bridging. Each `next` optionally accepts a REPLACEMENT GatewayContext
 * (via GatewayContext#with()) for stages downstream; a stage with nothing to add just calls
 * next() with no argument.
 *
 * None of these stages re-implement evidence/intelligence DATA validation, correlation, or
 * scoring logic -- capabilityValidationMiddleware validates gateway REQUEST shape only (method
 * is a string, args is an array). Phase 1's 8 registered capabilities are all read-only; any
 * future mutating capability inherits real evidence validation for free, transitively, the
 * moment its handler calls through EvidenceService's own mutating methods (which already
 * validate before persisting -- Stage 11/12 precedent). See TITAN_STAGE14_SERVICE_ARCHITECTURE.md
 * for why this is the correct Phase 1 scope, not an omission.
 */

import { checkContractCompatibility } from "./service-contracts.js";

export class GatewayValidationError extends Error {
  constructor(message, capability) {
    super(message);
    this.name = "GatewayValidationError";
    this.capability = capability;
  }
}

export class ContractVersionIncompatibleError extends Error {
  constructor(capability, callerExpectedVersion, currentVersion) {
    super(
      `Capability "${capability}" version mismatch: caller expected "${callerExpectedVersion}", ` +
        `gateway has "${currentVersion}", and that is not a forward-compatible upgrade path`
    );
    this.name = "ContractVersionIncompatibleError";
    this.capability = capability;
    this.callerExpectedVersion = callerExpectedVersion;
    this.currentVersion = currentVersion;
  }
}

/**
 * Outermost stage. Logs a trace-start/trace-end pair keyed by correlation id. Deliberately the
 * thinnest stage in Phase 1 -- no real distributed-tracing exporter exists in this platform yet;
 * this establishes the pipeline position for that future work rather than pretending to do more.
 */
export function tracingMiddleware() {
  return async function tracing(context, next) {
    console.log(`[Stage 14 gateway-trace] start correlationId=${context.correlationId} capability=${context.capability}`);
    try {
      const result = await next();
      console.log(
        `[Stage 14 gateway-trace] end correlationId=${context.correlationId} capability=${context.capability} ` +
          `elapsedMs=${Date.now() - context.startedAt} outcome=success`
      );
      return result;
    } catch (error) {
      console.log(
        `[Stage 14 gateway-trace] end correlationId=${context.correlationId} capability=${context.capability} ` +
          `elapsedMs=${Date.now() - context.startedAt} outcome=failure`
      );
      throw error;
    }
  };
}

/**
 * Resolves and records EIG_ENABLED for the current environment, then attaches the resolved
 * flags to context for downstream stages/handlers. Deliberately does NOT throw when
 * EIG_ENABLED is false: matching IntelligenceService/createIntelligencePlatform()'s own
 * precedent exactly, the flag gate lives at ONE place -- createEnterpriseGateway()'s
 * composition root, which already refuses to construct a gateway at all when EIG_ENABLED is
 * false. IntelligenceService's own methods never re-check EIPS_ENABLED per call either; a
 * directly-constructed EnterpriseGateway (bypassing the composition root, an intentional and
 * supported DI/testing path -- see gateway-service.js's own docstring) is exactly as callable
 * as a directly-constructed IntelligenceService is. An earlier version of this stage DID throw
 * here; that was found, during this stage's own test run, to be an inconsistent second gate
 * that made direct DI construction surprising to use -- removed rather than worked around.
 * @param {{resolveFlags: (environment: string) => {EIG_ENABLED: boolean},
 *   gatewayMetrics: import('./gateway-metrics.js').GatewayMetrics}} deps
 */
export function featureFlagEvaluationMiddleware(deps) {
  return async function featureFlagEvaluation(context, next) {
    const flags = deps.resolveFlags(context.environment);
    deps.gatewayMetrics.recordFeatureFlagEvaluation(context.environment, flags.EIG_ENABLED);
    return next(context.with({ featureFlags: flags }));
  };
}

/**
 * No-ops unless the caller supplied both `context.metadata.expectedContractVersion` and
 * `context.metadata.targetContract` (a contract object from service-contracts.js). Reuses
 * checkContractCompatibility() unchanged -- no new compatibility algorithm.
 * @param {{serviceMetrics: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
 */
export function versionCompatibilityMiddleware(deps) {
  return async function versionCompatibility(context, next) {
    const expected = context.metadata.expectedContractVersion;
    const contract = context.metadata.targetContract;
    if (!expected || !contract) {
      return next();
    }
    const result = checkContractCompatibility(contract, expected);
    if (!result.compatible) {
      deps.serviceMetrics.recordContractVersionMismatch();
      throw new ContractVersionIncompatibleError(context.capability, expected, result.currentVersion);
    }
    return next();
  };
}

/**
 * Gateway-REQUEST-shape validation only (method is a non-empty string, args is an array when
 * present) -- see this module's own docstring for why evidence/intelligence DATA validation is
 * out of scope here.
 * @param {{gatewayMetrics: import('./gateway-metrics.js').GatewayMetrics}} deps
 */
export function capabilityValidationMiddleware(deps) {
  return async function capabilityValidation(context, next) {
    const { method, args } = context.metadata.request || {};
    if (!method || typeof method !== "string") {
      deps.gatewayMetrics.recordMiddlewareValidationFailure(context.capability);
      throw new GatewayValidationError(
        `Capability "${context.capability}" dispatch requires a non-empty string 'method'`,
        context.capability
      );
    }
    if (args !== undefined && !Array.isArray(args)) {
      deps.gatewayMetrics.recordMiddlewareValidationFailure(context.capability);
      throw new GatewayValidationError(
        `Capability "${context.capability}" dispatch 'args' must be an array when present`,
        context.capability
      );
    }
    return next();
  };
}

/**
 * Wraps next() in try/finally, appends one bounded audit entry per call (success or failure),
 * logs one line, and always re-throws -- never swallows a handler failure.
 * @param {{gatewayMetrics: import('./gateway-metrics.js').GatewayMetrics}} deps
 */
export function auditLoggingMiddleware(deps) {
  return async function auditLogging(context, next) {
    const start = Date.now();
    let outcome = "success";
    try {
      return await next();
    } catch (error) {
      outcome = "failure";
      throw error;
    } finally {
      const entry = {
        correlationId: context.correlationId,
        capability: context.capability,
        method: (context.metadata.request || {}).method || null,
        caller: context.caller,
        outcome,
        elapsedMs: Date.now() - start,
        timestamp: new Date().toISOString(),
      };
      deps.gatewayMetrics.recordAuditEntry(entry);
      console.log(`[Stage 14 gateway-audit] ${JSON.stringify(entry)}`);
    }
  };
}

/**
 * Innermost stage. Pure passthrough for every capability except intelligence.validation: for
 * that one capability, bridges a non-throwing {valid: false, errors} result into
 * ServicePlatformMetrics.recordValidationFailure() -- an existing method with zero prior call
 * sites (confirmed by grep) before this bridge. Does not duplicate call_counts/latency, which
 * GatewayDispatcher's own outer serviceMetrics.timed() wrap already covers.
 * @param {{serviceMetrics: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
 */
export function metricsMiddleware(deps) {
  return async function metrics(context, next) {
    const result = await next();
    if (context.capability === "intelligence.validation" && result && result.valid === false) {
      deps.serviceMetrics.recordValidationFailure();
    }
    return result;
  };
}

/**
 * Onion-style composition: stages[0] is outermost (its timing covers every later stage,
 * including a rejection thrown by any of them); the last stage is innermost, closest to
 * finalHandler.
 * @param {Array<(context: import('./gateway-context.js').GatewayContext,
 *   next: (nextContext?: import('./gateway-context.js').GatewayContext) => Promise<any>) => Promise<any>>} stages
 * @returns {(initialContext: import('./gateway-context.js').GatewayContext,
 *   finalHandler: (context: import('./gateway-context.js').GatewayContext) => Promise<any>) => Promise<any>}
 */
export function composeGatewayMiddleware(stages) {
  return function runComposedMiddleware(initialContext, finalHandler) {
    let lastIndex = -1;
    function dispatch(index, context) {
      if (index <= lastIndex) {
        return Promise.reject(new Error("next() called multiple times in one middleware stage"));
      }
      lastIndex = index;
      if (index === stages.length) {
        return Promise.resolve(finalHandler(context));
      }
      const stage = stages[index];
      return stage(context, (nextContext) => dispatch(index + 1, nextContext || context));
    }
    return dispatch(0, initialContext);
  };
}

/**
 * @param {{resolveFlags: Function,
 *   serviceMetrics: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics,
 *   gatewayMetrics: import('./gateway-metrics.js').GatewayMetrics}} deps
 * @returns {Array<Function>} the 6 default stages, outermost first
 */
export function defaultGatewayMiddleware(deps) {
  return [
    tracingMiddleware(),
    featureFlagEvaluationMiddleware(deps),
    versionCompatibilityMiddleware(deps),
    capabilityValidationMiddleware(deps),
    auditLoggingMiddleware(deps),
    metricsMiddleware(deps),
  ];
}
