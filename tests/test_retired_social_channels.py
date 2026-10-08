"""Regression contracts for retired promotional distribution channels.

Run: python -m unittest discover -s tests -p 'test_retired_social_channels.py'
These checks are source-level guards, not evidence of a live deployment.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def source(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


class RetiredSocialChannelsTests(unittest.TestCase):
    def test_syndication_does_not_register_retired_publishers(self):
        code = source("syndicate/syndicate/main.py")
        for channel in ("twitter", "tumblr"):
            self.assertNotIn("PLATFORM_MODULES['" + channel + "']", code)
            self.assertNotIn("syndicate.platforms." + channel + " import", code)
        self.assertIn("PLATFORM_MODULES['linkedin']", code)

    def test_workflow_does_not_inject_retired_credentials(self):
        workflow = source(".github/workflows/syndicate.yml")
        for prefix in ("TWITTER_", "TUMBLR_"):
            self.assertNotIn("secrets." + prefix, workflow)
        self.assertIn("secrets.LINKEDIN_ACCESS_TOKEN", workflow)

    def test_config_excludes_retired_credentials(self):
        config = source("syndicate/syndicate/config.py")
        self.assertNotIn("TWITTER_API_KEY", config)
        self.assertNotIn("TUMBLR_CONSUMER_KEY", config)

    def test_amplifier_rejects_retired_channels(self):
        code = source("scripts/social_amplifier.py")
        self.assertIn('retired = {"twitter", "x", "tumblr"}', code)
        self.assertIn('parser.error("Twitter/X and Tumblr are retired distribution destinations")', code)
        self.assertIn('default="linkedin,telegram,mastodon"', code)
        self.assertNotIn('"twitter":   generate_twitter', code)

    def test_formatter_fails_closed_for_retired_destinations(self):
        code = source("syndicate/syndicate/formatter.py")
        self.assertIn("raise ValueError('Retired distribution destination: ' + platform)", code)
        self.assertNotIn("'twitter': 280", code)
        self.assertNotIn("'tumblr': 4096", code)

    def test_broadcast_does_not_fabricate_provider_success(self):
        code = source("scripts/broadcast_apex_syndication.py")
        self.assertNotIn("Successfully broadcasted", code)
        self.assertIn("No provider dispatch configured", code)

    def test_footer_does_not_advertise_retired_x(self):
        code = source("components/footer.html")
        self.assertNotIn('href="https://twitter.com/"', code)
        self.assertIn("https://www.linkedin.com/company/cyberdudebivash/", code)


if __name__ == "__main__":
    unittest.main()
