# SENTINEL APEX v185 — Subscription Expiry Production Cutover

## Scope

This change enables `SUBSCRIPTION_EXPIRY_ENABLED=true` in both the default Worker vars and `[env.production.vars]`.

No entitlement-resource expansion is included in this PR. `ENTITLEMENT_ENFORCEMENT_RESOURCES` remains `cve_detail_full`.

## Verified prerequisite

PR #256 completed live authenticated customer-operations certification, including a real expiry-boundary test against production: a controlled Enterprise key was accepted before its real `expires_at` boundary and denied afterward.

## Deployment gate

Before merge:

- existing regression and governance checks must pass;
- no unrelated Worker/source changes are permitted.

After merge/deploy:

- rerun `SENTINEL APEX -- Commercial Customer Operations Certification`;
- require authenticated customer-ops, lifecycle-state matrix, expiry-boundary validation, MSSP isolation, and rate-limit jobs to remain green;
- verify active keys remain allowed according to tier;
- verify expired, refunded, suspended, cancelled-as-effective, revoked, and rotated-old credentials remain denied as designed.

## Rollback

Emergency rollback is configuration-only: set `SUBSCRIPTION_EXPIRY_ENABLED=false` in both default and production vars and redeploy. No destructive schema rollback is required.

## Release posture

This cutover does not by itself authorize worldwide release. Entitlement migration to 100% of customer-reachable paid routes and final end-to-end customer journeys remain separate release gates.
