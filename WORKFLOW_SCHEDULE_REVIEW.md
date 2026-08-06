# Workflow Schedule (Cron) Review

**Program:** Enterprise Release Readiness Program — Phase 4
**Scope:** Cron overlap analysis, cross-referenced against `WORKFLOW_CONCURRENCY_REVIEW.md`'s finding of a
14-member shared `sentinel-data-writer` concurrency group.
**Method:** Every `cron:` line was extracted verbatim from the committed YAML: 46 total across the 55
workflows, of which 40 are active and 6 are commented out in-file (disabled schedules kept as documentation
of prior cadence, not deleted — consistent with this repo's Deprecation Instead of Deletion convention).
Overlap analysis for the `sentinel-data-writer` group was computed programmatically from the active literal
cron expressions, not estimated by inspection.

---

## 1. Headline finding

The 9 `sentinel-data-writer` members that currently run on a **daily** (non-weekly) cron — `sentinel-blogger`,
`multi-source-intel`, `detection-engine`, `enterprise-intel-quality`, `bughunter-resilient`,
`precognition-engine`, `arsenal`, `convergence`, `omnishield` — produce **28 trigger events per day**
against a single shared concurrency group that can only keep one run active and one run pending at a time
(see `WORKFLOW_CONCURRENCY_REVIEW.md` §2 for why a third arrival cancels the second). Plotting all 28
trigger times on one 24-hour UTC timeline surfaces four recurring collision clusters, the worst of which is
**severe and occurs every day without exception**:

| UTC window | Workflows triggering | Distinct workflows in window |
|---|---|---|
| **00:00–00:30** | `convergence` (00:00), `precognition-engine` (00:00), `sentinel-blogger` (00:00), `bughunter-resilient` (00:15), `omnishield` (00:15), `detection-engine` (00:30) | **6** |
| 08:00–08:15 | `precognition-engine` (08:00), `sentinel-blogger` (08:00), `bughunter-resilient` (08:15) | 3 |
| 12:00–12:30 | `convergence` (12:00), `omnishield` (12:15), `detection-engine` (12:30) | 3 |
| 16:00–16:15 | `precognition-engine` (16:00), `sentinel-blogger` (16:00), `bughunter-resilient` (16:15) | 3 |

Two additional soft clusters (`multi-source-intel` landing 30 minutes before `enterprise-intel-quality`,
six times a day, on every one of `multi-source-intel`'s six own daily slots) are lower-severity — a 2-workflow,
30-minute-apart pairing is exactly the case `cancel-in-progress: false` alone *does* protect against (the
first finishes or is still safely running; the second simply queues), **unless** a third arrival lands in
between, which is a realistic possibility during the 00:00 and 12:00 windows where `enterprise-intel-quality`
(02:15 / 14:15 / 18:15 / 22:15) does not directly overlap but sits close enough to the tail of a
longer-running member to matter in practice.

## 2. Why the 00:00 UTC window is the most severe

At `00:00`, three workflows fire in the same instant (`convergence`, `precognition-engine`,
`sentinel-blogger`). Per the concurrency group's documented behavior, at most two of these three can occupy
the group (one running, one pending) — **the third is cancelled outright at trigger time**, before it ever
runs. Then, 15 minutes later, two more arrivals (`bughunter-resilient`, `omnishield` — themselves
simultaneous with each other) compete for the single pending slot, and 15 minutes after that, a sixth
(`detection-engine`) arrives and can bump whatever is still sitting in the pending slot.

`sentinel-blogger.yml` is the platform's flagship pipeline (documented elsewhere as a 45–90 minute run with
a 90-minute hard job timeout). If it wins the "running" slot at 00:00, it is very plausibly still running
when `detection-engine` fires at 00:30 — meaning the entire 00:00–00:30 window's other four contenders
(`convergence`, `precognition-engine`, `bughunter-resilient`, `omnishield`) are competing for exactly one
pending slot, and only whichever one is still sitting in that slot when `sentinel-blogger` finally finishes
gets to run at all. **On a typical day, it is structurally likely that two or more of these six scheduled
runs never execute** — not delayed, not retried, simply cancelled and silently absent from that day's
run history, distinguishable from a "failure" only by deliberately checking job-level (not run-level)
conclusions, exactly as this program's Phase 0/2 work had to do to find this pattern in the first place.

This is consistent with, and now fully explains in general terms, the specific collision this program
directly observed and reported earlier today (`multi-source-intel`, `detection-engine`,
`enterprise-intel-quality` — two of three cancelled after near-simultaneous manual dispatch) and the
same-signature cancellations independently present in this repository's run history from August 4–5. Those
were not isolated incidents; they are instances of a standing, every-day, cron-driven pattern.

## 3. Weekly-cadence members — no additional collision found

Three `sentinel-data-writer` members run weekly, all on Monday, all at different times, all outside the
daily 00:00/08:00/12:00/16:00 clusters:

| Workflow | Schedule (UTC) |
|---|---|
| `weekly-threat-brief.yml` | `30 2 * * 1` — Monday 02:30 |
| `report-engine.yml` | `0 6 * * 1` — Monday 06:00 |
| `weekly-analyst-briefing.yml` | `0 8 * * 1` — Monday 08:00 |

`weekly-analyst-briefing` at Monday 08:00 **does** land exactly on the recurring 08:00 daily cluster
(`precognition-engine` + `sentinel-blogger`), making Monday's 08:00 window a 4-workflow collision instead of
the usual 3 — the single worst single moment in the week for this group. `report-engine` at Monday 06:00
does not land on the 06:15 `enterprise-intel-quality` slot closely enough to be a same-window concern (a
clean ~15-minute gap after `multi-source-intel`'s 05:45 run, `arsenal`'s independent 06:00, and before
`enterprise-intel-quality`'s 06:15 — three near-neighbors but each pairwise gap is ≥15 minutes, milder than
the 0–15 minute gaps driving §1's clusters).

## 4. Cron collisions checked and ruled out for non-`sentinel-data-writer` groups

Every other concurrency group identified in `WORKFLOW_CONCURRENCY_REVIEW.md` §4 is either single-workflow
or ref/input-scoped, so a cron collision within that group is definitionally impossible — two runs of the
*same* workflow on the *same* schedule cannot both be pending simultaneously in a way that surprises anyone;
that is the concurrency group functioning as designed. No cross-workflow cron collision exists outside the
`sentinel-data-writer` group documented above; this was confirmed by checking that no two *different*
YAML files share any group value outside that one string (see the concurrency review's full 42-group
enumeration).

## 5. What this review does not claim

This is a **static, cron-literal analysis** — it proves the *scheduling geometry* creates collision windows
every day, using only the committed `cron:` values as evidence, which is sufficient to establish the
pattern exists. It does not independently re-derive a full historical "how many runs were actually
cancelled in the last 30 days" count for every one of the 9 workflows — that would require pulling and
classifying 30 days of run history per workflow, which was scoped out of this pass in favor of covering all
55 workflows' static configuration first (see `WORKFLOW_INVENTORY.md`). The two directly-observed instances
cited in §2 (today, and August 4–5) corroborate that the predicted pattern does occur in practice, but a
precise frequency count is left as an explicitly-flagged gap rather than estimated.

## 6. Recommendation posture (holding for Phase 7)

No schedule changes are made in this document. Per this program's constraint against restructuring without
evidence, this review's role is to establish — with cron-literal, reproducible evidence — that the 00:00 and
Monday-08:00 UTC windows are the highest-value targets *if* staggering is later authorized in Phase 7. A
concrete, minimal staggering proposal (e.g., offsetting `convergence`, `bughunter-resilient`, or `omnishield`
by 20–40 minutes each, which would fully break up the 6-workflow 00:00 cluster into non-colliding pairs
without touching `sentinel-blogger`'s own schedule, its highest-criticality member) is deferred to Phase 7
so it can be evaluated alongside the alternative of widening the group's real concurrency slot behavior,
rather than decided inside a Phase 4 evidence-gathering document.
