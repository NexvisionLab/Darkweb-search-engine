"""Fetches the richer per-victim detail RansomLook's API actually has
(description, original-post link, a torrent magnet when the group
published one, and sometimes a screenshot) - the bulk /api/posts feed
used for seeding only carries group/title/discovery date. One extra
GET per victim, so this is deliberately throttled by the caller
rather than fired off in a burst against someone else's public API."""
import base64
import io
import os

import requests
from PIL import Image

API_BASE = "https://www.ransomlook.io/api"
TIMEOUT = 20
SCREEN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web", "ransomware-screens"
)


def fetch_post_detail(group_name, victim_name):
    url = f"{API_BASE}/post/{group_name}/{victim_name}"
    resp = requests.get(url, timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    return resp.json()


def save_screenshot(victim_id, screen_b64):
    """Returns True if a valid image was decoded and saved."""
    try:
        raw = base64.b64decode(screen_b64)
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))  # verify() consumes the file object, reopen to actually use it
    except Exception:
        return False
    os.makedirs(SCREEN_DIR, exist_ok=True)
    img.convert("RGB").save(os.path.join(SCREEN_DIR, f"{victim_id}.png"), format="PNG")
    return True
