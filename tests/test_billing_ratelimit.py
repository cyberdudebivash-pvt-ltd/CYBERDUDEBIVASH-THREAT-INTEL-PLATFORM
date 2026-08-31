"""
tests/test_billing_ratelimit.py

Verification for the 24h daily-quota rate limiter (workers/intel-gateway/
src/daily-quota.js) and the billing checkout router (.../billing-checkout.js).

Why this isn't 51 live HTTP calls against https://intel.cyberdudebivash.com:
this repository's own Python tests (tests/test_*.py) are static-analysis /
structural checks over committed files -- none of them make live network
calls, and there is no staging/local deployment of the Cloudflare Worker in
this environment (no miniflare/wrangler dev harness; see
workers/intel-gateway/src/__tests__/subscription-lifecycle.test.js's header
comment for why index.js itself can't even be imported under plain
`node --test`, let alone actually served). Hitting the real, live production
API 50+ times from an automated test would also burn real quota against a
system serving real customers, which is a worse outcome than not testing at
all. The actual enforcement logic (checkDailyQuota()) was therefore
extracted into its own dependency-free module specifically so it's
unit-testable -- workers/intel-gateway/src/__tests__/daily-quota.test.js
already covers the literal "51st call trips it" scenario against a fake
in-memory KV, and the exact 429 JSON schema this task asks for
(RATE_LIMIT_EXCEEDED / status / tier / message / upgrade_url /
direct_checkout.pro_usd+pro_inr). This file runs that real JS suite via
subprocess (not a re-implementation of the same assertions in Python) and
adds a few Python-side structural checks that index.js is actually wired to
call it, plus verification of the real (already-live, unmodified by this
work) Razorpay webhook -> key-provisioning pipeline.

There is no Stripe integration anywhere in this repository -- the real
dual-gateway split is Razorpay (India) + Gumroad (global), confirmed by
grepping the deployed worker for webhook handlers. This file verifies that
real pipeline, not a fabricated Stripe payload.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATEWAY_SRC = REPO_ROOT / "workers" / "intel-gateway" / "src"
INDEX_JS = GATEWAY_SRC / "index.js"


def _node_available() -> bool:
    return shutil.which("node") is not None


@unittest.skipUnless(_node_available(), "node is not on PATH in this environment")
class TestDailyQuotaJsSuite(unittest.TestCase):
    """
    Runs the real JS unit suite for checkDailyQuota()/buildQuotaExceededBody()
    and asserts it passes. That suite (not this file) is the actual proof of:
      - the 51st request from the same identity in a UTC day is blocked
        (call 1-50 allowed, call 51 allowed:false) -- FREE tier, 50/day
      - PRO/ENTERPRISE use the right matrix values (5,000 / 50,000 per day)
      - an anonymous caller is identified by a hashed IP, never a raw one
      - the 429 body matches the required schema, including
        direct_checkout.pro_usd / pro_inr with the exact URL shape
      - a RATE_LIMIT_KV outage fails open (never blocks a real customer on
        our own infra fault)
    """

    def _run_node_test(self, *test_files: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["node", "--test", *test_files],
            cwd=GATEWAY_SRC,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_daily_quota_suite_passes(self):
        result = self._run_node_test("__tests__/daily-quota.test.js")
        self.assertEqual(
            result.returncode, 0,
            f"daily-quota.test.js failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        pass_count = re.search(r"^# pass (\d+)$", result.stdout, re.M)
        self.assertIsNotNone(pass_count, result.stdout)
        self.assertGreaterEqual(int(pass_count.group(1)), 11, "expected at least the 11 core daily-quota assertions to run")
        self.assertIn("# fail 0", result.stdout, result.stdout)

    def test_billing_checkout_suite_passes(self):
        result = self._run_node_test("__tests__/billing-checkout.test.js")
        self.assertEqual(
            result.returncode, 0,
            f"billing-checkout.test.js failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("# fail 0", result.stdout, result.stdout)


class TestWorkerWiring(unittest.TestCase):
    """
    Structural checks that index.js (the deployed router) actually calls the
    new modules on the request path -- catches the class of bug where a
    module is written and tested but never imported/wired into production.
    """

    def setUp(self):
        self.source = INDEX_JS.read_text(encoding="utf-8")

    def test_daily_quota_module_is_imported(self):
        self.assertIn(
            "from './daily-quota.js'", self.source,
            "index.js must import checkDailyQuota/buildQuotaExceededBody from daily-quota.js",
        )

    def test_daily_quota_is_actually_invoked_in_the_request_path(self):
        self.assertIn("await checkDailyQuota(env, auth, ip)", self.source)

    def test_429_response_uses_the_shared_body_builder_not_a_second_inline_copy(self):
        # Guards against exactly the kind of drift this session found
        # elsewhere: two independent places constructing "the" 429 body
        # that can silently diverge. There must be exactly one call site.
        self.assertEqual(
            self.source.count("buildQuotaExceededBody(quota)"), 1,
            "buildQuotaExceededBody(quota) must be called from exactly one place in index.js",
        )

    def test_billing_checkout_route_is_registered(self):
        self.assertIn('path === "/api/billing/checkout"', self.source)
        self.assertIn("resolveCheckoutUrl(", self.source)

    def test_x_sentinel_key_header_alias_is_recognized(self):
        self.assertIn('request.headers.get("X-Sentinel-Key")', self.source)
        self.assertIn(
            "X-Sentinel-Key", self.source.split('"Access-Control-Allow-Headers"')[1][:200],
            "X-Sentinel-Key must also be CORS-allow-listed or browser callers can never send it",
        )

    def test_rate_limit_headers_are_stamped_on_the_final_response(self):
        self.assertIn("function withRateLimitHeaders(", self.source)
        self.assertIn("withRateLimitHeaders(response, quotaOut.headers)", self.source)


class TestRealPaymentPipelineUnmodified(unittest.TestCase):
    """
    This task also asked to verify that a signed payment webhook results in
    a provisioned API key at the correct tier quota. That pipeline already
    exists, live, in index.js (handleWebhookRazorpay -> provisionApiKey) and
    was deliberately NOT modified or duplicated by this work (a second,
    parallel checkout/webhook/provisioning path would violate this
    repository's own single-source-of-truth governance and risk real
    double-provisioning against a live Razorpay account). These checks
    confirm it is still intact exactly as found, not that this task built it.
    """

    def setUp(self):
        self.source = INDEX_JS.read_text(encoding="utf-8")

    def test_razorpay_webhook_route_exists(self):
        self.assertIn('path === "/api/webhooks/razorpay"', self.source)
        self.assertIn("handleWebhookRazorpay", self.source)

    def test_razorpay_webhook_verifies_an_hmac_sha256_signature(self):
        webhook_fn = re.search(
            r"async function handleWebhookRazorpay\([^)]*\)\s*\{.*?\n\}", self.source, re.S,
        )
        self.assertIsNotNone(webhook_fn, "handleWebhookRazorpay() not found")
        body = webhook_fn.group(0)
        self.assertIn("RAZORPAY_WEBHOOK_SECRET", body)
        # The signature check itself lives in a separate helper
        # (verifyRazorpayHmac) that handleWebhookRazorpay() calls -- assert
        # the call is present here, then verify that helper actually does
        # HMAC-SHA256 (not just that the two words appear somewhere in this
        # function's own body, which an inline comment could satisfy without
        # any real check existing).
        self.assertIn("verifyRazorpayHmac(rawBody, sig, secret)", body)

        helper_fn = re.search(
            r"async function verifyRazorpayHmac\([^)]*\)\s*\{.*?\n\}", self.source, re.S,
        )
        self.assertIsNotNone(helper_fn, "verifyRazorpayHmac() not found")
        helper_body = helper_fn.group(0)
        self.assertIn('name: "HMAC", hash: "SHA-256"', helper_body)
        self.assertIn("crypto.subtle.verify(", helper_body, "expected a constant-time verify, not a manual string compare")

    def test_provision_api_key_writes_a_real_tiered_key_record(self):
        # Confirms the real key shape (prefix_40hex, e.g. cdb_pro_<hex>) --
        # NOT literally "cdb_live_..." as an earlier draft of this task
        # assumed; that prefix does not exist anywhere in this codebase.
        fn = re.search(
            r"async function provisionApiKey\([^)]*\)\s*\{.*?\n\}", self.source, re.S,
        )
        self.assertIsNotNone(fn, "provisionApiKey() not found")
        body = fn.group(0)
        self.assertIn("API_KEYS_KV.put", body)
        self.assertRegex(body, r"cdb_(ent|mssp|free|pro)")
        self.assertIn("tier:", body)

    def test_no_stripe_integration_exists_anywhere(self):
        # Explicit negative check: the task brief assumed a Razorpay+Stripe
        # split. The real, live split is Razorpay+Gumroad -- confirmed here
        # so a future change can't silently reintroduce an unverified
        # "Stripe" path without this test failing first.
        #
        # Checks for functional Stripe usage (SDK import, API host, a secret
        # binding, a Stripe object construction), not the bare word "stripe"
        # -- this file's own header comment explains, in prose, that no
        # Stripe integration exists, which would otherwise trip a naive
        # substring check on itself.
        stripe_signals = re.compile(
            r"stripe\.com|STRIPE_SECRET_KEY|STRIPE_WEBHOOK_SECRET|"
            r"require\([\"']stripe[\"']\)|from [\"']stripe[\"']|new Stripe\(",
        )
        for path in GATEWAY_SRC.rglob("*.js"):
            if "__tests__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            match = stripe_signals.search(text)
            self.assertIsNone(
                match,
                f"unexpected functional Stripe reference in {path.relative_to(REPO_ROOT)}: "
                f"{match.group(0) if match else ''} -- this platform's real global gateway "
                "is Gumroad, not Stripe",
            )


class TestBillingCheckoutRedirectsToRealDestinations(unittest.TestCase):
    """
    billing-checkout.js must redirect to REAL, already-live checkout
    destinations, not invented ones -- verified against the same Gumroad
    links upgrade.html itself uses (v184.0, "verified live against the
    Gumroad v2 /products API").
    """

    def setUp(self):
        self.source = (GATEWAY_SRC / "billing-checkout.js").read_text(encoding="utf-8")
        self.upgrade_html = (REPO_ROOT / "upgrade.html").read_text(encoding="utf-8")

    def test_gumroad_links_match_the_real_ones_in_upgrade_html(self):
        gumroad_urls = re.findall(r"https://cyberdudebivash\.gumroad\.com/l/\w+", self.source)
        self.assertTrue(gumroad_urls, "no Gumroad URLs found in billing-checkout.js")
        for url in gumroad_urls:
            self.assertIn(
                url, self.upgrade_html,
                f"{url} does not appear in upgrade.html -- may not be a real, live product link",
            )

    def test_inr_path_reuses_the_existing_razorpay_flow_on_upgrade_html(self):
        self.assertIn("upgrade.html", self.source)
        # Must not construct its own Razorpay order/checkout call -- that
        # logic already exists once, in handleRazorpayCreateOrder (index.js).
        self.assertNotIn("razorpay.com", self.source.lower())


if __name__ == "__main__":
    unittest.main()
