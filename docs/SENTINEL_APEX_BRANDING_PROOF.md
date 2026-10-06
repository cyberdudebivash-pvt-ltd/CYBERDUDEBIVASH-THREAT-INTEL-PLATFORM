# SENTINEL APEX presentation branding — proof before change

Owner instruction (2026-10-05): use SENTINEL APEX product names and a prominent
Powered By CYBERDUDEBIVASH footer. Official Enterprise and Connect Hub excluded.

| Proof field | Decision/evidence |
| --- | --- |
| Objective | Rebrand browser-page presentation; retain parent identity in footer. |
| Affected production files | scripts/build_dist_artifact.py; scripts/sentinel-branding.cjs; index.html; workers/swarm-live/src/index.js; workers/intel-gateway/src/index.js (HTML report labels/footer only); workers/intel-gateway/src/cyber-watchdog.js (seller literal encoding only). |
| Supporting files | scripts/sentinel-branding.test.cjs; workers/swarm-live/src/index.test.mjs (updated accessibility label expectations); this proof; .github/workflows/sentinel-branding-check.yml. |
| Existing engine reused | Existing allowlisted dist builder, Pages publish workflows, deployment manifest and SWARM HTML renderer. |
| Why a presentation helper is needed | components/footer.html is reference-only; it is not included in all served pages. The dist builder packages many independent HTML documents. Shared build-time rendering covers that publication boundary. |
| Risk level | MEDIUM: multiple browser pages, one static publication boundary, one SWARM template; no functional API change. |
| Imports/runtime | Native Node helper at build time only; no new browser dependency or Worker import. |
| Routes/APIs/schema | Hostnames, paths, response contracts, auth, subscriptions, protocols and database schemas unchanged. |
| Reports | Source archive, JSON intelligence, downloadable/signed records and report generator attribution remain unchanged. Published HTML display copy changes; deployment checksums are calculated afterward. |
| Workflows/CI | Existing release gates retained; presentation tests added separately. Node is already used by Pages render checks. |
| Regression risks | HTML tokenization, duplicate footers, legacy inline scripts or images retaining old display names; preserve scripts/URLs/code/seller fields and test idempotence. |
| Required release evidence | Full dist build, existing freshness/render/report/provenance gates, complete SWARM suite and authenticated desktop/mobile QA before merge/deploy. Partial source checkout cannot certify those gates. |
| Rollback | Revert this coherent branding commit and redeploy through existing verified publication workflows. No migration or resource rollback needed. |

Reuse conclusion: extend the existing publication engine and presentation template;
do not add a competing platform, polling loop, API, billing path or intelligence engine.

Deploy-parity identity preservation: cyber-watchdog.js encodes the existing seller
registered-mark character as a JavaScript Unicode escape. Its runtime seller value
is unchanged. The existing ASCII deploy sanitizer previously transliterated the raw
mark into `(R)`, causing the commercial identity assertion to fail after sanitization.
This source-encoding correction preserves the authoritative seller string in both
source and deployment; no prices, seller records or API fields are renamed.
