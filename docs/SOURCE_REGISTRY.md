# Source Registry Reference (P40.0)

Canonical file: `data/registry/source_registry.json`
Generator: `scripts/build_source_registry.py`
Loader / query API: `scripts/source_registry.py`

## Regenerating the registry

The JSON file is the checked-in, canonical artifact every consumer reads.
The generator script is a maintainability tool — run it only when
adding/editing a source definition:

```bash
python3 scripts/build_source_registry.py    # writes data/registry/source_registry.json
python3 scripts/source_registry.py --validate   # 0 errors required before committing
python3 scripts/source_registry.py --summary    # human-readable breakdown
```

CI does **not** regenerate the registry automatically (its `generated_at`
timestamp would otherwise churn on every pipeline run for zero data change).
CI *does* regenerate `data/quality/source_fabric_health.json` every run
(`scripts/source_fabric_health.py`), since that artifact's entire purpose is
reflecting current freshness.

## `implementation_status` — the governance field

This is the field the whole honesty contract (mission Section 40, "no fake
integrations") is built on. Exactly six values, enforced by
`scripts/source_registry.py:validate_registry()`:

| Value | Meaning | Can claim `HEALTHY` / nonzero `reliability_score` / `enabled=true`? |
|---|---|---|
| `ACTIVE` | Real adapter code, actually scheduled and running today | Yes |
| `IMPLEMENTED` | Real adapter code exists, not currently scheduled | No (only `ACTIVE` can be `enabled=true`) |
| `REQUIRES_CREDENTIALS` | Would work today with a free/paid API key | No |
| `REQUIRES_LICENSE` | Requires a commercial contract / registration / MOU | No |
| `PLANNED` | No code yet; deferred with a documented reason in `notes` | No |
| `DISABLED` | Was active, deliberately turned off | No |

A source with any status other than `ACTIVE`/`IMPLEMENTED` that claims
`health_status: HEALTHY`, a nonzero `reliability_score`, or `enabled: true`
fails validation. This is checked by `p40_production_certification.py`'s G05
gate on every CI run, and it is what would have caught (and will catch, going
forward) the class of bug this change found live: URLhaus silently returning
zero items for months while still nominally being treated as working.

## Full field schema

Every entry has these fields (see `scripts/build_source_registry.py:mk()`
for the authoritative definition):

| Field | Description |
|---|---|
| `source_id` | Canonical snake_case identifier, unique |
| `canonical_name`, `provider`, `description` | Human-readable identity |
| `intelligence_domains` | List from the mission's Section 2 taxonomy (`vulnerability`, `ioc`, `malware`, `threat_actor`, `phishing`, `ransomware`, `dark_web`, `government_cert`, …) |
| `source_type`, `authority_level` | `GOVERNMENT_AUTHORITATIVE` / `VENDOR_AUTHORITATIVE` / `COMMERCIAL_VENDOR` / `RESEARCH_PUBLICATION` / `AGGREGATOR` / `COMMUNITY` |
| `geographic_scope`, `sector_scope` | e.g. `GLOBAL`, `US`, `EU`, `IN`; `["ALL"]` or specific sectors |
| `access_type` | `PUBLIC_FREE` / `FREE_REGISTRATION` / `COMMERCIAL_LICENSED` / `GOVERNMENT_RESTRICTED` |
| `protocol`, `endpoint`, `response_format`, `schema_version` | Transport details |
| `authentication_type`, `credential_reference` | `credential_reference` is an **env var name only** (e.g. `"ABUSECH_AUTH_KEY"`) — never a real secret |
| `polling_interval`, `rate_limit`, `pagination_strategy`, `incremental_cursor_strategy` | Adapter behavior contract |
| `licensing_class`, `redistribution_allowed`, `commercial_use_allowed`, `attribution_required`, `retention_policy` | See `SOURCE_LICENSING_MODEL.md` |
| `freshness_expectation` | `REALTIME` / `HOURLY` / `DAILY` / `WEEKLY` / `ON_DEMAND` / `HISTORICAL_STATIC` — drives the staleness thresholds in `scripts/source_fabric_health.py` |
| `reliability_score`, `quality_score`, `default_confidence` | 0 unless `implementation_status` is `ACTIVE`/`IMPLEMENTED`; otherwise seeded from `authority_level` as a starting point for the Source Quality Engine |
| `enabled`, `priority` (1-5), `criticality` | Operational scheduling metadata |
| `health_status`, `last_success`, `last_failure`, `last_event`, `records_received/accepted/rejected/deduplicated`, `error_rate`, `latency` | Live operational fields — see `source_fabric_health.json` for computed values (this registry file's copies are placeholders for non-live sources; live health is joined at query time) |
| `documentation_url`, `terms_url` | Provider references |
| `implementation_status`, `wave` (1-5), `integration_mode` | Governance fields — see above and `SOURCE_FABRIC_ARCHITECTURE.md` §4 |
| `connector_ref` | `file.py:function_name` pointer to the actual implementation, or `null` |
| `pipeline_feed_source_key` | Internal-only: bridges this registry's `source_id` to the literal `feed_source` string `scripts/true_intel_ingestor.py` writes onto manifest items. Not identical to `source_id` for every source (e.g. `github_advisory_database` → `github_advisory`) because the ingestor's internal `SOURCE_KEY` constants predate this registry and are not renamed to match it — renaming them would silently break already-persisted cursors in `data/cache/feed_state.json`. `"rss:<substring>"` / `"rss:*"` values are heuristic bucket matches for the ~30 blended RSS feeds — see `scripts/source_fabric_health.py:_match_manifest_key`. |
| `notes` | Rationale for `PLANNED`/`REQUIRES_*` status, or implementation caveats |

## `integration_mode`

- `EVENT_STREAM` — produces discrete new items in `feed_manifest.json`
- `ENRICHMENT` — attaches fields to items already collected in the same run (EPSS)
- `REFERENCE_SYNC` — maintains a standalone taxonomy/reference dataset, never touches the item manifest (MITRE ATT&CK)
- `NOT_INTEGRATED` — no live wiring (covers `PLANNED`/`REQUIRES_*` sources, and the dormant `core/ingestion` engine)

## Query API (`scripts/source_registry.py`)

```python
from source_registry import load_registry, get_source, sources_by_status, sources_by_wave, sources_by_domain, domain_coverage, licensing_summary, validate_registry

reg = load_registry()
kev = get_source("cisa_kev")
live = sources_by_status("ACTIVE")
wave1 = sources_by_wave(1)
vuln_sources = sources_by_domain("vulnerability")
errors = validate_registry()   # [] if clean
```
