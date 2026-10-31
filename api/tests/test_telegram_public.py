"""Public Telegram view for the Free tier (2026-09-20). stdlib unittest, run
from the repo root with the API's own venv and the platform .env sourced:
    api/.venv/bin/python3 -m unittest api.tests.test_telegram_public -v

The database tests insert channels and posts inside a transaction that is
ALWAYS rolled back - nothing is ever committed, so this cannot leave test rows
in production tables or publish anything. Handles are made up (pytestqzx...),
and every query is scoped to them, so real published channels (if any exist
when this runs) cannot affect the assertions."""
import unittest

from fastapi.testclient import TestClient

from api import db, telegram_public
from api.main import app

PUB = "pytestqzxpub"
PRIV = "pytestqzxpriv"


class SnippetTest(unittest.TestCase):
    def test_links_are_reduced_to_their_host(self):
        out = telegram_public.make_snippet("Data: https://files.example.com/dl/secret.zip?token=abc123 and http://x.org/a")
        self.assertIn("[link: files.example.com]", out)
        self.assertIn("[link: x.org]", out)
        self.assertNotIn("secret.zip", out)
        self.assertNotIn("token", out)

    def test_onion_addresses_and_magnet_links_are_neutralised(self):
        onion = "a" * 56
        out = telegram_public.make_snippet(f"mirror {onion}.onion/leaks/file1 and magnet:?xt=urn:btih:ABCDEF&dn=x")
        self.assertIn(f"[link: {onion}.onion]", out)
        self.assertIn("[magnet link]", out)
        self.assertNotIn("leaks/file1", out)
        self.assertNotIn("btih", out)

    def test_an_onion_url_is_defanged_once_not_nested(self):
        onion = "b" * 56
        out = telegram_public.make_snippet(f"VISIT OUR SITE -- http://{onion}.onion/x/y (if scripts are blocked it will not load)")
        self.assertEqual(out, f"VISIT OUR SITE -- [link: {onion}.onion] (if scripts are blocked it will not load)")
        self.assertNotIn("[link: [link", out)

    def test_sentence_punctuation_after_a_link_is_kept_outside_it(self):
        self.assertEqual(telegram_public.make_snippet("see (https://example.com/a/b)."), "see ([link: example.com]).")
        self.assertEqual(telegram_public.make_snippet("go to https://example.com/x, then stop"), "go to [link: example.com], then stop")

    def test_pii_is_masked(self):
        out = telegram_public.make_snippet("contact jane.doe@example.com or +1 415 555 0134")
        self.assertNotIn("jane.doe@example.com", out)
        self.assertNotIn("415 555 0134", out)

    def test_short_text_is_untouched_apart_from_whitespace(self):
        self.assertEqual(telegram_public.make_snippet("Company  Release:\n\nAcme"), "Company Release: Acme")

    def test_long_text_is_capped_on_a_word_boundary_with_an_ellipsis(self):
        out = telegram_public.make_snippet("lorem " * 200)
        self.assertLessEqual(len(out), telegram_public.SNIPPET_CHARS + 1)
        self.assertTrue(out.endswith("…"))
        self.assertNotIn("lore…", out)

    def test_empty_and_none(self):
        self.assertEqual(telegram_public.make_snippet(""), "")
        self.assertEqual(telegram_public.make_snippet(None), "")

    def test_handle_validation(self):
        for good in ("snatch_news", "Snatch", "abcd"):
            self.assertTrue(telegram_public.is_valid_handle(good), good)
        for bad in ("", None, "ab", "1abc", "has space", "a/b", "x" * 40, "t.me/x"):
            self.assertFalse(telegram_public.is_valid_handle(bad), bad)


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.get_connection()
        self.conn.autocommit = False
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO social_telegram_channels (handle, origin, public) VALUES (%s, 'operator', true)", (PUB,))
            cur.execute("INSERT INTO social_telegram_channels (handle, origin, public) VALUES (%s, 'operator', false)", (PRIV,))

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def post(self, source, n, text, age_days=0, expired=False, url=True):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO social_posts (platform, source, external_id, text, url, posted_at, expires_at) "
                "VALUES ('telegram', %s, %s, %s, %s, now() - make_interval(days => %s), "
                "now() + make_interval(days => %s)) RETURNING id",
                (source, f"{source}/{n}", text, f"https://t.me/{source}/{n}" if url else "javascript:alert(1)",
                 age_days, -1 if expired else 30),
            )
            return cur.fetchone()[0]

    def test_translation_is_returned_beside_the_original_redacted_and_searchable(self):
        pid = self.post(PUB, 91, "Безпілотники провели рейд на область")
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE social_posts SET lang = 'uk', text_en = %s, translation_engine = 'qwen', translated_at = now() WHERE id = %s",
                ("Drones raided the region. Data: https://files.example.com/x.zip mail leak@example.com", pid),
            )
        self.post(PUB, 92, "An English post about nothing much")
        posts, total = telegram_public.public_posts(self.conn, channel=PUB)
        by_url = {p["url"]: p for p in posts}
        uk = by_url[f"https://t.me/{PUB}/91"]
        self.assertEqual(uk["lang"], "uk")
        self.assertIn("Drones raided the region", uk["translation"])
        self.assertIn("[link: files.example.com]", uk["translation"])
        self.assertNotIn("x.zip", uk["translation"])
        self.assertNotIn("leak@example.com", uk["translation"])
        self.assertIn("Безпілотники", uk["snippet"])                       # the original is still there
        en = by_url[f"https://t.me/{PUB}/92"]
        self.assertEqual((en["lang"], en["translation"]), (None, None))
        found, _ = telegram_public.public_posts(self.conn, channel=PUB, q="drones")
        self.assertEqual([p["url"] for p in found], [f"https://t.me/{PUB}/91"])   # English search finds the Ukrainian post

    def test_a_post_marked_english_never_shows_a_translation(self):
        pid = self.post(PUB, 93, "plain english text here")
        with self.conn.cursor() as cur:
            cur.execute("UPDATE social_posts SET lang = 'en', text_en = 'should not appear' WHERE id = %s", (pid,))
        posts, _ = telegram_public.public_posts(self.conn, channel=PUB)
        self.assertIsNone(posts[0]["translation"])

    def test_only_published_in_window_unexpired_posts_are_returned(self):
        self.post(PUB, 1, "fresh post")
        self.post(PUB, 2, "eight days old", age_days=8)
        self.post(PUB, 3, "expired", expired=True)
        self.post(PRIV, 4, "private channel post")
        posts, total = telegram_public.public_posts(self.conn, channel=PUB)
        self.assertEqual(total, 1)
        self.assertEqual([p["snippet"] for p in posts], ["fresh post"])
        self.assertEqual(telegram_public.public_posts(self.conn, channel=PRIV), ([], 0))

    def test_a_dormant_channel_shows_its_latest_three_posts_flagged_older(self):
        for n, age in enumerate((40, 20, 15, 12, 10), start=1):
            self.post(PUB, n, f"old post age {age}", age_days=age)
        posts, total = telegram_public.public_posts(self.conn, channel=PUB)
        self.assertEqual(total, 3)
        self.assertEqual([p["snippet"] for p in posts], ["old post age 10", "old post age 12", "old post age 15"])
        self.assertTrue(all(p["older"] for p in posts))

    def test_no_fallback_once_the_channel_has_a_recent_post(self):
        self.post(PUB, 1, "recent", age_days=1)
        self.post(PUB, 2, "old but would be fallback", age_days=20)
        posts, total = telegram_public.public_posts(self.conn, channel=PUB)
        self.assertEqual(total, 1)
        self.assertFalse(posts[0]["older"])

    def test_fallback_never_shows_expired_posts(self):
        self.post(PUB, 1, "expired", age_days=30, expired=True)
        self.post(PUB, 2, "old but live", age_days=30)
        posts, _ = telegram_public.public_posts(self.conn, channel=PUB)
        self.assertEqual([p["snippet"] for p in posts], ["old but live"])

    def test_search_matches_only_the_visible_excerpt_not_the_rest_of_the_post(self):
        filler = "lorem ipsum dolor sit amet " * 20                      # ~540 chars, well past the 300-char excerpt
        self.post(PUB, 95, f"qzx9early {filler} qzx9late")
        pid = self.post(PUB, 96, "Ukrainian text here")
        with self.conn.cursor() as cur:
            cur.execute("UPDATE social_posts SET lang = 'uk', text_en = %s WHERE id = %s", (f"qzx9tr {filler} qzx9trlate", pid))
        early, _ = telegram_public.public_posts(self.conn, channel=PUB, q="qzx9early")
        late, _ = telegram_public.public_posts(self.conn, channel=PUB, q="qzx9late")
        tr_early, _ = telegram_public.public_posts(self.conn, channel=PUB, q="qzx9tr")
        tr_late, _ = telegram_public.public_posts(self.conn, channel=PUB, q="qzx9trlate")
        self.assertEqual(len(early), 1)          # in the excerpt: found
        self.assertEqual(len(late), 0)           # only past the excerpt: not found
        self.assertEqual(len(tr_early), 1)
        self.assertEqual(len(tr_late), 0)

    def test_search_works_within_the_visible_set_and_never_widens_it(self):
        for n, age in enumerate((40, 30, 20, 15), start=1):
            self.post(PUB, n, f"qzx7needle old {age}", age_days=age)
        posts, total = telegram_public.public_posts(self.conn, channel=PUB, q="qzx7needle")
        self.assertEqual(total, 3)  # only the latest 3 are visible, so the oldest can never match

    def test_newest_first_and_paging(self):
        for n, age in enumerate((3, 1, 2), start=1):
            self.post(PUB, n, f"post age {age}", age_days=age)
        posts, total = telegram_public.public_posts(self.conn, channel=PUB, limit=2)
        self.assertEqual(total, 3)
        self.assertEqual([p["snippet"] for p in posts], ["post age 1", "post age 2"])
        page2, _ = telegram_public.public_posts(self.conn, channel=PUB, limit=2, offset=2)
        self.assertEqual([p["snippet"] for p in page2], ["post age 3"])

    def test_search_finds_a_term_inside_a_link_or_handle_but_not_inside_a_longer_word(self):
        hit_link = self.post(PUB, 1, "Release https://qzx7snatch.press/news.php?id=1")
        hit_handle = self.post(PUB, 2, "see t.me/qzx7snatch_news")
        self.post(PUB, 3, "they qzx7snatched it")
        posts, total = telegram_public.public_posts(self.conn, channel=PUB, q="qzx7snatch")
        self.assertEqual(total, 2)
        self.assertEqual(len(posts), 2)

    def test_url_field_is_only_ever_a_tme_message_link(self):
        self.post(PUB, 1, "safe link post")
        self.post(PUB, 2, "unsafe stored url", url=False)
        posts, _ = telegram_public.public_posts(self.conn, channel=PUB)
        by_text = {p["snippet"]: p["url"] for p in posts}
        self.assertEqual(by_text["safe link post"], f"https://t.me/{PUB}/1")
        self.assertIsNone(by_text["unsafe stored url"])

    def test_snippets_never_contain_the_raw_link(self):
        self.post(PUB, 1, "leak: https://files.example.com/dl/all.zip?k=1")
        posts, _ = telegram_public.public_posts(self.conn, channel=PUB)
        self.assertEqual(posts[0]["snippet"], "leak: [link: files.example.com]")

    def test_channel_list_shows_only_published_channels_with_window_counts(self):
        self.post(PUB, 1, "a")
        self.post(PUB, 2, "b", age_days=9)
        self.post(PRIV, 3, "c")
        channels = {c["channel"]: c for c in telegram_public.public_channels(self.conn)}
        self.assertIn(PUB, channels)
        self.assertNotIn(PRIV, channels)
        self.assertEqual(channels[PUB]["posts_in_window"], 1)
        self.assertEqual(channels[PUB]["visible_posts"], 1)
        self.assertFalse(channels[PUB]["showing_older"])

    def test_channel_list_reports_a_dormant_channel_as_showing_older(self):
        for n, age in enumerate((20, 25, 30, 35), start=1):
            self.post(PUB, n, f"dormant {age}", age_days=age)
        channel = {c["channel"]: c for c in telegram_public.public_channels(self.conn)}[PUB]
        self.assertEqual(channel["posts_in_window"], 0)
        self.assertTrue(channel["showing_older"])
        self.assertEqual(channel["visible_posts"], 3)


class EndpointValidationTest(unittest.TestCase):
    """Only inputs rejected before any database access, so no rows are read or written."""

    def setUp(self):
        self.client = TestClient(app)

    def test_bad_channel_handle_is_rejected(self):
        self.assertEqual(self.client.get("/telegram/posts", params={"channel": "bad handle!"}).status_code, 400)

    def test_too_short_query_and_oversized_paging_are_rejected(self):
        self.assertEqual(self.client.get("/telegram/posts", params={"q": "ab"}).status_code, 422)
        self.assertEqual(self.client.get("/telegram/posts", params={"limit": 500}).status_code, 422)
        self.assertEqual(self.client.get("/telegram/posts", params={"offset": 100000}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
