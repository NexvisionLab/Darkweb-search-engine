"""Telegram ingest operations (2026-09-20): channel handle normalisation, the
starvation rule behind the health check, and the preview-page parser.
stdlib unittest, same invocation as the other crawler/tests modules:
    cd crawler && .venv/bin/python3 -m unittest tests.test_social_telegram_ops -v

Database- and network-free on purpose: pure functions and an inline HTML
fixture in the shape t.me/s/<channel> serves, so this never writes to
production rows or spends a request against Telegram."""
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

import social_maintenance
import social_telegram
import social_telegram_health as health

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

FIXTURE = """
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="somechan/41">
  <div class="tgme_widget_message_text">Leak posted #ransomware<br>see http://abc.onion/x</div>
  <a class="tgme_widget_message_date"><time datetime="2026-09-20T01:02:03+00:00"></time></a>
</div></div>
<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="somechan/42">
  <a class="tgme_widget_message_photo_wrap" style="background-image:url('https://cdn.example/p.jpg')"></a>
</div></div>
"""


class NormalizeHandleTest(unittest.TestCase):
    def test_accepts_the_common_ways_a_channel_is_written(self):
        for raw in ("@SomeChannel", "somechannel", "t.me/SomeChannel", "https://t.me/SomeChannel",
                    "https://t.me/s/SomeChannel", "  t.me/s/somechannel/ ", "https://t.me/somechannel/123"):
            self.assertEqual(social_maintenance.normalize_handle(raw), "somechannel", raw)

    def test_rejects_things_that_are_not_public_channel_handles(self):
        for raw in ("", "abc", "t.me/joinchat/AAAA", "https://t.me/+invite", "t.me/c/12345/6",
                    "1badstart", "has space", "x" * 40):
            self.assertIsNone(social_maintenance.normalize_handle(raw), raw)


class StarvationTest(unittest.TestCase):
    def test_never_stored_is_starved(self):
        self.assertTrue(health.is_starved(None, NOW, 3))

    def test_recent_store_is_healthy_and_old_store_is_starved(self):
        self.assertFalse(health.is_starved(NOW - timedelta(days=2), NOW, 3))
        self.assertTrue(health.is_starved(NOW - timedelta(days=4), NOW, 3))

    def row(self, handle, active, last_24h=0, last_stored=None, total=0):
        return (handle, "crawl", active, None, None, total, last_24h, last_stored)

    def test_evaluate_flags_no_channels_no_active_and_starvation(self):
        problems, _ = health.evaluate([], NOW, 3)
        self.assertIn("no Telegram channels are configured", problems)

        problems, _ = health.evaluate([self.row("a", False), self.row("b", False)], NOW, 3)
        self.assertTrue(any("no active channels" in p for p in problems))

        problems, summary = health.evaluate([self.row("a", True, 0, NOW - timedelta(days=9), 21)], NOW, 3)
        self.assertTrue(any("no Telegram post stored" in p for p in problems))
        self.assertIn("1 active", summary)

    def test_a_flowing_feed_has_no_problems(self):
        rows = [self.row("a", True, 12, NOW - timedelta(hours=1), 200), self.row("b", False)]
        problems, summary = health.evaluate(rows, NOW, 3)
        self.assertEqual(problems, [])
        self.assertIn("12 posts stored in the last 24h", summary)


class ParserFixtureTest(unittest.TestCase):
    def test_parses_a_text_post_and_currently_skips_a_media_only_post(self):
        posts = social_telegram.parse_channel_page("somechan", FIXTURE)
        self.assertEqual([p["external_id"] for p in posts], ["somechan/41"])
        post = posts[0]
        self.assertEqual(post["hashtags"], ["ransomware"])
        self.assertIn("\n", post["text"])  # <br> preserved as a line break
        self.assertEqual(post["url"], "https://t.me/somechan/41")
        self.assertEqual(post["posted_at"].year, 2026)


if __name__ == "__main__":
    unittest.main()
