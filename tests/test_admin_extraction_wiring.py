"""
tests/test_admin_extraction_wiring.py

Structural verification that index.js is actually wired to the two modules
extracted this pass (admin-cache-bust.js, feed-lookup.js) -- catches the
class of bug where a module is written and unit-tested but never imported
or called from production.

Why structural (text) checks rather than importing index.js from Python:
index.js is a Cloudflare Worker (JS), not Python -- its own logic is
verified by the real JS unit suites
(workers/intel-gateway/src/__tests__/admin-cache-bust.test.js and
find-item-by-slug.test.js, both run via `node --test`). This file only
confirms index.js's routing actually reaches those modules, and that the
one behavior that can't be observed from either extracted module alone --
"the new cache-bust route only matches its own two exact paths, so every
other /api/admin/* path is unaffected" -- holds by construction: the
routing condition is a simple, directly-inspectable `if`, not logic that
needs its own KV-backed test harness.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_JS = REPO_ROOT / "workers" / "intel-gateway" / "src" / "index.js"


class TestAdminCacheBustWiring(unittest.TestCase):
    def setUp(self):
        self.source = INDEX_JS.read_text(encoding="utf-8")

    def test_admin_cache_bust_module_is_imported(self):
        self.assertIn("from './admin-cache-bust.js'", self.source)

    def test_handle_admin_calls_the_extracted_function_for_exactly_its_two_paths(self):
        match = re.search(
            r'if \(path === "/api/admin/cache/bust" \|\| path === "/api/admin/cache/bust-prefix"\) \{\s*'
            r"return await handleAdminCacheBust\(request, env, ctx, path, method, \{ timingSafeEqual, auditLog, jsonResp \}\);",
            self.source,
        )
        self.assertIsNotNone(
            match,
            "handleAdmin must route exactly these two exact-match paths to handleAdminCacheBust(), "
            "unchanged from the extracted module's real call signature",
        )

    def test_only_one_call_site_invokes_the_extracted_cache_bust_handler(self):
        # Guards the "does not affect pre-existing ADMIN_SECRET-gated
        # routes" property by construction: if this ever became a broader
        # match (e.g. a prefix check) or gained a second call site, that
        # boundary could silently break without any test noticing.
        self.assertEqual(self.source.count("handleAdminCacheBust("), 1)

    def test_feed_lookup_module_is_imported_and_reexported(self):
        self.assertIn("from './feed-lookup.js'", self.source)
        self.assertIn("export { findItemBySlug }", self.source)

    def test_index_js_no_longer_carries_a_duplicate_find_item_by_slug(self):
        # Single source of truth: exactly one definition (in feed-lookup.js,
        # imported here), not a second copy left behind in index.js.
        self.assertEqual(self.source.count("function findItemBySlug"), 0)
        self.assertEqual(self.source.count("async function r2Get("), 0)


if __name__ == "__main__":
    unittest.main()
