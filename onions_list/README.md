# onions.txt

A large (~19,000-address) list of `.onion` URLs, carried forward from this
project's earlier public repository as a real starting point for a first
crawl.

**Important**: this list is unverified. It has not been checked for
liveness, and a real, meaningful fraction of these addresses are likely
dead, parked, or otherwise unreachable — that's normal for any list of this
size and age, not a defect in the list itself. It exists to give the crawler
something real to work with on day one, not as a curated or trusted seed
set.

## How to use it

Point the crawler at it directly for a first run:

```bash
cd crawler
scrapy crawl onion -a seeds_file=../onions_list/onions.txt -s DEPTH_LIMIT=1
```

`scripts/check_liveness.py` and `scripts/verify_discoveries.py` are what
actually separate the live, real sites from the dead ones over time — run
the normal pipeline (`ops/scheduled-crawl/darkweb-pipeline.sh`) rather than
treating this file as a one-time import, so liveness gets rechecked on an
ongoing basis as addresses inevitably go up and down.

## Format

One `.onion` URL per line, `http://` scheme (Tor doesn't distinguish
http/https the way the clearnet does — TLS is irrelevant once you're
already inside the Tor circuit).
