# Project TITAN Stage 8 — Canonical Runtime Ownership & Architecture Compliance Audit (Phases 6–7)

## Phase 6 — Canonical Runtime Ownership

Per capability, the six owner types Stage 8 asks for. Only listed where ownership actually
diverges across the six types — where all six are the same, stated once rather than repeated
six times per row.

| Capability | Canonical | Runtime | Repository | Documentation | Deployment | Business | Divergence explained |
|---|---|---|---|---|---|---|---|
| Item confidence (P25) | Intelligence Eng | Intelligence Eng | intel-platform | Intelligence Eng | Platform SRE (`deploy-worker.yml`) | Product/Revenue (drives tier gating) | Deployment owner (SRE) differs from feature owner (Intelligence Eng) — normal, expected split, not a gap |
| Evidence record (P20) | Intelligence Eng | Intelligence Eng | intel-platform | Intelligence Eng | Platform SRE | Product/Revenue | Same pattern |
| Relationship graph — R1 (P31) | Intelligence Eng | Intelligence Eng | intel-platform | Intelligence Eng | Platform SRE | Product/Revenue | Standard |
| Relationship graph — R3 (`api-extensions.js`) | **Intelligence Eng (same as R1)** | Intelligence Eng | intel-platform | **None** — undocumented in any architecture doc before this program | Platform SRE | Unclear — no product owner named for this specific path | **This row is the ownership anomaly**: same canonical/runtime/repo owner as R1, but no documentation owner and no clear business owner, despite being live and tier-gated (implying real commercial intent). This gap is exactly why DEBT-000B exists |
| Newsletter signup | **None found** | Vercel platform (implicit) | blog | **None** | Vercel (implicit, no explicit deploy workflow found for it specifically) | Growth/Marketing (implied by function, per blog CLAUDE.md's "Newsletter and community growth") | Live, working, revenue-adjacent capability with zero named owner across five of six categories — the starkest single ownership gap this audit found for something that actually works |
| `api/v1/intelligence/*` etc. (21 unreachable files) | N/A — not live | N/A — not live | blog | Partial (inline code comments only) | **None — not deployed** | Unknown | Ownership question is moot while unreachable; becomes urgent the moment (if ever) it's made reachable |
| `lib/` tree (ADR-0013) | N/A — archived recommendation | N/A — never deployed | blog | Self-documented (its own ADRs 0001-0002) but inaccurate re: integration status | None | None | Already fully covered by ADR-0013, not re-litigated here |

## Phase 7 — Architecture Compliance Audit

Validated against every named source: Project TITAN ADRs (0007–0013), Ownership Matrix,
Migration Roadmap, API Governance (ADR-0012), Confidence/Evidence/Relationship Frameworks
(ADR-0007/0008/0010), Versioning Rules (ADR-0012).

### Deviations found

| Deviation | Source of truth violated | Severity | Status |
|---|---|---|---|
| R1 vs. R3 same-repo graph fragmentation | ADR-0010 (One relationship-graph owner) | High | Open — DEBT-000B |
| `/taxii/*` vs. `/api/taxii/*` dual path, undocumented distinction | ADR-0012 (canonical route per capability) | Medium | Open — DEBT-014 |
| Newsletter route live with zero named owner | `TITAN_INTERFACE_OWNERSHIP.md`'s "every API must have a single owner" requirement (Stage 7, Task 5) | Medium | **New this stage** — added to registry, owner still unassigned |
| 21 unreachable blog routes overlapping confidence/evidence/relationship territory exist at all, unexplained | Blog's own CLAUDE.md ("DO NOT duplicate Sentinel APEX functionality") — **conditionally**: the rule is written to bind *live* duplication; unreachable code's compliance status is genuinely ambiguous, not a clean violation | Low (downgraded from Critical, see AR-000 resolution) | Open — DEBT-000, downgraded |
| No monitoring/logging discoverable for any tested route | Stage 8's own "Engineering Requirements: Observable, Auditable" | Medium | **New this stage** — DEBT-015 |
| CLAUDE.md's own CI STAGE NUMBERING table stale | Internal governance-file accuracy (not a TITAN ADR, but this repo's own supreme-authority doc) | Low | Open, unchanged — DEBT-011 (Stage 6) |

### Compliant (no deviation found)

- P16–P38's additive-only import chain: verified via live-route testing that new capability
  (P34–P38) works alongside old (P16–P33) with no evidence of breakage.
- Regression suite (21/21) and P33 certification (WORLDWIDE_RELEASE, 0 blockers) both re-run
  this stage — see `TITAN_STAGE8_VERIFICATION_REPORT.md`'s implicit confirmation via the same
  Bash session; explicit re-run recorded in the commit history for this stage.
- STAGE 5.9.4's advisory governance check remains clean (all 7 ADRs present, cited references
  resolve — re-run this stage before writing this report).
- ADR-0011's Evidence Lifecycle approach (derive from P30, don't re-instrument) has no
  compliance concerns raised by this stage's live verification — P30's routes were not
  independently re-tested but no new lifecycle-shaped implementation was found competing with it.

### Explicitly not audited this stage

- Full P16–P38 route-by-route compliance (only a representative sample was live-tested;
  exhaustive re-verification of ~150 routes was judged disproportionate to this stage's
  AR-000-focused mandate).
- `revenue-engine` and `intel-retention-engine` sibling workers.
- Blog's SEO/Lighthouse/monetization compliance dimensions (outside TITAN's architecture scope).
