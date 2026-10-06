/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19 Phase 3,
 * Product Profiles. Not imported by index.js or any production route. See README.md.
 *
 * Six reusable audience profiles, each a named, deterministic subset of an already-assembled
 * ProductEngineService.assemble() output's three sections (knowledgeObject, correlation,
 * briefing). Mirrors knowledge-platform/knowledge-quality.js's pure-function style: no I/O, no
 * new correlation/provenance/explanation/confidence logic, no metrics wrapper (nothing here is
 * expensive enough to warrant one, matching KnowledgeQualityService's identical precedent).
 *
 * Phase 3's own constraint, made structural: "Profiles may change presentation and included
 * sections but must not alter the underlying intelligence." applyProductProfile() below never
 * mutates or recomputes a section's value -- it only selects which already-computed sections are
 * included in the returned view.
 */

export const PRODUCT_AUDIENCE_PROFILES = Object.freeze({
  soc_analyst: Object.freeze({
    name: "SOC Analyst",
    description:
      "Technical detail for triage and response: the full Knowledge Object and correlation " +
      "view. No executive framing.",
    sections: Object.freeze(["knowledgeObject", "correlation"]),
  }),
  threat_intelligence_analyst: Object.freeze({
    name: "Threat Intelligence Analyst",
    description:
      "Full technical and correlation detail plus the executive briefing's evidentiary inputs, " +
      "for deep analysis.",
    sections: Object.freeze(["knowledgeObject", "correlation", "briefing"]),
  }),
  executive_leadership: Object.freeze({
    name: "Executive Leadership",
    description: "Business/operational framing only -- the executive briefing.",
    sections: Object.freeze(["briefing"]),
  }),
  mssp_operations: Object.freeze({
    name: "MSSP Operations",
    description:
      "The full assembly -- Knowledge Object, correlation, and briefing -- for a managed " +
      "service provider operating on behalf of a client.",
    sections: Object.freeze(["knowledgeObject", "correlation", "briefing"]),
  }),
  vulnerability_management: Object.freeze({
    name: "Vulnerability Management",
    description: "The Knowledge Object only -- relationships, gaps, and collection recommendations.",
    sections: Object.freeze(["knowledgeObject"]),
  }),
  incident_response: Object.freeze({
    name: "Incident Response",
    description:
      "Knowledge Object, correlation (including contradictory evidence), and the briefing's " +
      "recommended actions.",
    sections: Object.freeze(["knowledgeObject", "correlation", "briefing"]),
  }),
});

/**
 * Unrecognized profile keys throw rather than silently returning an empty/default view -- secure
 * by default, matching resolveKpFlags()'s Object.hasOwn() idiom (avoids resolving an inherited
 * Object.prototype member for a string like "constructor"/"toString").
 * @param {string} profileKey
 * @returns {{key: string, name: string, description: string, sections: string[]}}
 */
export function resolveProductProfile(profileKey) {
  if (!Object.hasOwn(PRODUCT_AUDIENCE_PROFILES, profileKey)) {
    throw new Error(
      `Unknown product profile "${profileKey}". Known profiles: ${Object.keys(PRODUCT_AUDIENCE_PROFILES).join(", ")}`
    );
  }
  return { key: profileKey, ...PRODUCT_AUDIENCE_PROFILES[profileKey] };
}

/** Auditability/introspection surface, mirroring correlation-policy.js's describePolicy(). */
export function listProductProfiles() {
  return Object.keys(PRODUCT_AUDIENCE_PROFILES).map((key) => ({ key, ...PRODUCT_AUDIENCE_PROFILES[key] }));
}

/**
 * Selects the profile's declared sections from an already-assembled product, unchanged. Never
 * recomputes a section's value -- pure field selection over ProductEngineService.assemble()'s
 * output.
 * @param {object} assembly - ProductEngineService.assemble()'s output
 * @param {string} profileKey
 * @returns {object}
 */
export function applyProductProfile(assembly, profileKey) {
  const profile = resolveProductProfile(profileKey);
  if (!assembly.found) {
    return { evidenceUuid: assembly.evidenceUuid, found: false, reason: assembly.reason, profileKey: profile.key, profileName: profile.name };
  }
  const view = { evidenceUuid: assembly.evidenceUuid, found: true, profileKey: profile.key, profileName: profile.name };
  for (const section of profile.sections) {
    view[section] = assembly[section];
  }
  return view;
}

/**
 * Thin class wrapper exposing the pure functions above as instance methods -- the shape the
 * Gateway's createServiceMethodHandler() adapter expects, mirroring KnowledgeQualityService's
 * identical "wrap pure functions for capability registration" pattern. Every method below
 * delegates verbatim; no logic is duplicated.
 */
export class ProductProfileService {
  listProfiles() {
    return listProductProfiles();
  }

  resolveProfile(profileKey) {
    return resolveProductProfile(profileKey);
  }

  applyProfile(assembly, profileKey) {
    return applyProductProfile(assembly, profileKey);
  }
}
