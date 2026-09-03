"""Live group-level intel from RansomLook's public /api/group/{name}
endpoint - added 2026-09-03 to back a "Group info" panel on the
Ransomware Activity tab, replacing reliance on RansomLook's per-post
"link" field, which was confirmed dead across every pattern present in
ransomware_victims.link on 2026-09-03 (including ones their own API
was still returning that same morning - not stale historical data,
their post-level pages are currently broken). /api/group/{name} and
the human-facing /group/{name} page were both confirmed live instead,
so victim links now point to the group page (see db.py), and this
module gives the frontend real content to show instead of just an
outbound link: known onion mirrors, whether each is currently
reachable, whether it exposes a chat or admin panel, and when it was
last scraped.

Lives in api/, not crawler/darkweb_crawler/, on purpose - api/main.py's
own docstring is explicit that this package never imports the crawler
so it can be deployed and scaled independently; this endpoint is only
ever called live, on demand, from a request here, not from the crawl
pipeline.

2026-09-03 follow-up: still never touches the "screen" field itself
here - the actual decode/NudeNet-check/save now happens offline, on a
timer, in crawler/scripts/capture_ransomware_mirror_previews.py (the
same safety-review discipline used for onion preview captures). This
module only checks whether that script already produced a gated file
for a given fqdn (has_preview) - a cheap filesystem stat, not image
handling - so the frontend knows whether a "Show preview" button has
anything to reveal. The actual bytes are served by main.py's
/ransomware/mirror-preview/{fqdn} endpoint, never by this module.

A short in-memory cache avoids hitting someone else's public API on
every page view of a group that multiple visitors are looking at
around the same time - lost on restart, which is fine, it's just a
courtesy to RansomLook's API, not a source of truth."""
import hashlib
import os
import time

import requests

API_BASE = "https://www.ransomlook.io/api"
TIMEOUT = 10
CACHE_TTL_SECONDS = 3600

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR_PREVIEW_DIR = os.path.join(_REPO_ROOT, "ransomware_mirrors_gated")

_cache = {}  # group_name -> (fetched_at, result)


def mirror_preview_filename(fqdn):
    # Must match capture_ransomware_mirror_previews.py's preview_filename()
    # exactly - same hash, same reasoning (fqdn is RansomLook's data, not
    # ours, so hash it rather than trust it as a path component).
    return hashlib.sha256(fqdn.encode("utf-8", errors="ignore")).hexdigest()[:24] + ".png"


def has_mirror_preview(fqdn):
    return os.path.exists(os.path.join(MIRROR_PREVIEW_DIR, mirror_preview_filename(fqdn)))


def get_group_info(group_name):
    cached = _cache.get(group_name)
    if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
        result = cached[1]
    else:
        result = _fetch_group_info(group_name)
        _cache[group_name] = (time.time(), result)

    # Checked fresh every call, never cached alongside the RansomLook
    # data above - a preview can appear between the capture timer's
    # runs independently of whatever TTL the group data itself is on.
    if result:
        for mirror in result:
            mirror["has_preview"] = has_mirror_preview(mirror["fqdn"])
    return result


def _fetch_group_info(group_name):
    url = f"{API_BASE}/group/{group_name}"
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        entries = resp.json()
    except ValueError:
        return None
    if not isinstance(entries, list):
        return None
    # The response is a list of entries, each carrying its own nested
    # "locations" list (real shape observed live, not assumed) - fqdn/
    # available/chat/admin/fs/lastscrape live one level down from the
    # top-level list items, not on the items themselves.
    locations = [
        loc
        for entry in entries
        if isinstance(entry, dict)
        for loc in entry.get("locations", [])
        if isinstance(loc, dict) and loc.get("fqdn")
    ]
    return [
        {
            "fqdn": loc.get("fqdn"),
            "available": bool(loc.get("available")),
            "has_chat": bool(loc.get("chat")),
            "has_admin_panel": bool(loc.get("admin")),
            "has_file_share": bool(loc.get("fs")),
            "last_scraped_at": loc.get("lastscrape"),
        }
        for loc in locations
    ]
