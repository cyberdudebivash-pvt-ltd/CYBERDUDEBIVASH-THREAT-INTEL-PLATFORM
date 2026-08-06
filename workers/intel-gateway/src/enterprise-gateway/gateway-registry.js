/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Registry (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Pure capability-name -> handler registration. This module never references IntelligenceService,
 * EvidenceService, or any other concrete service by name or import -- registration of the actual
 * Stage 13 capability table happens entirely in gateway-service.js's composition, not here (see
 * that file for where "no hardcoded service wiring" is actually satisfied). This module is
 * generic over any handler.
 */

export class DuplicateCapabilityError extends Error {
  constructor(name) {
    super(`Capability "${name}" is already registered -- register() does not allow silent overwrite`);
    this.name = "DuplicateCapabilityError";
    this.capability = name;
  }
}

export class CapabilityNotRegisteredError extends Error {
  constructor(name) {
    super(`Capability "${name}" is not registered`);
    this.name = "CapabilityNotRegisteredError";
    this.capability = name;
  }
}

/**
 * @typedef {(context: import('./gateway-context.js').GatewayContext, method: string,
 *   ...args: any[]) => Promise<any>} GatewayCapabilityHandler
 */

/**
 * Generic adapter turning any multi-method service object into a single GatewayCapabilityHandler
 * -- dispatches `(context, method, ...args)` to `service[method](...args)`. Composes an
 * already-existing service's already-public methods; adds no new business logic, only
 * method-name dispatch over it.
 * @param {object} service
 * @param {{allowedMethods?: string[]}} [options]
 * @returns {GatewayCapabilityHandler}
 */
export function createServiceMethodHandler(service, options = {}) {
  if (!service || typeof service !== "object") {
    throw new Error("createServiceMethodHandler requires a service object");
  }
  const allowed = options.allowedMethods ? new Set(options.allowedMethods) : null;
  return async function serviceMethodHandler(context, method, ...args) {
    if (allowed && !allowed.has(method)) {
      throw new Error(`Method "${method}" is not an allowed method for capability "${context.capability}"`);
    }
    const fn = service[method];
    if (typeof fn !== "function") {
      throw new Error(`Method "${method}" does not exist on the target service for capability "${context.capability}"`);
    }
    return fn.apply(service, args);
  };
}

export class GatewayRegistry {
  constructor() {
    this._entries = new Map();
  }

  /**
   * @param {string} name
   * @param {GatewayCapabilityHandler} handler
   * @param {{requiredCapabilities?: string[], version?: string, description?: string}} [options]
   */
  register(name, handler, options = {}) {
    if (!name || typeof name !== "string") {
      throw new Error("register() requires a non-empty string capability name");
    }
    if (typeof handler !== "function") {
      throw new Error(`register("${name}") requires a handler function`);
    }
    if (this._entries.has(name)) {
      throw new DuplicateCapabilityError(name);
    }
    this._entries.set(name, {
      name,
      handler,
      // Secure by default: a capability requires itself unless the caller explicitly widens or
      // narrows that via options.requiredCapabilities.
      requiredCapabilities: options.requiredCapabilities || [name],
      version: options.version || "1.0.0",
      description: options.description || "",
    });
  }

  has(name) {
    return this._entries.has(name);
  }

  get(name) {
    const entry = this._entries.get(name);
    if (!entry) throw new CapabilityNotRegisteredError(name);
    return entry;
  }

  list() {
    return [...this._entries.keys()];
  }

  /**
   * Safe, read-only capability metadata -- unlike get(), never exposes the handler function
   * itself, so this is fine to hand to a diagnostic/observability caller that has no business
   * invoking capabilities directly. Stage 14 Phase 2 registry-maturity addition (see
   * TITAN_STAGE14_SERVICE_ARCHITECTURE.md Sec 5); check_gateway_registry_describe_omits_handler()
   * guards this property going forward.
   * @param {string} name
   * @returns {{name: string, version: string, description: string, requiredCapabilities: string[]}}
   */
  describe(name) {
    const entry = this.get(name);
    return {
      name: entry.name,
      version: entry.version,
      description: entry.description,
      requiredCapabilities: entry.requiredCapabilities,
    };
  }

  /** @returns {Array<{name: string, version: string, description: string, requiredCapabilities: string[]}>} */
  describeAll() {
    return this.list().map((name) => this.describe(name));
  }

  /** Test/rollback hook only -- production capability registration never needs to unregister. */
  unregister(name) {
    return this._entries.delete(name);
  }
}
