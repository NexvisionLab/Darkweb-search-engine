"""Checks pending discovery candidates (new .onion hosts found via
bounded open-link-following during crawls - see onion_spider.py) with
a lightweight fetch: alive and reachable, or dead. A verified
candidate is promoted straight into the domains table - the spider
itself already pulls every known domain from the database on each
run (not just the seed file), so promotion alone is enough to get it
crawled going forward; nothing else needs to be written anywhere."""
import os
import re
import sys

sys.path.insert(0, ".")
import requests
from darkweb_crawler import db

TOR_PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")
TIMEOUT = 20
MAX_PER_RUN = 20

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def check(host):
    """Returns a title string (possibly empty) if alive, None if dead."""
    url = f"http://{host}/"
    try:
        resp = requests.get(
            url,
            proxies={"http": TOR_PROXY, "https": TOR_PROXY},
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except requests.RequestException:
        return None
    if resp.status_code >= 500:
        return None
    match = TITLE_RE.search(resp.text or "")
    return match.group(1).strip()[:200] if match else ""


def main():
    conn = db.get_connection()
    candidates = db.get_pending_discovery_candidates(conn, MAX_PER_RUN)
    if not candidates:
        print("No pending discovery candidates")
        conn.close()
        return

    promoted = 0
    for candidate_id, host in candidates:
        title = check(host)
        if title is None:
            db.mark_discovery_dead(conn, candidate_id)
            print(f"dead: {host}")
            continue
        db.mark_discovery_verified(conn, candidate_id, title)
        db.upsert_domain(conn, host, title or None)
        promoted += 1
        print(f"verified + promoted: {host} ({title or '(no title)'})")

    print(f"Promoted {promoted}/{len(candidates)} discovered domains")
    conn.close()


if __name__ == "__main__":
    main()
