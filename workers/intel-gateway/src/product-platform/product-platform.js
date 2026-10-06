/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19,
 * Composition Root. Not imported by index.js or any production route. See README.md.
 *
 * "One Product Platform" -- the single aggregating facade mirroring Stage 12's EvidenceService,
 * Stage 13's IntelligenceService, and Stage 18's KnowledgePlatform pattern, one layer up each
 * time. Composes the four Stage 19 services (Engine, Profiles, Packaging, Quality) over exactly
 * one shared dependency: an already-constructed KnowledgePlatform (Stage 18). No business logic
 * of its own.
 */

import { ProductEngineService } from "./product-engine.js";
import { ProductProfileService } from "./product-profiles.js";
import { ProductPackagingService } from "./product-packaging.js";
import { ProductQualityService } from "./product-quality.js";

export class ProductPlatform {
  /**
   * @param {{knowledgePlatform: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    const { knowledgePlatform } = deps;
    if (!knowledgePlatform) {
      throw new Error("ProductPlatform requires a knowledgePlatform dependency");
    }
    // Prefer an explicitly-injected metrics instance; fall back to the one KnowledgePlatform
    // itself now exposes (knowledge-platform.js's own `this.metrics`, added this stage) so the
    // whole five-layer chain (evidence-registry -> intelligence-platform -> knowledge-platform ->
    // product-platform) shares exactly one ServicePlatformMetrics instance end to end, the same
    // "no duplicate metrics instance" property every layer below already guards.
    const metrics = deps.metrics || knowledgePlatform.metrics || null;

    this.engine = new ProductEngineService({ knowledgePlatform, metrics });
    this.profiles = new ProductProfileService();
    this.packaging = new ProductPackagingService({ metrics });
    this.quality = new ProductQualityService({ productEngine: this.engine, profiles: this.profiles, packaging: this.packaging });
  }
}
