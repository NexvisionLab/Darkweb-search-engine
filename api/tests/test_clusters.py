"""Clone clusters: the list, the clone: search operator, and that looking at one cluster lists every copy.
    python3 -m unittest api.tests.test_clusters -v
Offline: a fake OpenSearch client and a fake database."""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from api import clusters, search
from api import main as api_main
from api.main import app

http = TestClient(app)
GROUP = "0123456789abcdef"


def bucket(key, pages, hosts, title="Welcome", ratings=None, cats=None, last="2026-10-07T00:00:00.000Z"):
    return {"key": key, "doc_count": pages, "hosts": {"value": hosts},
            "latest": {"value": 1.7e12, "value_as_string": last},
            "categories": {"buckets": cats or [{"key": "fraud", "doc_count": pages}]},
            "ratings": {"buckets": ratings or [{"key": "unrated", "doc_count": pages}]},
            "sample": {"hits": {"hits": [{"_source": {"title": title, "language": "en"}}]}}}


def answer(*buckets):
    return {"aggregations": {"clusters": {"buckets": list(buckets)}}}


class BodyTests(unittest.TestCase):
    def test_the_aggregation_counts_hosts_and_filters_to_pages_with_a_fingerprint(self):
        b = clusters.build_body(min_hosts=5, suppressed_hosts=("b.onion", "a.onion"))
        self.assertIn({"exists": {"field": "dup_group"}}, b["query"]["bool"]["filter"])
        self.assertEqual(b["query"]["bool"]["must_not"], [{"terms": {"domain": ["a.onion", "b.onion"]}}])
        agg = b["aggs"]["clusters"]
        self.assertEqual(agg["terms"]["field"], "dup_group")
        self.assertEqual(agg["terms"]["min_doc_count"], 2)
        self.assertEqual(agg["aggs"]["enough_hosts"]["bucket_selector"]["script"], "params.h >= 5")
        self.assertEqual(agg["aggs"]["hosts"]["cardinality"]["field"], "domain")

    def test_the_window_is_always_the_clusters_on_the_most_sites(self):
        # ordering the aggregation by pages or recency would cut the window before the min_hosts filter ran
        for sort in clusters.SORTS:
            self.assertEqual(clusters.build_body(sort=sort)["aggs"]["clusters"]["terms"]["order"], {"hosts": "desc"})

    def test_bounds(self):
        for bad in ({"sort": "random"}, {"min_hosts": 1}, {"min_hosts": 1001}):
            with self.assertRaises(ValueError):
                clusters.build_body(**bad)
        self.assertEqual(clusters.build_body(size=99999)["aggs"]["clusters"]["terms"]["size"], clusters.MAX_BUCKETS)

    def test_a_category_narrows_it(self):
        self.assertIn({"term": {"content_category": "fraud"}}, clusters.build_body(category="fraud")["query"]["bool"]["filter"])

    def test_no_suppressed_hosts_means_no_clause(self):
        self.assertNotIn("must_not", clusters.build_body()["query"]["bool"])


class ShapeTests(unittest.TestCase):
    def test_a_bucket_becomes_a_cluster_without_any_host_address(self):
        items, total = clusters.shape(answer(bucket("abc", 358, 352, "Parked page contact bob@example.com",
                                                    ratings=[{"key": "illicit-marketplace", "doc_count": 300}, {"key": "unrated", "doc_count": 58}])),
                                      lambda t: t.replace("bob@example.com", "b**@example.com"))
        self.assertEqual(total, 1)
        c = items[0]
        self.assertEqual((c["id"], c["pages"], c["hosts"]), ("abc", 358, 352))
        self.assertEqual(c["title"], "Parked page contact b**@example.com")
        self.assertEqual(c["safety"], {"Suspicious": 300, "Unrated": 58})
        self.assertEqual(c["last_crawled"], "2026-10-07T00:00:00.000Z")
        self.assertNotIn("onion", json.dumps(c))

    def test_paging_inside_the_window_and_missing_sample(self):
        a = answer(*[bucket(f"k{i}", 10 - i, 5) for i in range(5)])
        items, total = clusters.shape(a, lambda t: t, limit=2, offset=1)
        self.assertEqual((total, [c["id"] for c in items]), (5, ["k1", "k2"]))
        b = bucket("z", 2, 2)
        b["sample"] = {"hits": {"hits": []}}
        self.assertEqual(clusters.shape(answer(b), lambda t: t)[0][0]["title"], "(no title)")

    def test_an_empty_answer_is_an_empty_list(self):
        self.assertEqual(clusters.shape({}, lambda t: t), ([], 0))

    def test_the_sort_is_applied_inside_the_window(self):
        a = answer(bucket("wide", 40, 30, last="2026-09-05T00:00:00.000Z"),
                   bucket("deep", 90, 8, last="2026-09-20T00:00:00.000Z"),
                   bucket("fresh", 12, 4, last="2026-10-20T00:00:00.000Z"))
        ids = lambda sort: [c["id"] for c in clusters.shape(a, lambda t: t, sort=sort)[0]]
        self.assertEqual(ids("hosts"), ["wide", "deep", "fresh"])
        self.assertEqual(ids("pages"), ["deep", "wide", "fresh"])
        self.assertEqual(ids("recent"), ["fresh", "deep", "wide"])


class EndpointTests(unittest.TestCase):
    def setUp(self):
        api_main._CLUSTER_CACHE.clear()
        self.client = mock.Mock()
        self.client.search.return_value = answer(bucket("aa", 30, 20, last="2026-09-01T00:00:00.000Z"),
                                                 bucket("bb", 12, 6, last="2026-10-09T00:00:00.000Z"),
                                                 bucket("cc", 4, 3))
        patches = [mock.patch("api.main.ratelimit.check_rate_limit", return_value=True),
                   mock.patch("api.main.search.get_client", return_value=self.client),
                   mock.patch("api.main.db.get_connection", return_value=mock.Mock()),
                   mock.patch("api.main.db.get_suppressed_hosts", return_value=["hidden.onion"])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(api_main._CLUSTER_CACHE.clear)

    def get(self, **params):
        return http.get("/clusters", params=params).json()

    def test_the_list_and_its_paging(self):
        d = self.get(limit=2)
        self.assertEqual((d["total"], d["count"], [c["id"] for c in d["clusters"]]), (3, 2, ["aa", "bb"]))
        self.assertEqual([c["id"] for c in self.get(limit=2, offset=2)["clusters"]], ["cc"])

    def test_changing_the_sort_re_sorts_the_cached_window_without_a_new_query(self):
        self.assertEqual([c["id"] for c in self.get(sort="hosts")["clusters"]], ["aa", "bb", "cc"])
        self.assertEqual([c["id"] for c in self.get(sort="recent")["clusters"]], ["bb", "cc", "aa"])      # crawled 10-09, 10-07, 09-01
        self.assertEqual(self.client.search.call_count, 1)

    def test_the_answer_is_cached_so_paging_does_not_query_again(self):
        self.get()
        self.get(offset=1)
        self.get(limit=5)
        self.assertEqual(self.client.search.call_count, 1)
        self.get(min_hosts=10)
        self.assertEqual(self.client.search.call_count, 2)

    def test_capped_says_when_the_window_is_full(self):
        self.assertFalse(self.get()["capped"])
        api_main._CLUSTER_CACHE.clear()
        self.client.search.return_value = answer(*[bucket(f"k{i}", 5, 5) for i in range(clusters.MAX_BUCKETS)])
        d = self.get(limit=10)
        self.assertEqual((d["total"], d["capped"]), (clusters.MAX_BUCKETS, True))

    def test_suppressed_hosts_are_excluded_in_the_query(self):
        self.get()
        body = self.client.search.call_args.kwargs["body"]
        self.assertEqual(body["query"]["bool"]["must_not"], [{"terms": {"domain": ["hidden.onion"]}}])

    def test_bad_input_is_refused(self):
        self.assertEqual(http.get("/clusters", params={"min_hosts": 1}).status_code, 422)
        self.assertEqual(http.get("/clusters", params={"sort": "random"}).status_code, 422)
        self.assertIn("error", self.get(category="nonsense"))
        self.assertIn("error", self.get(limit=100, offset=450))


class SplitCloneTests(unittest.TestCase):
    def test_the_code_is_taken_out_and_the_rest_is_kept(self):
        self.assertEqual(api_main._split_clone(f"clone:{GROUP.upper()}"), (GROUP, "", None))
        code, rest, err = api_main._split_clone(f"escrow clone:{GROUP} usa")
        self.assertEqual((code, err), (GROUP, None))
        self.assertEqual(rest.split(), ["escrow", "usa"])

    def test_plain_queries_are_left_alone(self):
        self.assertEqual(api_main._split_clone("escrow"), (None, "escrow", None))
        self.assertEqual(api_main._split_clone(None), (None, None, None))
        self.assertEqual(api_main._split_clone("myclone:" + GROUP), (None, "myclone:" + GROUP, None))

    def test_bad_codes_are_refused(self):
        for bad in ("clone:xyz", "clone:" + "g" * 16, "clone:" + "a" * 15, "clone:" + "a" * 17, "clone:"):
            code, rest, err = api_main._split_clone(bad)
            self.assertIsNone(code)
            self.assertIn("16-character", err)


class CloneSearchTests(unittest.TestCase):
    def setUp(self):
        self.search_pages = mock.Mock(return_value=([], 0))
        patches = [mock.patch("api.main.ratelimit.check_rate_limit", return_value=True),
                   mock.patch("api.main.search.get_client", return_value=mock.Mock()),
                   mock.patch("api.main.search.search_pages", self.search_pages),
                   mock.patch("api.main.db.get_connection", return_value=mock.Mock()),
                   mock.patch("api.main.db.get_suppressed_hosts", return_value=["hidden.onion"]),
                   mock.patch("api.main.db.get_domain_meta", return_value={})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def get(self, **params):
        return http.get("/search", params=params).json()

    def test_a_cluster_lists_every_copy_and_never_a_suppressed_host(self):
        d = self.get(q=f"clone:{GROUP}")
        self.assertNotIn("error", d)
        kwargs = self.search_pages.call_args.kwargs
        self.assertEqual((kwargs["dup_group"], kwargs["exclude_domains"], kwargs["merge_mirrors"]), (GROUP, ["hidden.onion"], False))
        self.assertEqual(self.search_pages.call_args.args[1], "")

    def test_words_next_to_the_operator_still_search(self):
        self.get(q=f"escrow clone:{GROUP}")
        self.assertEqual(self.search_pages.call_args.args[1].split(), ["escrow"])

    def test_an_ordinary_search_is_unchanged(self):
        self.get(q="escrow")
        kwargs = self.search_pages.call_args.kwargs
        self.assertEqual((kwargs["dup_group"], kwargs["exclude_domains"], kwargs["merge_mirrors"]), (None, None, True))

    def test_bad_codes_and_the_semantic_mode_are_refused(self):
        self.assertIn("16-character", self.get(q="clone:xyz")["error"])
        self.assertIn("clone:", self.get(q=f"clone:{GROUP}", semantic="true")["error"])
        self.search_pages.assert_not_called()


class SearchPagesBodyTests(unittest.TestCase):
    def run_search(self, *args, **kwargs):
        client = mock.Mock()
        client.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
        search.search_pages(client, *args, **kwargs)
        return client.search.call_args.kwargs["body"]["query"]["bool"]

    def test_the_default_call_has_no_extra_clauses(self):
        q = self.run_search("escrow")
        self.assertNotIn("must_not", q)
        self.assertEqual(q["filter"], [])

    def test_a_cluster_filters_on_the_fingerprint_and_leaves_suppressed_hosts_out(self):
        q = self.run_search("", dup_group=GROUP, exclude_domains=["b.onion", "a.onion"])
        self.assertIn({"term": {"dup_group": GROUP}}, q["filter"])
        self.assertEqual(q["must_not"], [{"terms": {"domain": ["a.onion", "b.onion"]}}])
        q = self.run_search("escrow", dup_group=GROUP, exclude_domains=["a.onion"])
        self.assertIn({"term": {"dup_group": GROUP}}, q["filter"])
        self.assertEqual(q["must_not"], [{"terms": {"domain": ["a.onion"]}}])

    def test_mirrors_are_not_merged_when_asked_not_to(self):
        hit = {"_source": {"domain": "x.onion", "url": "http://x.onion/", "embedding": [1.0, 0.0]}}
        twin = {"_source": {"domain": "y.onion", "url": "http://y.onion/", "embedding": [1.0, 0.0]}}
        client = mock.Mock()
        client.search.return_value = {"hits": {"total": {"value": 2}, "hits": [hit, twin]}}
        self.assertEqual(len(search.search_pages(client, "x")[0]), 1)
        client.search.return_value = {"hits": {"total": {"value": 2}, "hits": [dict(hit), dict(twin)]}}
        self.assertEqual(len(search.search_pages(client, "x", merge_mirrors=False)[0]), 2)


if __name__ == "__main__":
    unittest.main()
