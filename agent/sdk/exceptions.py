"""
agent/sdk/exceptions.py — CYBERDUDEBIVASH® Sentinel APEX
Shared exception types for the agent/sdk/ client tree
(cdb_python_sdk.py, cdb_enterprise_sdk.py, sentinel_apex_client.py).

Single source of truth so each client file doesn't redefine its own copy.
"""


class FeatureNotDeployedError(Exception):
    """
    Raised when a client method has no real, deployed backend endpoint to
    call — a roadmap/aspirational capability (e.g. the Vault encrypted-asset
    store, the Sovereign Cortex predictive stream, per-item exploit
    forecasting) rather than a wrong URL or a fixable path mismatch.

    This is deliberately distinct from an HTTP error: no request is made,
    because no request could succeed. Callers should treat it the same way
    as "not implemented," not as a transient network/auth failure.
    """

    def __init__(self, message: str, feature: str = "") -> None:
        super().__init__(message)
        self.feature = feature


__all__ = ["FeatureNotDeployedError"]
