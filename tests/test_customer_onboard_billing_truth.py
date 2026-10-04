"""Manual onboarding must not invent renewal mandates or captured amounts."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

with patch.dict(sys.modules, {"generate_key": types.ModuleType("generate_key")}):
    spec = importlib.util.spec_from_file_location(
        "onboarding_truth", Path(__file__).resolve().parents[1] / "scripts/customer_onboard.py")
    onboarding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(onboarding)

class ManualBillingTruthTests(unittest.TestCase):
    def subscription(self, payment_ref):
        with patch.object(onboarding, "load_json", return_value={"subscriptions": []}), \
             patch.object(onboarding, "save_json"):
            return onboarding.register_subscription(
                "SUB-TEST", "C-TEST", "buyer@example.com", "PRO", 30,
                "TEST-REF", payment_ref, "a" * 16)

    def test_reference_does_not_prove_renewal_or_payment(self):
        record = self.subscription("OPERATOR-REFERENCE")
        self.assertIs(record["auto_renew"], False)
        self.assertEqual(record["payment_verification"], "operator_reference_unverified")

    def test_no_reference_has_no_payment_claim(self):
        self.assertEqual(self.subscription("")["payment_verification"], "not_applicable")

    def test_subscription_metadata_does_not_invent_revenue(self):
        with patch.object(onboarding, "load_json", return_value={"subscriptions": []}), patch.object(onboarding, "save_json") as save:
            onboarding.register_subscription("SUB-TEST", "C-TEST", "buyer@example.com", "PRO", 30, "TEST-REF", "OPERATOR-REF", "a" * 16)
        meta = save.call_args.args[1]["_meta"]
        self.assertIsNone(meta["mrr_inr"])
        self.assertIsNone(meta["arr_equivalent_inr"])
        self.assertEqual(meta["estimated_monthly_catalog_value_inr"], 4100)

    def test_customer_metadata_does_not_invent_revenue(self):
        with patch.object(onboarding, "load_json", return_value={"customers": []}), patch.object(onboarding, "save_json") as save:
            onboarding.register_customer("C-TEST", "Test", "buyer@example.com", "Test", "IN", "PRO", "TEST-REF", "a" * 16)
        meta = save.call_args.args[1]["_meta"]
        self.assertIsNone(meta["mrr_inr"])
        self.assertIsNone(meta["arr_inr"])

    def test_plan_price_is_not_captured_revenue(self):
        with patch.object(onboarding, "append_jsonl") as append:
            onboarding.write_payment_audit(
                "CUSTOMER_ONBOARDED", "C-TEST", "buyer@example.com",
                "PRO", "TEST-REF", "OPERATOR-REFERENCE", 4100, "IN")
        record = append.call_args.args[1]
        self.assertIsNone(record["amount_inr"])
        self.assertEqual(record["amount_status"], "not_verified")
        self.assertEqual(record["listed_plan_price_inr"], 4100)

if __name__ == "__main__":
    unittest.main()

