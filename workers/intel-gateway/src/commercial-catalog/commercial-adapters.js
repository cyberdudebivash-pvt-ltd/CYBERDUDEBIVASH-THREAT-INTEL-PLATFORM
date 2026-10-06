/**
 * Commercial Catalog (Project TITAN Stage 21 Phase 2) -- Gateway Commercial Adapters.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md.
 *
 * Gateway -> Adapter -> Internal Platform -> Engine (never Gateway -> Engine). Every adapter here
 * is a real GatewayCapabilityHandler ((context, method, ...args) => Promise<result>), registered
 * via the Gateway's existing, unmodified registerCapability() -- so every commercial capability
 * inherits GatewayDispatcher's authorization check, middleware chain, and shared-metrics-timed
 * dispatch for free, exactly like the 9 Stage 14 capabilities. No new dispatch mechanism.
 *
 * Each adapter owns:
 *  - validation: method name against an explicit allowlist, required args present and correctly
 *    typed, before ever calling through to a platform method.
 *  - mapping: reshapes/redacts the underlying platform's return value into a stable envelope
 *    (buildCommercialEnvelope below); commercial.evidenceProvenanceSummary additionally excludes
 *    getAuditLineage entirely via createServiceMethodHandler()'s own allowedMethods option
 *    (reused unchanged from enterprise-gateway/gateway-registry.js, not reimplemented).
 *  - translation: composes the Gateway's (context, method, ...args) calling convention with each
 *    underlying platform's own positional-argument methods, including multi-call composition
 *    (e.g. commercial.productPackage: assemble -> applyProfile -> package).
 *  - versioning: every envelope carries capabilityId + namespace + contractVersion (internal/v1,
 *    CommercialAdaptersContract.version), so a caller can see which contract shape it received.
 *
 * ProductPackagingService.package() is ASYNC (product-platform/product-packaging.js:87) while
 * ProductProfileService.applyProfile() is SYNCHRONOUS (product-platform/product-profiles.js) --
 * verified directly, not assumed, because forgetting to await the former is a real bug class this
 * program has hit before. Every call site below is explicit about which is which.
 */

import { createServiceMethodHandler } from "../enterprise-gateway/gateway-registry.js";
import {
  buildCommercialQualityView,
  buildCommercialReadinessSummary,
  buildCommercialExplanation,
  buildCommercialRecommendationLayer,
} from "../p39-handlers.js";
import { CommercialAdaptersContract, INTERNAL_V1_NAMESPACE } from "./service-contracts.js";

export class CommercialAdapterValidationError extends Error {
  constructor(capabilityId, message) {
    super(`Commercial adapter "${capabilityId}" rejected the call: ${message}`);
    this.name = "CommercialAdapterValidationError";
    this.capabilityId = capabilityId;
  }
}

function requireDep(value, paramName, factoryName) {
  if (!value) {
    throw new Error(`${factoryName}() requires a ${paramName} dependency`);
  }
}

function assertAllowedMethod(capabilityId, method, allowed) {
  if (!allowed.includes(method)) {
    throw new CommercialAdapterValidationError(
      capabilityId,
      `method "${method}" is not one of the allowed methods: ${allowed.join(", ")}`
    );
  }
}

function assertNonEmptyString(value, paramName, capabilityId) {
  if (typeof value !== "string" || value.length === 0) {
    throw new CommercialAdapterValidationError(capabilityId, `"${paramName}" must be a non-empty string`);
  }
}

function assertPlainObject(value, paramName, capabilityId) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CommercialAdapterValidationError(capabilityId, `"${paramName}" must be a plain object`);
  }
}

/**
 * @param {{capabilityId: string, data: any}} input
 * @returns {{capabilityId: string, namespace: string, contractVersion: string, generatedAt: string, data: any}}
 */
function buildCommercialEnvelope({ capabilityId, data }) {
  return {
    capabilityId,
    namespace: INTERNAL_V1_NAMESPACE,
    contractVersion: CommercialAdaptersContract.version,
    generatedAt: new Date().toISOString(),
    data,
  };
}

// --- Knowledge Platform adapters -------------------------------------------------------------

/** @param {{knowledgePlatform: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform}} deps */
export function createKnowledgeObjectAdapter({ knowledgePlatform } = {}) {
  requireDep(knowledgePlatform, "knowledgePlatform", "createKnowledgeObjectAdapter");
  return async function knowledgeObjectAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.knowledgeObject", method, ["build"]);
    const [evidenceUuid] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.knowledgeObject");
    const data = await knowledgePlatform.object.build(evidenceUuid);
    return buildCommercialEnvelope({ capabilityId: "commercial.knowledgeObject", data });
  };
}

const KNOWLEDGE_NAVIGATION_METHODS = Object.freeze([
  "relatedIntelligence",
  "supportingEvidence",
  "similarIntelligence",
  "contradictoryEvidence",
  "historicalIntelligence",
  "collectionGaps",
]);

/** @param {{knowledgePlatform: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform}} deps */
export function createKnowledgeNavigationAdapter({ knowledgePlatform } = {}) {
  requireDep(knowledgePlatform, "knowledgePlatform", "createKnowledgeNavigationAdapter");
  return async function knowledgeNavigationAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.knowledgeNavigation", method, KNOWLEDGE_NAVIGATION_METHODS);
    const [evidenceUuid] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.knowledgeNavigation");
    const data = await knowledgePlatform.navigation[method](evidenceUuid);
    return buildCommercialEnvelope({ capabilityId: "commercial.knowledgeNavigation", data });
  };
}

/** @param {{knowledgePlatform: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform}} deps */
export function createKnowledgeExecutiveBriefingAdapter({ knowledgePlatform } = {}) {
  requireDep(knowledgePlatform, "knowledgePlatform", "createKnowledgeExecutiveBriefingAdapter");
  return async function knowledgeExecutiveBriefingAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.knowledgeExecutiveBriefing", method, ["executiveBriefing"]);
    const [evidenceUuid] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.knowledgeExecutiveBriefing");
    const data = await knowledgePlatform.executiveViews.executiveBriefing(evidenceUuid);
    return buildCommercialEnvelope({ capabilityId: "commercial.knowledgeExecutiveBriefing", data });
  };
}

// --- Evidence Registry adapter (narrower than the existing evidence.provenance capability) -----

/**
 * getAuditLineage is deliberately excluded -- it carries internal actor identity (see the audit
 * doc Sec 2.1). This does not change the pre-existing "evidence.provenance" capability's own
 * registration (still all 6 methods, annotated internal-only -- see catalog.js's
 * INTERNAL_ONLY_CAPABILITY_ANNOTATIONS); this is a separate, additive, narrower capability.
 */
const EVIDENCE_PROVENANCE_COMMERCIAL_SAFE_METHODS = Object.freeze([
  "getEvidenceLineage",
  "getVersionLineage",
  "getRelationshipLineage",
  "getConfidenceLineage",
  "getSourceLineage",
]);

/** @param {{gateway: import('../enterprise-gateway/gateway-service.js').EnterpriseGateway}} deps */
export function createEvidenceProvenanceSummaryAdapter({ gateway } = {}) {
  requireDep(gateway, "gateway", "createEvidenceProvenanceSummaryAdapter");
  // Reuses createServiceMethodHandler() unchanged (Reuse Before Build) -- its own allowedMethods
  // option is the real enforcement mechanism, not a duplicate check here.
  const restrictedHandler = createServiceMethodHandler(gateway.platform.provenance, {
    allowedMethods: EVIDENCE_PROVENANCE_COMMERCIAL_SAFE_METHODS,
  });
  return async function evidenceProvenanceSummaryAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.evidenceProvenanceSummary", method, EVIDENCE_PROVENANCE_COMMERCIAL_SAFE_METHODS);
    const data = await restrictedHandler(context, method, ...args);
    return buildCommercialEnvelope({ capabilityId: "commercial.evidenceProvenanceSummary", data });
  };
}

// --- Product Platform adapters --------------------------------------------------------------

/** @param {{productPlatform: import('../product-platform/product-platform.js').ProductPlatform}} deps */
export function createProductAssemblyAdapter({ productPlatform } = {}) {
  requireDep(productPlatform, "productPlatform", "createProductAssemblyAdapter");
  return async function productAssemblyAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.productAssembly", method, ["assemble"]);
    const [evidenceUuid] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.productAssembly");
    const data = await productPlatform.engine.assemble(evidenceUuid);
    return buildCommercialEnvelope({ capabilityId: "commercial.productAssembly", data });
  };
}

/** @param {{productPlatform: import('../product-platform/product-platform.js').ProductPlatform}} deps */
export function createProductProfiledViewAdapter({ productPlatform } = {}) {
  requireDep(productPlatform, "productPlatform", "createProductProfiledViewAdapter");
  return async function productProfiledViewAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.productProfiledView", method, ["applyProfile"]);
    const [evidenceUuid, profileKey] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.productProfiledView");
    assertNonEmptyString(profileKey, "profileKey", "commercial.productProfiledView");
    const assembly = await productPlatform.engine.assemble(evidenceUuid);
    // applyProfile() is SYNCHRONOUS -- no await. Only the profiled (audience-scoped) view is
    // returned; the full unprofiled assembly is intentionally NOT included in the envelope, or a
    // narrow profile (e.g. executive_leadership) would leak the full technical backbone it exists
    // to exclude.
    const data = productPlatform.profiles.applyProfile(assembly, profileKey);
    return buildCommercialEnvelope({ capabilityId: "commercial.productProfiledView", data });
  };
}

/** @param {{productPlatform: import('../product-platform/product-platform.js').ProductPlatform}} deps */
export function createProductPackageAdapter({ productPlatform } = {}) {
  requireDep(productPlatform, "productPlatform", "createProductPackageAdapter");
  return async function productPackageAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.productPackage", method, ["package"]);
    const [evidenceUuid, profileKey, packageType] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.productPackage");
    assertNonEmptyString(profileKey, "profileKey", "commercial.productPackage");
    assertNonEmptyString(packageType, "packageType", "commercial.productPackage");
    const assembly = await productPlatform.engine.assemble(evidenceUuid);
    const profiledView = productPlatform.profiles.applyProfile(assembly, profileKey); // sync
    // package() is ASYNCHRONOUS -- must be awaited, or `data` becomes a spread Promise rather
    // than its resolved fields (a real bug class this program has hit before over this exact
    // call).
    const data = await productPlatform.packaging.package(assembly, profiledView, packageType);
    return buildCommercialEnvelope({ capabilityId: "commercial.productPackage", data });
  };
}

/** @param {{productPlatform: import('../product-platform/product-platform.js').ProductPlatform}} deps */
export function createMsspPartnerPackageAdapter({ productPlatform } = {}) {
  requireDep(productPlatform, "productPlatform", "createMsspPartnerPackageAdapter");
  return async function msspPartnerPackageAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.msspPartnerPackage", method, ["package"]);
    const [evidenceUuid, packageType] = args;
    assertNonEmptyString(evidenceUuid, "evidenceUuid", "commercial.msspPartnerPackage");
    assertNonEmptyString(packageType, "packageType", "commercial.msspPartnerPackage");
    const assembly = await productPlatform.engine.assemble(evidenceUuid);
    // profileKey is pinned to "mssp_operations" -- not caller-selectable. This is what makes the
    // capability a *partner* package rather than a general profiled package (see
    // commercial.productProfiledView/commercial.productPackage above for the caller-selectable
    // versions).
    const profiledView = productPlatform.profiles.applyProfile(assembly, "mssp_operations"); // sync
    const data = await productPlatform.packaging.package(assembly, profiledView, packageType); // async -- must await
    return buildCommercialEnvelope({ capabilityId: "commercial.msspPartnerPackage", data });
  };
}

// --- Commercial Quality Orchestrator (P39) adapters --------------------------------------------
//
// P39 operates on a DIFFERENT data model than every adapter above: a flat feed item (the P16-P38
// handler stack's own shape), not a CanonicalEvidence evidenceUuid. There is no existing bridge
// between the two models in this repository (confirmed in the audit doc Sec 2.4/2.1) and building
// one is a separate, larger, out-of-scope architectural event -- these two adapters take an
// already-formed `item` object directly, matching p39-handlers.js's own exported function
// signatures exactly (Reuse Before Build: called unchanged, never reimplemented). No platform DI
// dependency is needed -- P39's exported functions are pure.

export function createCommercialReadinessSummaryAdapter() {
  return async function commercialReadinessSummaryAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.readinessSummary", method, ["summarize"]);
    const [item, feedContext] = args;
    assertPlainObject(item, "item", "commercial.readinessSummary");
    const view = buildCommercialQualityView(item, feedContext || {});
    const summary = buildCommercialReadinessSummary(view);
    return buildCommercialEnvelope({ capabilityId: "commercial.readinessSummary", data: { view, summary } });
  };
}

export function createCommercialExplanationAdapter() {
  return async function commercialExplanationAdapter(context, method, ...args) {
    assertAllowedMethod("commercial.explanationSummary", method, ["explain"]);
    const [item, feedContext] = args;
    assertPlainObject(item, "item", "commercial.explanationSummary");
    const view = buildCommercialQualityView(item, feedContext || {});
    const explanation = buildCommercialExplanation(view);
    const recommendation = buildCommercialRecommendationLayer(view);
    return buildCommercialEnvelope({ capabilityId: "commercial.explanationSummary", data: { explanation, recommendation } });
  };
}
