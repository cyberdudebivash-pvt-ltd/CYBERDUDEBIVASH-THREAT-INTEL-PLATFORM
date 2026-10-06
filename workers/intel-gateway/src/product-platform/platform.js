/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19, Platform
 * Orchestration. Not imported by index.js or any production route. See README.md.
 *
 * Resolves PP_FLAGS for `environment` and, if enabled, builds a ProductPlatform over a
 * caller-supplied KnowledgePlatform. Mirrors knowledge-platform/platform.js's
 * createKnowledgePlatform() shape, with the identical one necessary difference: this layer has
 * no root of its own to construct from scratch (it composes an upstream KnowledgePlatform's
 * already-built properties), so `knowledgePlatform` is a required input, not something this
 * function builds.
 *
 * No circular dependencies: this file imports FROM product-platform.js and feature-flags.js
 * only; nothing in evidence-registry/, intelligence-platform/, enterprise-gateway/, or
 * knowledge-platform/ imports this file.
 */

import { ProductPlatform } from "./product-platform.js";
import { resolvePpFlags } from "./feature-flags.js";

/**
 * @param {{environment?: string,
 *   knowledgePlatform: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform}} options
 * @returns {{enabled: boolean, platform: ProductPlatform | null, environment: string, reason?: string}}
 */
export function createProductPlatform(options = {}) {
  const environment = options.environment || "production";
  const flags = resolvePpFlags(environment);

  if (!flags.PP_ENABLED) {
    return {
      enabled: false,
      platform: null,
      environment,
      reason: `PP_ENABLED is false for environment "${environment}"`,
    };
  }

  if (!options.knowledgePlatform) {
    throw new Error("createProductPlatform() requires options.knowledgePlatform -- this layer composes an existing KnowledgePlatform, it does not construct one");
  }

  const platform = new ProductPlatform({ knowledgePlatform: options.knowledgePlatform, metrics: options.knowledgePlatform.metrics });
  return { enabled: true, platform, environment };
}
