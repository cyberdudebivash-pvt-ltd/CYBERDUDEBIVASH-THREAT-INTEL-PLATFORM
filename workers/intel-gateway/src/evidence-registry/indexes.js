/**
 * Evidence Registry Indexing  -  Stage 11 Phase 5 (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Abstract, backend-independent indexes: plain in-memory Map<key, Set<evidence_uuid>>
 * structures. "Indexes should be abstract and backend-independent"  -  nothing here assumes any
 * particular storage engine; a future KV/D1-backed repository could maintain equivalent
 * indexes using whatever native indexing that backend offers, satisfying the same query
 * methods this class exposes.
 *
 * Indexes ten dimensions, per Phase 5's own list: Evidence ID, UUID, CVE, Threat Actor,
 * Campaign, IOC, ATT&CK Technique, Source, Report, Relationship, Confidence. UUID itself is a
 * repository's own primary key (no separate index needed here); "Relationship" is implemented
 * as a cross-cutting union over the other related_* dimensions rather than its own Map, since
 * CanonicalEvidence has no single "relationship" field to index  -  see byRelatedEntity().
 */

/** @typedef {import('./entity.js').CanonicalEvidence} CanonicalEvidence */

const RELATIONSHIP_INDEX_FIELDS = Object.freeze({
  related_reports: "byReport",
  related_cves: "byCve",
  related_threat_actors: "byThreatActor",
  related_campaigns: "byCampaign",
  related_attack_techniques: "byAttackTechnique",
  related_iocs: "byIoc",
});

export class EvidenceRegistryIndexes {
  constructor() {
    this._byEvidenceId = new Map();
    this._bySource = new Map();
    this._byConfidenceTier = new Map();
    this._byReport = new Map();
    this._byCve = new Map();
    this._byThreatActor = new Map();
    this._byCampaign = new Map();
    this._byAttackTechnique = new Map();
    this._byIoc = new Map();
  }

  _addTo(map, key, uuid) {
    if (key === undefined || key === null || key === "") return;
    if (!map.has(key)) map.set(key, new Set());
    map.get(key).add(uuid);
  }

  _removeFrom(map, key, uuid) {
    if (key === undefined || key === null) return;
    const set = map.get(key);
    if (!set) return;
    set.delete(uuid);
    if (set.size === 0) map.delete(key);
  }

  /**
   * Indexes one evidence record's current field values. Safe to call more than once for the
   * same record (Set semantics  -  re-indexing an unchanged record is a no-op past the first
   * call).
   * @param {CanonicalEvidence} evidence
   */
  index(evidence) {
    const uuid = evidence.evidence_uuid;
    if (!uuid) return;
    this._addTo(this._byEvidenceId, evidence.evidence_id, uuid);
    this._addTo(this._bySource, evidence.source_id, uuid);
    this._addTo(this._byConfidenceTier, evidence.canonical_confidence_object?.tier, uuid);
    for (const [field, mapName] of Object.entries(RELATIONSHIP_INDEX_FIELDS)) {
      const map = this[`_${mapName}`];
      for (const value of evidence[field] || []) this._addTo(map, value, uuid);
    }
  }

  /**
   * Fully removes one evidence record's entries from every index.
   * @param {CanonicalEvidence} evidence
   */
  remove(evidence) {
    const uuid = evidence.evidence_uuid;
    if (!uuid) return;
    this._removeFrom(this._byEvidenceId, evidence.evidence_id, uuid);
    this._removeFrom(this._bySource, evidence.source_id, uuid);
    this._removeFrom(this._byConfidenceTier, evidence.canonical_confidence_object?.tier, uuid);
    for (const [field, mapName] of Object.entries(RELATIONSHIP_INDEX_FIELDS)) {
      const map = this[`_${mapName}`];
      for (const value of evidence[field] || []) this._removeFrom(map, value, uuid);
    }
  }

  /**
   * Removes `previous`'s index entries, then indexes `next`  -  used after update()/supersede()
   * so stale associations (e.g. a CVE reference removed by an edit) don't linger.
   * @param {CanonicalEvidence | null} previous @param {CanonicalEvidence} next
   */
  reindex(previous, next) {
    if (previous) this.remove(previous);
    this.index(next);
  }

  byEvidenceId(evidenceId) {
    return [...(this._byEvidenceId.get(evidenceId) || [])];
  }

  bySource(sourceId) {
    return [...(this._bySource.get(sourceId) || [])];
  }

  byConfidenceTier(tier) {
    return [...(this._byConfidenceTier.get(tier) || [])];
  }

  byReport(reportId) {
    return [...(this._byReport.get(reportId) || [])];
  }

  byCve(cve) {
    return [...(this._byCve.get(cve) || [])];
  }

  byThreatActor(actor) {
    return [...(this._byThreatActor.get(actor) || [])];
  }

  byCampaign(campaign) {
    return [...(this._byCampaign.get(campaign) || [])];
  }

  byAttackTechnique(technique) {
    return [...(this._byAttackTechnique.get(technique) || [])];
  }

  byIoc(ioc) {
    return [...(this._byIoc.get(ioc) || [])];
  }

  /**
   * Cross-cutting "Relationship" index (Phase 5's 10th dimension): union of every related_*
   * dimension for a given entity id  -  an evidence record's relationships ARE its related_*
   * arrays, so there is no separate structure to maintain beyond the six indexes above.
   * @param {string} entityId
   * @returns {string[]} evidence_uuids referencing entityId in any related_* field
   */
  byRelatedEntity(entityId) {
    const uuids = new Set([
      ...this.byReport(entityId),
      ...this.byCve(entityId),
      ...this.byThreatActor(entityId),
      ...this.byCampaign(entityId),
      ...this.byAttackTechnique(entityId),
      ...this.byIoc(entityId),
    ]);
    return [...uuids];
  }
}
