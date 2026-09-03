# DarkNyx (Free)

DarkNyx is a free, open-source dark-web search engine and threat-intelligence
platform: a Tor-crawling search core, a public read-only API, a set of free
OSINT/safety tools, and a single-page web frontend — all runnable on your own
infrastructure.

This is the **Free-tier** codebase. It is a genuine, complete, self-hostable
product on its own — not a crippled demo. A separate, closed-source Pro tier
(bulk AI summarization, an investigation copilot, risk-score narratives) is
built as an add-on gateway that this codebase never needs and never imports.

## What it does

- **Search** onion sites and pages crawled over Tor — full-text and semantic
  (embedding) search, 14 content categories (marketplace, forum, leak-dump,
  ransomware, carding, and more).
- **Entity search** — search by Bitcoin/Ethereum/Monero address, IP, CVE,
  API key, IBAN, PGP key, .onion link, and 15 other structured entity types
  extracted from crawled pages.
- **Safety ratings** — every domain gets a Verified / Unrated / Suspicious /
  Dangerous rating from automatic content classification, with a
  reveal-before-you-click gate on anything rated Suspicious or worse.
- **Ransomware activity tracking** — a live victim feed sourced from
  RansomLook, per-group "known mirrors" info (live up/down status, safety-
  reviewed mirror screenshots), and per-victim detail.
- **Marketplace price trend tracking.**
- **Free OSINT safety tools** — breach/credential exposure check, image
  metadata scrubber, URL/site safety checker, phishing email analyzer, scam
  message classifier, QR code checker, Tor Browser configuration checker.
- **Watchlist alerts** — a webhook fires the moment a keyword or regex is
  matched on a new ransomware victim, plus an immediate retro-hunt against
  the existing corpus.
- **A local, on-demand AI page summarizer** (llama.cpp + Qwen3.5-4B) — zero
  external API calls, zero per-query cost.

## Architecture

```
                          ┌─────────────┐
                          │   web/      │  static single-page frontend
                          └──────┬──────┘
                                 │ HTTPS
                          ┌──────▼──────┐
                          │   api/      │  FastAPI, read-only public surface
                          └──────┬──────┘
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌─────────┐ ┌───────────┐ ┌──────────┐
              │Postgres │ │OpenSearch │ │  Valkey   │  rate limiting
              └─────────┘ └───────────┘ └──────────┘
                    ▲
                    │ writes
              ┌─────┴──────┐        ┌──────────────┐
              │  crawler/   │───────▶│ Tor + Privoxy │  outbound .onion access
              │  (Scrapy)   │        └──────────────┘
              └─────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full component
breakdown, [docs/API.md](docs/API.md) for the API reference, and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for a from-scratch production
deployment guide (systemd units, nginx, TLS via DNS-01).

## Quickstart (local development)

Requires Docker, Python 3.11+, and a Tor-capable network path.

```bash
git clone <this-repo>
cd darknyx
cp .env.example .env        # fill in real values - see the comments in the file
docker compose up -d postgres opensearch redis tor-privoxy-0
psql "postgresql://darknyx:<password>@localhost:5432/darknyx" -f db/schema.sql

cd api && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload --port 8000

# in a second terminal
cd crawler && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl onion -a seeds_file=../onions_list/onions.txt -s DEPTH_LIMIT=1

# in a third terminal, serve web/ with any static file server
python3 -m http.server 8080 --directory web
```

Open `web/index.html` (proxied through your static server) — searches will
be empty until the crawler has run at least once and `reindex_opensearch.py`
has synced Postgres into the search index.

## Repository layout

| Path | What it is |
|---|---|
| `api/` | FastAPI app — the public read-only API. No crawling code, deployable independently. |
| `crawler/` | Scrapy crawler + enrichment pipeline (classification, entity extraction, PII masking, safety rating) + operational scripts (`crawler/scripts/`). |
| `web/` | The frontend — one static HTML file, no build step. |
| `db/schema.sql` | Full Postgres schema, idempotent (`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — safe to re-run. |
| `tor-proxy/` | Docker image for the Tor + Privoxy HTTP-proxy bridge the crawler routes through. |
| `ops/` | systemd units, nginx config, and TLS/networking fixes for a real production deployment. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). |
| `docker-compose.yml` | Postgres, OpenSearch, Valkey, and the Tor proxy — the four backing services. |
| `onions_list/onions.txt` | A large (~19,000-address) unverified `.onion` URL list to bootstrap a first crawl. See [onions_list/README.md](onions_list/README.md) — real, but not liveness-checked; the crawl pipeline sorts out what's actually reachable. |

## Configuration

All configuration is environment variables, loaded from `.env`. See
[.env.example](.env.example) for the full list with explanations, and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for how each one is used in
production.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE). DarkNyx is provided for security research and
personal-safety purposes. It is not a substitute for legal, security, or
law-enforcement advice.
