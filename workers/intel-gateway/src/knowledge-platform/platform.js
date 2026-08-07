/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18, Platform
 * Orchestration. Not imported by index.js or any production route. See README.md.
 *
 * Resolves KP_FLAGS for `environment` and, if enabled, builds a KnowledgePlatform over a
 * caller-supplied IntelligenceService. Mirrors intelligence-platform/platform.js's
 * createIntelligencePlatform() shape, with one necessary difference: this layer has no root of
 * its own to construct from scratch (it composes an upstream IntelligenceService's already-built
 * properties), so `intelligenceService` is a required input, not something this function builds.
 *
 * No circular dependencies: this file imports FROM knowledge-platform.js and feature-flags.js
 * only; nothing in evidence-registry/, intelligence-platform/, or knowledge-platform.js imports
 * this file.
 */

import { KnowledgePlatform } from "./knowledge-platform.js";
import { resolveKpFlags } from "./feature-flags.js";

/**
 * @param {{environment?: string,
 *   intelligenceService: import('../intelligence-platform/intelligence-service.js').IntelligenceService}} options
 * @returns {{enabled: boolean, platform: KnowledgePlatform | null, environment: string, reason?: string}}
 */
export function createKnowledgePlatform(options = {}) {
  const environment = options.environment || "production";
  const flags = resolveKpFlags(environment);

  if (!flags.KP_ENABLED) {
    return {
      enabled: false,
      platform: null,
      environment,
      reason: `KP_ENABLED is false for environment "${environment}"`,
    };
  }

  if (!options.intelligenceService) {
    throw new Error("createKnowledgePlatform() requires options.intelligenceService -- this layer composes an existing IntelligenceService, it does not construct one");
  }

  const { lookup, correlation, provenance, explainability } = options.intelligenceService;
  // IntelligenceService.metrics is IntelligenceMetricsService (a wrapper), not the raw
  // ServicePlatformMetrics instance KnowledgePlatform's services call .timed() on --
  // .sharedServiceMetrics is the one property that unwraps to the actual shared instance
  // (see intelligence-service.js's IntelligenceMetricsService docs).
  const metrics = options.intelligenceService.metrics?.sharedServiceMetrics;
  const platform = new KnowledgePlatform({ lookup, correlation, provenance, explainability, metrics });
  return { enabled: true, platform, environment };
}
