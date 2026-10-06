/**
 * Canonical Evidence Core migration adapters  -  Stage 10 Phase 7 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Every adapter here is a pure function operating on a documented DATA SHAPE, not an import
 * of the actual P-layer handler file that produces that shape. This is a deliberate design
 * choice, not an oversight: it means adopting these adapters never creates a real module
 * dependency edge from evidence-registry/ into p20-handlers.js / p25-handlers.js /
 * p31-handlers.js, keeping this directory's "zero blast radius" property (enforced by
 * scripts/titan_architecture_governance_check.py's boundary check) trivially true regardless
 * of how sophisticated these adapters get. Each adapter's docstring cites exactly where its
 * source shape was verified, so a shape change upstream is a documentation-review trigger,
 * not a silent drift.
 *
 * "Migration must be transparent. No consumer rewrites." (Phase 7) is satisfied by
 * construction: nothing calls these adapters yet, so there is no consumer to rewrite. When a
 * future, separately-authorized stage does wire one in, it is choosing to call a pure
 * function  -  no existing code needs to change shape to accommodate it.
 */

import { createCanonicalEvidence, createEvidenceEntity } from "./entity.js";
import { EvidenceMigrationAdapterInterface } from "./interfaces.js";

/**
 * Adapts P20's live `item.evidence_chain` shape (p20-handlers.js, buildEvidenceChainBlock  - 
 * the same shape entity.js's EvidenceChainCore already documents) into a CanonicalEvidence.
 * Composes createEvidenceEntity() + createCanonicalEvidence() rather than reimplementing
 * either (Reuse Before Build).
 */
export class P20EvidenceChainAdapter extends EvidenceMigrationAdapterInterface {
  /**
   * @param {import('./entity.js').EvidenceChainCore} evidenceChain
   * @returns {import('./entity.js').CanonicalEvidence}
   */
  adapt(evidenceChain) {
    const base = createEvidenceEntity(evidenceChain || {});
    return createCanonicalEvidence(base, {
      audit_metadata: { producer_implementation: this.sourceShapeName() },
    });
  }

  sourceShapeName() {
    return "p20-evidence-chain";
  }
}

/**
 * Adapts a set of CanonicalRelationship records (TITAN_GRAPH_INTERFACE_SPECIFICATION.md
 * Part A) that reference a given evidence entity into that entity's lightweight
 * related_reports / related_cves / related_threat_actors / related_campaigns /
 * related_attack_techniques arrays. Direction note: CanonicalRelationship.evidence_references
 * points FROM a relationship TO evidence (an edge citing this evidence as support); this
 * adapter reads the *other* endpoint of each such relationship (whichever of source_entity /
 * target_entity is not the evidence's own related entity) and buckets it by entity_type  - 
 * the inverse direction, populating what this evidence itself speaks to.
 */
export class CanonicalRelationshipAdapter extends EvidenceMigrationAdapterInterface {
  /**
   * @param {{evidence: import('./entity.js').CanonicalEvidence, relationships: Array<{
   *   evidence_references?: string[], source_entity?: {entity_type: string, entity_id: string},
   *   target_entity?: {entity_type: string, entity_id: string}
   * }>}} input
   * @returns {import('./entity.js').CanonicalEvidence}
   */
  adapt(input) {
    const { evidence, relationships = [] } = input || {};
    if (!evidence) {
      throw new Error("CanonicalRelationshipAdapter.adapt requires { evidence, relationships }");
    }

    const buckets = {
      ThreatReport: new Set(evidence.related_reports || []),
      CVE: new Set(evidence.related_cves || []),
      ThreatActor: new Set(evidence.related_threat_actors || []),
      Campaign: new Set(evidence.related_campaigns || []),
      MitreTechnique: new Set(evidence.related_attack_techniques || []),
    };

    const evidenceUuid = evidence.evidence_uuid;
    for (const rel of relationships) {
      if (!evidenceUuid || !(rel.evidence_references || []).includes(evidenceUuid)) continue;
      for (const endpoint of [rel.source_entity, rel.target_entity]) {
        if (endpoint && buckets[endpoint.entity_type]) {
          buckets[endpoint.entity_type].add(endpoint.entity_id);
        }
      }
    }

    return {
      ...evidence,
      related_reports: [...buckets.ThreatReport],
      related_cves: [...buckets.CVE],
      related_threat_actors: [...buckets.ThreatActor],
      related_campaigns: [...buckets.Campaign],
      related_attack_techniques: [...buckets.MitreTechnique],
    };
  }

  sourceShapeName() {
    return "canonical-relationship.0.1-draft";
  }
}

/**
 * Attaches a P25 computeEnterpriseTrustScore(item) output verbatim as canonical_confidence_
 * object. Shape `{dims, totalEarned, totalMax, pct, tier, tierColor}`, verified directly
 * against p25-handlers.js's own return statement, not assumed  -  this adapter does not
 * redeclare or recompute that shape, only carries it (Single Source of Truth: P25 remains the
 * one place trust scores are computed).
 */
export class P25ConfidenceAdapter extends EvidenceMigrationAdapterInterface {
  /**
   * @param {{evidence: import('./entity.js').CanonicalEvidence, trustScore: {
   *   dims?: unknown, totalEarned?: number, totalMax?: number, pct?: number, tier?: string,
   *   tierColor?: string
   * }}} input
   * @returns {import('./entity.js').CanonicalEvidence}
   */
  adapt(input) {
    const { evidence, trustScore } = input || {};
    if (!evidence || !trustScore) {
      throw new Error("P25ConfidenceAdapter.adapt requires { evidence, trustScore }");
    }
    const evidenceWeight =
      typeof trustScore.pct === "number" ? Math.max(0, Math.min(1, trustScore.pct / 100)) : undefined;
    return {
      ...evidence,
      canonical_confidence_object: trustScore,
      evidence_weight: evidenceWeight !== undefined ? evidenceWeight : evidence.evidence_weight,
    };
  }

  sourceShapeName() {
    return "p25-enterprise-trust-score";
  }
}

/**
 * Composite adapter: given a whole P-layer `item` (a feed/report record, the shape passed
 * through the standard P-layer response chain), extracts every evidence-relevant field into a
 * single CanonicalEvidence in one call, composing the three adapters above rather than
 * reimplementing their logic. This is the "Existing Report Structures" adapter Phase 7 asks
 * for  -  `item` here is documented by field access only (item.evidence_chain, item.id,
 * item.cve_id/cves, item.actor_tag, item.mitre_techniques, item.iocs), the same defensive
 * field-presence style p20/p25-handlers.js themselves already use, so a field's absence degrades
 * gracefully rather than throwing. `item.iocs` verified against the live shape (p20/p22/
 * p18-handlers.js: an array of `{value, confidence, ...}` objects) in Stage 11 Phase 5, when
 * related_iocs was added to CanonicalEvidence for registry indexing.
 */
export class ReportItemAdapter extends EvidenceMigrationAdapterInterface {
  constructor() {
    super();
    this._evidenceChainAdapter = new P20EvidenceChainAdapter();
    this._confidenceAdapter = new P25ConfidenceAdapter();
  }

  /**
   * @param {Record<string, unknown>} item
   * @returns {import('./entity.js').CanonicalEvidence}
   */
  adapt(item) {
    if (!item || typeof item !== "object") {
      throw new Error("ReportItemAdapter.adapt requires a report item object");
    }
    let evidence = this._evidenceChainAdapter.adapt(item.evidence_chain || {});

    const reportId = item.id || item.stix_id;
    const cves = item.cves || (item.cve_id ? [item.cve_id] : []);
    const actorTag = item.actor_tag || item.threat_actor;
    const techniques = (item.mitre_techniques || [])
      .map((t) => (typeof t === "string" ? t : t?.id))
      .filter(Boolean);
    const iocs = (item.iocs || [])
      .map((ioc) => (typeof ioc === "string" ? ioc : ioc?.value))
      .filter(Boolean);

    evidence = {
      ...evidence,
      related_reports: reportId ? [String(reportId)] : [],
      related_cves: cves.map(String),
      related_threat_actors: actorTag ? [String(actorTag)] : [],
      related_campaigns: item.campaign_id ? [String(item.campaign_id)] : [],
      related_attack_techniques: techniques,
      related_iocs: iocs.map(String),
      audit_metadata: {
        ...evidence.audit_metadata,
        producer_implementation: this.sourceShapeName(),
      },
    };

    // Best-effort: only P25's own computeEnterpriseTrustScore() produces the full
    // {dims, totalEarned, totalMax, pct, tier, tierColor} shape; if the caller has already
    // computed and passed it as item.__trustScore, use it verbatim (composition, not
    // recomputation). This adapter does not call computeEnterpriseTrustScore itself (see
    // file-level docstring on why these adapters avoid importing handler files).
    if (item.__trustScore) {
      evidence = this._confidenceAdapter.adapt({ evidence, trustScore: item.__trustScore });
    }

    return evidence;
  }

  sourceShapeName() {
    return "p-layer-report-item";
  }
}
