# Project TITAN — Canonical Ownership Matrix

**Status:** Reflects ADR-0007 through ADR-0011 as **Proposed** decisions (not yet Accepted —
see each ADR's Approval section). This matrix is the single consolidated view; the ADRs are the
authoritative rationale. Where this matrix and an ADR ever disagree, the ADR wins — file an
issue rather than trusting this table blindly, per this program's own standing "governance
documentation being wrong is worse than stale" precedent (`platform/open-issues.md` Issue 15).

No row in this matrix has more than one Canonical Owner. That is the point of this document.

---

## Confidence, Evidence, Reliability, Relationships, Lifecycle

| Capability | Canonical Owner | Compatibility Adapter | Deprecated Components | Migration Target | Consumer Systems | Status |
|---|---|---|---|---|---|---|
| **Item-level confidence/trust score** | `computeEnterpriseTrustScore()` — P25, intel-platform | P37.3 `_confidenceAudit` (already reuses P25 directly — no adapter needed) | `scoring.py::_analyst_confidence()` (A4, blog); `computeTransparentConfidence()` (A9, P18, intel-platform) | A4's commercial-tier gate consumers migrate to intel-platform's confidence API once it exists; A9 superseded by P18's ADR-0009 migration | P26,P27,P29,P30,P31,P32,P33,P35,P36,P37,P38, `p26_intelligence_excellence.py` | Proposed (ADR-0007) |
| **Confidence-graph visualization dimensions** | Not decided — 2 of 7 dimensions already correctly read P20/P26; 5 independently invented | N/A yet | None yet | Future: 5 non-delegating dimensions evaluated against A1's existing 12 | `p29-handlers.js` (`_computeConfidenceGraph`, `buildP29ConfidenceGraphBlock`) | **Tracked (DEBT-012), not decided** |
| **Human-facing narrative confidence** | EIOS Layer 7 Mechanism 1 (analyst prose), blog | — (not a machine system; no adapter applicable) | None | None — retained as-is, advisory link to P25 documented | Published report readers | Proposed (ADR-0007) — not competing, coexists by design |
| **`ai_confidence` fallback defaults** | Already resolved, Stage 4 | N/A | 3 constants fixed (81→50, 30.0→50.0, 21.3→50.0) | N/A | Various | **Closed** (Stage 4, PR #108) |
| **Marketing "AI Confidence: 99.9%" copy** | Business/marketing decision, not engineering | N/A | N/A — deliberately excluded from Stage 4's engineering pass | Separate business decision if ever revisited | `apex_marketing_matrix.py`, `syndicate.yml` | **Explicitly out of scope**, tracked in tech debt register |
| **Evidence record schema** | `item.evidence_chain` — P20, intel-platform | `buildP32EvidenceTransparencyBlock` (P32) extended with `evidence_uuid` reference | `buildEvidenceAttribution()` (P18) — migrates to consumer role, not deleted | P18 becomes a formatter over P20's canonical fields | P20 quality score, P38 G19 gate, P32 evidence-transparency block | Proposed (ADR-0008) |
| **Source-reliability grade** | `evidence_chain.reliability_code` (A–F) — P20, intel-platform | New `mapReliabilityCodeToDisplayGrade()` (A–F → A–E) | `buildEvidenceAttribution()`'s independent A–E computation — same component as above, distinct decision | P18 reads P20's grade through the mapping adapter | P19 SOC/executive narrative | Proposed (ADR-0009) |
| **Evidence-presence heuristics** (fleet audits) | Not decided — flagged for consolidation, not a canonical-ownership question | N/A yet | None yet | Future: all three (P23 gate, P37 `_hasEvidence`, P35 `handleP35Evidence`) converge on reading P20's extended schema | P23 certification, P37 reporting, P35 reporting | **Tracked, not decided** — see tech debt register |
| **Entity relationship graph (operational/API)** | `p31-handlers.js` (`_buildGraph`) — P31, intel-platform | None yet — R1 lacks persistence, a named blocker, not an adapter gap | `KnowledgeGraph` (`engine/sentinel_engine/knowledge_graph.py`, blog) | Blog report-generation queries migrate to R1's future relationship API | Blog report pipeline (current, via R2); P31's own routes (current, via R1) | Proposed (ADR-0010) — **contingent on R1 persistence work, Blocked in readiness assessment** |
| **Evidence lifecycle state** | New derivation function over P30's existing signals — intel-platform | The derivation function itself *is* the adapter (wraps L1–L4 without modifying them) | None — nothing existing is deprecated, P30 is extended-by-composition only | N/A — additive only | Wherever Evidence records are rendered, once implemented | Proposed (ADR-0011) |
| **Publication workflow state machine** | Out of scope for Project TITAN — different capability than evidence lifecycle | N/A | N/A | N/A | None (zero production consumers today) | **Not a TITAN decision** — `lib/governance/workflow.ts` (blog) noted as prior art only |

---

## The `lib/` RC1 initiative (blog repo) — tracked separately, not a capability row

`lib/intelligence`, `lib/reporting`, `lib/ioc`, `lib/detection`, `lib/governance`, `lib/api`
(blog repo) is not included as a normal capability row above because it does not currently
implement any *of these specific* capabilities in production — it implements its own complete,
parallel version of several of them, live nowhere. Per ADR-0007/0008/0011, each of its
overlapping pieces (`ConfidenceEngine`, `Evidence` type, `WorkflowEngine`) is individually
excluded from canonical candidacy on zero-consumer grounds, not evaluated as a bloc. Its
disposition as a *whole initiative* — integrate, formally shelve, or delete — is a distinct
governance question, tracked as the top entry in `TITAN_TECH_DEBT_REGISTER.md`, owned by
whoever holds the blog repo's architecture-review authority. It has no Canonical Owner, no
Compatibility Adapter, and no Migration Target in this matrix because no decision has been made
to migrate anything to or from it.

---

## Adjacent capabilities named in Stage 4/5 discovery, not re-litigated here

| Capability | Owner (already established, not a TITAN decision) | Note |
|---|---|---|
| Cloudflare Workers production runtime | intel-platform (`workers/intel-gateway`, `workers/revenue-engine`, `workers/intel-retention-engine`) | `ARCHITECTURE_DECISIONS.md`, pre-TITAN |
| `API_KEYS_KV` credential authority | intel-platform | `ARCHITECTURE_DECISIONS.md`, pre-TITAN |
| Report structure (5-section gate / 14-section spine / 66-section menu) | blog, `Sentinel-APEX/eios/sentinel-intelligence-standard.md` §8 | Resolved Stage 1 (PR #65) — three tiers of one hierarchy, not competing systems |
| Cross-repo data consumption pattern | intel-platform = system of record, blog = API consumer | Stage 2 (PR #106), the precedent every ADR above cites |
| Severity scale (`CRITICAL\|HIGH\|MEDIUM\|LOW`) | blog, `report_parser.SEVERITIES` | Fixed Stage 1; not re-opened by any TITAN Stage 6 ADR |

---

## Matrix maintenance

This table must be updated whenever an ADR's status changes (Proposed → Accepted →
Superseded), or when a new fragmentation finding is discovered — per the same rule that
produced `TITAN_STAGE6_VALIDATION.md` §2–3. Recommended enforcement: the CI check proposed in
`TITAN_CI_GOVERNANCE.md` flags new functions matching known confidence/evidence/reliability
signatures that aren't reflected here, rather than relying on this document being remembered.
