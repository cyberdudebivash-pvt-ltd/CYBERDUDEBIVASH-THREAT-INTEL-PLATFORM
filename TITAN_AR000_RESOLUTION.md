# Project TITAN Stage 8 — AR-000 Resolution Report (Phase 3)

**Status:** Resolved for the purpose it was raised for (does this compete with canonical
systems for production traffic), with one sub-item left explicitly open. AR-000 is the renamed
DEBT-000 from Stage 7 ("undocumented, very-likely-live second CTI platform in the blog repo").

Answering Stage 8's Phase 3 questions in order, per route group:

## `api/v1/newsletter.js`

| Question | Answer |
|---|---|
| Is it deployed? | **Yes** — confirmed live, HTTP 405 (GET) / 200 (POST), application-crafted response |
| Is it reachable? | **Yes** |
| Is it monitored? | Unknown — no monitoring/alerting configuration found in-repo; not falsifiable from outside |
| Is it documented? | **No** — not in any architecture document prior to this program; now documented here and in the interface registry |
| Is it supported? | Presumed yes (it works, has explicit input validation and a real `resend`-backed email flow) but no named owner exists |
| Is it duplicated? | **No** — no other newsletter-signup mechanism was found competing with it |
| Does it violate architecture? | **No** — newsletter capture is explicitly named as blog's own responsibility in its CLAUDE.md ("Newsletter and community growth"), unlike the confidence/evidence/graph capabilities |

**Resolution: legitimate, live, low-risk capability. Needs an owner named and a line added to
the interface registry — does not need architectural reconciliation.**

## The other 21 files (`api/v1/{intelligence,workbench,analysis,customer,products,quality,reports,detections,ioc}/*`)

| Question | Answer |
|---|---|
| Is it deployed? | **No** — direct, repeated HTTP verification (GET and POST, across all 22 originally-flagged paths except newsletter) returns Vercel's platform-level `NOT_FOUND`, byte-identical to a deliberately-nonexistent baseline path. See `TITAN_STAGE8_VERIFICATION_REPORT.md` for the full evidence table |
| Is it reachable? | **No** (from the public internet; cannot rule out an internal-only Vercel preview/staging deployment this environment has no way to discover or reach) |
| Is it monitored? | N/A — nothing to monitor if nothing is receiving traffic |
| Is it documented? | **No** — this remains true; the code's own inline documentation (e.g., `confidence.js`'s worked example) is real and good, but no architecture document references any of it |
| Is it supported? | **No** — unreachable code cannot be "supported" in any operational sense |
| Is it duplicated? | **Not currently, in production** — while unreachable, it does not compete with P25/P20/P18/P31 for live traffic. This is the key finding that resolves the blocking concern raised in ADR-0007/0008/0009/0010's Stage 7 revisions |
| Does it violate architecture? | **Ambiguous, and this is the one sub-item left open.** The code exists in the repository, is substantively engineered (not a stub), and directly overlaps confidence/evidence/relationship-graph territory blog's own CLAUDE.md reserves for intel-platform — *if it were live*, it would violate architecture. Since it is not live, the more precise finding is: **the repository contains ~21 files' worth of unreachable code whose existence is itself unexplained**, structurally identical in kind (though not in mechanism) to the dormant `lib/` tree ADR-0013 already assessed. This is not fully resolved — see Recommendation below |

**Resolution: the specific fear that motivated AR-000/DEBT-000 — a live, undocumented,
traffic-serving competitor to the canonical confidence/evidence/relationship systems — does
not hold. ADR-0007, ADR-0008, ADR-0009, and ADR-0010 are un-blocked from this specific
concern**, each updated with a second, dated Revision section below. **The narrower question of
why unreachable, substantially-built code exists in the repository at all remains open**,
tracked as a downgraded, non-blocking tech-debt item (see revised `TITAN_TECH_DEBT_REGISTER.md`).

## Recommendation for the still-open sub-item

Three candidate explanations were considered, none confirmable from outside Vercel's own
dashboard/build logs — listed for whoever does have that access, not resolved here:

1. **Vercel project-level configuration** (Root Directory, an Ignored Build Step script, or a
   dashboard-configured function include/exclude pattern) invisible in the repository excludes
   these paths while allowing the original 8 plus `newsletter.js`.
2. **A per-function build failure** — if one of the engine files in the `api/_lib/` import
   chain (e.g., a Redis client initialization, a large dependency) fails to bundle in Vercel's
   build environment, Vercel can silently exclude just that function while the rest of the
   deployment succeeds.
3. **Work in progress, intentionally not yet promoted** — the files could represent active
   development toward a future release, deployed only to preview environments this session
   cannot discover or reach.

Recommended action, not performed here: whoever holds Vercel dashboard/CLI access runs `vercel
ls` / checks the project's Functions tab / reviews the most recent production build log for
these specific files, to convert "unreachable, reason unconfirmed" into a definitive answer.
This is now a **due-diligence follow-up**, not a blocker — a materially different priority than
Stage 7 left it at.

## Revision — 2026-08-05, Stage 8, applied to ADR-0007

The Stage 7 Revision section above (A10: `api/v1/intelligence/confidence.js` +
`confidence-exposure.js`/`confidence-scorer.js`) is **resolved**: direct HTTP verification
confirms this route is not live (`TITAN_STAGE8_VERIFICATION_REPORT.md`). A10 is not a
production competitor to A1. This ADR's original Decision (A1/P25 canonical) is no longer
blocked by A10 specifically. A10 remains excluded from canonical candidacy, now on the same
"zero production consumers" basis as A8/A9 rather than as an unresolved live-status question.
**This ADR is ready for human Acceptance review** as far as this concern goes.

## Revision — 2026-08-05, Stage 8, applied to ADR-0008

E9–E12 (`evidence-manager.js` and siblings) confirmed not live via the same verification.
Excluded from canonical candidacy on zero-consumer grounds. **This ADR is ready for human
Acceptance review** as far as this concern goes.

## Revision — 2026-08-05, Stage 8, applied to ADR-0009

S6 (`source-reliability-engine.js`) confirmed not live via the same verification (its only
consumers were among the 21 unreachable route files). Excluded from canonical candidacy on
zero-consumer grounds. **This ADR is ready for human Acceptance review** as far as this concern
goes.

## Revision — 2026-08-05, Stage 8, applied to ADR-0010

R5 (`graph-engine.js`/`graph-traversal.js`/`relationship-engine.js`/`correlation-engine.js`)
confirmed **not live** — its only consumers (`api/v1/intelligence/graph.js`,
`api/v1/intelligence/correlations.js`, `api/v1/workbench/*`) are among the 21 unreachable
files. This removes R5 from serious contention as an alternative to R1 (P31); the "R5 already
has the persistence property R1 lacks" argument in the Stage 7 revision no longer carries
practical weight, since R5 has no live consumer regardless of its technical properties.

**However, this ADR's fragmentation count does not drop back to two.** Direct verification this
stage additionally confirmed, independent of R5:
- **R3** (`api-extensions.js`'s `handleIntelGraph`/`handleIntelRelations`, reading
  `data/ai/intel_graph.json`) is **confirmed live** (HTTP 403, tier-gated, real route) — this
  was already known from Stage 7's code reading, now confirmed with live traffic evidence.
- **R4** (`api/_lib/threat-graph.js`) is **confirmed live**, same basis as before, reconfirmed.

So the live fragmentation is **R1 (P31) vs. R3 (`api-extensions.js`) vs. R4 (blog
`threat-graph.js`)** — three, not five, and critically, **R1 and R3 are both intel-platform,
both live, both genuinely competing for the same "give me the relationship graph" request
today** — this is the single most actionable, highest-confidence fragmentation finding in this
entire program: same repository, same team, two live, independently-computed answers to the
same question. R5's exclusion doesn't reduce this ADR's urgency, it clarifies where the urgency
actually is. **This ADR remains not-yet-ready to default to R1 vs. R2 as originally written —
R1 vs. R3 must be resolved first, since they're both intel-platform-owned and therefore fully
within this program's authority to reconcile without a cross-repo negotiation.** Recommended:
prioritize R1-vs-R3 reconciliation ahead of the cross-repo R1-vs-R2/R4 question in any future
implementation stage.
