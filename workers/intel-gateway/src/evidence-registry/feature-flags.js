/**
 * Evidence Registry feature flags  -  Phase 9 scaffolding (Project TITAN Stage 8).
 * Not imported by index.js or any production route. See README.md.
 *
 * Nothing reads these flags yet, because nothing is wired up yet. This file
 * establishes the naming convention a future, authorized integration should
 * follow (Stage 8 Engineering Requirements: "Feature-flagged").
 */

export const EVIDENCE_REGISTRY_FLAGS = Object.freeze({
  // Master switch for wiring this scaffolding into any live code path.
  // Must remain false until ADR-0008 is formally Accepted and Migration
  // Roadmap Phase 3 has shipped - see TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md.
  SCAFFOLDING_ENABLED: false,

  // Sub-flags for future, separately-authorized capability - not active,
  // listed here only to reserve the naming convention.
  REGISTRY_SERVICE_ENABLED: false,
  EVIDENCE_API_ENABLED: false,
});

// =======================================================================
// Stage 10 Phase 6  -  environment-aware flag support for the Canonical
// Evidence Core specifically. EVIDENCE_REGISTRY_FLAGS above is unchanged:
// it still governs the Registry/Service/API and is still all-false,
// still gated on ADR-0008 Acceptance. CEC_FLAGS below governs only
// whether this directory's own inert domain-model/validation/serialization
// code may be *exercised* (e.g. by this stage's own test suite)  -  it does
// not gate wiring into any production route, which SCAFFOLDING_ENABLED
// above continues to gate.
// =======================================================================

export const DEPLOYMENT_ENVIRONMENTS = Object.freeze(["development", "testing", "canary", "production"]);

/**
 * Per-environment CEC flag table. Every environment except "canary"/"production" defaults to
 * enabled *for exercising this directory's own code in isolation* (tests, local dev)  -  none of
 * these values are read by index.js or any P-layer handler, so "enabled" here has zero
 * production blast radius regardless of value, unlike SCAFFOLDING_ENABLED above.
 */
export const CEC_FLAGS = Object.freeze({
  development: Object.freeze({ CEC_ENABLED: true }),
  testing: Object.freeze({ CEC_ENABLED: true }),
  canary: Object.freeze({ CEC_ENABLED: false }),
  production: Object.freeze({ CEC_ENABLED: false }),
});

/**
 * Resolves CEC flag state for an environment. Unrecognized/missing environment strings
 * resolve to "production" (the all-disabled state)  -  secure by default (Principle 9), never
 * fails open.
 * @param {string} [environment]
 * @returns {{CEC_ENABLED: boolean}}
 */
export function resolveCecFlags(environment) {
  return CEC_FLAGS[environment] || CEC_FLAGS.production;
}

/**
 * Rollback: forces the safest (all-disabled) flag state regardless of environment. A rollback
 * procedure calls this one function rather than needing to remember which environment string
 * means "off."
 * @returns {{CEC_ENABLED: boolean}}
 */
export function rollbackCecFlags() {
  return CEC_FLAGS.production;
}

// =======================================================================
// Stage 11  -  environment-aware flag support for the Enterprise Evidence
// Registry (EER) specifically. EVIDENCE_REGISTRY_FLAGS and CEC_FLAGS above
// are both unchanged. EER_FLAGS below governs only whether this directory's
// registry-service.js/in-memory-repository.js/lifecycle.js/versioning.js/
// indexes.js may be *exercised* (tests, local dev)  -  same "zero production
// blast radius regardless of value" property as CEC_FLAGS, since nothing
// reads this from index.js or any P-layer handler. Reuses
// DEPLOYMENT_ENVIRONMENTS above rather than redefining the environment list.
// =======================================================================

/**
 * Per-environment EER flag table. Mirrors CEC_FLAGS's exact shape and defaults  - 
 * development/testing enabled, canary/production disabled.
 */
export const EER_FLAGS = Object.freeze({
  development: Object.freeze({ EER_ENABLED: true }),
  testing: Object.freeze({ EER_ENABLED: true }),
  canary: Object.freeze({ EER_ENABLED: false }),
  production: Object.freeze({ EER_ENABLED: false }),
});

/**
 * Resolves EER flag state for an environment. Unrecognized/missing environment strings resolve
 * to "production" (the all-disabled state)  -  secure by default, never fails open. Mirrors
 * resolveCecFlags() exactly.
 * @param {string} [environment]
 * @returns {{EER_ENABLED: boolean}}
 */
export function resolveEerFlags(environment) {
  return EER_FLAGS[environment] || EER_FLAGS.production;
}

/**
 * Rollback: forces the safest (all-disabled) flag state regardless of environment. Mirrors
 * rollbackCecFlags() exactly.
 * @returns {{EER_ENABLED: boolean}}
 */
export function rollbackEerFlags() {
  return EER_FLAGS.production;
}
