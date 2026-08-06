# Project TITAN — Architecture Acceptance Record

**Status:** Reopened once, Stage 16 (2026-08-06). Originally closed Stage 11.5 with three of
three dispositions recorded, all **Accepted**. A fourth ADR — ADR-0010 — was added and Accepted
in this same executive session at Stage 16, when Relationship Framework implementation was
authorized; see the Stage 16 Addendum at the end of this record rather than assuming the
original three-ADR scope below still describes this file's full contents. All four dispositions
are, by direct executive architecture authority (cyberdudebivash, confirmed in session).
This was an executive-authority acceptance, not a completed multi-party review: the
individually-named sign-offs in each ADR's own "Approval" section were not independently
obtained, and each ADR now says so explicitly rather than implying otherwise. This record exists
so that authority has one place to act, and so every later stage can verify disposition by
reading a file instead of assuming — that verification now reads Accepted, on this basis, for
all four.

**Program:** Project TITAN, Stage 11.5 (Executive Architecture Acceptance), reopened Stage 16
**Created:** 2026-08-06, in response to an executive architecture decision to insert a
governance milestone between Stage 11 (merged) and Stage 12 (not yet authorized).
**Original scope:** ADR-0008, ADR-0011, ADR-0012 — the three ADRs `TITAN_TECH_DEBT_REGISTER.md`'s
DEBT-021 identifies as blocking Stage 12 (Enterprise Evidence Service Platform).
**Stage 16 addition:** ADR-0010 (Relationship Graph Ownership) — see the addendum at the end of
this file. Not part of DEBT-021's original three; added when Stage 16 needed a disposition on
record before implementing the Relationship Framework.

---

## How to use this record

1. Read the linked ADR in full, especially its "Approval" section (required sign-offs) and any
   Revision history (prior blockers and how they were resolved, if any).
2. Record a disposition below: **Accepted**, **Accepted with Conditions**, **Requires Revision**,
   or **Rejected**. If conditions are attached, list them — they become the actual gate, not just
   a note.
3. Sign with name/role and date in the row provided.
4. Once all three ADRs this record tracks show **Accepted** (or **Accepted with Conditions** with
   conditions since satisfied), update `docs/adr/README.md`'s index Status column to match, and
   Stage 12's authorization gate (`TITAN_STAGE11_5_EXECUTIVE_ARCHITECTURE_ACCEPTANCE.md` §5)
   clears.

This engineering session's role in the three entries below is limited to **summarizing each ADR
faithfully and offering an engineering recommendation** — not deciding. The recommendation is
input to the actual Decider's judgment, not a substitute for it.

---

## Summary

| ADR | Subject | Current Status | Disposition | Decided By | Date |
|---|---|---|---|---|---|
| [0008](docs/adr/0008-canonical-evidence-framework.md) | Canonical Evidence Framework | **Accepted** | **Accepted** | cyberdudebivash (executive authority) | 2026-08-06 |
| [0011](docs/adr/0011-evidence-lifecycle-ownership.md) | Evidence Lifecycle Ownership | **Accepted** | **Accepted** | cyberdudebivash (executive authority) | 2026-08-06 |
| [0012](docs/adr/0012-api-versioning-interface-governance.md) | API Versioning & Interface Governance | **Accepted** | **Accepted*** | cyberdudebivash (executive authority) | 2026-08-06 |
| [0010](docs/adr/0010-relationship-graph-ownership.md) | Relationship Graph Ownership | **Accepted** | **Accepted**† | cyberdudebivash (executive authority) | 2026-08-06 (Stage 16) |

\* Engineering recommendation below was Accepted *with Conditions* (Blog/Vercel confirmation).
Executive disposition is unconditional Accepted — recorded as decided, not as recommended; see
ADR-0012's section below for both, side by side.

† Added Stage 16, not part of the original Stage 11.5 scope — see the Stage 16 Addendum.

---

## ADR-0008 — Canonical Evidence Framework

**Decides:** Which system is the canonical Evidence record schema and system of record (E1,
`p20-handlers.js`'s Evidence Chain, becomes canonical over the alternatives the ADR surveys).

**Where it stands:** Revision 2 (Stage 8) resolved the one blocker Revision 1 raised — direct
HTTP verification confirmed E9–E12 are not deployed (Vercel `NOT_FOUND`, same evidence as AR-000),
so they were reclassified from "blocking open question" to "excluded, zero production
consumers." The ADR's own text: *"This ADR's Decision stands as originally written and is ready
for human Acceptance review."*

**Required sign-offs (per the ADR's own Approval section):**
- [ ] Platform Governance Lead
- [ ] Chief Threat Intelligence Architect / P-layer stack owner (P20, P18, P32 owner)
- [ ] Blog/EIOS engineering owner (acknowledgment only, not a blocking approval)

**Downstream evidence available to this decision:** Stage 10 and Stage 11 built and shipped
(inert, zero-blast-radius, merged into `main`) a full entity/schema/serialization/validation/
repository/lifecycle/versioning/indexing implementation against this ADR's Evidence entity shape
— 153/153 tests passing, zero regressions across two stages. That is not a substitute for
Acceptance, but it is real evidence the schema is implementable as specified, not just
theoretically sound.

**Engineering recommendation:** No open technical blocker was found in this review. The
Revision-1 concern was closed with direct verification evidence, not assumption. Recommend
**Accepted**, or **Accepted with Conditions** if reviewers want the E9–E12 exclusion re-verified
independently before signing rather than relying on Stage 8's verification alone.

**Disposition:** **ACCEPTED**
☑ Accepted&nbsp;&nbsp;☐ Accepted with Conditions&nbsp;&nbsp;☐ Requires Revision&nbsp;&nbsp;☐ Rejected
Conditions (if any): None attached by the deciding authority
Decided by / date: cyberdudebivash, executive architecture authority — 2026-08-06, direct session confirmation ("yes all three accepted... confirmed, production approved")

---

## ADR-0011 — Evidence Lifecycle Ownership

**Decides:** The canonical evidence lifecycle state model (a 9-state derived model, built and
tested in Stage 11's `lifecycle.js`, composing rather than replacing P30's existing signals).

**Where it stands:** No open blocker recorded in the ADR itself. Its "Future Considerations"
section notes two explicitly-deferred, non-blocking extension questions (an assertable-state
model if read-only derivation proves insufficient later; revisiting "physical storage lifecycle"
scoping once a real Evidence Registry exists) — both are forward-looking notes, not conditions
on Accepting the model as specified.

**Required sign-offs (per the ADR's own Approval section):**
- [ ] Platform Governance Lead
- [ ] Chief Threat Intelligence Architect / P30 owner

**Downstream evidence available to this decision:** Stage 11's `lifecycle.js` implements this
ADR's state model directly (9 states, validated transitions, audit trail) with a dedicated test
suite (`lifecycle.test.js`) plus a governance check (`check_lifecycle_violations_detectable`)
verified to fire on invalid transitions. Zero deviation found between the ADR's specified model
and the shipped implementation during this review.

**Engineering recommendation:** No open technical blocker found. Recommend **Accepted**.

**Disposition:** **ACCEPTED**
☑ Accepted&nbsp;&nbsp;☐ Accepted with Conditions&nbsp;&nbsp;☐ Requires Revision&nbsp;&nbsp;☐ Rejected
Conditions (if any): None attached by the deciding authority
Decided by / date: cyberdudebivash, executive architecture authority — 2026-08-06, direct session confirmation ("yes all three accepted... confirmed, production approved")

---

## ADR-0012 — API Versioning & Interface Governance

**Decides:** A cross-surface API versioning policy spanning three independently-versioned
delivery patterns found across **two repositories**: intel-platform's Cloudflare Worker
(`/api/v1/*`, ~150+ routes), the blog's Vercel deployment (a separate, coincidentally-named
`/api/v1/*`), and the blog's static checksummed manifest bundles.

**Where it stands:** Drafted Stage 7 (PR #110) specifically to close the gap Stage 6's
`TITAN_IMPLEMENTATION_READINESS.md` flagged (API versioning was one of Stage 5's original six
required ADRs and had no owner through Stage 6). No open blocker recorded in the ADR beyond
Acceptance itself.

**Required sign-offs (per the ADR's own Approval section) — note this is the only one of the
three naming a cross-repository Decider:**
- [ ] Platform Governance Lead
- [ ] Chief Threat Intelligence Architect
- [ ] Principal API Gateway Architect
- [ ] Blog/Vercel Engineering

**Why this one may take longer than 0008/0011:** it is the only ADR in this record whose scope
crosses both repositories and both engineering surfaces this program touches. `docs/adr/0012`'s
own Context section notes that `lib/api/*` (the archived, zero-consumer TypeScript RC1 tree —
ADR-0013's subject) is the only place either repository ever wrote a *formal* versioning policy
down, and that policy has never been tested against a real breaking change. Recommend the Blog/
Vercel sign-off not be treated as a formality — it is a genuinely separate team's API surface.

**Engineering recommendation:** No technical blocker found in the ADR text itself, but this is
the one of the three where I'd weight the cross-team sign-off most heavily rather than assume
alignment. Recommend **Accepted with Conditions** — condition: explicit confirmation from
Blog/Vercel Engineering that the policy as written is workable against their existing `api/v1/*`
manifest and webhook surface, since that surface wasn't built with this ADR in view.

**Executive disposition (overrides the conditional recommendation above):** **ACCEPTED**,
unconditionally, by direct executive authority. The Blog/Vercel confirmation this session
recommended as a condition was not independently obtained before this disposition was recorded —
stated plainly, not silently dropped. If that surface later proves incompatible with this ADR's
policy, reopen per this ADR's own Revision pattern; this is a real residual risk carried forward
by choice, not by oversight.

**Disposition:** **ACCEPTED**
☑ Accepted&nbsp;&nbsp;☐ Accepted with Conditions&nbsp;&nbsp;☐ Requires Revision&nbsp;&nbsp;☐ Rejected
Conditions (if any): None attached by the deciding authority (engineering had recommended one — see above)
Decided by / date: cyberdudebivash, executive architecture authority — 2026-08-06, direct session confirmation ("yes all three accepted... confirmed, production approved")

---

## What happens after all three are disposed

- **All Accepted (or Accepted-with-Conditions, conditions met):** update the Summary table and
  `docs/adr/README.md`'s index Status column for all three to `Accepted`. Stage 12's
  authorization gate (`TITAN_STAGE11_5_EXECUTIVE_ARCHITECTURE_ACCEPTANCE.md` §5) clears on that
  evidence alone — no separate sign-off ceremony beyond keeping this file accurate.
- **Any Requires Revision:** the revising author reopens the ADR (new Revision section, per the
  pattern ADR-0008 Revision 2 already established), not a new ADR number.
- **Any Rejected:** document why in this file's per-ADR section (append, don't delete — this
  file follows the same Deprecation Instead of Deletion / document-don't-silently-resolve
  discipline as `TITAN_TECH_DEBT_REGISTER.md`), and record what, if anything, replaces the
  rejected decision.

This record is itself subject to that same discipline: update it in place as dispositions land,
keep prior recommendation text intact even if a Decider disagrees with it — the disagreement is
useful signal, not noise to delete.

---

## Stage 16 Addendum — ADR-0010 (Relationship Graph Ownership)

Added 2026-08-06, outside this record's original Stage 11.5 scope. Project TITAN Stage 16
("Enterprise Relationship Framework Activation") required a governance-verified disposition on
ADR-0010 before implementation could proceed. The pre-implementation gate found ADR-0010
Proposed, not Accepted (see `TITAN_STAGE16_GOVERNANCE_REPORT.md` for that verification, performed
against both the local repository and the live GitHub API). The executive authority who owns
this record's disposition process was then asked directly and accepted it in-session.

**Decides:** Canonical entity-relationship graph ownership. R1 (`p31-handlers.js`'s `_buildGraph`
/ `buildP31RelationshipBlock` / `handleP31Relationships`) is target-canonical, per the ADR's
original Decision (unchanged since Revision 4).

**Where it stood:** Revision 4 left one prerequisite open for engineering scoping, not decided
by any prior stage: Decision item 2's persistence-layer requirement, and specifically whether it
should be satisfied by adopting R6 (`core/intelligence/enrichment_graph.py`, cross-language,
DEBT-000B) or by building persistence natively into R1's own consumption boundary.

**What resolved it:** ADR-0010's own Revision 5 (added this session) makes the scoping call:
native persistence, not R6 adoption — see that revision for the full reasoning. This was an
engineering scoping decision made in service of the executive's acceptance, using one of the two
paths DEBT-000B's own entry already named as valid; it is not a new architectural direction
invented for this occasion.

**Downstream evidence available to this decision:** None yet at acceptance time — unlike
ADR-0008/0011 (which had Stage 10/11's shipped, tested implementation as evidence before
Acceptance), ADR-0010's Acceptance here precedes its implementation. Stage 16's own completion
report (`TITAN_STAGE16_RELATIONSHIP_FRAMEWORK_REPORT.md`) is the evidence trail for whether the
accepted design held up in practice — read that alongside this disposition, not in place of it.

**Required sign-offs (per the ADR's own Approval section):** Platform Governance Lead, Chief
Threat Intelligence Architect / P31 owner, Blog/EIOS engineering owner. Not independently
obtained — see ADR-0010's own Approval section for the per-row disposition (the Blog/EIOS row
specifically remains deferred, not accepted-by-proxy, since R2/`knowledge_graph.py` is untouched
by this session's work).

**Disposition:** **ACCEPTED**
☑ Accepted&nbsp;&nbsp;☐ Accepted with Conditions&nbsp;&nbsp;☐ Requires Revision&nbsp;&nbsp;☐ Rejected
Conditions (if any): None attached by the deciding authority. Engineering note carried forward
(not a condition, a disclosure): R6-vs-native-persistence was an engineering scoping call made
to unblock this Acceptance, not independently reviewed by the P31-owning team beyond this
session.
Decided by / date: cyberdudebivash, executive architecture authority — 2026-08-06, direct
session authorization ("Yes accepted ADR-0010 right now go ahead build real Relationship
Framework").
