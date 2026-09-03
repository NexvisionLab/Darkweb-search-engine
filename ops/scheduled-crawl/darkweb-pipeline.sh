#!/bin/bash
# Recurring pipeline run: refresh seeds and victim data from RansomLook,
# crawl, extract marketplace prices, check liveness, reindex search. Run as
# the darknyx user via systemd (darkweb-pipeline.timer) - not as
# root, since it just needs the crawler's own venv and .env, same as
# running it by hand.
set -e

cd /opt/darknyx/crawler
set -a
source ../.env
set +a
source .venv/bin/activate

echo "=== $(date -u) refreshing seeds ==="
python3 scripts/import_ransomlook_seeds.py --limit 60 --out seeds_runtime.txt

echo "=== $(date -u) importing ransomware victim feed ==="
python3 scripts/import_ransomlook_victims.py

echo "=== $(date -u) backfilling ransomware victim detail ==="
python3 scripts/backfill_ransomware_details.py

echo "=== $(date -u) verifying discovered onion domains ==="
python3 scripts/verify_discoveries.py

echo "=== $(date -u) crawling ==="
scrapy crawl onion -a seeds_file=seeds_runtime.txt -s DEPTH_LIMIT=1 --logfile=/tmp/darkweb-pipeline-crawl.log

echo "=== $(date -u) backfilling marketplace prices ==="
python3 scripts/backfill_prices.py

echo "=== $(date -u) backfilling breach email hashes ==="
python3 scripts/backfill_breach_emails.py

echo "=== $(date -u) backfilling entity extraction (crypto/IP) ==="
python3 scripts/backfill_entities.py

echo "=== $(date -u) checking domain liveness ==="
python3 scripts/check_liveness.py

echo "=== $(date -u) checking pending verification claims ==="
python3 scripts/check_verification_claims.py

echo "=== $(date -u) checking for possible exit scams ==="
python3 scripts/detect_exit_scams.py

echo "=== $(date -u) capturing site preview thumbnails ==="
python3 scripts/capture_previews.py

echo "=== $(date -u) capturing favicons ==="
python3 scripts/capture_favicons.py

echo "=== $(date -u) reindexing search ==="
python3 scripts/reindex_opensearch.py

echo "=== $(date -u) pipeline run complete ==="
