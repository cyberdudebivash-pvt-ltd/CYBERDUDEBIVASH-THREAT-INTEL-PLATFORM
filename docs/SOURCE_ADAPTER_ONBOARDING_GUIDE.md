# Source Onboarding Guide (P40.0)

How to add a new intelligence source to Sentinel APEX, per mission Section
38 ("adding a new source should require: registry configuration, adapter
implementation, parser, normalization mapping, contract tests, health check,
documentation — avoid modifying unrelated core systems for each new
source").

## 0. Before you write any code

Check `data/registry/source_registry.json` first — the source may already be
declared as `PLANNED`/`REQUIRES_CREDENTIALS`/`REQUIRES_LICENSE`, with `notes`
explaining what's blocking it. If a `PLANNED` entry exists, update it in
place (`scripts/build_source_registry.py`) rather than adding a duplicate.

## 1. Decide the integration shape

| If the source produces… | Use `integration_mode` | Example |
|---|---|---|
| Discrete new items on a schedule (advisories, IOCs, victims) | `EVENT_STREAM` | `openphish` |
| A score/field that enriches items you already have | `ENRICHMENT` | `first_epss` |
| A taxonomy/reference dataset (not "news") | `REFERENCE_SYNC` | `mitre_attack` |

Getting this wrong is the single biggest mistake to avoid — see
`SOURCE_FABRIC_ARCHITECTURE.md` §5 for why EPSS is `ENRICHMENT` and not a
280k-item-per-day event stream, and why MITRE ATT&CK never touches
`feed_manifest.json`.

## 2. Registry configuration (always required, always first)

Add or update an entry in `scripts/build_source_registry.py`'s `_WAVE*`
lists using the `mk()` helper — every field is documented in
`docs/SOURCE_REGISTRY.md`. Start the source at `implementation_status =
"PLANNED"` with a `notes` string explaining what's needed, even before
writing adapter code — this makes the gap visible in the registry
immediately.

```bash
python3 scripts/build_source_registry.py
python3 scripts/source_registry.py --validate   # must be 0 errors
```

## 3. Adapter implementation

For `EVENT_STREAM` / `ENRICHMENT` / `REFERENCE_SYNC` sources feeding the live
pipeline, add a new function to `scripts/true_intel_ingestor.py` following
the existing conventions:

- **Fetch** via `_get_json(url, timeout=...)` or `_get_text(url, timeout=...)`
  — both already handle timeouts and return `None` on any failure (never
  raise). Do not add a new HTTP client.
- **Checkpoint** via the shared `FeedState` instance (`feed_state.get_last_seen`
  / `feed_state.is_new` / `feed_state.update_last_seen`) if the source has a
  genuine per-item publish timestamp to cursor against. If it doesn't (like
  OpenPhish), rely on the existing `_merge_into_manifest` id/`stix_id` dedup
  instead — do not fabricate a fake timestamp cursor.
- **Normalize** `EVENT_STREAM` items via `_normalize_item(...)` — this is the
  canonical manifest schema; every downstream P-layer (P16-P39) depends on
  its shape.
- **Isolate failures**: your new source must never raise out of
  `run_ingestion()`. Wrap the call site in `run_ingestion()`'s existing
  try/except pattern (see how `ingest_openphish`/`enrich_with_epss`/
  `sync_mitre_attack` are wired in) — one source failing must never stop the
  others (mission Section 20).
- **Respect `--dry-run`**: any function with disk side effects must accept
  and honor a way to skip writes under dry-run (see `sync_mitre_attack`'s
  `dry_run` parameter) — a "fetch and report" invocation must never mutate
  committed state.

For sources you intend to run via the formal adapter contract
(`core/ingestion/sources/base.py:BaseSource` — retry/backoff/rate-limit/
health/structured-errors), that framework exists and is well-tested, but is
**currently dormant** (see `SOURCE_FABRIC_ARCHITECTURE.md` §3) — adding a
new `BaseSource` subclass there does not make it run in production without a
separate decision to activate `IngestionEngine.start()`.

## 4. Credentials

Never hardcode a credential, and never commit one. Reference it in the
registry's `credential_reference` field as an **env var name only** (e.g.
`"OTX_API_KEY"`), read it via `os.environ.get(...)` in the adapter, and have
the adapter degrade to an explicit "requires credentials" log line (not a
silent empty result, not a crash) when the env var is absent — see
`ingest_urlhaus()`'s `ABUSECH_AUTH_KEY` check for the pattern to copy.

## 5. Contract / unit tests

Add tests to `tests/test_true_intel_ingestor_p40.py` (or a new file
following its naming convention) that mock `_get_json`/`_get_text` — never
depend on live network in the automated suite. Cover at minimum:

- successful response → correct item count / shape
- empty response
- malformed JSON
- network failure (`_get_json`/`_get_text` return `None`)
- if credential-gated: missing-credential path makes **zero** network calls

## 6. Health check

No extra work needed if your `pipeline_feed_source_key` matches the literal
`feed_source` value your adapter writes onto manifest items (the common
case) — `scripts/source_fabric_health.py` will pick it up automatically via
`data/cache/feed_state.json` and `data/stix/feed_manifest.json`. If your
source's manifest key doesn't match its registry `source_id` (see
`SOURCE_REGISTRY.md`'s note on `pipeline_feed_source_key`), set that field
explicitly.

## 7. Documentation

Update this guide only if the onboarding *process* changes. Per-source
documentation lives entirely in the registry entry itself
(`description`, `documentation_url`, `terms_url`, `notes`) — there is no
separate per-source markdown file to maintain.

## 8. Before merging

```bash
python3 scripts/source_registry.py --validate
python3 scripts/source_fabric_health.py
python3 scripts/p40_production_certification.py     # must stay WORLDWIDE_RELEASE, 0 blockers
python3 -m pytest tests/test_source_registry.py tests/test_true_intel_ingestor_p40.py -v
python3 scripts/regression_tests.py                  # must stay 21/21
```
