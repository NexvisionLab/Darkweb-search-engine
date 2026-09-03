# DarkNyx Community

DarkNyx is a free, open-source dark-web search engine and threat-intelligence
platform: a Tor-crawling search core, a public read-only API, a set of free
OSINT/safety tools, and a single-page web frontend — all runnable on your own
infrastructure.

This is the **Community** codebase. It is a genuine, complete, self-hostable
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
- **Free OSINT safety tools** — see [below](#free-osint-safety-tools) for what
  each one actually does.
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

### How the engine actually works

A page goes through six stages between being discovered and showing up in a
search result:

1. **Discovery.** A crawled page's outbound links become discovery
   candidates. `DiscoveryPipeline` records each one against its source host
   and drops it immediately — a discovered-but-not-yet-crawled link has no
   meaning to any of the downstream stages, so it never reaches them.
2. **Crawl.** Scrapy fetches the page through the `tor-privoxy-0` container —
   the crawler never touches the open internet directly for `.onion` fetches.
3. **Enrichment.** Each crawled page runs through `classification.py` (14
   content categories), `pii.py` (flags personal data without exposing it),
   `entity_extract.py` (Bitcoin/Ethereum/Monero addresses, IPs, CVEs, API
   keys, IBANs, PGP keys, and 15 other structured types), `email_extract.py`,
   `price_extract.py` (marketplace listings), and `clone_detect.py` (checks
   near-duplicate pages against known-legitimate mirrors — how the platform
   tells a real onion service apart from a phishing clone of one).
4. **Safety rating.** `safety_rating.py` rolls a domain's crawled pages up
   into one Verified / Unrated / Suspicious / Dangerous rating. Most
   categories are ranked by severity (extremism-violence and leak-dump sit
   above the rest), but two signals override that ranking outright regardless
   of category: a page linking to malware, or a near-duplicate of a
   known-legitimate page from a different domain (both mean the domain is
   dangerous no matter what else is on it). **CSAM is checked before every
   other signal, including those overrides** — a single CSAM-classified page
   makes the whole domain CSAM-confirmed unconditionally. A CSAM-confirmed
   domain isn't just rated Dangerous like everything else here; `api/labels.py`
   drops it from search results, entity search, and domain lookups entirely.
   The URL checker tool (below) won't even live-fetch or explain why it's
   refusing to check such a host — a flat refusal, never a hint.
5. **Storage.** Structured data (domains, pages, entities, prices) goes to
   Postgres. The same page content is embedded with `all-MiniLM-L6-v2`
   (384 dimensions — the same model `classification.py` already loads for
   content classification, reused rather than loading a second model) and
   indexed into OpenSearch alongside the raw text, so one query serves both
   full-text and semantic (k-NN vector) search.
6. **Serving.** The `api/` FastAPI app is entirely read-only against that
   index and Postgres — it has no crawling code and no write path back into
   the pipeline, so it's safe to deploy and scale independently of the
   crawler.

### Free OSINT safety tools

Seven tools, all under `/tools/*`, all free, all usable without running your
own crawl — each is a thin API wrapper (or, for the Tor checker, pure
client-side JavaScript) around the same engines the platform already runs
internally.

- **Breach & credential exposure checker** — checks whether an email appears
  in PII the crawler has already flagged on real leak-dump pages. The email
  is hashed before checking and **never stored or logged**; a match tells
  you it exists and how many times it's been seen, never which domain or
  page it came from.
- **Image metadata scrubber** — strips EXIF and other embedded metadata from
  an uploaded image and returns a clean copy, re-encoded rather than merely
  stripped-in-place. The protective mirror of the same forensic work this
  platform does to *find* that kind of metadata in crawled images.
- **URL/site safety checker** — checks the platform's own crawled index
  first, so checking a known host never requires connecting to it live; only
  falls back to a live fetch for a host that hasn't been crawled yet. Also
  backs the fake-shop checker on the frontend — same engine, different
  framing.
- **Phishing email analyzer** — runs pasted email content through the same
  scam-classification model as the message checker below, and separately
  checks up to 3 embedded links against the URL checker. Doesn't verify
  SPF/DKIM/DMARC yet — that needs a live DNS lookup against the sender's
  domain, a distinct capability not yet built.
- **Scam message classifier** — one shared model behind both a general
  scam-message checker and a job/investment-scam checker; most scam-pattern
  detection is the same problem regardless of which framing a user picks.
- **QR code checker** — decodes an uploaded QR code and safety-checks
  whatever URL it points to through the same engine as the URL checker,
  before you ever open it. Built specifically against "quishing" (malicious
  QR codes) — a destination you can't eyeball before scanning.
- **Tor Browser configuration checker** — runs entirely client-side in your
  browser, no server round-trip, so nothing about your setup is ever sent
  anywhere. Checks real anti-fingerprinting hygiene: whether any plugins are
  reporting, whether more than one language is exposed, and whether your
  reported hardware concurrency is high enough to help fingerprint you. Not
  exhaustive — a quick read on your current setup, not a full audit.

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
