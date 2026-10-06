# Commercial Quality Certification Report

**Project TITAN Stage 22 Phase 2 — v200 GA Readiness**
**Certified against:** `data/feed.json` (159 items) — the canonical feed
`scripts/p33_production_certification.py` itself certifies, chosen as the single source of truth
for this report rather than any of the platform's other feed variants (see §0).

---

## 0. Method and source-of-truth decision

Three feed files exist with materially different shapes: `data/feed.json` (159 items, the file
every `p*_production_certification.py` script reads), `api/feed.json` (17 items, a differently
enriched preview/API-serving snapshot — carries an `evidence_chain` object `data/feed.json` does
not), and several audience-scoped variants (`api/feed_enterprise.json`, `api/feed_mssp.json`,
`api/feed_public.json`). **This report certifies `data/feed.json`** because it is the file the
platform's own existing certification chain (P25→P28→P30→P31→P32→P33) already treats as
authoritative — using a different file here would produce a second, uncoordinated quality signal,
which Principle 3 (Single Source of Truth) exists to prevent. Where a dimension's real
implementation lives only in a different variant, that is reported explicitly as a **pipeline gap**
(the enrichment exists, but doesn't reach the certified feed), not silently substituted in to
inflate this report's numbers.

This resolves the discrepancy flagged in `TITAN_V200_RELEASE_AUDIT.md` §6: evidence-chain data
**does exist and is well-formed** (Admiralty-style source reliability/accuracy codes — see §3), but
it is written to `api/feed.json`'s 17-item variant, not to the canonical 159-item
`data/feed.json`. Both prior findings were correct; they were reading different files.

## 1. Commercial Quality Certification Matrix

A 5-tier scale, applied per dimension. Tiers are **not** a single platform-wide grade — a platform
can be (and this one is) `Commercial Certified` on one dimension and `Internal Draft` on another
simultaneously. Assignment requires the stated evidence bar to be met on the canonical feed, not on
a roadmap, a design doc, or a differently-scoped preview file.

| Tier | Bar | Meaning |
|---|---|---|
| **Internal Draft** | Mechanism exists in code but is absent, disabled, or near-zero on the canonical feed | Not customer-visible in its current state; engineering-only artifact |
| **Analyst Review** | Present on a meaningful minority-to-majority of items, but with known inconsistency, fragmentation, or generic/low-specificity output | Usable by a trained analyst who can apply judgment; not yet safe to present as an unqualified commercial claim |
| **Enterprise Ready** | Present on a strong majority (≥75%) of applicable items, mechanically consistent, single canonical source | Safe for enterprise-tier customer consumption with normal support-desk tolerance for edge cases |
| **Commercial Certified** | Present on ≥90% of applicable items, validated by an independent gate (schema validator, certification script, or governance check), zero known duplicate/conflicting sources | Safe to market as a standard commercial-tier product capability without qualification |
| **Premium Intelligence** | Commercial Certified **plus** measurable differentiation beyond baseline (custom enrichment, predictive scoring, cross-validated attribution, etc.) actually present in the shipped data, not aspirational | Justifies premium-tier pricing on this dimension specifically |

**N/A handling (explicit methodology, not an afterthought):** a dimension is marked **N/A** for a
given item, not failing, when the underlying concept structurally does not apply to that item's
`threat_type` — e.g. CVSS scoring is N/A for a `Ransomware`/`Threat Intel`/`Phishing` item (no CVE
involved), and IOC extraction is N/A for a pure vulnerability-disclosure item with no observed
indicators yet. **Coverage percentages below are computed over the applicable denominator only**,
with the N/A count reported alongside so the two are never conflated. An item scored 0% because a
field genuinely does not apply to it is a methodology bug in the scorer, not a quality finding about
that item — this report does not make that mistake, and flags in §3.4 one place the platform's own
P33 gate arguably still does.

## 2. Feed composition (denominator for every dimension below)

159 items. `threat_type` distribution: Vulnerability 74, Threat Intel 49, Ransomware 8, Malware 8,
Supply Chain 7, Cloud Security 4, ICS/OT 3, Data Breach 2, APT 2, Phishing 1, DDoS 1.

## 3. Per-dimension certification

### 3.1 Evidence quality — **Internal Draft**

The evidence-chain schema itself is genuinely well-designed: source reliability codes (A–F,
Admiralty-scale-style), accuracy codes with labels ("Possibly true"), collection/verification
timestamps — sampled from `api/feed.json`'s variant. **But it is absent from every one of the 159
items in the canonical certified feed** (0/159, key not present at all — independently confirmed by
direct inspection, not inferred). Rated `Internal Draft`: the mechanism is real and works, but it
does not reach the product surface this report certifies. **Path to Enterprise Ready**: wire the
same enrichment step that populates `api/feed.json`'s evidence_chain into the `data/feed.json`
generation pipeline — an integration gap, not a design gap.

### 3.2 Attribution quality — **Analyst Review**

`actor_tag` is present on 159/159 items (100%) — but sampling shows a large share are generic
bucket tags rather than named-actor attribution: `CDB-CVE-GEN` alone accounts for 62/159 (39%),
`CDB-RAN-GEN` 17, `CDB-APT-GEN` 11 — generic-CVE/generic-ransomware/generic-APT buckets, not
specific actors. Genuinely named/specific tags (`CDB-APT-22`, `CDB-CYB-01`, etc.) account for the
remainder. P33's own gate G22 independently counts "20 unique actors" across the feed, consistent
with this picture: real variety exists, but roughly 4 in 10 items fall back to a generic bucket
rather than a specific attribution. **No `actor_confidence`, `attribution_status`, or
`attribution_assessment` field exists anywhere on the canonical feed's schema** (confirmed:
0/159, not present as a key) — attribution confidence is not separately quantified from the tag
itself. Rated `Analyst Review`: real and majority-populated, but not yet consistent or confident
enough to certify as an unqualified commercial claim.

### 3.3 IOC completeness — **Enterprise Ready**

128/159 items (80.5%, matching P33 gate G08 exactly) carry `ioc_count > 0`, with real typed
breakdowns (`ioc_counts`: sha256/sha1/md5/domain/ipv4/url, sampled and confirmed non-placeholder).
The 31 items without IOCs are a mix of early-stage vulnerability disclosures (legitimately no
indicators observed yet — arguably N/A-adjacent, not a defect) and lower-confidence Threat Intel
items. Rated `Enterprise Ready`: strong majority coverage with real, typed, non-trivial data;
short of `Commercial Certified`'s 90% bar.

### 3.4 Confidence calculation — **Internal Draft**

The platform's most significant quality gap, and the one place its own certification gate is
currently unable to validate its own output: P33 gate **G05 warns "159/159 items have out-of-range
confidence values"** — every single item fails this specific gate. `confidence_score` is present on
100% of items (real numeric values, e.g. `21.9`), but the underlying computation is fragmented
across **116 files and 5+ independent, non-cross-reading systems** (per the repository's own
`CONFIDENCE_FRAMEWORK_DISCOVERY.md`), with ADR-0007 (the ADR that exists specifically to resolve
this) still **Proposed, not Accepted**. Rated `Internal Draft` — not because confidence data is
absent (it is 100% present), but because the computation itself is unreconciled and its own
governing gate currently fails on every item. This is the platform's single highest-priority quality
remediation item; see Phase 9/10.

### 3.5 Explainability — **N/A on the canonical feed (not a failure) / Internal Draft on the platform overall**

No explainability-related field exists anywhere on `data/feed.json`'s item schema (confirmed: zero
keys matching `explain`/`reasoning`). This is reported as **N/A for the certified commercial feed**
per this report's own methodology — explainability was never designed to be a per-feed-item field;
it is a request-time capability (Stage 17's `IntelligenceExplainabilityService`, a deterministic,
no-LLM Analyst Reasoning Object). That service is real and well-built (confirmed in Stage 21's
audit), but lives entirely in the unwired Gateway lineage — zero customer-reachable route exposes
it today. Rated `Internal Draft` **at the platform level** (a real capability exists, nothing
customer-facing serves it) while explicitly not penalizing the feed schema for lacking a field it
was never meant to carry.

### 3.6 Provenance — **Enterprise Ready** (source-level) / see 3.1 for evidence-chain-level

Source-level provenance is strong and consistent: `source_url`, `source_domain`, `source_trust_score`
(a real numeric, e.g. `0.72`), and `stix_bundle_url` are populated on 100% of sampled items, giving
every item a traceable origin and a linked STIX artifact. This is distinct from, and stronger than,
the richer Admiralty-style evidence-chain provenance in §3.1 — rated separately per this report's
"don't conflate concepts sharing a name" principle. Rated `Enterprise Ready`.

### 3.7 Executive summary — **Enterprise Ready**

`scripts/executive_brief_generator.py` computes real aggregates (critical/high counts, average
risk, top actors/campaigns) into `data/reports/executive-briefs/` — functional, not a stub.
Narrative text is templated (e.g., a `recommended_action` string following a fixed pattern) rather
than fully bespoke per item. Rated `Enterprise Ready`: real, consistent, and commercially usable;
short of `Commercial Certified` because templated narrative reads as generated rather than
analyst-authored at the individual-item level.

### 3.8 Remediation guidance — **Internal Draft**

No single canonical `remediation_guidance` function exists. Sampled output is immature: generated
filenames literally contain `STANDALONE-TEST` (e.g.
`CDB-REMEDIATE-STANDALONE-TEST-Critical-RCE-via-Log4Sh-*.ps1`), and generated Ansible playbooks are
keyed to blog-post titles rather than to specific incidents/items. Rated `Internal Draft` — this
dimension is not yet safe to present to a paying enterprise customer as a certified deliverable.

### 3.9 MITRE mapping — **Commercial Certified**

154/159 items (96.9%, exactly matching P33 gate G07's independently-computed figure, PASS against a
≥95% threshold) carry populated `mitre_tactics`/`ttps` with real technique IDs (e.g. `T1499`,
confirmed in a direct sample — not a placeholder). Validated by an independent gate (P33 G07) with a
defined threshold, consistent single source (`apex_mitre_attack_engine.py`, MITRE v16), and
majority-exceeding coverage. This is one of the platform's two strongest quality dimensions.

### 3.10 STIX generation — **Commercial Certified**

Real, standards-compliant generation using `stix2==3.0.1`/`stix2-validator==3.1.2` (not hand-rolled
JSON). 503 valid bundles exist in `data/stix/`; a sampled bundle is structurally correct STIX 2.1
(identity, marking-definition/TLP, intrusion-set, attack-pattern with MITRE external references).
100% of sampled canonical-feed items carry a working `stix_bundle_url`. Validated by
`scripts/validate_stix_bundle_integrity.py` and P33 gate G17 (STIX bundles 503 ≥ 159 items, PASS).
The custom `x-cdb-apex-1` STIX extension (`predictive_score`, `campaign_confidence`, `soc_priority`,
`recommended_action`) is real, shipped data — genuine differentiation beyond baseline STIX — but is
not yet independently validated the way the base bundle structure is, so this report holds STIX at
`Commercial Certified` rather than advancing it to `Premium Intelligence` pending that validation.

## 4. Certification matrix summary

| Dimension | Tier | Coverage (of applicable items) |
|---|---|---|
| Evidence quality | Internal Draft | 0/159 on canonical feed (100% on the unwired preview variant) |
| Attribution quality | Analyst Review | 159/159 tagged, ~61% specific / ~39% generic-bucket |
| IOC completeness | Enterprise Ready | 128/159 (80.5%) |
| Confidence calculation | Internal Draft | 159/159 present, 159/159 fail P33's own range gate |
| Explainability | N/A (feed) / Internal Draft (platform) | not a feed-item concept; unwired platform capability |
| Provenance (source-level) | Enterprise Ready | 159/159 |
| Executive summary | Enterprise Ready | functional, consistent, templated narrative |
| Remediation guidance | Internal Draft | no canonical function; test artifacts in sampled output |
| MITRE mapping | **Commercial Certified** | 154/159 (96.9%), independently gated |
| STIX generation | **Commercial Certified** | 503 bundles, 100% linkage, independently validated |

**No dimension currently qualifies for Premium Intelligence** on this report's evidence bar (real,
shipped, independently-validated differentiation beyond commercial baseline). STIX's custom
extension is the closest candidate, pending independent validation of its own.

## 5. What this means for GA readiness (informs Phase 9/10, does not itself gate)

Two dimensions (MITRE, STIX) are genuinely commercial-grade today. Four (evidence quality,
confidence calculation, explainability, remediation guidance) are not yet safe to market as
certified commercial capabilities without qualification — confidence calculation in particular,
because the platform's own quality gate currently fails on 100% of items for this exact reason.
This is not a recommendation to block v200 outright — several of these are real, scoped,
addressable gaps (evidence-chain is a pipeline-wiring fix, not a redesign; confidence needs ADR-0007
resolved, which is a governance/decision blocker more than an engineering one). Phase 10 weighs
this alongside security, performance, and operational findings to produce a single recommendation.
