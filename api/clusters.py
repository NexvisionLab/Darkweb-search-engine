"""Clone clusters: groups of pages whose opening text is identical on several onion hosts (the index's dup_group fingerprint, written by
the crawler when it indexes a page). A page found word for word on 350 hosts is a template: a hosting provider's placeholder, a scam or
phishing kit copied across sites, a mirrored marketplace. This module builds the aggregation that lists the biggest groups and shapes its
answer. Pure functions; api/main.py runs the request and caches the answer.

Nothing here lists a host address: a cluster is shown with how many pages and sites it has, a sample title, its categories, the safety
mix of the sites and the last crawl date. Hosts with a suppressed rating are left out inside the query, by host name read from the
database when the list is built (not from the rating stored in the index), so a host rated after its pages were indexed is still left
out and is not counted either."""
from . import labels

SORTS = ("hosts", "pages", "recent")
# The window is always the MAX_BUCKETS clusters present on the most sites; the sort is applied inside it (shape). Ordering the
# aggregation itself by pages or recency would cut the window before the min_hosts filter ran and drop large clusters.
MAX_BUCKETS = 500          # terms buckets asked for (paging works inside this window)
MIN_HOSTS_CHOICES = (2, 3, 5, 10, 25, 50)


def build_body(min_hosts=3, category=None, sort="hosts", suppressed_hosts=(), size=100):
    if sort not in SORTS:
        raise ValueError("sort must be hosts, pages or recent")
    if not 2 <= min_hosts <= 1000:
        raise ValueError("min_hosts must be between 2 and 1000")
    flt = [{"exists": {"field": "dup_group"}}]
    if category:
        flt.append({"term": {"content_category": category}})
    hosts = sorted(h for h in (suppressed_hosts or ()) if h)
    query = {"bool": {"filter": flt}}
    if hosts:
        query["bool"]["must_not"] = [{"terms": {"domain": hosts}}]
    return {
        "size": 0,
        "query": query,
        "aggs": {"clusters": {
            "terms": {"field": "dup_group", "size": min(size, MAX_BUCKETS), "min_doc_count": 2, "order": {"hosts": "desc"}},
            "aggs": {
                "hosts": {"cardinality": {"field": "domain", "precision_threshold": 1000}},
                "latest": {"max": {"field": "crawled_at"}},
                "categories": {"terms": {"field": "content_category", "size": 3}},
                "ratings": {"terms": {"field": "safety_rating", "size": 8}},
                "sample": {"top_hits": {"size": 1, "sort": [{"crawled_at": {"order": "desc", "unmapped_type": "date"}}],
                                        "_source": ["title", "language"]}},
                "enough_hosts": {"bucket_selector": {"buckets_path": {"h": "hosts"}, "script": f"params.h >= {int(min_hosts)}"}},
            },
        }},
    }


def _label_mix(rating_buckets):
    """{public label: pages}: the stored ratings folded into the four labels the site shows."""
    mix = {}
    for b in rating_buckets:
        label = labels.public_label(b["key"])["label"]
        mix[label] = mix.get(label, 0) + b["doc_count"]
    return mix


def _date(agg):
    return agg.get("value_as_string") if agg and agg.get("value") is not None else None


def sort_items(items, sort):
    if sort == "pages":
        return sorted(items, key=lambda c: (-c["pages"], -c["hosts"]))
    if sort == "recent":
        return sorted(items, key=lambda c: (c["last_crawled"] or "", c["hosts"]), reverse=True)
    return sorted(items, key=lambda c: (-c["hosts"], -c["pages"]))


def shape(response, redact, limit=30, offset=0, sort="hosts"):
    """The cluster list from an OpenSearch answer, sorted as asked inside the window the query returned. `redact` is api/redact.redact
    (titles are shown, so they are masked like everywhere)."""
    out = []
    for b in response.get("aggregations", {}).get("clusters", {}).get("buckets", []):
        hits = ((b.get("sample") or {}).get("hits") or {}).get("hits") or []
        source = hits[0].get("_source", {}) if hits else {}
        out.append({
            "id": b["key"],
            "pages": b["doc_count"],
            "hosts": int(b["hosts"]["value"]),
            "title": redact(source.get("title")) or "(no title)",
            "language": source.get("language"),
            "categories": [{"category": c["key"], "count": c["doc_count"]} for c in b.get("categories", {}).get("buckets", [])],
            "safety": _label_mix(b.get("ratings", {}).get("buckets", [])),
            "last_crawled": _date(b.get("latest")),
        })
    out = sort_items(out, sort)
    return out[offset:offset + limit], len(out)
