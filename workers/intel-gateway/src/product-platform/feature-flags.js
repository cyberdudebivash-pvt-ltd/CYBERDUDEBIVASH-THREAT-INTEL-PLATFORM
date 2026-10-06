/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) feature flags -- Stage 19 Phase 1
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Mirrors knowledge-platform/feature-flags.js's exact per-environment shape, defaults
 * (development/testing enabled, canary/production disabled), and Object.hasOwn() resolution.
 * Re-exports DEPLOYMENT_ENVIRONMENTS from knowledge-platform/ (which re-exports it from
 * intelligence-platform/, which re-exports evidence-registry's) rather than redefining it a
 * fifth time. Imported from knowledge-platform/, not intelligence-platform/ or
 * enterprise-gateway/ directly: this directory composes KnowledgePlatform (the one authorized
 * hop down), it does not reach past it -- see README.md and product-platform.js's own dependency
 * list. Keeping this directory's dependency to that one authorized hop (see
 * zero-blast-radius.test.js).
 *
 * PP_ENABLED: governs whether createProductPlatform() may construct a live product platform.
 * No second "internal adoption" flag is introduced here -- unlike EIG_FLAGS/EIPS_FLAGS/KP_FLAGS,
 * this stage has no authorized internal consumer yet to gate (that would be a Stage 20+ decision,
 * out of scope per this stage's own NON-GOALS), so a second always-false flag would be
 * speculative rather than testable.
 */

import { DEPLOYMENT_ENVIRONMENTS } from "../knowledge-platform/feature-flags.js";

export { DEPLOYMENT_ENVIRONMENTS };

export const PP_FLAGS = Object.freeze({
  development: Object.freeze({ PP_ENABLED: true }),
  testing: Object.freeze({ PP_ENABLED: true }),
  canary: Object.freeze({ PP_ENABLED: false }),
  production: Object.freeze({ PP_ENABLED: false }),
});

/**
 * Unrecognized/missing environment strings resolve to "production" (all-disabled) -- secure by
 * default, never fails open. Object.hasOwn(), not a bare `PP_FLAGS[environment] || ...` lookup,
 * for the same reason every lower layer's resolve*Flags() does: avoids resolving an inherited
 * Object.prototype member for a string like "constructor"/"toString".
 * @param {string} [environment]
 * @returns {{PP_ENABLED: boolean}}
 */
export function resolvePpFlags(environment) {
  return Object.hasOwn(PP_FLAGS, environment) ? PP_FLAGS[environment] : PP_FLAGS.production;
}

/** Rollback: forces the safest (all-disabled) flag state regardless of environment. */
export function rollbackPpFlags() {
  return PP_FLAGS.production;
}
