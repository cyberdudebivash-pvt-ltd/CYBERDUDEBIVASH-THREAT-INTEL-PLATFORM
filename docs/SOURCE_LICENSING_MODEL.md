# Source Licensing & Data Governance Model (P40.0)

Mission Section 23: "the system must prevent accidental redistribution of
restricted data. Do not assume that publicly accessible data is commercially
redistributable." This document is the model; enforcement lives in
`scripts/source_registry.py:validate_registry()` and
`scripts/p40_production_certification.py`'s G21 gate.

## Licensing classes

| `licensing_class` | Meaning | `commercial_use_allowed` default |
|---|---|---|
| `PUBLIC_DOMAIN` | Government/public-domain data (NVD, CISA KEV) | `true` |
| `OPEN_ATTRIBUTION` | Freely usable including commercially, attribution required (MITRE ATT&CK, GHSA, EPSS) | `true` |
| `FREE_NONCOMMERCIAL` | Free for defensive/internal use, **not** for commercial resale without separate arrangement (abuse.ch feeds, OpenPhish, PhishTank, OTX, ransomware.live) | **`false`** |
| `COMMERCIAL_LICENSED` | Requires a paid license/contract | `true` once licensed |
| `INTERNAL_USE_ONLY` | Contractually restricted to internal defensive use, no redistribution (Shadowserver, CIRCL Passive DNS, Team Cymru) | **`false`** |

`commercial_use_allowed` is **derived**, not independently hand-set, in
`scripts/build_source_registry.py:mk()`: it defaults to `false` for
`FREE_NONCOMMERCIAL`/`INTERNAL_USE_ONLY` and `true` otherwise, unless a
source's actually-published terms justify an explicit override at the call
site. This exists because of a real bug found and fixed during this change's
development: every source initially defaulted to `commercial_use_allowed:
true` regardless of `licensing_class`, which would have silently
misrepresented 13 non-commercial sources (abuse.ch's three feeds, OpenPhish,
PhishTank, OTX, ransomware.live, and others) as commercially redistributable.
`p40_production_certification.py`'s **G21 gate is a permanent regression
guard against this exact class of bug** — it fails the build (`BLOCKER`
severity) if any `FREE_NONCOMMERCIAL`/`INTERNAL_USE_ONLY` source is ever
flagged `commercial_use_allowed: true` again.

## Fields governing redistribution

- **`redistribution_allowed`** (bool) — can normalized/derived data from this
  source be re-shared outside the platform's own reporting? `false` for
  commercial-vendor threat-actor research (Mandiant, CrowdStrike, GTIG),
  passive-DNS providers under MOU (CIRCL, Farsight, RiskIQ), and all Wave 4
  dark-web/underground providers.
- **`commercial_use_allowed`** (bool) — see above.
- **`attribution_required`** (bool) — must the original source be cited when
  its data is surfaced? `true` for all `OPEN_ATTRIBUTION` and
  `FREE_NONCOMMERCIAL` sources.
- **`retention_policy`** — `INDEFINITE` / `90_DAYS` / `PER_CONTRACT`, etc.

## Querying licensing state

```python
from source_registry import licensing_summary
licensing_summary()
# {
#   "total": 104, "redistribution_allowed": 83, "redistribution_restricted": 21,
#   "commercial_use_allowed": 88, "attribution_required": 16,
#   "by_licensing_class": {"PUBLIC_DOMAIN": 49, "OPEN_ATTRIBUTION": 6,
#                           "FREE_NONCOMMERCIAL": 13, "COMMERCIAL_LICENSED": 33,
#                           "INTERNAL_USE_ONLY": 3},
# }
```

Or via the live API: `GET /api/v1/p40/licensing` — returns the same rollup
plus an explicit `restricted_sources` list (every source with
`redistribution_allowed: false`), so any consumer can check before
exporting/re-sharing intelligence derived from a specific source.

## Wave 4 (commercial / dark-web) sources specifically

Per mission Section 5's explicit instruction — "DO NOT scrape unauthorized
sources. DO NOT bypass authentication. DO NOT circumvent access controls...
treat these as licensed intelligence integrations" — every Wave 4 source
(Recorded Future, Flashpoint, Intel 471, KELA, SOCRadar, Cyble, Group-IB,
Searchlight Cyber, DarkOwl, Flare, Constella) is registered as
`REQUIRES_LICENSE` with `redistribution_allowed: false`. No connector code
exists for any of them — a connector is only built once a contract is
executed and its actual terms (not an assumption) can be encoded into the
registry entry's `redistribution_allowed`/`commercial_use_allowed`/
`retention_policy` fields.

## Enforcement summary

| Check | Where | Severity |
|---|---|---|
| `commercial_use_allowed` coherent with `licensing_class` | `source_registry.py:validate_registry()` | Hard error (registry fails to validate) |
| Same check, as a CI gate | `p40_production_certification.py` G21 | `BLOCKER` (fails the build) |
| Non-live source cannot claim a real reliability/quality score | `validate_registry()` | Hard error |
| Restricted sources enumerable at query time | `GET /api/v1/p40/licensing` | N/A (observability, not a gate) |
