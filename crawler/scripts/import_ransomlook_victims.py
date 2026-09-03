"""Ingests RansomLook's structured leak-post feed (group, victim, discovery
date) directly into ransomware_victims - the same legitimate public API
already used to seed onion addresses, now used for what it's actually
built for: a real victim/activity feed, rather than trying to parse this
out of arbitrary crawled leak-site HTML. Also fires the webhook watchlist
for any newly-inserted victim whose name matches a registered keyword,
and fetches the richer per-post detail (description/link/magnet/screenshot)
for each new victim - throttled, since that's one extra request per
victim against someone else's public API."""
import re
import sys
import threading
import time
from urllib.parse import quote

import requests

sys.path.insert(0, ".")
from darkweb_crawler import db, ransomlook_detail

API_URL = "https://www.ransomlook.io/api/posts"
WEBHOOK_TIMEOUT = 10
DETAIL_FETCH_DELAY = 0.5


def fetch_posts():
    resp = requests.get(API_URL, timeout=30)
    resp.raise_for_status()
    return resp.json().get("posts", [])


REGEX_MATCH_TIMEOUT_SECONDS = 1.0


def _regex_search_safe(pattern, haystack):
    """Same ReDoS guard as api/main.py's watchlist creation endpoint -
    duplicated rather than imported across the api/crawler package
    boundary this project keeps deliberately separate. A watchlist
    keyword is public, anonymous, user-submitted input; a crafted
    catastrophic-backtracking pattern gets a hard wall-clock ceiling
    instead of a chance to hang this recurring pipeline run."""
    outcome = {}

    def run():
        outcome["hit"] = pattern.search(haystack) is not None

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(REGEX_MATCH_TIMEOUT_SECONDS)
    if t.is_alive():
        return False
    return outcome.get("hit", False)


def notify_watchlists(conn, group_name, victim_name):
    watchlists = db.get_all_watchlists(conn)
    if not watchlists:
        return
    for watchlist_id, keyword, webhook_url in watchlists:
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
        except re.error:
            continue  # already rejected at creation time; skip a stale bad row defensively
        if not _regex_search_safe(pattern, victim_name):
            continue
        payload = {"keyword": keyword, "group_name": group_name, "victim_name": victim_name}
        try:
            requests.post(webhook_url, json=payload, timeout=WEBHOOK_TIMEOUT)
            db.touch_watchlist(conn, watchlist_id)
        except requests.RequestException as e:
            print(f"  webhook failed for watchlist {watchlist_id} ({webhook_url}): {e}")


def fetch_and_store_detail(conn, victim_id, group_name, victim_name):
    try:
        detail = ransomlook_detail.fetch_post_detail(group_name, quote(victim_name, safe=""))
    except requests.RequestException as e:
        print(f"  detail fetch failed for {victim_name}: {e}")
        return
    if detail is None:
        return
    has_screenshot = False
    if detail.get("screen"):
        has_screenshot = ransomlook_detail.save_screenshot(victim_id, detail["screen"])
    db.update_ransomware_victim_detail(
        conn, victim_id, detail.get("description"), detail.get("link"), detail.get("magnet"), has_screenshot
    )


def main():
    posts = fetch_posts()
    conn = db.get_connection()
    inserted = 0
    for post in posts:
        group_name = post.get("group_name")
        victim_name = post.get("post_title")
        discovered = post.get("discovered")
        if not group_name or not victim_name:
            continue
        victim_id = db.upsert_ransomware_victim(conn, group_name, victim_name, discovered)
        if victim_id:
            inserted += 1
            notify_watchlists(conn, group_name, victim_name)
            time.sleep(DETAIL_FETCH_DELAY)
            fetch_and_store_detail(conn, victim_id, group_name, victim_name)
    print(f"Fetched {len(posts)} posts, inserted {inserted} new victim records")
    conn.close()


if __name__ == "__main__":
    main()
