/** Evidence-only APT radar. Classification/mentions are not attribution or live attacks. */
const text = value => typeof value === 'string' ? value.trim() : '';
const generic = value => !value || /^(?:CDB-UNATTR(?:-.*)?|UNC-(?:UNKNOWN|CDB-99)|unknown(?:\s.*)?|unattributed(?:\s.*)?|unclassified|n\/a|none|null|-)$/i.test(value);
const topic = /\bAPT(?:[- ]?\d+)?\b|\bnation[- ]state\b|\bstate[- ]sponsored\b|\bLazarus\b|\bSandworm\b|\bFancy Bear\b|\bCozy Bear\b|\b(?:Volt|Salt) Typhoon\b/i;
const words = value => text(value).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const list = value => Array.isArray(value) ? value : [];
const technique = value => text(typeof value === 'object' && value ? value.id || value.technique_id : value).toUpperCase();

export function buildAPTPayload(input, profiles = [], generatedAt = '', options = {}) {
  const items = list(input).filter(item => item && typeof item === 'object');
  const actors = new Map(), sectors = new Set(), ttps = new Set();
  const related = [];
  for (const item of items) {
    const candidates = [item.actor_display_name, item.mitre_group_name, item.actor_tag, item.actor].map(text);
    const reported = candidates.find(value => !generic(value)) || '';
    const profile = reported && profiles.find(p => [p.id, p.alias].some(v => words(v) === words(reported)));
    const classification = [item.threat_type, item.actor_type, item.threat_actor_type, item.actor_threat_level].map(text).join(' ');
    const actorClassified = candidates.some(value => /^CDB-(?:UNATTR-)?APT(?:-|\d|$)/i.test(value)) || topic.test(classification) || topic.test(candidates.join(' '));
    const blob = [item.title, item.description, ...list(item.tags)].map(text).join(' ');
    const isRelated = actorClassified || topic.test(blob) || !!profile || /^APT[- ]?\d+$/i.test(reported);
    if (!isRelated) continue;
    related.push(item);
    const attributionAllowed = options.includeAttribution !== false && item.actor_paywall?.allowed !== false;
    // Respect a supplied entitlement restriction. Catalog names/countries,
    // CVE/vendor names and title mentions never manufacture actor identity.
    if (reported && (actorClassified || profile || /^APT[- ]?\d+$/i.test(reported)) && attributionAllowed) {
      const key = words(profile?.id || reported);
      const row = actors.get(key) || {
        id: profile?.id || reported, alias: reported,
        attribution_basis: 'reported_actor_field', source_urls: [],
      };
      const nation = text(item.actor_country);
      if (!generic(nation)) row.nation = nation;
      const url = text(item.source_url);
      if (/^https?:\/\//i.test(url) && !row.source_urls.includes(url)) row.source_urls.push(url);
      actors.set(key, row);
    }
    if (attributionAllowed) {
      for (const sector of list(item.actor_sectors)) { const value = text(sector); if (!generic(value)) sectors.add(value); }
    }
    for (const field of ['mitre_techniques', 'mitre_ttps', 'attck_techniques', 'attck_technique_ids', 'actor_ttps']) {
      if (field === 'actor_ttps' && !attributionAllowed) continue;
      for (const entry of list(item[field])) {
        const id = technique(entry);
        if (/^T\d{4}(?:\.\d{3})?$/.test(id)) ttps.add(id);
      }
    }
  }
  const sources = new Set(related.map(item => text(item.source) || text(item.feed_source)).filter(value => !generic(value)));
  const epoch = item => Date.parse(item.published || item.published_at || item.timestamp || '') || 0;
  return {
    tracked_apts: actors.size, active_sectors: sectors.size, total_ttps: ttps.size,
    apt_advisories: related.length, items_evaluated: items.length, sources_reporting: sources.size,
    attribution_status: actors.size ? 'REPORTED_ACTOR_IDENTITIES' : 'NAMED_ATTRIBUTION_NOT_PROVIDED',
    coverage_status: related.length ? 'APT_RELATED_REPORTING' : 'NO_APT_CLASSIFIED_REPORTING',
    recent_activity: related.sort((a,b) => epoch(b) - epoch(a)).slice(0,5).map(item => ({
      title: text(item.title), severity: text(item.severity), source: text(item.source) || text(item.feed_source),
      published: text(item.published) || text(item.published_at) || text(item.timestamp),
      source_url: /^https?:\/\//i.test(text(item.source_url)) ? text(item.source_url) : '',
      evidence_basis: 'apt_classification_or_source_reporting',
    })),
    top_actors: [...actors.values()].slice(0,5),
    generated_at: generatedAt, derivation_method: 'reported_actor_fields_and_apt_topic_evidence',
  };
}
