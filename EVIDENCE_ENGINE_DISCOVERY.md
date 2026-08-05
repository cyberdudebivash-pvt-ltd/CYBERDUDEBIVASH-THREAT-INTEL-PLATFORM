# Project TITAN Stage 5 — Enterprise Evidence Intelligence Engine (EIE)
## Discovery: Existing Evidence Infrastructure vs. the 10-EPIC Request

**Status: Phase 1 discovery only. No Evidence Registry, Evidence API, relationship
engine, or cross-repository wiring is introduced by this document or its
companion commit. See "What this document deliberately does not do" at the
end.**

---

## 0. Correcting the Stage 5 dispatch's Prerequisites section

Stage 5's own Prerequisites list states:

> ✅ Stage 4 — Canonical Confidence Framework (**ADR approved**)

This is inaccurate and is corrected here so it isn't carried forward
silently. What actually happened in Stage 4 (`CONFIDENCE_FRAMEWORK_DISCOVERY.md`,
PR #108):

- Phase 1 (Discovery) was completed — a comparison matrix across
  `computeEnterpriseTrustScore` (P25), P20's `evidence_chain.reliability_code`,
  the blog's EIOS Layer 7 (two mechanisms), and an `ai_confidence`
  sub-fragmentation.
- Phase 3 (Ownership Decision / ADR) was explicitly **not** done. When asked
  to choose a direction, the confirmed instruction was to fix the narrower
  `ai_confidence` fallback-constant sprawl only — explicitly declining the
  ADR-writing option.
- **No ADR exists.** The P25-vs-P20-vs-EIOS-layer-07 canonical-ownership
  question is still open, unchanged since Stage 1 first flagged it.

Stage 5 itself is gated on exactly this fact: its own "Architecture Decision
Records (Required)" section states *"No architectural behavior should exist
without an approved ADR,"* and lists Evidence ownership, Evidence lifecycle,
Relationship model, API versioning, Registry responsibilities, and Migration
strategy as ADR subjects. None of the six exist. Sections 2–3 below take that
rule at face value: the EPICs that constitute new cross-cutting architecture
do not proceed in this pass. The EPICs (and sub-slices of EPICs) that are
pure discovery, or that were already-existing capability mislabeled as
missing, are documented and, in one case, corrected.

---

## 1. Method

Grepped and read (not assumed) across both repos for every noun Stage 5's
EPICs name: evidence identity/hashing, registries, lifecycle states,
relationship engines, source-reliability computation, and publication
governance gates. Findings below cite `file:line`.

---

## 2. EPIC-by-EPIC gap matrix

| EPIC | Stage 5 ask | Current state | Verdict |
|---|---|---|---|
| **1 — Canonical Evidence Entity** | Versioned `Evidence` object: UUID, hash/fingerprint, immutable record ID, signature metadata, version number, canonical confidence, relationships | **Partial, fragmented.** P20's `item.evidence_chain` (`p20-handlers.js:185-244`) already carries `evidence_id`, `source_reliability`, `reliability_code` (A–F), `source_category`, `analyst_review`, `chain_of_custody[]`, `known_limitations[]`, `iq_breakdown{}`, `corroboration_count`. It has **no** UUID, hash/fingerprint, immutable record ID, signature metadata, or version number — none of the *Integrity* field group Stage 5 asks for exists anywhere. | Partial — Identity/Quality partially covered, Integrity group is a genuine gap |
| **2 — Evidence Registry** (centralized creation/update/validation/dedup/versioning) | Authoritative, centralized repository for evidence metadata | **Does not exist.** Confirmed no match for `EvidenceRegistry`, `evidence_registry`, or any centralized evidence store. The only `*_REGISTRY` constants in the Worker are `dark-web-monitor.js:16` `BREACH_SOURCE_REGISTRY` (8 hardcoded breach-monitoring sources, unrelated) and P38's `SCHEMA_REGISTRY`/`FEED_REGISTRY` (field/feed governance, not evidence records). | Gap — real, and the one EPIC most clearly requiring the "Registry responsibilities" ADR before any code is written |
| **3 — Statement-to-Evidence Mapping** | Optional evidence references per report section, backend-first, no rendered-output change | **Partial, narrower than asked.** `buildP32EvidenceTransparencyBlock` (`p32-handlers.js:804+`) already maps 5 claim types (KEV, CVSS, EPSS, Attribution, IOC count) to `{claim, source, verification, confidence, reasoning}`, with confidence sourced from P25's real per-dimension scores (Stage 3 fix). This covers claims, not Stage 5's 8 named *report sections* (Executive Summary, Threat Overview, Technical Analysis, ATT&CK Mapping, IOC Analysis, Detection Engineering, Business Impact, Executive Recommendations), and the claims aren't keyed to a canonical Evidence UUID because EPIC 1's Integrity fields don't exist yet. | Partial — real prior art, wrong grain (claim-level, not section-level; no stable evidence ID to point at) |
| **4 — Evidence Relationship Engine** | Typed relationships (Evidence→CVE/Actor/Campaign/Malware/IOC/ATT&CK/Report/DetectionRule), graph-ready but no graph dependency | **Exists, on the blog side, and is explicitly designed for this.** `engine/sentinel_engine/knowledge_graph.py`'s `KnowledgeGraph` (documented in `Sentinel-APEX/eios/layer-09-intelligence-relationships.md`) is a persistent, JSON-backed (no DB dependency — matches Stage 5's own constraint) entity+typed-relation graph, already relating Report/Actor/Malware/CVE/Technique/IOC via `mentions`/`references`/`maps_to`/`observed`/`associated_with`/`linked_to` edges. Layer 9 explicitly says future object types should upsert into this same graph rather than build a second mechanism. Intel-platform's P31 (`p31-handlers.js`, `buildP31RelationshipBlock`, `_buildGraph`) independently builds a *second*, JS-side lightweight graph from the feed corpus. Neither currently has a first-class `Evidence` node type — both relate reports/actors/CVEs/IOCs to each other, not to evidence records specifically. | Partial — two independent graph implementations already exist (one per repo); adding an `Evidence` node type to either is a real gap, but *which* graph is canonical is itself an unresolved ownership question this EPIC's own ADR list names ("Relationship model") |
| **5 — Evidence Lifecycle** | States: Collected → Validated → Correlated → Published → Updated → Superseded → Archived, immutable audit history | **Conceptually covered, not state-machine-shaped.** P30 (`p30-handlers.js`) computes verification status across 8 signal dimensions (`buildP30VerificationBlock`), a chronological event timeline (`buildP30TimelineBlock`/`_computeTimeline`), IOC-specific lifecycle (`_computeIOCLifecycle`: ACTIVE/MONITORING/HISTORICAL), and change tracking (`buildP30ChangeTrackingBlock`). None of this is named or enumerated as Stage 5's 7 states, and none of it is evidence-record-scoped (it's item/report-scoped). Blog's `layer-08-report-version-control.md` adds front-matter versioning fields but explicitly disclaims touching "physical storage lifecycle." | Partial — real signal exists, no unifying state enum; genuinely new work to introduce one |
| **6 — Evidence APIs** | Versioned, paginated, filterable lookup by Evidence ID/Report/CVE/Campaign/Actor/ATT&CK/Detection Rule | **Does not exist as a dedicated surface.** Existing `/api/v1/p*` routes return evidence *embedded in* item/report responses (P19, P20, P30, P32 blocks); there is no standalone `/api/v1/evidence/*` lookup surface. | Gap — real, blocked on EPIC 1/2 existing first (an API can't expose canonical evidence records that don't yet exist) |
| **7 — Publication Governance Integration** | Fail publish on missing/duplicate/invalid evidence, orphaned relationships, schema violations | **Partial — a real gate already exists.** P23's certification gate list (`p23-handlers.js:683`) already includes `{ name: "Evidence Chain", pass: !!(ec && ec.source_reliability) }`, and `G9_EVIDENCE` (`p23-handlers.js:829`) gates on the same condition; both feed `P21 Certification` (`p23-handlers.js:684`), which is itself in the same gate list — evidence presence already contributes to whether an item certifies. It checks *presence* of `source_reliability`, not duplicate detection, orphaned relationships, or schema conformance against EPIC 1's not-yet-built schema. | Partial — the hook point exists and already blocks/flags; extending its checks is future work, not a from-scratch build |
| **8 — Cross-Repository Consumption** | Intel-platform owns ingestion/registry/validation/API; blog is read-only consumer | **No new architecture needed to *decide* this — it's already the established pattern.** Stage 2 (PR #106) settled cross-repo integration as API-based: intel-platform is system of record, blog consumes via HTTP, no shared package. Applying that same precedent to evidence specifically is consistent, but there is nothing to consume yet (no Evidence API — EPIC 6 — exists), so there is no blog-side change to make in this pass. | Not started — correctly sequenced *after* EPICs 1/2/6, not blocked on new architectural debate (the pattern is already decided) |
| **9 — Migration Strategy** | Existing reports/APIs stay valid; legacy structures adapted not removed; feature flags; rollback documented | N/A until EPICs 1–2 exist — nothing to migrate to yet. | Not started — correctly sequenced last |
| **10 — Testing & QA** | Unit/integration/schema/relationship/API-contract/migration/performance tests for new evidence components | N/A until there are new evidence components to test. `regression_tests.py` (21/21) continues to cover all existing, unmodified surfaces. | Not started — correctly sequenced last |

---

## 3. A concrete illustration of why "One Evidence Model" isn't optional polish

Stage 5's architectural principles open with *"One Evidence Model... One
Source of Truth."* This isn't aspirational — the repo already has a working
example of the failure mode that principle exists to prevent. Three
independent, disagreeing implementations of "how reliable is this source"
exist today in the same Worker:

1. **`p20-handlers.js` `item.evidence_chain.reliability_code`** — an
   A–F NATO/Admiralty-style code, populated upstream in the ingestion
   pipeline (not computed in this file).
2. **`p18-handlers.js:78` `buildEvidenceAttribution(item)`** — an
   **independently computed** A–E letter grade, derived at render time by
   substring-matching `item.source`/`item.feed_source` against hardcoded
   strings (`"nvd"`, `"cisa"`, `"github"`, `"vendor"`, `"rss"`,
   `"api_ingest"`) — a completely different scale, different letters, and a
   different computation method than #1, used by `p19-handlers.js:561,651,700`
   for the SOC/executive narrative.
3. **`p25-handlers.js` `computeEnterpriseTrustScore(item)`** — a 12-dimension
   0–100 composite score (imported by 12 consumer files), which is what
   `p32-handlers.js`'s evidence-transparency claims actually surface as
   numeric confidence per Stage 3's fix.

None of these three call each other. An item can carry a P20 reliability
code of "B," independently render a P18 attribution string of "D — Unknown,"
and separately surface a P25 trust percentage — three different reliability
signals for the same underlying source, computed three different ways, with
no cross-check between them. This is exactly the kind of fragmentation
Stage 5's Registry (EPIC 2) and canonical Entity (EPIC 1) are meant to
collapse into one place — which is also exactly why doing so is an
architectural event under both repos' CLAUDE.md (**Architecture Preservation
Rule**: *"changing the architecture... requires substantially stronger
evidence than feature additions"*) and not a same-PR fix alongside a
discovery document.

---

## 4. The six required ADRs — starting points only, not decisions

Stage 5 names six ADR subjects. None are decided here. For whoever picks
this up next, here is what Section 2's findings already establish as the
*starting* position for each — informative, not binding:

| ADR subject | What Section 2 already shows |
|---|---|
| **Evidence ownership** | Same unresolved fork as Stage 4's confidence-ownership question: P20 (`evidence_chain`, richest existing field set), P18 (`buildEvidenceAttribution`, independently computed, actively used by P19 narrative), or a new EPIC-1 schema that supersedes both. Not the same question as Stage 4's (P25 vs. P20 vs. EIOS-07 was about *confidence scores*; this is about *evidence records*), but structurally identical in shape and consequence. |
| **Evidence lifecycle** | P30 already has real signal (verification status, timeline, IOC lifecycle, change tracking) that a state-machine could be built *on top of* rather than replacing — Stage 5's own "Zero Business Logic Duplication" principle argues for wrapping P30's existing computations in named states rather than re-deriving them. |
| **Relationship model** | Two independent graphs already exist (blog's Python `KnowledgeGraph`, intel-platform's JS `p31-handlers.js` graph). EIOS Layer 9 already declares the JSON-backed, no-DB-dependency approach as intentional and asks future object types to converge on it rather than fork again — a relevant precedent for whichever repo's graph is chosen. |
| **API versioning** | No prior art in-repo specifically for evidence; P38's schema-registry versioning (`version_introduced` per field, `SCHEMA_REGISTRY`) is the closest existing convention to extend rather than invent a new one for. |
| **Registry responsibilities** | Per Stage 2's already-settled cross-repo precedent (API-based integration, intel-platform as system of record), a Registry — if built — belongs in intel-platform, not the blog, consistent with EPIC 8's own proposed split. This is the one ADR subject where an existing decision (Stage 2's) already constrains the answer. |
| **Migration strategy** | Not assessable until EPIC 1/2 exist; no current schema to migrate away from since no canonical Evidence schema exists yet. |

---

## 5. What this document deliberately does not do

- Does not create an `Evidence` entity, table, KV namespace, or schema.
- Does not create an Evidence Registry, Evidence API, or any new route.
- Does not add an `Evidence` node type to either existing relationship graph.
- Does not touch `evidence_chain`, `buildEvidenceAttribution`,
  `computeEnterpriseTrustScore`, `buildP32EvidenceTransparencyBlock`, P30's
  lifecycle computations, or P23's certification gates — all read-only
  investigation, zero production code modified.
- Does not write any of the six ADRs Stage 5 requires — it inventories what
  each ADR would need to reconcile, which is a precondition for writing one,
  not the ADR itself.
- Does not touch the blog repository — all blog-side findings (EIOS layers
  3, 8, 9) are cited by path from read-only inspection; nothing in
  `cyberdudebivash-blog` is modified by this pass.
- Does not resolve the Stage 4 P25-vs-P20-vs-EIOS-07 confidence-ownership
  question — Section 3's three-way source-reliability fragmentation is a
  distinct, evidence-specific finding, not a restatement of Stage 4's.

---

*CYBERDUDEBIVASH® SENTINEL APEX — Project TITAN Stage 5 Discovery*
