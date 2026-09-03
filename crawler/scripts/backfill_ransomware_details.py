"""Fetches RansomLook's per-post detail for victims that predate this
feature (imported before detail-fetching existed). Capped and
throttled per run, same as the other backfills - ~1200+ existing
victims means this catches up gradually over several scheduled
pipeline runs rather than one large burst against RansomLook's API."""
import sys
import time
from urllib.parse import quote

import requests

sys.path.insert(0, ".")
from darkweb_crawler import db, ransomlook_detail

MAX_PER_RUN = 50
DETAIL_FETCH_DELAY = 0.5


def main():
    conn = db.get_connection()
    victims = db.get_ransomware_victims_needing_detail(conn, MAX_PER_RUN)
    if not victims:
        print("No victims need detail backfill")
        conn.close()
        return

    updated = 0
    for victim_id, group_name, victim_name in victims:
        try:
            detail = ransomlook_detail.fetch_post_detail(group_name, quote(victim_name, safe=""))
        except requests.RequestException as e:
            print(f"failed: {victim_name} ({e})")
            time.sleep(DETAIL_FETCH_DELAY)
            continue

        if detail is None:
            db.update_ransomware_victim_detail(conn, victim_id, None, None, None, False)
            time.sleep(DETAIL_FETCH_DELAY)
            continue

        has_screenshot = False
        if detail.get("screen"):
            has_screenshot = ransomlook_detail.save_screenshot(victim_id, detail["screen"])
        db.update_ransomware_victim_detail(
            conn, victim_id, detail.get("description"), detail.get("link"), detail.get("magnet"), has_screenshot
        )
        updated += 1
        print(f"updated: {victim_name}")
        time.sleep(DETAIL_FETCH_DELAY)

    print(f"Backfilled detail for {updated}/{len(victims)} victims")
    conn.close()


if __name__ == "__main__":
    main()
