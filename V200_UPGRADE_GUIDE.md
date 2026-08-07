# Upgrade Guide — v200

**Project TITAN Stage 22 Phase 8**

## For API/platform customers: no action required

v200 is a certification milestone, not a breaking release (`V200_RELEASE_NOTES.md`). No API route,
response shape, or authentication mechanism changes as part of this document. Existing API keys,
JWTs, and integrations continue to work unchanged. ADR-0012's compatibility rules (additive changes
only, without a `v2` path prefix) remain in effect and were not violated by anything in Stage 22.

## For customers relying on the dashboard

`UI_FREEZE_POLICY.md` freezes `dashboard/enterprise_dashboard.html` — the dashboard reachable from
the live site today — as the v200 baseline. If you have bookmarked or embedded links to
`enterprise-cyber-intelligence-os.html` (ECIOS), be aware that page is real and functional but is
not part of the frozen, linked navigation; see `UI_FREEZE_POLICY.md` §1 for the full picture and
watch for a future ADR if the platform consolidates onto it.

## For platform operators upgrading toward an actual v200.0.0 tag

Before treating a future `v200.0.0` tag as deployable, verify the conditions in
`V200_RELEASE_GATE.md` are satisfied — this guide does not repeat that gate's contents, it points to
it as the authoritative pre-upgrade checklist. At minimum, before tagging:

1. Resolve or explicitly accept (with sign-off) the pricing-table duplication in
   `workers/revenue-engine/src/index.js` (`COMMERCIAL_READINESS.md` §1) — customers should not see
   two different PRO prices depending on which code path they hit.
2. Decide on `SUBSCRIPTION_EXPIRY_ENABLED` (`COMMERCIAL_READINESS.md` §6) — enabling it changes
   behavior for newly-provisioned keys going forward (existing keys are unaffected, since the
   change only touches new provisioning); this is exactly the kind of behavior change that needs a
   deliberate decision, not a silent default flip.
3. Either correct or replace `docs/BCP_DISASTER_RECOVERY.md` (`OPERATIONAL_READINESS.md` §1) before
   this document, or its RTO/RPO claims, are shown to any customer, auditor, or regulator.
4. Review the dependency vulnerability list (`SECURITY_CERTIFICATION.md` §1) and either patch or
   explicitly risk-accept the 4 critical findings.

## Rollback

If a future v200.0.0 deploy needs to be rolled back, use the existing, real rollback tooling
documented in `V200_OPERATIONS_RUNBOOK.md` (`enterprise-rollback-governance.yml` +
`scripts/rollback_authority.py`) — no new rollback mechanism was introduced by this certification
work, and none is needed since no runtime code changed.

## Migration path for the confidence-framework gap

Not a v200-blocking migration, but the platform's most significant tracked debt
(`COMMERCIAL_QUALITY_CERTIFICATION_REPORT.md` §3.4): ADR-0007 needs to move from Proposed to
Accepted, and the 116 files computing confidence independently need to be reconciled to the
resulting canonical implementation. This is a multi-stage effort in its own right, tracked here as
a forward pointer, not attempted within Stage 22's scope.
