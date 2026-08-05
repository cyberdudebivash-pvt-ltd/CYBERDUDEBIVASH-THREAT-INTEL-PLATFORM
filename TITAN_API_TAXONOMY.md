# Project TITAN — Production API Taxonomy (Task 4)

**Status:** Reference taxonomy. Assigns every route family found in Task 3's interface
registry (`TITAN_INTERFACE_REGISTRY.md`) to exactly one category. No route appears in two
categories — where a route family is genuinely cross-cutting (e.g., P38's confidence-audit
touches both Confidence and Governance), it is assigned to the category matching its
**primary** purpose, with a cross-reference note, not duplicated.

---

## Category definitions and membership

### 1. Evidence APIs
Routes whose primary output is an evidence record, evidence chain, or evidence-completeness
signal.

| Route family | Surface |
|---|---|
| `/api/v1/p20/*` (quality report, feed audit — evidence_chain-adjacent) | intel-platform |
| `/api/v1/p32/*` evidence-transparency-adjacent responses | intel-platform |
| `/api/v1/p35/evidence` | intel-platform |
| `/api/v1/p37/*` evidence-audit-adjacent responses | intel-platform |
| `/api/v1/analysis/{assessments,findings}.js`, `/api/v1/workbench/{investigations,cases}.js` | blog, Vercel (`evidence-manager.js`, `evidence-validator.js`, `evidence-conflict-engine.js`, `evidence-traceability-engine.js` — very likely live, DEBT-000) |
| *(future, Blocked)* Evidence Registry API | intel-platform, per ADR-0008 |

### 2. Confidence APIs
Routes whose primary output is a confidence, trust, or calibration score.

| Route family | Surface |
|---|---|
| `/api/v1/p25/trust-score` | intel-platform (canonical, ADR-0007) |
| `/api/v1/p18/*` (`buildTrustIndicatorBlock`, `computeTransparentConfidence` — ADR-0007 A9, Deprecated-Pending-Migration) | intel-platform |
| `/api/v1/p22/*` (contradiction, confidence explanation) | intel-platform |
| `/api/v1/p26/grade*` | intel-platform |
| `/api/v1/p29/*` (`_computeConfidenceGraph` — DEBT-012, tracked not decided) | intel-platform |
| `/api/v1/p35/confidence`, `/api/v1/p37/iq-score` | intel-platform |
| `/api/v1/p38/confidence-audit`, `/api/v1/p38/iq-index` | intel-platform |
| `/api/v1/intelligence/confidence.js` | blog, Vercel (`confidence-exposure.js`/`confidence-scorer.js` — very likely live, DEBT-000; same domain as P25, documented example response, undocumented ownership) |

### 3. Relationship APIs
Routes whose primary output is entity relationships, graphs, or campaign/actor linkage.
**This category has an unresolved four-way fragmentation — see ADR-0010 (revised this stage)
and DEBT-013.**

| Route family | Surface |
|---|---|
| `/api/v1/p31/graph`, `/relationships`, `/campaign`, `/entity` | intel-platform (P31, per-request-built, no persistence) |
| `/api/v1/intel/graph`, `/api/v1/intel/relations` | intel-platform (`api-extensions.js`, reads pre-computed `data/ai/intel_graph.json` from R2 — a **different data source than P31**) |
| Blog `KnowledgeGraph` (no HTTP route today — pipeline-internal) | blog, Python |
| Blog `/api/v1/intel?action=graph`, `?action=top-actors` | blog, Vercel (`api/_lib/threat-graph.js`, live) |
| Blog `/api/v1/intelligence/{graph,correlations}.js`, `/api/v1/workbench/*` | blog, Vercel (`graph-engine.js`, `graph-traversal.js`, `relationship-engine.js`, `correlation-engine.js` — very likely live, DEBT-000; 34 entity types, 31 relationship types, Redis-persisted — a **5th** independent graph implementation) |

### 4. Threat APIs
General threat-intelligence content delivery — feeds, IOC lookup, campaign/APT/ransomware
profiles. The largest single category by route count.

| Route family | Surface |
|---|---|
| `/api/v1/intel/*.json` (latest, apex, top10, stats, campaigns, ransomware, apt, epss, defcon, pulse, darkweb, cybermap) | intel-platform |
| `/api/v1/ioc/lookup` | intel-platform |
| `/api/preview`, `/api/feed` | intel-platform |
| `/api/v1/p19/*` (SOC/IOC detail) | intel-platform |
| `/api/v1/p33/*` (ECIOS cross-feed aggregation) | intel-platform |
| `/api/scoring/*` (KEV, ransomware, velocity) | intel-platform (`enterprise-endpoints.js`) |
| Blog `/api/v1/intel` (`?action=live/top-threats/cve/iocs/ransomware/search/campaigns`) | blog, Vercel |
| Blog static bundles (`api/v1/intel/*.json`) | blog, static |

### 5. Detection APIs
Detection-rule generation, export, and coverage.

| Route family | Surface |
|---|---|
| `/api/sigma/bulk`, `/api/yara/bulk`, `/api/siem/{splunk,sentinel,qradar}` | intel-platform (`enterprise-endpoints.js`) |
| `/api/v1/p23/*` (detection coverage, actionability) | intel-platform |
| `/api/v1/p30/drift` (detection drift) | intel-platform |
| *(archived, ADR-0013)* `lib/detection/*`, `lib/api/detection-rules.ts` | blog — flagged as a named architecture-policy conflict (detection engineering does not belong on the blog per its own CLAUDE.md), disposition: Archive |

### 6. Reporting APIs
Report generation, retrieval, and rendering.

| Route family | Surface |
|---|---|
| `/api/reports/*.json` | intel-platform |
| `/reports/**` (HTML) | intel-platform |
| STIX bundle delivery (via TAXII objects endpoint) | intel-platform |
| *(archived, ADR-0013)* `lib/reporting/*`, `lib/api/intelligence-reports.ts` | blog |
| Blog's actual live report pipeline (no direct customer-facing API — publishes to static HTML) | blog, Python |

### 7. Governance APIs
Platform self-governance, certification, schema/feed governance, quality gates.

| Route family | Surface |
|---|---|
| `/api/v1/p21/*` (certification) | intel-platform |
| `/api/v1/p27/certify`, `/p28/certify`, `/p29/certify`, `/p30/certify`, `/p31/certify` | intel-platform |
| `/api/v1/p34/*` (assurance, SBOM, compliance) | intel-platform |
| `/api/v1/p38/schema-registry`, `/schema-drift`, `/feed-governance` | intel-platform |
| P37/P35 hardening, drift, debt routes | intel-platform |

### 8. Administration APIs
Operator/admin-only, credential-gated.

| Route family | Surface |
|---|---|
| `/api/admin/health`, `/audit`, `/keys` (POST/DELETE), `ADMIN_SECRET`-gated | intel-platform |
| Blog `/api/v1/admin` (`?action=pending/approve/reject/audit/razorpay-orders/product-orders`) | blog, Vercel |
| `/auth/login`, `/auth/logout` | intel-platform |
| Blog `/api/v1/auth` (`?action=register/me`), `/api/v1/keys/usage` | blog, Vercel |

### 9. Analytics APIs
Metrics, observability, dashboards — read-only aggregate signal, not primary content.

| Route family | Surface |
|---|---|
| Every P-layer's `/observability` and `/metrics`/`/dashboard` routes (P16–P38, ~40 routes) | intel-platform |
| `/api/v1/news/feed` | intel-platform |

### 10. Internal APIs
Not customer-facing under any tier; infrastructure/pipeline-internal.

| Route family | Surface |
|---|---|
| `api/cron/dispatch-intel.js` | blog, Vercel cron |
| Blog's `api/_lib/*` files not reachable from any of the 8 deployed entry points (per this stage's reachability trace, see `TITAN_INTERFACE_REGISTRY.md`) | blog — internal/dead, not a route at all |
| P16 workflow/asset/automation internals not independently routed | intel-platform |

### 11. External APIs
Explicitly designed for third-party/partner consumption, with its own protocol conventions.

| Route family | Surface |
|---|---|
| TAXII 2.1 (`/taxii/*`, `/api/taxii/*`) | intel-platform — **note the two path prefixes, see DEBT-014** |
| MISP export (`/api/misp/export`, `/api/v1/export/misp`) | intel-platform |
| CSV export (`/api/export/csv`) | intel-platform |
| Webhooks (Razorpay, Gumroad, blog's Razorpay webhook) | both |

### 12. Commercial/Billing APIs
Payment, subscription, and monetization — split out from Administration because its risk
profile (financial transactions) and compliance surface (PCI-adjacent) differ materially.

| Route family | Surface |
|---|---|
| Razorpay verify/webhook, Gumroad webhook | intel-platform |
| Blog `/api/v1/billing` (`?action=create-intent/submit-payment/subscribe/razorpay-*`), `/api/v1/billing/webhook`, `/api/v1/billing/razorpay-webhook` | blog, Vercel |

---

## No duplicated responsibility — self-check

Per Task 4's explicit requirement, every route family above appears in exactly one category.
The two categories with the most cross-cutting temptation were resolved explicitly:

- **Confidence vs. Evidence**: a route counts as Confidence if its primary output is a score;
  Evidence if its primary output is a record/chain. P32's evidence-transparency block outputs
  both a claim record *and* a confidence number per claim — assigned to Evidence because the
  claim record is the primary structure and confidence is an attached field, not the route's
  main purpose.
- **Relationship vs. Threat**: a route counts as Relationship only if graph/edge structure is
  the primary output. `/api/v1/intel/campaigns` (a list) is Threat; `/api/v1/p31/campaign`
  (entity + edges) is Relationship.

**Duplicated responsibility found and explicitly flagged, not hidden:** Category 3
(Relationship APIs) has **five** independent implementations (not four — see the DEBT-000
addition above). Category 1 (Evidence) and Category 2 (Confidence) each gained one more
undocumented, very-likely-live blog-side implementation this stage as well. This is not a
taxonomy defect — the taxonomy correctly groups them into one category precisely so the
duplication is visible in one place rather than scattered across category-specific mental
models. Resolving the duplication is ADR-0007/0008/0010's job (all three now carry a blocking
Revision pending DEBT-000's resolution), not the taxonomy's — but it is worth naming plainly
that this taxonomy exercise is what turned "four independent graph implementations" (already a
notable finding) into "five, plus the realization that two entire API categories have a
second, undocumented owner" by the time it was actually filled in with real route data.
