"""Downloads the actual favicon image for each domain that has a
favicon_url captured (found during crawl - see page_metadata.py) but
no local copy yet, via the same Tor/Privoxy proxy the crawler uses.
Converts to PNG at a fixed small size for one predictable extension,
mirroring how site preview thumbnails are stored - a plain requests
GET, not a full browser, since a favicon is just a static file."""
import io
import os
import re
import sys

sys.path.insert(0, ".")
import requests
from darkweb_crawler import db
from PIL import Image

TOR_PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")
FAVICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web", "favicons"
)
MAX_PER_RUN = 30
TIMEOUT = 15
MAX_BYTES = 2 * 1024 * 1024
ICON_SIZE = (64, 64)


def safe_filename(host):
    return re.sub(r"[^a-z0-9.]", "_", host.lower()) + ".png"


def main():
    os.makedirs(FAVICON_DIR, exist_ok=True)
    conn = db.get_connection()
    domains = db.get_domains_needing_favicon(conn, MAX_PER_RUN)
    if not domains:
        print("No domains need a favicon capture")
        conn.close()
        return

    captured = 0
    for domain_id, host, favicon_url in domains:
        try:
            resp = requests.get(
                favicon_url,
                proxies={"http": TOR_PROXY, "https": TOR_PROXY},
                timeout=TIMEOUT,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            content = resp.raw.read(MAX_BYTES, decode_content=True)
            img = Image.open(io.BytesIO(content))
            img = img.convert("RGBA")
            img.thumbnail(ICON_SIZE)
            img.save(os.path.join(FAVICON_DIR, safe_filename(host)), format="PNG")
            captured += 1
            print(f"captured: {host}")
        except Exception as e:
            print(f"failed: {host} ({e})")
        db.mark_domain_favicon_captured(conn, domain_id)  # don't retry every run either way

    print(f"Captured {captured}/{len(domains)} favicons")
    conn.close()


if __name__ == "__main__":
    main()
