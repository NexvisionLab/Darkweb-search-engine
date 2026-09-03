"""Captures a preview screenshot for each known ransomware group's
onion/clearnet mirror, sourced from RansomLook's own /api/group/{name}
response (the "screen" field each location can carry) rather than
rendering anything ourselves - unlike capture_previews.py, there's no
Playwright/Tor step here, just decoding and safety-checking an image
someone else already captured.

Sensitive-content gate: same discipline as capture_previews.py -
every decoded image passes through NudeNet before it's saved anywhere.
A flagged image is discarded outright, never saved and hidden. This
only catches exposed nudity/adult content, not CSAM - see that
script's docstring for why a real CSAM check needs an authorized
partner (NCMEC/Thorn) and isn't attempted here.

Unlike domain previews, there is no "ungated" tier for these - a
ransomware group's negotiation/leak-site mirror is inherently
Dangerous-equivalent content by definition, so every surviving image
goes to MIRROR_PREVIEW_DIR (outside nginx's web root, same posture as
previews_gated/) and is only ever served through
api/main.py's /ransomware/mirror-preview/{fqdn} endpoint, behind the
frontend's click-to-reveal gate - never a bare public file.

Bounded to groups we actually track (distinct group_name already in
ransomware_victims), not RansomLook's full ~600-group catalog - we
have no reason to pull mirror images for a group with zero tracked
victims here. Skips any fqdn with a still-fresh saved preview so a
recurring timer doesn't re-fetch/re-classify the same image every run."""
import base64
import hashlib
import io
import os
import sys
import time

import requests
from PIL import Image

sys.path.insert(0, ".")
from darkweb_crawler import db

API_BASE = "https://www.ransomlook.io/api"
TIMEOUT = 15
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIRROR_PREVIEW_DIR = os.path.join(_REPO_ROOT, "ransomware_mirrors_gated")
MAX_GROUPS_PER_RUN = 30
STALE_DAYS = 14
NUDITY_SCORE_THRESHOLD = 0.5

_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        from nudenet import NudeDetector
        _detector = NudeDetector()
    return _detector


def is_sensitive(image_path):
    result = _get_detector().detect(image_path)
    return any(r["score"] > NUDITY_SCORE_THRESHOLD for r in result)


def preview_filename(fqdn):
    # Hashed rather than sanitized-as-text: fqdn comes from RansomLook's
    # API, not our own crawl, and a hash sidesteps any path-traversal or
    # weird-character concern from a string we don't fully control the
    # shape of, the same reasoning entity_extract.py's fingerprinting
    # already applies to sensitive raw values elsewhere in this project.
    return hashlib.sha256(fqdn.encode("utf-8", errors="ignore")).hexdigest()[:24] + ".png"


def _is_fresh(path):
    if not os.path.exists(path):
        return False
    age_days = (time.time() - os.path.getmtime(path)) / 86400
    return age_days < STALE_DAYS


def fetch_group_locations(group_name):
    """Same nested shape as api/ransomlook_group.py's fetcher (each
    top-level entry carries its own "locations" list) - duplicated
    rather than imported since crawler/ and api/ are deliberately
    separate deployable packages, and this is the one caller anywhere
    that needs the "screen" field, which the api/ version intentionally
    never extracts."""
    url = f"{API_BASE}/group/{group_name}"
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if resp.status_code != 200:
        return []
    try:
        entries = resp.json()
    except ValueError:
        return []
    if not isinstance(entries, list):
        return []
    return [
        loc
        for entry in entries
        if isinstance(entry, dict)
        for loc in entry.get("locations", [])
        if isinstance(loc, dict) and loc.get("fqdn")
    ]


def main():
    os.makedirs(MIRROR_PREVIEW_DIR, exist_ok=True)
    conn = db.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT group_name FROM ransomware_victims "
            "ORDER BY group_name LIMIT %s",
            (MAX_GROUPS_PER_RUN,),
        )
        groups = [row[0] for row in cur.fetchall()]
    conn.close()

    if not groups:
        print("No tracked ransomware groups found")
        return

    captured = 0
    skipped_fresh = 0
    withheld = 0
    no_image = 0
    for group_name in groups:
        locations = fetch_group_locations(group_name)
        for loc in locations:
            fqdn = loc.get("fqdn")
            screen_b64 = loc.get("screen")
            if not fqdn or not screen_b64:
                no_image += 1
                continue

            final_path = os.path.join(MIRROR_PREVIEW_DIR, preview_filename(fqdn))
            if _is_fresh(final_path):
                skipped_fresh += 1
                continue

            try:
                raw = base64.b64decode(screen_b64)
                img = Image.open(io.BytesIO(raw))
                img.load()
            except Exception as e:
                print(f"  could not decode screenshot for {fqdn}: {e}")
                continue

            tmp_path = final_path + ".tmp"
            img.convert("RGB").save(tmp_path, format="PNG", optimize=True)

            if is_sensitive(tmp_path):
                os.remove(tmp_path)
                withheld += 1
                print(f"withheld (sensitive content): {group_name} / {fqdn}")
            else:
                os.replace(tmp_path, final_path)
                captured += 1
                print(f"captured: {group_name} / {fqdn}")

    print(
        f"Done. captured={captured} withheld={withheld} "
        f"skipped_fresh={skipped_fresh} no_image={no_image} groups_checked={len(groups)}"
    )


if __name__ == "__main__":
    main()
