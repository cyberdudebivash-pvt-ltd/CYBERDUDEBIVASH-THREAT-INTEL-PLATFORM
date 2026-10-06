# Project TITAN — Canonical Interface Registry (Task 3)

**Status:** Complete for intel-platform and blog's Vercel-deployed surface. Grain is
**route-family** (matching the P-layer/module boundary already used throughout this program's
documentation, per Reuse Before Build — see `docs/adr/README.md`'s reasoning for the same
choice), not one row per exact HTTP path — a ~175-route platform is more useful catalogued at
this grain than as an undifferentiated flat list. Exact paths are in
`TITAN_API_TAXONOMY.md` and cited directly in ADR text where a specific path matters.

Columns per Task 3: **Interface Name, Owner, Repository, Consumer, Status.** Status values:
**Canonical** (the authoritative implementation for its capability), **Legacy** (superseded but
still live), **Deprecated** (marked for removal, still live during migration window),
**Compatibility Adapter** (exists specifically to bridge two systems), **Future Target** (not
yet built, named as the eventual canonical destination).

---

## intel-platform (`workers/intel-gateway/src/index.js` + extension modules)

| Interface | Owner | Consumer | Status |
|---|---|---|---|
| P16 — Subsystems/Workflows/Assets/Health/Analytics | Intelligence Engineering | Internal + dashboard | Canonical |
| P17 — Orchestrator/Digital Twin/Campaign Forecast | Intelligence Engineering | Internal | Canonical |
| P18 — Correlation/Trust Indicators/Validation | Intelligence Engineering | P19 narrative | **Mixed** — `buildEvidenceAttribution`, `computeTransparentConfidence` Deprecated-Pending-Migration (ADR-0007/0009); `handleP18Correlation` etc. Canonical |
| P19 — SOC/IOC Detail/Detection/MITRE/Executive | Intelligence Engineering | Customer-facing narrative | Canonical |
| P20 — Quality Score/Evidence Chain/IOC Quality | Intelligence Engineering | 12+ downstream P-layers | Canonical (ADR-0008 E1) |
| P21 — Certification/Scorecard | Intelligence Engineering | P23, dashboards | Canonical |
| P22 — Contradiction/Confidence Explanation | Intelligence Engineering | Internal QA | Canonical |
| P23 — Actionability/IR Package/Threat Hunting | Intelligence Engineering | Customer-facing | Canonical |
| P25 — Trust Score/Explainable Score | Intelligence Engineering | 13 files (ADR-0007 A1) | **Canonical** (ADR-0007 designated) |
| P26 — Composite Grade/Trust Badges | Intelligence Engineering | Dashboards | Canonical |
| P27 — Exposure Analysis (7-dim)/Multi-Audience | Intelligence Engineering | Customer-facing | Canonical |
| P28 — Environment Risk/Business Impact/Action Center | Intelligence Engineering | Customer-facing | Canonical |
| P29 — Enterprise Intelligence Network/Decision Engine | Intelligence Engineering | Customer-facing | **Mixed** — `_computeConfidenceGraph` tracked-not-decided (DEBT-012); rest Canonical |
| P30 — Verification/Timeline/Change Tracking | Intelligence Engineering | ADR-0011's L1-L4 canonical derivation source | Canonical |
| P31 — Knowledge Graph/Entity/Campaign/Relationships | Intelligence Engineering | P-layer stack | **Legacy pending persistence** — ADR-0010 target-canonical, blocked on persistence work (DEBT-004) |
| P32 — Operational Lifecycle/Strategic Decisions/Maturity | Intelligence Engineering | Customer-facing | Canonical |
| P33 — ECIOS Cross-Feed Aggregation/SOC Mission | Intelligence Engineering | Customer-facing, dashboards | Canonical |
| P34 — Engineering Assurance (health/security/SBOM/compliance) | Intelligence Engineering | Enterprise sales enablement | Canonical |
| P35 — Intelligence Quality (freshness/confidence/diversity) | Intelligence Engineering | Internal audit, P37/P38 chain | Canonical (fleet-level auditor, not a scorer — ADR-0007/0008) |
| P36 — Intelligence Excellence/Maturity/Customer Value | Intelligence Engineering | Sales/customer-facing | Canonical |
| P37 — Platform Hardening/Confidence Calibration | Intelligence Engineering | Internal audit | Canonical (fleet-level auditor — ADR-0007/0008/0009) |
| P38 — Governance/Schema Registry/Feed Governance | Intelligence Engineering | Cross-repo schema contract (explicitly documents blog as a consumer) | **Canonical** — this repo's schema-versioning reference pattern, reused by ADR-0012 |
| TAXII 2.1 server (`/taxii/*`) | Intelligence Engineering | External/partner (STIX consumers) | Canonical |
| TAXII 2.1 server, second path (`/api/taxii/*`, `enterprise-endpoints.js`) | Intelligence Engineering | External/partner | **Legacy / needs reconciliation — DEBT-014** (two TAXII path prefixes, unclear which is documented-canonical externally) |
| MISP/CSV/Sigma/YARA/SIEM bulk export | Intelligence Engineering | External/partner | Canonical |
| `/api/scoring/*` (KEV, ransomware, velocity) | Intelligence Engineering | External/partner | Canonical |
| `/api/v1/intel/graph`, `/relations` (`api-extensions.js`) | Intelligence Engineering | Customer-facing (paid tiers) | **Fragmented — DEBT-013**, reads a different data source (`data/ai/intel_graph.json`) than P31 |
| Admin API (`/api/admin/*`) | Platform SRE | Internal ops only | Canonical |
| Auth (`/auth/login`, `/auth/logout`) | Platform SRE | All authenticated consumers | Canonical |
| Payments (Razorpay/Gumroad webhooks) | Revenue Engineering | Payment processors | Canonical |
| Static immutable bundles (`generate_api_manifests.py` → `api/v1/intel/*.json`) | Platform SRE | Frontend, external consumers preferring static | Canonical (distinct delivery pattern from dynamic routes, not a duplicate — see ADR-0012) |
| `revenue-enforcement.js` tier gating | Revenue Engineering | Applied across all tiered routes | Canonical (cross-cutting, not a route family itself) |
| `public_api_sanitizer.py` (PII/internal-field leak prevention) | Platform SRE | All public JSON output | Canonical, existing infrastructure — cited in `TITAN_CONTRACT_GOVERNANCE.md` as prior art |

---

## blog repository — live surface

| Interface | Owner | Consumer | Status |
|---|---|---|---|
| `api/v1/intel.js` (`?action=live/top-threats/cve/iocs/ransomware/search/graph/campaigns/top-actors`) | Blog/Vercel Engineering | Blog frontend, external | Canonical (blog's own namespace — see ADR-0012's "v1 label collision" note) |
| `api/v1/auth.js` (`?action=register/me`, `/api/v1/keys/usage`) | Blog/Vercel Engineering | Blog frontend | Canonical |
| `api/v1/billing.js` (`?action=create-intent/submit-payment/subscribe/razorpay-*`) | Blog/Vercel Engineering | Blog frontend, Razorpay | Canonical |
| `api/v1/admin.js` (`?action=pending/approve/reject/audit/*-orders`) | Blog/Vercel Engineering | Internal ops only | Canonical |
| `api/v1/billing/webhook.js`, `razorpay-webhook.js` | Blog/Vercel Engineering | Payment processors | Canonical |
| `api/cron/dispatch-intel.js` | Blog/Vercel Engineering | Scheduled, internal | Canonical |
| `api/og.js` | Blog/Vercel Engineering | Social-preview image generation | Canonical |
| `api/_lib/threat-graph.js` | Blog/Vercel Engineering | `api/_lib/intel.js` → `api/v1/intel.js` | **Canonical for blog's live graph, but see ADR-0010 revision** — one of four relationship-graph implementations ecosystem-wide, not yet reconciled |
| `api/_lib/campaign-engine.js` | Blog/Vercel Engineering | Confirmed live per `platform/open-issues.md` Issue 15 | Canonical for blog's live campaign clustering — cross-check against P31's `buildP31CampaignBlock` not yet done, logged in tech debt register |

**`api/_lib/` reachability trace — complete.** The trace initially scoped to `vercel.json`'s 8
explicitly-configured functions found only 12 of 125 `api/_lib/*.js` files reachable, and
concluded the 18 confidence/evidence/graph engines were dormant. **That scoping was wrong** —
`vercel.json` has no `"builds"` key restricting deployment, so Vercel's default file-based
routing very likely deploys all 30 files under `api/v1/`, not just the 8 configured ones. A
second pass found 22 additional route files, ~18 of which import directly into the
confidence/evidence/graph/quality/governance engine cluster. See
`TITAN_STAGE7_VALIDATION.md` §2A and `TITAN_TECH_DEBT_REGISTER.md` DEBT-000 for full detail.
Registered below as its own surface rather than folded into the table above, since it is large
enough and consequential enough to warrant separate visual weight.

## blog repository — second, undocumented surface (very likely live, DEBT-000)

| Interface | Owner | Consumer | Status |
|---|---|---|---|
| `api/v1/intelligence/{confidence,correlations,graph,objects,publish,similarity}.js` | **Unassigned** | Very likely live, external | **Ungoverned — DEBT-000.** Confidence/relationship functionality directly overlapping ADR-0007/0010's scope |
| `api/v1/workbench/{cases,dashboard,investigations,search}.js` | **Unassigned** | Very likely live, external (analyst-facing) | **Ungoverned — DEBT-000** |
| `api/v1/analysis/{assessments,findings}.js` | **Unassigned** | Very likely live | **Ungoverned — DEBT-000.** Backs `evidence-validator.js`/`evidence-conflict-engine.js` |
| `api/v1/customer/{dashboard,download}.js` | **Unassigned** | Very likely live, customer-facing | **Ungoverned — DEBT-000.** This is the "Customer Portal" `TITAN_IMPLEMENTATION_AUTHORIZATION.md` originally (incorrectly) assessed as not yet built |
| `api/v1/detections/rules{,/[id]}.js`, `api/v1/ioc/{search,[id]}.js`, `api/v1/products/*`, `api/v1/quality/index.js`, `api/v1/newsletter.js`, `api/v1/reports/index.js` | **Unassigned** | Very likely live | **Ungoverned — DEBT-000** |
| Underlying engines: `confidence-scorer.js`, `confidence-exposure.js`, `evidence-manager.js`, `evidence-validator.js`, `evidence-conflict-engine.js`, `evidence-traceability-engine.js`, `source-reliability-engine.js`, `graph-engine.js`, `graph-traversal.js`, `relationship-engine.js`, `correlation-engine.js`, `governance-engine.js`, `quality-gates-engine.js`, `quality-scorer.js`, `quality-validators.js`, `threat-scorer.js`, `consistency-engine.js` | **Unassigned** | The routes above | **Ungoverned — DEBT-000** |

**113 of 125 `api/_lib/*.js` files remain confirmed-not-reachable** even under the corrected
understanding (verified by full expansion of the reachable set's own import graph) — the
dormant/live split within `api/_lib/` is real, not "everything turned out to be live." The
correction is specifically that *more* is live than the first pass found, not that the
directory is uniformly live.

---

## blog repository — archived surface (ADR-0013)

| Interface | Owner | Consumer | Status |
|---|---|---|---|
| `lib/intelligence/*`, `lib/reporting/*`, `lib/ioc/*`, `lib/detection/*`, `lib/governance/*`, `lib/api/*` | Unassigned (per DEBT-001) | None (zero production consumers, confirmed twice) | **Deprecated-in-spirit / Archive recommended (ADR-0013)** — not formally Deprecated since deprecation implies prior active use |

---

## Future Target rows

| Interface | Owner (proposed) | Consumer (future) | Status |
|---|---|---|---|
| Enterprise Evidence Registry API | intel-platform | Internal + external, once built | Future Target — Blocked (`TITAN_IMPLEMENTATION_READINESS.md`) |
| Intelligence Provenance API | intel-platform | External | Future Target — Blocked, additionally blocked on ADR-0012 approval per this stage |
| Persisted P31 graph API | intel-platform | Replaces both P31's current form and, eventually, `api/v1/intel/graph`'s R2-snapshot approach | Future Target — Blocked on persistence engineering |
| Consolidated TAXII path (resolving DEBT-014) | intel-platform | External/partner | Future Target |

---

## Registry maintenance

This registry should be re-derived, not hand-edited into permanent drift, whenever
`TITAN_CONTRACT_GOVERNANCE.md`'s planned Interface Completeness / API Drift Detection checks
(#4, #6) are implemented (Stage 8+) — until then, it is maintained manually and should be
re-verified at the start of any future stage that touches API surface, the same discipline
Task 1 applied to Stage 6's ADRs this stage.
