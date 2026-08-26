# CYBERDUDEBIVASH SENTINEL APEX — Entitlement Migration Wave Plan (v185.6)

**Mission:** SENTINEL APEX v185.0 Phase 11 (P0 Authenticated Commercial
Certification, Expiry Cutover & Customer Access Release Gate). This is a
**plan document**, not a flip. Per the mission's own Phase 11 instruction
("For this PR: migrate only resources whose legacy/canonical decisions
have zero divergence under automated tests"), **zero resources move from
shadow to enforced in this pass.**

## 1. Why nothing is flipped this pass

Confirming zero divergence between a resource's legacy ad-hoc gate and its
canonical `resolveEntitlement()` decision requires one of:

1. Live shadow-mismatch telemetry from production (`shadowCheckEntitlement()`
   already logs every mismatch it sees) — reading that log requires
   production log/analytics access this session does not have, or
2. `ADMIN_SECRET`-gated live traffic against a controlled test identity to
   force every code path deliberately.

Mission Phase 0 of this same pass confirmed `ADMIN_SECRET_PRESENT=false`
(workflow run 32961266467, job "Phase 2 - Secret Presence Gate", value
never printed). Neither path is available. Flipping any resource from
shadow to enforced without that evidence would be exactly the "blind mass
flip" Phase 11 explicitly forbids — so this pass produces the wave
sequencing only, per the mission's own required Wave A/B/C structure.

## 2. Current state (unchanged this pass)

- 31 resources defined in `enforceTierGate()` (revenue-enforcement.js).
- 15 of ~46 identified paid resources wired to `resolveEntitlement()`
  (shadow mode).
- 1 resource (`cve_detail_full`) actually enforced.
- Drift guard: `scripts/entitlement_resource_drift_gate.py`, STAGE 4.065,
  non-blocking with `::error::` annotation, 0 drift as of this pass.

Full per-resource detail: `docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md`.

## 3. Wave plan (sequencing only — each wave is separate, future, bounded work)

### Wave A — highest commercial/compliance exposure, already partially wired

Resources whose current ad-hoc gates are simple tier checks (lowest
divergence risk once shadow data confirms it), and whose gaps carry the
most enterprise-contract exposure if wrong:

| Resource | Route(s) | Status entering Wave A |
|---|---|---|
| `stix_bundle` / `stix_export_full` | STIX/TAXII object export | Defined, unwired; two independent TAXII gates exist today (index.js's `taxii_access` vs. enterprise-endpoints.js's separate helper) — **reconciling those two gates is a Wave A prerequisite, not optional**, since wiring on top of two disagreeing gates would itself introduce the divergence Phase 11 says not to ship |
| TAXII discovery/root/collections | `/api/taxii/*` | Same reconciliation prerequisite as above |
| MISP export | `/api/misp/export` | **Blocked on a standing open question, not new to this pass**: `docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md` §3b flags that production may route this path through a *different* handler (`handleMISPExportExt` in api-extensions.js) than the one enterprise-endpoints.js defines — confirming which handler is actually live is a prerequisite, otherwise Wave A could wire the dead code path and leave the live one unenforced |
| `report_full` | `/api/reports/premium` | Already wired in shadow mode (v185.5) — Wave A's job for this one is only the shadow→enforced flip, no new wiring |
| SIEM (`siem`) | `/api/siem/splunk`, `/api/siem/sentinel`, `/api/siem/qradar` | Defined, unwired |
| Webhooks/alerts (`alerts`) | `/api/alerts/dispatch` and related | Defined, unwired |
| SLA (`sla_report`, `sla_incidents`, `sla_certificate`) | `/api/sla/*` | Already wired in shadow mode (PR #253) — flip-only, no new wiring |

### Wave B — high-traffic customer-facing paths, needs volume-safe rollout

Resources with materially higher request volume than Wave A, where a
shadow-mode false-positive burst would be more visible to customers and
needs a longer shadow-observation window before flipping:

| Resource | Route(s) |
|---|---|
| Premium feed (`intel_manifest_full` overlap TBD) | `/api/feed` full-tier paths |
| IOC arrays (`ioc_full`) | IOC list/detail endpoints |
| Search (scope-gated `applyTierGateV2`) | `/api/search` |
| Actor intel | `/api/actors` |
| Detection/export paths | `/api/export/csv`, `/api/intel/correlate`, `/api/predict` |
| Graph/relations | `/api/v1/intel/graph`, `/api/v1/intel/relations` |
| Campaign/anomaly intel | `/api/v1/campaigns/intel`, `/api/v1/anomalies` |

### Wave C — remaining / architecture-blocked resources

Resources that need a design decision before wiring is even meaningful,
not just a shadow-observation window:

| Resource | Route(s) | Why it's Wave C |
|---|---|---|
| Enterprise scoring/stream | `/api/scoring/*`, `/api/stream` | No matching `enforceTierGate` resource case exists yet — needs new policy entries added first, which is itself the kind of change that must not be done blind |
| MSSP tenant feed | `/api/mssp/tenants/{id}/feed` | Tenant-identity verification (this mission's Phase 7) is a prerequisite to wiring, not a parallel track — enforcing entitlement on top of an already-mislabeled tenant-scoping claim would compound rather than fix the truth-in-product-behavior gap documented in `docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md` §5 |
| CVEs (`read:cves` scope) | `/api/cves` | Already scope-gated by a different mechanism (`applyTierGateV2`/scopes) — needs a decision on whether `resolveEntitlement()` replaces or layers with the existing scope system, not a straight wire-up |

## 4. What Phase 11 actually produces this pass

- This wave sequencing document (supersedes no prior document; extends
  `docs/ENTITLEMENT_RESOURCE_INVENTORY_V185.md` §4's backlog with explicit
  wave grouping and the reconciliation/architecture prerequisites each wave
  surfaced).
- No `ENTITLEMENT_ENFORCEMENT_RESOURCES` change in `wrangler.toml`.
- No new `resolveEntitlement()` call sites added.
- `entitlement_coverage_pct` remains 33% (15/46), 1/31 enforced — unchanged
  from the PR #254 baseline, honestly reported as unchanged rather than
  incremented without evidence.

## 5. Exit criteria to begin Wave A for real (next pass with ADMIN_SECRET)

1. `ADMIN_SECRET` present and the authenticated certification workflow
   run green (Mission Phase 0/1 of whichever pass attempts this).
2. Shadow-mismatch log for each Wave A resource reviewed for a minimum
   observation window; 0 unexplained mismatches before flipping.
3. STIX/TAXII dual-gate reconciliation and the MISP live-handler
   confirmation resolved first (see Wave A table above) — flipping on top
   of an unresolved dual-gate or dead-handler ambiguity is explicitly out
   of scope for "zero divergence."
4. Each flip ships as its own bounded PR, not a batch — consistent with
   how SLA (PR #253) and `report_full` (PR #254) were each individually
   wired and shadow-verified before this pass.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 11 deliverable*
