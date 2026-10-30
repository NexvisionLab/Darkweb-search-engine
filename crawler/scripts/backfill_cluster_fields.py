"""Adds the fields Clone clusters needs (dup_group, safety_rating, crawled_at) to pages that were indexed before the crawler wrote them.
ADD-ONLY partial updates on the documents already in OpenSearch: no text, embedding or other field is touched, and a field that is already
set is left alone. New crawls write these fields themselves, so run this once after upgrading.

    cd crawler && python3 scripts/backfill_cluster_fields.py            # dry run: report only
    cd crawler && python3 scripts/backfill_cluster_fields.py --apply    # write

dup_group comes from the stored body_text, safety_rating from the owning domain and crawled_at from the page row with the same URL.
Idempotent."""
import argparse
import sys

from opensearchpy import helpers

sys.path.insert(0, ".")
from darkweb_crawler import db, search

CHUNK = 500


def plan_update(source, ratings_by_host, crawled_by_url):
    """The partial update for one indexed document: only the fields it lacks and we can fill. {} when there is nothing to add."""
    fields = {}
    if not source.get("dup_group"):
        group = search.dup_group(source.get("body_text"))
        if group:
            fields["dup_group"] = group
    if not source.get("safety_rating"):
        rating = ratings_by_host.get(source.get("domain"))
        if rating:
            fields["safety_rating"] = rating
    if not source.get("crawled_at"):
        crawled = crawled_by_url.get(source.get("url"))
        if crawled:
            fields["crawled_at"] = crawled.isoformat()
    return fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    args = parser.parse_args()

    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT host, safety_rating FROM domains WHERE safety_rating IS NOT NULL")
        ratings_by_host = dict(cur.fetchall())
        cur.execute("SELECT url, crawled_at FROM pages WHERE crawled_at IS NOT NULL")
        crawled_by_url = dict(cur.fetchall())
    conn.close()

    client = search.get_client()
    search.ensure_index(client)      # adds the new field mappings to an existing index
    seen = changed = 0
    counts = {"dup_group": 0, "safety_rating": 0, "crawled_at": 0}
    actions = []
    for hit in helpers.scan(client, index=search.INDEX_NAME, query={"query": {"match_all": {}}},
                            _source=["url", "domain", "body_text", "dup_group", "safety_rating", "crawled_at"]):
        seen += 1
        fields = plan_update(hit["_source"], ratings_by_host, crawled_by_url)
        if not fields:
            continue
        changed += 1
        for name in fields:
            counts[name] += 1
        if args.apply:
            actions.append({"_op_type": "update", "_index": search.INDEX_NAME, "_id": hit["_id"], "doc": fields})
            if len(actions) >= CHUNK:
                helpers.bulk(client, actions)
                actions = []
    if args.apply and actions:
        helpers.bulk(client, actions)
    verb = "updated" if args.apply else "would be updated"
    print(f"{seen} indexed pages scanned; {changed} {verb} "
          f"(dup_group {counts['dup_group']}, safety_rating {counts['safety_rating']}, crawled_at {counts['crawled_at']})"
          f"{'' if args.apply else ' (dry run)'}")


if __name__ == "__main__":
    main()
