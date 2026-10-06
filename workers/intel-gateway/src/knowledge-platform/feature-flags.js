/**
 * Enterprise Intelligence Knowledge Platform (EIKP) feature flags -- Stage 18 Phase 1 (Project
 * TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Mirrors enterprise-gateway/feature-flags.js's exact per-environment shape, defaults
 * (development/testing enabled, canary/production disabled), and Object.hasOwn() resolution.
 * Re-exports DEPLOYMENT_ENVIRONMENTS from intelligence-platform/ (which re-exports
 * evidence-registry's) rather than redefining it a fourth time. Imported from
 * intelligence-platform/, not enterprise-gateway/: this directory composes IntelligenceService
 * directly (the same one hop enterprise-gateway/ takes), it is a peer of enterprise-gateway/, not
 * a consumer of it -- see README.md and knowledge-platform.js's own dependency list. Keeping this
 * directory's dependency to that one authorized hop (see zero-blast-radius.test.js).
 *
 * KP_ENABLED: governs whether createKnowledgePlatform() may construct a live knowledge platform.
 * INTERNAL_ADOPTION_ENABLED: a separate, narrower gate for a future authorized internal consumer,
 * mirroring EIG_FLAGS/EIPS_FLAGS's identical two-flag shape for the identical reason: the
 * property that matters is zero blast radius in canary/production, not a flag that's never true
 * anywhere (which couldn't be regression-tested at all).
 */

import { DEPLOYMENT_ENVIRONMENTS } from "../intelligence-platform/feature-flags.js";

export { DEPLOYMENT_ENVIRONMENTS };

export const KP_FLAGS = Object.freeze({
  development: Object.freeze({ KP_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  testing: Object.freeze({ KP_ENABLED: true, INTERNAL_ADOPTION_ENABLED: true }),
  canary: Object.freeze({ KP_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
  production: Object.freeze({ KP_ENABLED: false, INTERNAL_ADOPTION_ENABLED: false }),
});

/**
 * Unrecognized/missing environment strings resolve to "production" (all-disabled) -- secure by
 * default, never fails open. Object.hasOwn(), not a bare `KP_FLAGS[environment] || ...` lookup,
 * for the same reason every lower layer's resolve*Flags() does: avoids resolving an inherited
 * Object.prototype member for a string like "constructor"/"toString".
 * @param {string} [environment]
 * @returns {{KP_ENABLED: boolean, INTERNAL_ADOPTION_ENABLED: boolean}}
 */
export function resolveKpFlags(environment) {
  return Object.hasOwn(KP_FLAGS, environment) ? KP_FLAGS[environment] : KP_FLAGS.production;
}

/** Rollback: forces the safest (all-disabled) flag state regardless of environment. */
export function rollbackKpFlags() {
  return KP_FLAGS.production;
}
