"""Periodic liveness check for every known onion domain - updates
domains.is_up (and last_seen_at when up) so the search UI can show a
real uptime indicator instead of a static, one-time crawl snapshot."""
import os
import sys

import requests

sys.path.insert(0, ".")
from darkweb_crawler import db

PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")
PROXIES = {"http": PROXY, "https": PROXY}
TIMEOUT = 25


def check(host):
    url = f"http://{host}/"
    try:
        resp = requests.head(url, proxies=PROXIES, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400:
            resp = requests.get(url, proxies=PROXIES, timeout=TIMEOUT, stream=True)
        return resp.status_code < 500
    except requests.RequestException:
        return False


def main():
    conn = db.get_connection()
    domains = db.get_all_domains(conn)
    up_count = 0
    for domain_id, host in domains:
        is_up = check(host)
        db.update_domain_liveness(conn, domain_id, is_up)
        if is_up:
            up_count += 1
        print(f"{host}: {'UP' if is_up else 'DOWN'}")
    print(f"\n{up_count}/{len(domains)} domains up")
    conn.close()


if __name__ == "__main__":
    main()
