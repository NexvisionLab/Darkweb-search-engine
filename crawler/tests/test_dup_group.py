"""The dup_group fingerprint, the index fields Clone clusters reads, and the backfill that fills them on older pages.
    cd crawler && python3 -m unittest tests.test_dup_group -v
Offline: a fake OpenSearch client."""
import datetime
import sys
import unittest
from unittest import mock

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
from darkweb_crawler import search
import backfill_cluster_fields

WORDS = "the quick brown fox jumps over the lazy dog while nobody is watching the river flow past the old mill " * 4


class DupGroupTests(unittest.TestCase):
    def test_same_opening_text_gives_the_same_value_whatever_the_case_punctuation_or_spacing(self):
        a = search.dup_group(WORDS)
        self.assertEqual(len(a), 16)
        self.assertEqual(a, search.dup_group(WORDS.upper().replace(" ", "  ,  ")))

    def test_short_pages_have_no_fingerprint(self):
        self.assertIsNone(search.dup_group("a short page"))
        self.assertIsNone(search.dup_group(None))
        self.assertIsNone(search.dup_group(""))

    def test_only_the_opening_words_count(self):
        opening = " ".join(f"w{i}" for i in range(search.DUP_WORDS))
        self.assertEqual(search.dup_group(opening), search.dup_group(opening + " a different ending entirely"))
        self.assertNotEqual(search.dup_group(opening), search.dup_group("x " + opening))

    def test_different_text_gives_a_different_value(self):
        self.assertNotEqual(search.dup_group(WORDS), search.dup_group(WORDS + " " + WORDS.replace("fox", "cat")))
        self.assertNotEqual(search.dup_group(WORDS), search.dup_group(WORDS.replace("fox", "cat")))


class IndexPageTests(unittest.TestCase):
    def doc(self, **kwargs):
        client = mock.Mock()
        search.index_page(client, 1, "http://a.onion/", "a.onion", "t", kwargs.pop("body_text", WORDS), **kwargs)
        return client.index.call_args.kwargs["body"]

    def test_the_cluster_fields_are_written(self):
        when = datetime.datetime(2026, 10, 7, tzinfo=datetime.timezone.utc)
        d = self.doc(safety_rating="fraud-risk", crawled_at=when)
        self.assertEqual(d["dup_group"], search.dup_group(WORDS))
        self.assertEqual((d["safety_rating"], d["crawled_at"]), ("fraud-risk", when.isoformat()))

    def test_crawled_at_defaults_to_now_and_empty_fields_are_left_out(self):
        d = self.doc(body_text="short")
        self.assertNotIn("dup_group", d)
        self.assertNotIn("safety_rating", d)
        self.assertTrue(d["crawled_at"])

    def test_an_existing_index_gets_the_new_mappings(self):
        client = mock.Mock()
        client.indices.exists.return_value = True
        search.ensure_index(client)
        client.indices.create.assert_not_called()
        props = client.indices.put_mapping.call_args.kwargs["body"]["properties"]
        self.assertEqual(props, {"dup_group": {"type": "keyword"}, "safety_rating": {"type": "keyword"}})

    def test_a_new_index_is_created_with_them(self):
        client = mock.Mock()
        client.indices.exists.return_value = False
        search.ensure_index(client)
        client.indices.put_mapping.assert_not_called()
        props = client.indices.create.call_args.kwargs["body"]["mappings"]["properties"]
        self.assertEqual((props["dup_group"], props["safety_rating"]), ({"type": "keyword"}, {"type": "keyword"}))


class BackfillPlanTests(unittest.TestCase):
    WHEN = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)

    def plan(self, source):
        return backfill_cluster_fields.plan_update(source, {"a.onion": "fraud-risk"}, {"http://a.onion/": self.WHEN})

    def test_it_fills_only_what_is_missing(self):
        full = self.plan({"url": "http://a.onion/", "domain": "a.onion", "body_text": WORDS})
        self.assertEqual(full, {"dup_group": search.dup_group(WORDS), "safety_rating": "fraud-risk", "crawled_at": self.WHEN.isoformat()})
        partly = self.plan({"url": "http://a.onion/", "domain": "a.onion", "body_text": WORDS, "dup_group": "keep",
                            "crawled_at": "2026-10-01T00:00:00+00:00"})
        self.assertEqual(partly, {"safety_rating": "fraud-risk"})

    def test_nothing_to_add_is_an_empty_update(self):
        self.assertEqual(self.plan({"url": "http://a.onion/", "domain": "a.onion", "body_text": WORDS, "dup_group": "x",
                                    "safety_rating": "y", "crawled_at": "z"}), {})

    def test_unknown_hosts_and_short_pages_add_nothing(self):
        self.assertEqual(self.plan({"url": "http://zz.onion/", "domain": "zz.onion", "body_text": "short"}), {})


if __name__ == "__main__":
    unittest.main()
