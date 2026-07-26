#!/usr/bin/env python3
"""
subscription_manager.py - CYBERDUDEBIVASH(R) SENTINEL APEX v44.0
TENANT LIFECYCLE MANAGEMENT
Founder & CEO - CyberDudeBivash Pvt. Ltd.
"""

import json
import secrets
from datetime import datetime, timedelta
from agent.license_validator import LICENSE_VALIDATOR


def _generate_key(tier: str) -> str:
    """RB-17: 256-bit CSPRNG-based key. Single source of truth for the key
    format -- provision_tenant() and rotate_tenant() both call this, so a
    future format change only happens in one place."""
    return f"CDB-{tier.upper()}-{secrets.token_urlsafe(32)}"


class CDBSubscriptionManager:
    def provision_tenant(self, name: str, tier: str = "pro") -> str:
        """Provisions a new high-value tenant and returns an API Key.

        RB-17: key is a 256-bit token from `secrets` (a CSPRNG), not the
        prior tier+minute-timestamp scheme -- that format was both guessable
        (small search space for a known approximate signup time) and prone
        to silent same-minute collisions between two provisioning calls for
        the same tier (identical key -> the second call overwrote the
        first's registry entry). Neither issue is possible with a random
        256-bit value.
        """
        new_key = _generate_key(tier)
        expiry = (datetime.now() + timedelta(days=30)).isoformat()

        tenant_entry = {
            "tier": tier,
            "status": "active",
            "expires": expiry,
            "owner": name,
            "created_at": datetime.now().isoformat()
        }

        with open(LICENSE_VALIDATOR.tenant_store, "r+") as f:
            data = json.load(f)
            data[new_key] = tenant_entry
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()

        return new_key

    def revoke_tenant(self, api_key: str, reason: str = "") -> dict:
        """RB-16: revokes a tenant's credential.

        Idempotent -- revoking an already-revoked or unknown key returns a
        clear, non-exceptional result rather than raising. Historical
        metadata (owner, tier, created_at) is preserved; the entry is
        marked revoked, never deleted, so there's a record of what existed
        even after revocation.
        """
        try:
            with open(LICENSE_VALIDATOR.tenant_store, "r+") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as exc:
                    return {"ok": False, "status": "error", "detail": f"tenant store unreadable: {exc}"}

                if api_key not in data:
                    return {"ok": False, "status": "not_found", "detail": "no tenant with that credential"}

                entry = data[api_key]
                if entry.get("status") == "revoked":
                    return {"ok": True, "status": "already_revoked", "detail": "no change -- already revoked"}

                entry["status"] = "revoked"
                entry["revoked_at"] = datetime.now().isoformat()
                entry["revoked_reason"] = reason or "manual revocation"
                data[api_key] = entry

                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
        except OSError as exc:
            return {"ok": False, "status": "error", "detail": f"tenant store unavailable: {exc}"}

        return {"ok": True, "status": "revoked", "detail": "credential revoked"}

    def rotate_tenant(self, old_key: str) -> dict:
        """RB-16: rotates a tenant's credential.

        Issues a new RB-17-generated key preserving the tenant's owner and
        tier, and revokes the old key in the same operation so there is
        never a window with two simultaneously active credentials for the
        same tenant. The new key is returned exactly once, in the result --
        it is not retrievable afterward (same guarantee as provision_tenant).
        """
        try:
            with open(LICENSE_VALIDATOR.tenant_store, "r+") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as exc:
                    return {"ok": False, "status": "error", "detail": f"tenant store unreadable: {exc}"}

                if old_key not in data:
                    return {"ok": False, "status": "not_found", "detail": "no tenant with that credential"}

                old_entry = data[old_key]
                if old_entry.get("status") == "revoked":
                    return {"ok": False, "status": "already_revoked", "detail": "cannot rotate a revoked credential"}

                tier = old_entry.get("tier", "pro")
                owner = old_entry.get("owner")

                new_key = _generate_key(tier)
                while new_key in data:
                    new_key = _generate_key(tier)

                data[new_key] = {
                    "tier": tier,
                    "status": "active",
                    "expires": (datetime.now() + timedelta(days=30)).isoformat(),
                    "owner": owner,
                    "created_at": datetime.now().isoformat(),
                    "rotated_from": old_key,
                }

                old_entry["status"] = "revoked"
                old_entry["revoked_at"] = datetime.now().isoformat()
                old_entry["revoked_reason"] = "rotated"
                data[old_key] = old_entry

                f.seek(0)
                json.dump(data, f, indent=4)
                f.truncate()
        except OSError as exc:
            return {"ok": False, "status": "error", "detail": f"tenant store unavailable: {exc}"}

        return {"ok": True, "status": "rotated", "new_key": new_key}


# Global instance
SUBSCRIPTION_CORE = CDBSubscriptionManager()
