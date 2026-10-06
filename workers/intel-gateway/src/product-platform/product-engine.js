/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19 Phase 2,
 * Intelligence Product Engine. Not imported by index.js or any production route. See README.md.
 *
 * Composes exactly one dependency -- an already-constructed KnowledgePlatform (Stage 18) --
 * assembling its already-public object/analystViews/executiveViews output into one Product
 * Assembly per evidence record. No new storage, no new correlation/provenance/explanation/
 * confidence logic: every field below is read directly off an already-existing KnowledgePlatform
 * call (KnowledgeObjectService.build(), AnalystViewService.correlationView() -- itself composing
 * three Navigation calls, ExecutiveViewService.executiveBriefing()).
 *
 * ADR-0007 boundary (see TITAN_STAGE19_READINESS_REPORT.md Sec 0): confidenceAsRecorded reaches
 * this file only inside knowledgeObject, copied verbatim from Stage 18. This file computes
 * nothing confidence-shaped.
 */

export class ProductEngineService {
  /**
   * @param {{knowledgePlatform: import('../knowledge-platform/knowledge-platform.js').KnowledgePlatform,
   *   metrics?: import('../evidence-registry/service-metrics.js').ServicePlatformMetrics}} deps
   */
  constructor(deps = {}) {
    this._knowledgePlatform = deps.knowledgePlatform;
    this._metrics = deps.metrics || null;
    if (!this._knowledgePlatform) {
      throw new Error("ProductEngineService requires a knowledgePlatform dependency");
    }
  }

  async _timed(name, fn) {
    if (this._metrics) return this._metrics.timed(`product.engine.${name}`, fn);
    return fn();
  }

  /**
   * Assembles one complete, audience-agnostic Intelligence Product for one evidence record: the
   * Knowledge Object (Stage 18 Phase 2), its correlation view (Stage 18 Phase 4's
   * correlationView(), itself composing relatedIntelligence/similarIntelligence/
   * contradictoryEvidence), and its executive briefing (Stage 18 Phase 5) -- three
   * already-existing KnowledgePlatform calls composed into one bundle, not three new analyses.
   * @param {string} evidenceUuid
   * @returns {Promise<object>}
   */
  async assemble(evidenceUuid) {
    return this._timed("assemble", async () => {
      const [knowledgeObject, correlation, briefing] = await Promise.all([
        this._knowledgePlatform.object.build(evidenceUuid),
        this._knowledgePlatform.analystViews.correlationView(evidenceUuid),
        this._knowledgePlatform.executiveViews.executiveBriefing(evidenceUuid),
      ]);

      if (!knowledgeObject.found) {
        return { evidenceUuid, found: false, reason: "not_found", generatedAt: new Date().toISOString() };
      }

      return {
        evidenceUuid,
        found: true,
        knowledgeObject,
        correlation,
        briefing,
        generatedAt: new Date().toISOString(),
      };
    });
  }

  /**
   * Deterministic batch composition: assembles each evidence record independently and returns
   * them as one list. Introduces no cross-record correlation or aggregation logic of its own --
   * that would be new analysis, not composition, and is explicitly out of scope (see README.md's
   * NON-GOALS). Exists because Phase 4 packaging types like "Enterprise Threat Intelligence
   * Report" typically span more than one evidence record.
   * @param {string[]} evidenceUuids
   * @returns {Promise<{evidenceUuids: string[], assemblies: object[]}>}
   */
  async assembleMany(evidenceUuids) {
    return this._timed("assembleMany", async () => {
      const assemblies = await Promise.all(evidenceUuids.map((uuid) => this.assemble(uuid)));
      return { evidenceUuids, assemblies };
    });
  }
}
