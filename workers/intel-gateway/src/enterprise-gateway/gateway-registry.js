/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Registry (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Pure capability-name -> handler registration. This module never references IntelligenceService,
 * EvidenceService, or any other concrete service by name or import -- registration of the actual
 * Stage 13 capability table happens entirely in gateway-service.js's composition, not here (see
 * that file for where "no hardcoded service wiring" is actually satisfied). This module is
 * generic over any handler.
 *
 * Stage 21 Phase 4 addition (see TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md Sec 3.1): register()'s
 * options gained 5 optional commercial-classification fields (owner, consumers,
 * securityClassification, visibility, lifecycle), all defaulted so every pre-Stage-21 call site
 * is byte-for-byte unaffected -- CapabilityRegistryContract bumped 1.1.0 -> 1.2.0, additive,
 * mirroring the exact precedent Stage 14 Phase 2 set for its own describe()/describeAll()
 * addition. annotate() is new: it lets Stage 21 classify the 9 pre-Stage-21 capabilities without
 * re-registering them (register() throws DuplicateCapabilityError on a second call for the same
 * name).
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
   * @param {{requiredCapabilities?: string[], version?: string, description?: string,
   *   owner?: string, consumers?: string[], securityClassification?: string,
   *   visibility?: string, lifecycle?: string}} [options]
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
      // Stage 21 Phase 4: commercial-classification metadata, secure-by-default (unclassified
      // capabilities read as internal/internal-only until explicitly annotated otherwise -- see
      // commercial-catalog/platform.js for the Stage 21 annotation pass over the 9 pre-existing
      // capabilities).
      owner: options.owner || null,
      consumers: options.consumers || [],
      securityClassification: options.securityClassification || "internal",
      visibility: options.visibility || "internal",
      lifecycle: options.lifecycle || "internal-only",
    });
  }

  /**
   * Merges Stage 21 commercial-classification metadata onto an already-registered capability
   * without re-registering it (register() throws DuplicateCapabilityError on a second call for
   * the same name). Only the 5 fields register() accepts above may be patched -- name, handler,
   * requiredCapabilities, version, and description are immutable after registration; annotate()
   * is not a general-purpose entry mutator.
   * @param {string} name
   * @param {{owner?: string, consumers?: string[], securityClassification?: string,
   *   visibility?: string, lifecycle?: string}} [patch]
   */
  annotate(name, patch = {}) {
    const entry = this.get(name); // throws CapabilityNotRegisteredError if unknown
    const ALLOWED_KEYS = Object.freeze(["owner", "consumers", "securityClassification", "visibility", "lifecycle"]);
    for (const key of Object.keys(patch)) {
      if (!ALLOWED_KEYS.includes(key)) {
        throw new Error(
          `annotate("${name}") received unsupported field "${key}" -- only ${ALLOWED_KEYS.join(", ")} may be annotated`
        );
      }
    }
    Object.assign(entry, patch);
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
   * @returns {{name: string, version: string, description: string, requiredCapabilities: string[],
   *   owner: string|null, consumers: string[], securityClassification: string, visibility: string,
   *   lifecycle: string}}
   */
  describe(name) {
    const entry = this.get(name);
    return {
      name: entry.name,
      version: entry.version,
      description: entry.description,
      requiredCapabilities: entry.requiredCapabilities,
      // Stage 21 Phase 4 addition -- additive fields, CapabilityRegistryContract 1.1.0 -> 1.2.0.
      owner: entry.owner,
      consumers: entry.consumers,
      securityClassification: entry.securityClassification,
      visibility: entry.visibility,
      lifecycle: entry.lifecycle,
    };
  }

  /** @returns {ReturnType<GatewayRegistry['describe']>[]} */
  describeAll() {
    return this.list().map((name) => this.describe(name));
  }

  /** Test/rollback hook only -- production capability registration never needs to unregister. */
  unregister(name) {
    return this._entries.delete(name);
  }
}
