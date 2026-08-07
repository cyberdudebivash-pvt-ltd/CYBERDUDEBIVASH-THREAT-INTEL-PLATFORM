/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18, Composition Root.
 * Not imported by index.js or any production route. See README.md.
 *
 * "One Knowledge Platform" -- the single aggregating facade mirroring Stage 12's EvidenceService
 * and Stage 13's IntelligenceService pattern two layers up. Composes the five Stage 18 services
 * (Object, Navigation, Analyst Views, Executive Views, Quality) over exactly one shared
 * dependency set: IntelligenceService's own already-public lookup/correlation/provenance/
 * explainability properties (Stage 12/13/17). No business logic of its own.
 */

import { KnowledgeObjectService } from "./knowledge-object.js";
import { KnowledgeNavigationService } from "./knowledge-navigation.js";
import { AnalystViewService } from "./analyst-views.js";
import { ExecutiveViewService } from "./executive-views.js";
import { KnowledgeQualityService } from "./knowledge-quality.js";

export class KnowledgePlatform {
  /**
   * @param {{lookup: import('../intelligence-platform/intelligence-service.js').IntelligenceLookupService,
   *   correlation: import('../intelligence-platform/correlation-engine.js').IntelligenceCorrelationService,
   *   provenance: import('../evidence-registry/provenance-engine.js').EvidenceProvenanceEngine,
   *   explainability: import('../intelligence-platform/explainability-engine.js').IntelligenceExplainabilityService,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    const { lookup, correlation, provenance, explainability, metrics } = deps;
    if (!lookup || !correlation || !provenance || !explainability) {
      throw new Error("KnowledgePlatform requires lookup, correlation, provenance, and explainability dependencies");
    }

    this.object = new KnowledgeObjectService({ lookup, explainability, metrics });
    this.navigation = new KnowledgeNavigationService({ lookup, correlation, provenance, explainability, metrics });
    this.analystViews = new AnalystViewService({ knowledgeObject: this.object, navigation: this.navigation, metrics });
    this.executiveViews = new ExecutiveViewService({ knowledgeObject: this.object, navigation: this.navigation, metrics });
    this.quality = new KnowledgeQualityService({ knowledgeObject: this.object });
    // Retained (not just threaded into the five services above) so a future external composer
    // one layer up can share this exact instance rather than going without metrics or
    // constructing a second one. Read-only by convention (no setter); every existing consumer of
    // this class ignores an added property it doesn't ask for.
    this.metrics = metrics || null;
  }
}
