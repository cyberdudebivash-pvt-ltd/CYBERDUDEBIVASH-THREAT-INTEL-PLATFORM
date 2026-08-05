# Project TITAN — Stage 9 Readiness Assessment

**Status:** Planning input only, per this program's standing practice — not an authorization
for any Stage 9 work, only an assessment of what Stage 9 could responsibly contain given Stage
8's findings.

---

## What Stage 8 changed about the picture

Stage 8 was framed as "the gateway between governance and implementation," and it functioned
as one: it resolved the single largest open blocker (AR-000) through direct production
verification rather than further inference, and it converted four "Proposed, revised, blocked"
ADRs into "Proposed, ready for human Acceptance review." It also found one new high-priority,
concretely actionable item (DEBT-000B: R1-vs-R3 same-repo graph fragmentation) and authorized
the narrowest possible slice of forward implementation (Evidence entity scaffolding, inert,
zero blast radius).

## Preconditions for Stage 9

1. **Human Acceptance review of ADR-0007, 0008, 0009, 0010, 0012.** This is not a TITAN-stage
   task — it requires a human reviewer (Platform Governance Lead / Chief Threat Intelligence
   Architect, per each ADR's own Approval section) to actually check the boxes. Every stage
   since Stage 6 has produced Proposed ADRs; none have been marked Accepted by anyone with
   that authority. Stage 9 should not begin assuming Acceptance has happened — it should
   confirm it, or proceed only with whatever subset has been Accepted.
2. **AR-000's residual due-diligence item** — confirming via Vercel dashboard/build logs why
   the 21 routes are unreachable — is not blocking, but should happen before Stage 9 if
   feasible, since "we verified it's not live" and "we know why it's not live" are different
   confidence levels for a decision this consequential.
3. **DEBT-000B scoping** — identifying the `data/ai/intel_graph.json` producer is a
   prerequisite to any R1-vs-R3 reconciliation work, and nobody has done it yet.

## Candidate Stage 9 scope, if the above clear

In priority order, matching this stage's own findings about what's both valuable and low-risk:

1. **DEBT-000B resolution (R1 vs. R3)** — highest-confidence, same-repo, same-team, no
   cross-repo dependency. Candidate for Stage 9's primary focus if ADR-0010 is Accepted.
2. **Migration Roadmap Phase 1–3** (P25 dimension addition, A4 deprecation notice, P20 schema
   extension) — unchanged from Stage 7/8's assessment, still low-risk, still additive-only,
   contingent on ADR-0007/0008 Acceptance.
3. **AR-000's remaining due-diligence** (Vercel config confirmation) — not engineering work in
   the traditional sense, but worth resolving early in Stage 9 rather than letting it linger.
4. **DEBT-014 resolution** (TAXII path documentation) — requires checking partner-facing docs
   outside this codebase; low engineering effort once someone with access to that
   documentation participates.
5. **Contract Governance's remaining unimplemented items** (`TITAN_CONTRACT_GOVERNANCE.md`) —
   Interface Completeness linting is the cheapest remaining one, recommended as a quick win
   if Stage 9 has spare capacity.

## Explicitly not ready for Stage 9

- **Evidence Registry service, Evidence APIs** — remain Blocked per
  `TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md`, pending ADR-0008 Acceptance at minimum.
- **Knowledge Graph, Explainable AI, Customer Portal formalization** — Stage 8's own
  Non-Goals list explicitly excludes the first two; Customer Portal (newly discovered to
  already exist, ungoverned, via `newsletter.js`) needs an owner named before any
  formalization work, which is a business/organizational step, not an engineering one.
- **`lib/` tree and the 21 unreachable blog routes' disposition** — both are due-diligence /
  documentation-correction items (ADR-0013's Archive recommendation, AR-000's root-cause
  confirmation), not implementation work, and neither is scoped for Stage 9's engineering
  capacity under this assessment.

## Success metrics carried forward

Same discipline this program has applied since Stage 6: track whether the number of
"discovered via our own tooling, not prior planning" surprises trends down. Stage 8 found one
major one (the Vercel routing-behavior correction) and resolved it with more rigor than Stage 7
had available (external verification vs. static analysis) — a good sign for the program's own
trajectory, worth continuing to measure, not just claim.
