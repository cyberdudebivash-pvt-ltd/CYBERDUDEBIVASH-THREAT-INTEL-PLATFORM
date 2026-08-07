/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19 Phase 5,
 * Product Quality & Governance. Not imported by index.js or any production route. See README.md.
 *
 * Composes knowledge-platform/knowledge-quality.js's evaluateKnowledgeObjectQuality() wholesale
 * for the evidence-completeness/provenance/correlation/explanation/unsupported-assertion
 * dimensions -- Phase 5's own instruction ("compose KnowledgeQualityService rather than
 * reimplementing"). Only the two dimensions Stage 18 has no equivalent for (provenance/
 * explainability preserved *in a package*, and profile/packaging consistency) are new checks
 * here, over an already-built package rather than a bare Knowledge Object.
 */

import { evaluateKnowledgeObjectQuality } from "../knowledge-platform/knowledge-quality.js";
import { resolveProductProfile } from "./product-profiles.js";

export const PRODUCT_QUALITY_VERSION = "19.1.0";

export const PRODUCT_QUALITY_RULES = Object.freeze([
  "evidence.completeness", // delegated wholesale to knowledge-platform's evaluateKnowledgeObjectQuality()
  "provenance.preserved-in-package",
  "explainability.included-in-package",
  "profile.compliance",
  "assertions.every-statement-has-basis", // also delegated, via the same evaluateKnowledgeObjectQuality() call
  "packaging.consistency",
]);

/**
 * Flattens every basis-carrying item across a package's briefing content so
 * detectUnsupportedAssertions() (Stage 18, reused via evaluateKnowledgeObjectQuality()'s own
 * `assertionItems` context parameter) can check all of them in one pass. businessImpact and
 * operationalImpact are single objects on ExecutiveViewService's own output (unlike
 * strategicObservations/keyEvidence/recommendedActions/intelligenceLimitations, which are
 * arrays) -- pushed individually here, not spread, to match executive-views.js's actual shape.
 * @param {object} pkg - ProductPackagingService.package()'s output
 */
export function flattenAssertionItems(pkg) {
  const items = [];
  const briefing = pkg?.content?.briefing;
  if (!briefing || briefing.found === false) return items;
  if (briefing.businessImpact) items.push(briefing.businessImpact);
  if (briefing.operationalImpact) items.push(briefing.operationalImpact);
  items.push(...(briefing.strategicObservations || []));
  items.push(...(briefing.keyEvidence || []));
  items.push(...(briefing.recommendedActions || []));
  items.push(...(briefing.intelligenceLimitations || []));
  return items;
}

/** Provenance survives packaging: the package's own `provenance` field is non-empty. */
export function validateProvenancePreservedInPackage(pkg) {
  const rule = "provenance.preserved-in-package";
  const preserved = pkg.found !== false && pkg.provenance != null && Object.keys(pkg.provenance).length > 0;
  return { preserved, rule };
}

/** Explainability survives packaging: the package's own `explainability.summary` is a non-empty string. */
export function validateExplainabilityIncludedInPackage(pkg) {
  const rule = "explainability.included-in-package";
  const included = pkg.found !== false && typeof pkg.explainability?.summary === "string" && pkg.explainability.summary.length > 0;
  return { included, rule };
}

/**
 * Profile compliance: the package's `content` carries exactly the sections its declared profile
 * promises -- neither a missing section (an incomplete package) nor a silently-invented one.
 * @param {object} pkg
 * @param {string} profileKey
 */
export function validateProfileCompliance(pkg, profileKey) {
  const rule = "profile.compliance";
  let profile;
  try {
    profile = resolveProductProfile(profileKey);
  } catch {
    return { compliant: false, rule, reason: "unknown_profile" };
  }
  if (pkg.found === false) return { compliant: true, rule, reason: "not_found_package_has_no_content_to_check" };
  const content = pkg.content || {};
  const missingSections = profile.sections.filter((section) => !Object.hasOwn(content, section));
  return { compliant: missingSections.length === 0, rule, expectedSections: profile.sections, missingSections };
}

/** Packaging consistency: the envelope's own required fields are present. */
export function validatePackagingConsistency(pkg) {
  const rule = "packaging.consistency";
  const requiredFields = ["packageId", "packageType", "evidenceUuid", "metadata"];
  const missingFields = pkg.found === false ? [] : requiredFields.filter((field) => pkg[field] == null);
  return { consistent: pkg.found === false || missingFields.length === 0, rule, missingFields };
}

/**
 * Aggregating evaluation -- runs every Stage 19 quality check against one package (plus the
 * assembly it was built from, needed for the delegated Knowledge Object check) and returns one
 * combined report.
 * @param {object} assembly - ProductEngineService.assemble()'s output
 * @param {object} pkg - ProductPackagingService.package()'s output
 * @param {string} profileKey
 */
export function evaluateProductQuality(assembly, pkg, profileKey) {
  const knowledgeObjectQuality = assembly.found
    ? evaluateKnowledgeObjectQuality(assembly.knowledgeObject, { assertionItems: flattenAssertionItems(pkg) })
    : null;
  return {
    qualityVersion: PRODUCT_QUALITY_VERSION,
    knowledgeObjectQuality,
    provenancePreservedInPackage: validateProvenancePreservedInPackage(pkg),
    explainabilityIncludedInPackage: validateExplainabilityIncludedInPackage(pkg),
    profileCompliance: validateProfileCompliance(pkg, profileKey),
    packagingConsistency: validatePackagingConsistency(pkg),
  };
}

/** Auditability/introspection surface, mirroring correlation-policy.js's/knowledge-quality.js's describe*(). */
export function describeProductQualityFramework() {
  return { version: PRODUCT_QUALITY_VERSION, rules: [...PRODUCT_QUALITY_RULES] };
}

/**
 * Thin class wrapper exposing the functions above as instance methods -- the shape the Gateway's
 * createServiceMethodHandler() adapter expects, mirroring KnowledgeQualityService's identical
 * pattern. Every method below delegates verbatim; no logic is duplicated.
 */
export class ProductQualityService {
  /**
   * @param {{productEngine: import('./product-engine.js').ProductEngineService,
   *   profiles: import('./product-profiles.js').ProductProfileService,
   *   packaging: import('./product-packaging.js').ProductPackagingService}} deps
   */
  constructor(deps = {}) {
    this._productEngine = deps.productEngine;
    this._profiles = deps.profiles;
    this._packaging = deps.packaging;
    if (!this._productEngine || !this._profiles || !this._packaging) {
      throw new Error("ProductQualityService requires productEngine, profiles, and packaging dependencies");
    }
  }

  evaluate(assembly, pkg, profileKey) {
    return evaluateProductQuality(assembly, pkg, profileKey);
  }

  describeQualityFramework() {
    return describeProductQualityFramework();
  }

  /**
   * Convenience method for Gateway callers: runs the full assemble -> profile -> package ->
   * evaluate pipeline in one round trip.
   * @param {string} evidenceUuid
   * @param {string} profileKey
   * @param {string} packageType
   */
  async evaluateForEvidence(evidenceUuid, profileKey, packageType) {
    const assembly = await this._productEngine.assemble(evidenceUuid);
    if (!assembly.found) return { evidenceUuid, found: false, reason: assembly.reason };
    const profiledView = this._profiles.applyProfile(assembly, profileKey);
    const pkg = await this._packaging.package(assembly, profiledView, packageType);
    return { evidenceUuid, found: true, quality: evaluateProductQuality(assembly, pkg, profileKey) };
  }
}
