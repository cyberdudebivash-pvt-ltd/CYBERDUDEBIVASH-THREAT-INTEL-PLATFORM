/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Gateway Service Facade
 * (Project TITAN). Not imported by index.js or any production route.
 * See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * "One Gateway" -- the single aggregating facade this stage's brief names as its primary
 * deliverable, mirroring Stage 12's EvidenceService and Stage 13's IntelligenceService pattern
 * one layer up. Composes Context/Registry/Dispatcher/Lifecycle/Metrics and pre-registers the 8
 * Stage 13 capabilities below against an injected IntelligenceService instance, plus one Stage 17
 * addition (`intelligence.explainability`). No business logic of its own: every capability
 * handler is a thin createServiceMethodHandler() adapter over an already-existing, already-public
 * IntelligenceService property.
 */

import { GatewayRegistry, createServiceMethodHandler } from "./gateway-registry.js";
import { GatewayDispatcher } from "./gateway-dispatcher.js";
import { GatewayLifecycle } from "./gateway-lifecycle.js";
import { GatewayMetrics } from "./gateway-metrics.js";

export class EnterpriseGateway {
  /**
   * @param {{platform: import('../intelligence-platform/intelligence-service.js').IntelligenceService,
   *   serviceMetrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics,
   *   environment?: string}} deps
   */
  constructor(deps = {}) {
    if (!deps.platform) {
      throw new Error("EnterpriseGateway requires a platform (IntelligenceService) dependency");
    }
    // Must derive the shared serviceMetrics AFTER resolving _platform, not before -- the exact
    // bug class Stage 13 found and fixed in its own constructor (see intelligence-service.js's
    // own comment): an injected platform already owns a ServicePlatformMetrics instance, and
    // building a fresh one here first would silently split observability in two. If both a
    // platform AND an explicit, different serviceMetrics are injected, that's a caller error --
    // fail loudly rather than silently picking one.
    this._platform = deps.platform;
    const serviceMetrics = deps.serviceMetrics || this._platform.metrics.sharedServiceMetrics;
    if (this._platform.metrics.sharedServiceMetrics !== serviceMetrics) {
      throw new Error(
        "EnterpriseGateway: deps.serviceMetrics does not match the injected deps.platform's own " +
          "shared metrics instance -- inject one or the other, not two different ones."
      );
    }

    this.metrics = new GatewayMetrics(this._platform.metrics);
    this._registry = new GatewayRegistry();
    this._dispatcher = new GatewayDispatcher({
      registry: this._registry,
      serviceMetrics,
      gatewayMetrics: this.metrics,
    });
    this._lifecycle = new GatewayLifecycle();
    this._environment = deps.environment || "production";

    this._registerDefaultCapabilities();
    this._lifecycle.markReady();
  }

  _registerDefaultCapabilities() {
    const platform = this._platform;
    this._registry.register("evidence.lookup", createServiceMethodHandler(platform.lookup), {
      description: "IntelligenceLookupService -- unified evidence-registry + enterprise query lookup surface",
    });
    this._registry.register("intelligence.query", createServiceMethodHandler(platform.enterpriseQuery), {
      description: "EnterpriseQueryService -- 12-dimension query surface (3 document platform gaps)",
    });
    this._registry.register("intelligence.correlation", createServiceMethodHandler(platform.correlation), {
      description: "IntelligenceCorrelationService",
    });
    this._registry.register("intelligence.validation", createServiceMethodHandler(platform.validation), {
      description: "IntelligenceValidationService",
    });
    this._registry.register("intelligence.threatProfile", createServiceMethodHandler(platform.threatIntelligence), {
      description: "ThreatIntelligenceService.getThreatProfile",
    });
    this._registry.register("evidence.provenance", createServiceMethodHandler(platform.provenance), {
      description: "EvidenceProvenanceEngine -- 6 lineage kinds",
    });
    this._registry.register("evidence.relationships", createServiceMethodHandler(platform.relationshipResolution), {
      description: "RelationshipResolutionService -- ADR-0010 Accepted (Stage 16); real data when " +
        "platform was composed with a relationship-framework/-backed provider, NOT_WIRED otherwise",
    });
    this._registry.register("platform.metrics", createServiceMethodHandler(platform.metrics), {
      description: "IntelligenceMetricsService",
    });
    this._registry.register("intelligence.explainability", createServiceMethodHandler(platform.explainability), {
      description: "IntelligenceExplainabilityService -- Stage 17 Explainable Intelligence Engine / " +
        "Analyst Reasoning Object; confidence fields surfaced verbatim only (ADR-0007 Proposed, not Accepted)",
    });
  }

  /**
   * Extension point for a future capability beyond the 8 pre-registered above -- still
   * DI-composed over an existing service, per this stage's own "no hardcoded service wiring"
   * requirement; this method does not create or own any service itself.
   * @param {string} name
   * @param {import('./gateway-registry.js').GatewayCapabilityHandler} handler
   * @param {object} [options]
   */
  registerCapability(name, handler, options) {
    this._registry.register(name, handler, options);
  }

  listCapabilities() {
    return this._registry.list();
  }

  /**
   * Declared async (not just "returns a promise from its happy path") so every failure mode --
   * including the readiness check below, which would otherwise throw synchronously while the
   * normal path returns a promise -- is uniformly a rejected promise. A method that sometimes
   * throws synchronously and sometimes returns a promise is unsafe to blindly `await` or pass to
   * assert.rejects()/.catch(); this stage's own test suite caught exactly that inconsistency.
   * @param {{capability: string, method: string, args?: any[], caller?: object,
   *   grantedCapabilities?: string[], correlationId?: string, metadata?: object}} request
   */
  async dispatch(request = {}) {
    if (!this._lifecycle.isReady()) {
      throw new Error(`EnterpriseGateway is not ready (lifecycle state: ${this._lifecycle.state}) -- cannot dispatch`);
    }
    return this._dispatcher.dispatch({ environment: this._environment, ...request });
  }

  stop() {
    this._lifecycle.stop();
  }

  healthCheck() {
    return {
      ...this._lifecycle.healthCheck(),
      capabilities: this.listCapabilities(),
      environment: this._environment,
    };
  }

  /**
   * @returns {import('../intelligence-platform/intelligence-service.js').IntelligenceService} the
   *   underlying Stage 13 facade, for components that need it directly
   */
  get platform() {
    return this._platform;
  }
}
