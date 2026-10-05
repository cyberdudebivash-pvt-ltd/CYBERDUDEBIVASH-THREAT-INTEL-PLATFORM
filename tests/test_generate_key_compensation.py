"""Live key issuance must compensate when local recording fails."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

spec = importlib.util.spec_from_file_location(
    "key_compensation", Path(__file__).resolve().parents[1] / "agent/tools/generate_key.py")
keys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keys)

class KeyCompensationTests(unittest.TestCase):
    def generate(self):
        return keys.generate_key("PRO", "buyer@example.com", "TEST-REF", 30)

    def test_success_does_not_revoke_or_persist_plaintext(self):
        secret = "SYNTHETIC-KEY"
        with patch.object(keys, "live_provision_key", return_value={"key": secret}), \
             patch.object(keys, "load_json", return_value={"keys": {}}), \
             patch.object(keys, "save_json") as save, \
             patch.object(keys, "_append_audit"), \
             patch.object(keys, "live_revoke_key") as revoke:
            result = self.generate()
        self.assertEqual(result["key"], secret)
        self.assertNotIn(secret, repr(save.call_args))
        revoke.assert_not_called()

    def test_each_local_failure_revokes_before_returning_error(self):
        for operation in ("days_from_now", "load_json", "save_json", "_append_audit"):
            with self.subTest(operation=operation), \
                 patch.object(keys, "live_provision_key", return_value={"key": "SYNTHETIC-KEY"}), \
                 patch.object(keys, "load_json", return_value={"keys": {}}), \
                 patch.object(keys, "save_json"), \
                 patch.object(keys, "_append_audit"), \
                 patch.object(keys, operation, side_effect=OSError("SYNTHETIC-KEY")), \
                 patch.object(keys, "live_revoke_key") as revoke:
                with self.assertRaisesRegex(keys.LiveProvisionError, "live credential was revoked") as caught:
                    self.generate()
                self.assertNotIn("SYNTHETIC-KEY", str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)
                revoke.assert_called_once_with("SYNTHETIC-KEY")

    def test_compensation_failure_is_critical_and_secret_safe(self):
        with patch.object(keys, "live_provision_key", return_value={"key": "SYNTHETIC-KEY"}), \
             patch.object(keys, "load_json", side_effect=OSError("SYNTHETIC-KEY")), \
             patch.object(keys, "live_revoke_key", side_effect=RuntimeError("SYNTHETIC-KEY")) as revoke:
            with self.assertRaisesRegex(keys.LiveProvisionError, "CRITICAL") as caught:
                self.generate()
            self.assertNotIn("SYNTHETIC-KEY", str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)
            revoke.assert_called_once()

    def test_keys_do_not_prove_realized_revenue(self):
        with patch.object(keys, "load_json", return_value={"keys": {
                "test": {"status": "active", "tier": "PRO",
                         "expires_at": "2099-01-01T00:00:00+00:00"}}}):
            summary = keys.revenue_summary()
        self.assertIsNone(summary["mrr_inr"])
        self.assertIsNone(summary["arr_equivalent_inr"])
        self.assertEqual(summary["estimated_monthly_catalog_value_inr"], 4100)
        self.assertEqual(summary["estimated_annual_catalog_value_inr"], 49200)

    def test_authority_failure_does_not_attempt_local_commit(self):
        with patch.object(keys, "live_provision_key", side_effect=keys.LiveProvisionError("unavailable")), \
             patch.object(keys, "load_json") as load, \
             patch.object(keys, "live_revoke_key") as revoke:
            with self.assertRaises(keys.LiveProvisionError):
                self.generate()
            load.assert_not_called()
            revoke.assert_not_called()

if __name__ == "__main__":
    unittest.main()

