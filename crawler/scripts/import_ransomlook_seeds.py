"""Bootstraps a real onion seed list from RansomLook's public API
(https://www.ransomlook.io) - a legitimate, openly documented OSINT
source built specifically for this kind of programmatic use, unlike
scraping a general search engine's results (which several sites, e.g.
Ahmia, explicitly disallow via robots.txt).

Usage: python scripts/import_ransomlook_seeds.py [--out PATH] [--limit N]
"""
import argparse
import sys

import requests

API_BASE = "https://www.ransomlook.io/api"
DEFAULT_OUT = "seeds_runtime.txt"


def fetch_recent_group_names(limit):
    resp = requests.get(f"{API_BASE}/posts", timeout=30)
    resp.raise_for_status()
    posts = resp.json().get("posts", [])
    names = []
    for post in posts:
        name = post.get("group_name")
        if name and name not in names:
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _flatten(data):
    # The API has returned both a bare dict and (nested) lists for
    # different groups in practice - normalize to a flat list of dicts
    # rather than assume one shape.
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        flat = []
        for item in data:
            flat.extend(_flatten(item))
        return flat
    return []


def fetch_available_onions(group_name):
    resp = requests.get(f"{API_BASE}/group/{group_name}", timeout=30)
    if resp.status_code != 200:
        return []
    entries = _flatten(resp.json())
    onions = []
    for entry in entries:
        for loc in entry.get("locations", []):
            if loc.get("available") and loc.get("fqdn", "").endswith(".onion"):
                onions.append(loc["fqdn"])
    return onions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=15, help="how many distinct groups to check")
    args = parser.parse_args()

    print(f"Fetching recent posts to find up to {args.limit} distinct groups...")
    group_names = fetch_recent_group_names(args.limit)
    print(f"Found {len(group_names)} groups: {', '.join(group_names)}")

    all_onions = []
    for name in group_names:
        try:
            onions = fetch_available_onions(name)
        except Exception as e:
            print(f"  {name}: FAILED ({e})")
            continue
        print(f"  {name}: {len(onions)} available onion location(s)")
        all_onions.extend(onions)

    seen = set()
    urls = []
    for fqdn in all_onions:
        if fqdn not in seen:
            seen.add(fqdn)
            urls.append(f"http://{fqdn}/")

    with open(args.out, "w") as f:
        f.write("\n".join(urls) + "\n")

    print(f"\nWrote {len(urls)} unique onion seed URLs to {args.out}")


if __name__ == "__main__":
    sys.exit(main())
