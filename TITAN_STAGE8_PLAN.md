# Project TITAN — Stage 8 Engineering Plan (Task 9)

**Status:** Planning only, per this stage's explicit instruction. Nothing here is implemented.
This plan is restructured relative to what a Stage 8 plan would have looked like before this
stage's DEBT-000 finding — verification now precedes migration, where Stage 6/7's original
sequencing assumed migration could proceed once ADRs were Accepted.

---

## Scope

Stage 8 has two phases with a hard ordering dependency between them.

### Phase A — Verification (must complete first, blocks everything else)

1. **Confirm DEBT-000's live status.** Someone with Vercel dashboard/CLI/deployment access
   checks whether the 22 undeclared `api/v1/*` routes are actually receiving traffic (deploy
   logs, analytics, or a direct `curl` against each). This is not an engineering task in the
   normal sense — it requires access this environment does not have, and no other Stage 8 item
   can be responsibly scheduled until it resolves.
2. **Identify DEBT-000's owner or origin.** Git blame / commit history on `api/_lib/` and
   `api/v1/{intelligence,workbench,analysis,customer}/*` to establish when this was built and
   by whom/what process, informing whether it represents active, ongoing work elsewhere that
   this program simply hadn't discovered, or genuinely abandoned/orphaned code that happens to
   still be wired up.
3. **Identify the `data/ai/intel_graph.json` producer** (DEBT-013) — likely one of the
   automated pipeline workflows visible in intel-platform's git history; not identified this
   stage.
4. **Determine which TAXII path (`/taxii/*` vs `/api/taxii/*`) external partners actually use**
   (DEBT-014) — requires checking partner-facing documentation or traffic logs, neither
   examined this stage.

### Phase B — Everything originally planned for Stage 7/8, contingent on Phase A

5. Stage 6's original Migration Roadmap Phases 1–3 (P25 dimension addition, A4 deprecation
   notice, P20 schema extension) — **these remain low-risk and arguably could proceed
   independent of DEBT-000**, since they don't touch the newly-found surface. Recommended as
   the one exception allowed to proceed in parallel with Phase A rather than strictly after it,
   given their already-established low risk profile (ADR-0007/0008's original Risk tables).
6. ADR-0007, ADR-0008, ADR-0009, ADR-0010 re-review and Acceptance — **cannot complete until
   Phase A resolves**, since all four now carry an explicit blocking Revision.
7. ADR-0012 (API Versioning) review and Acceptance — independent of DEBT-000, could proceed in
   Phase A's timeframe.
8. `TITAN_CONTRACT_GOVERNANCE.md`'s Priority 1–2 items (Interface Completeness, API Drift
   Detection) — recommended to implement early in Phase B specifically *because* they would
   have caught classes of surprise similar to DEBT-000 sooner; concretely, extend #4's route-
   list-vs-router-conditions diff check to also cover Vercel's `api/v1/*` tree in the blog repo
   (a new, blog-side counterpart to the intel-platform-side check this stage only specified for
   `index.js`) — not scoped in detail here, flagged as the most directly DEBT-000-motivated new
   governance work.
9. If Phase A confirms DEBT-000 is live and worth keeping: draft ADR-0014 ("Investigation
   Workbench & Customer Portal Ownership") — not written this stage, explicitly out of this
   report's authority since it requires the Phase A findings as a precondition.
10. If Phase A confirms DEBT-000 should be unwound instead: a deprecation plan for ~22 live
    customer-facing routes, which is a materially bigger and more sensitive undertaking than
    anything else in this program to date, requiring its own dedicated stage.

---

## Dependencies

| Item | Depends on |
|---|---|
| Phase A entirely | Human with Vercel deployment access — cannot be completed by this environment alone |
| ADR-0007/0008/0009/0010 Acceptance | Phase A items 1–2 |
| ADR-0012 Acceptance | Independent — no DEBT-000 dependency |
| Migration Roadmap Phases 1–3 | Independent — no DEBT-000 dependency, may proceed in parallel with Phase A |
| ADR-0014 (drafting) | Phase A items 1–2, and a decision on DEBT-000's disposition direction |

---

## Deliverables

1. A short, factual verification report (not written by this environment) answering Phase A's
   four questions.
2. Updated ADR-0007/0008/0009/0010 status (Accepted, or a further-revised Proposed state if
   Phase A surfaces yet more information — this program's own track record this stage suggests
   not assuming Phase A is the last correction).
3. Migration Roadmap Phases 1–3 shipped (contingent on their respective ADR approvals, same as
   already documented in `TITAN_MIGRATION_ROADMAP.md` — unchanged by this plan).
4. ADR-0012 Accepted, or a documented reason it wasn't.
5. If applicable, ADR-0014 drafted (not Accepted — same Proposed-first discipline as every
   other ADR in this program).

---

## Acceptance Criteria

- Phase A's four questions have documented, evidenced answers — not assumptions.
- No route in DEBT-000's surface is modified, deprecated, or removed before Phase A completes.
- Regression suite remains 21/21 and P33 certification remains WORLDWIDE_RELEASE/0 blockers
  throughout — unaffected by Phase A (pure investigation, no code change) and protected by the
  same acceptance bar as every prior stage for Phase B's items.
- STAGE 5.9.4's advisory check remains clean or has only already-logged findings.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase A never gets prioritized because it requires access/authority outside normal engineering flow | Medium | High — every other Stage 8 item stalls | Name it explicitly as the top blocker in this plan and in the Implementation Authorization Report, so it isn't lost among more "normal-shaped" engineering tasks |
| DEBT-000 turns out to be actively maintained by a team/process this program's authors simply didn't know to ask | Low-Medium | Low if found early, embarrassing if found late | Phase A item 2 (git history / origin check) specifically defends against acting on an incomplete picture |
| Migration Roadmap Phases 1–3 get delayed waiting for Phase A despite being independent | Medium | Low (delay, not harm) | Explicitly called out as parallel-safe in Phase B item 5 |

---

## Migration Strategy

No migration is authorized by this plan. Phase B item 5's migrations follow
`TITAN_MIGRATION_ROADMAP.md`'s already-documented phases unchanged. Any DEBT-000-related
migration (item 10) is explicitly out of scope for a strategy to be defined here — it depends
on a decision this plan cannot make.

---

## Testing Strategy

Unchanged from `TITAN_STAGE7_PLAN.md`'s equivalent section for Phase B's items (regression
suite + P33 certification gate every change; new unit tests per migration phase as already
specified in the roadmap). Phase A has no testing strategy because it is not a code change —
its "test" is simply whether its four questions get correct, evidenced answers.

---

## Rollback Plan

Phase A is pure investigation — nothing to roll back. Phase B's items each carry their own
rollback plans already documented in `TITAN_MIGRATION_ROADMAP.md` and the relevant ADRs.

---

## Operational Readiness

Recommend the human running Phase A treat it with the same urgency as an incident, not a
backlog item — a system serving real customer data with zero monitoring/ownership is an
operational risk independent of this program's architecture-governance concerns (e.g., who
gets paged if `api/v1/customer/dashboard.js` starts erroring?). This is outside Project TITAN's
scope to resolve, but worth surfacing to whoever owns on-call/operational readiness generally.

---

## CI Requirements

No new CI gates required for Phase A. Phase B item 8 (blog-side route/engine drift check) is
the one new CI capability this plan recommends, sequenced as described.

---

## Documentation Requirements

- Phase A's findings must be written up with the same rigor as this stage's own discovery
  documents — cited, verified, not assumed — before any ADR is Accepted on their basis.
- Once Phase A resolves, `TITAN_STAGE6_VALIDATION.md`, `TITAN_STAGE7_VALIDATION.md`, all four
  revised ADRs, and this document should get a final "Resolved" annotation rather than being
  left in their current "pending verification" state indefinitely.

---

## Success Metrics

- Phase A's four questions answered with evidence, not assumption.
- Zero of DEBT-000's routes modified before their disposition is decided.
- ADR-0007, ADR-0008, ADR-0009, ADR-0010, ADR-0012 reach a final status (Accepted or a
  documented reason they remain Proposed) rather than sitting in revision limbo indefinitely.
- The number of "found via this stage's own tooling, not prior discovery" surprises trends
  toward zero in future stages — this stage found three in sequence (P18/P29 confidence
  functions, the four-way-then-five-way graph fragmentation, DEBT-000 itself), which is a
  useful signal that discovery rigor is improving, not a pattern to expect indefinitely.
