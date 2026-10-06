"""Credential handoff regression controls; no live API calls."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "customer_onboard.py"
fake = types.ModuleType("generate_key")
with patch.dict(sys.modules, {"generate_key": fake}):
    spec = importlib.util.spec_from_file_location("onboarding_handoff", SOURCE)
    onboarding = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(onboarding)

class CredentialHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = str(Path(self.tmp.name) / "packages")
        self.scope = patch.object(onboarding, "WELCOME_PKG_DIR", self.directory)
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def test_private_artifact(self):
        path = onboarding.save_welcome_package("C-1234ABCD", "synthetic credential")
        self.assertEqual(Path(path).name, "C-1234ABCD.txt")
        self.assertEqual(Path(path).read_text(), "synthetic credential")
        if os.name == "posix":
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(self.directory).st_mode & 0o777, 0o700)

    def test_invalid_ids_cannot_escape(self):
        for identity in ("../outside", "C-1234ABCD/../escape", "C-1234abcd", ""):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                onboarding.save_welcome_package(identity, "secret")
        self.assertFalse(Path(self.directory).exists())

    def test_existing_artifact_is_never_overwritten(self):
        path = onboarding.save_welcome_package("C-1234ABCD", "original")
        with self.assertRaises(FileExistsError):
            onboarding.save_welcome_package("C-1234ABCD", "replacement")
        self.assertEqual(Path(path).read_text(), "original")

    @unittest.skipUnless(os.name == "posix", "POSIX symlink behavior")
    def test_directory_symlink_refused(self):
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        os.symlink(target, self.directory)
        with self.assertRaises(ValueError):
            onboarding.save_welcome_package("C-1234ABCD", "secret")
        self.assertEqual(list(target.iterdir()), [])

    @unittest.skipUnless(os.name == "posix", "POSIX symlink behavior")
    def test_file_symlink_refused(self):
        Path(self.directory).mkdir()
        target = Path(self.tmp.name) / "outside"
        target.write_text("original")
        os.symlink(target, Path(self.directory) / "C-1234ABCD.txt")
        with self.assertRaises(FileExistsError):
            onboarding.save_welcome_package("C-1234ABCD", "secret")
        self.assertEqual(target.read_text(), "original")

    def test_provision_does_not_print_credential(self):
        secret = "SYNTHETIC-CREDENTIAL-DO-NOT-PRINT"
        key = {"key": secret, "key_hash": "a" * 64}
        args = types.SimpleNamespace(tier="free", country="US", ref="TEST-REF",
            payment_ref="", days=30, email="../outside@example.com",
            name="Test", company="Test")
        stream = io.StringIO()
        with patch.object(onboarding, "find_existing_customer", return_value=None), \
             patch.object(fake, "generate_key", return_value=key, create=True), \
             patch.object(onboarding, "register_customer", return_value={}), \
             patch.object(onboarding, "register_subscription", return_value={}), \
             patch.object(onboarding, "write_payment_audit"), \
             patch.object(onboarding, "generate_welcome_package", return_value=secret), \
             patch.object(onboarding, "gen_customer_id", return_value="C-1234ABCD"), \
             contextlib.redirect_stdout(stream):
            onboarding.cmd_provision(args)
        self.assertNotIn(secret, stream.getvalue())
        self.assertEqual((Path(self.directory) / "C-1234ABCD.txt").read_text(), secret)

if __name__ == "__main__":
    unittest.main()
