/**
 * Commercial Catalog (Project TITAN Stage 21) -- Composition Root.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md
 * Sec 3 for the full architectural placement rationale.
 *
 * wireCommercialCapabilities() is the Phase 2/4 integration point: registers every catalog
 * "newAdapter" entry onto an already-constructed EnterpriseGateway via its existing, unmodified
 * registerCapability() extension point, and annotates the 9 pre-Stage-21 capabilities (6 via
 * catalog entries, 3 via INTERNAL_ONLY_CAPABILITY_ANNOTATIONS) via its Stage 21
 * annotateCapability() addition. gateway-service.js's _registerDefaultCapabilities() is never
 * touched -- wiring happens one level up, exactly as
 * check_knowledge_platform_still_unwired()/check_product_platform_still_unwired()'s own
 * docstrings anticipate ("wired via registerCapability() from a composition script").
 *
 * createCommercialGateway() is the convenience full-stack factory mirroring
 * enterprise-gateway/platform.js's createEnterpriseGateway() shape, composing all the way down
 * when flags allow. It receives IntelligenceService via gateway.platform (EnterpriseGateway's own
 * existing public getter) rather than importing intelligence-platform/platform.js directly -- this
 * directory's dependency stays scoped to enterprise-gateway/, knowledge-platform/,
 * product-platform/, and p39-handlers.js, never intelligence-platform/ or evidence-registry/
 * directly (see __tests__/zero-blast-radius.test.js).
 */

import { createEnterpriseGateway } from "../enterprise-gateway/platform.js";
import { createKnowledgePlatform } from "../knowledge-platform/platform.js";
import { createProductPlatform } from "../product-platform/platform.js";
import {
  listNewAdapterEntries,
  listExistingCapabilityEntries,
  INTERNAL_ONLY_CAPABILITY_ANNOTATIONS,
} from "./catalog.js";
import { resolveCcFlags } from "./feature-flags.js";
import { CommercialMetrics } from "./commercial-metrics.js";
import {
  createKnowledgeObjectAdapter,
  createKnowledgeNavigationAdapter,
  createKnowledgeExecutiveBriefingAdapter,
  createEvidenceProvenanceSummaryAdapter,
  createProductAssemblyAdapter,
  createProductProfiledViewAdapter,
  createProductPackageAdapter,
  createMsspPartnerPackageAdapter,
  createCommercialReadinessSummaryAdapter,
  createCommercialExplanationAdapter,
} from "./commercial-adapters.js";

/**
 * catalog id -> factory. One entry per listNewAdapterEntries() row; a drift between the two is a
 * programming error (wireCommercialCapabilities() throws loudly rather than silently skipping).
 */
const ADAPTER_FACTORIES = Object.freeze({
  "commercial.knowledgeObject": ({ knowledgePlatform }) => createKnowledgeObjectAdapter({ knowledgePlatform }),
  "commercial.knowledgeNavigation": ({ knowledgePlatform }) => createKnowledgeNavigationAdapter({ knowledgePlatform }),
  "commercial.knowledgeExecutiveBriefing": ({ knowledgePlatform }) =>
    createKnowledgeExecutiveBriefingAdapter({ knowledgePlatform }),
  "commercial.evidenceProvenanceSummary": ({ gateway }) => createEvidenceProvenanceSummaryAdapter({ gateway }),
  "commercial.productAssembly": ({ productPlatform }) => createProductAssemblyAdapter({ productPlatform }),
  "commercial.productProfiledView": ({ productPlatform }) => createProductProfiledViewAdapter({ productPlatform }),
  "commercial.productPackage": ({ productPlatform }) => createProductPackageAdapter({ productPlatform }),
  "commercial.msspPartnerPackage": ({ productPlatform }) => createMsspPartnerPackageAdapter({ productPlatform }),
  "commercial.readinessSummary": () => createCommercialReadinessSummaryAdapter(),
  "commercial.explanationSummary": () => createCommercialExplanationAdapter(),
});

/**
 * @param {{gateway: import('../enterprise-gateway/gateway-service.js').EnterpriseGateway,
 *   knowledgePlatform?: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform|null,
 *   productPlatform?: import('../product-platform/product-platform.js').ProductPlatform|null,
 *   commercialMetrics?: CommercialMetrics}} options
 * @returns {{registered: string[], skipped: string[], metrics: CommercialMetrics}}
 */
export function wireCommercialCapabilities({
  gateway,
  knowledgePlatform = null,
  productPlatform = null,
  commercialMetrics = null,
} = {}) {
  if (!gateway) {
    throw new Error("wireCommercialCapabilities() requires a gateway dependency");
  }
  const metrics = commercialMetrics || new CommercialMetrics({ gatewayMetrics: gateway.metrics });

  const registered = [];
  const skipped = [];
  for (const entry of listNewAdapterEntries()) {
    const factory = ADAPTER_FACTORIES[entry.id];
    if (!factory) {
      throw new Error(
        `wireCommercialCapabilities(): no adapter factory registered for catalog entry "${entry.id}" -- ` +
          "catalog.js and commercial-adapters.js/platform.js have drifted"
      );
    }
    // Partial wiring is allowed (e.g. Gateway + P39 adapters only, Knowledge/Product Platform
    // not yet composed) -- skip rather than throw when a required upstream dependency is absent.
    if (entry.sourceLayer === "knowledge-platform" && !knowledgePlatform) {
      skipped.push(entry.id);
      continue;
    }
    if (entry.sourceLayer === "product-platform" && !productPlatform) {
      skipped.push(entry.id);
      continue;
    }

    const rawHandler = factory({ gateway, knowledgePlatform, productPlatform });
    const handler = metrics.wrapWithFailureClassification(entry.id, rawHandler);
    gateway.registerCapability(entry.id, handler, {
      description: entry.description,
      owner: entry.owner,
      consumers: entry.internalConsumers,
      securityClassification: entry.securityClassification,
      visibility: entry.visibility,
      lifecycle: entry.lifecycle,
    });
    registered.push(entry.id);
  }

  for (const entry of listExistingCapabilityEntries()) {
    gateway.annotateCapability(entry.gatewayCapability, {
      owner: entry.owner,
      consumers: entry.internalConsumers,
      securityClassification: entry.securityClassification,
      visibility: entry.visibility,
      lifecycle: entry.lifecycle,
    });
  }

  for (const annotation of INTERNAL_ONLY_CAPABILITY_ANNOTATIONS) {
    gateway.annotateCapability(annotation.gatewayCapability, {
      owner: annotation.owner,
      consumers: annotation.consumers,
      securityClassification: annotation.securityClassification,
      visibility: annotation.visibility,
      lifecycle: annotation.lifecycle,
    });
  }

  return { registered, skipped, metrics };
}

/**
 * @param {{environment?: string, deps?: {gateway?: object, gatewayDeps?: object,
 *   knowledgePlatform?: object, productPlatform?: object, commercialMetrics?: CommercialMetrics}}} [options]
 * @returns {{enabled: boolean, gateway: object|null, knowledgePlatform: object|null,
 *   productPlatform: object|null, commercialMetrics: CommercialMetrics|null, environment: string,
 *   reason?: string, wiring?: {registered: string[], skipped: string[]}}}
 */
export function createCommercialGateway(options = {}) {
  const environment = options.environment || "production";
  const flags = resolveCcFlags(environment);

  if (!flags.CC_ENABLED) {
    return {
      enabled: false,
      gateway: null,
      knowledgePlatform: null,
      productPlatform: null,
      commercialMetrics: null,
      environment,
      reason: `CC_ENABLED is false for environment "${environment}"`,
    };
  }

  const deps = options.deps || {};

  const gatewayResult = deps.gateway
    ? { enabled: true, gateway: deps.gateway }
    : createEnterpriseGateway({ environment, deps: deps.gatewayDeps });
  if (!gatewayResult.enabled) {
    return {
      enabled: false,
      gateway: null,
      knowledgePlatform: null,
      productPlatform: null,
      commercialMetrics: null,
      environment,
      reason: `Underlying EnterpriseGateway is disabled: ${gatewayResult.reason}`,
    };
  }
  const gateway = gatewayResult.gateway;

  let knowledgePlatform = deps.knowledgePlatform || null;
  if (!knowledgePlatform) {
    const kpResult = createKnowledgePlatform({ environment, intelligenceService: gateway.platform });
    knowledgePlatform = kpResult.enabled ? kpResult.platform : null;
  }

  let productPlatform = deps.productPlatform || null;
  if (!productPlatform && knowledgePlatform) {
    const ppResult = createProductPlatform({ environment, knowledgePlatform });
    productPlatform = ppResult.enabled ? ppResult.platform : null;
  }

  const commercialMetrics = deps.commercialMetrics || new CommercialMetrics({ gatewayMetrics: gateway.metrics });
  const wiring = wireCommercialCapabilities({ gateway, knowledgePlatform, productPlatform, commercialMetrics });

  return { enabled: true, gateway, knowledgePlatform, productPlatform, commercialMetrics, environment, wiring };
}
