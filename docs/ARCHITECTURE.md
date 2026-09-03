# Architecture

## Components

### `crawler/` — Scrapy crawler + enrichment pipeline

A standard Scrapy project (`crawler/darkweb_crawler/`) whose spider
(`spiders/onion_spider.py`) fetches `.onion` pages through the Tor/Privoxy
proxy (`TOR_PROXY` env var). Every crawled page runs through a pipeline chain
(`pipelines.py`):

1. **`DiscoveryPipeline`** — records new `.onion` links found on a page as
   discovery candidates, without crawling them yet (see
   `scripts/verify_discoveries.py`, which checks and promotes them
   separately — bounded, not automatic).
2. **`PostgresPipeline`** — upserts the domain/page rows.
3. **`EnrichmentPipeline`** — runs, per page:
   - `classification.py` — zero-shot content-category classification via
     sentence-transformer embeddings (`all-MiniLM-L6-v2`), cosine similarity
     against a fixed set of category description embeddings. No training
     data, no external API.
   - `language.py` — language detection.
   - `pii.py` — PII detection, and PCI DSS–compliant credit-card masking
     (truncates any Luhn-valid card number to BIN + last 4 digits before the
     text is ever stored).
   - `price_extract.py` — marketplace price extraction.
   - `entity_extract.py` — regex-based extraction of 25 structured entity
     types (crypto addresses, IPs, CVEs, API keys, IBANs, PGP key
     fingerprints, .onion links, and more) — format-shaped pattern matching,
     not a full protocol validator; genuinely sensitive values (private
     keys, wallet seed phrases) are stored only as a SHA-256 fingerprint,
     never the raw value.
   - `email_extract.py` — emails are hashed before storage; the raw address
     is never written anywhere.
   - `classification.embed()` — a semantic-search embedding vector, reusing
     the same model already loaded for classification.
   - `clone_detect.py` — flags a page as a possible phishing clone of a
     known-legitimate mirror.
4. **`DBUpdatePipeline`** — writes enrichment results back to Postgres, then
   recomputes the owning domain's aggregate `safety_rating`
   (`safety_rating.py`) from all of its pages' categories and risk flags —
   highest-concern category wins (e.g. one leak-dump page makes the whole
   domain "confirmed-leak", regardless of what its other pages look like).
5. **`OpenSearchPipeline`** — indexes the page into OpenSearch for full-text
   and vector search.

`crawler/scripts/` holds every operational script that isn't the crawl
itself: seeding, backfills, liveness checks, exit-scam detection, preview/
favicon capture, RansomLook victim-feed import, the weekly digest sender,
and `crawl_surface_web.py` (a separate Playwright-based crawler for
JavaScript-heavy surface-web sites — carding shops, leak forums — that
doesn't fit Scrapy's request/response model).

### `api/` — the public API

A FastAPI app (`api/main.py`), deliberately kept thin and self-contained —
it never imports from `crawler/`, so it can be deployed and scaled
independently of the Scrapy process. OpenSearch does the full-text ranking;
Postgres supplies each result's safety rating; this layer shapes the
response, redacting/masking anything that shouldn't be shown to an anonymous
caller (see `redact.py`, `pii.py`).

Every route is rate-limited per source IP via Valkey (`ratelimit.py`), on top
of a stricter free-tier daily search quota tracked by IP *and* a long-lived
anonymous cookie together (so a shared-NAT IP doesn't get one shared quota).

See [API.md](API.md) for the full endpoint reference.

### `web/` — the frontend

A single static HTML file with inline CSS/JS, no build step, no framework.
Talks to the API over `/api/*` (proxied by nginx in production — see
[DEPLOYMENT.md](DEPLOYMENT.md)).

### Backing services (`docker-compose.yml`)

| Service | Purpose |
|---|---|
| Postgres | Structured data — domains, pages, ransomware victims, watchlists, entities. |
| OpenSearch | Full-text + vector (semantic) search index. |
| Valkey (Redis-compatible) | Rate limiting counters. |
| Tor + Privoxy | HTTP-proxy bridge onto the Tor network — the crawler's only path to `.onion` addresses. |

### `ai/` (not in this repo — see deployment docs)

The free on-demand summarizer runs a local llama.cpp server hosting
Qwen3.5-4B, started by `ops/systemd/darkweb-summarizer.service`. It is not
part of this repository's Python code — `api/summarize.py` just calls its
OpenAI-compatible completions endpoint (`SUMMARIZER_URL`). Downloading and
running the model is a deployment step, documented in
[DEPLOYMENT.md](DEPLOYMENT.md).

## What's deliberately not in this repo

This is the Community codebase. A separate, closed-source Pro tier exists as
an add-on inference gateway (bulk AI page summarization, an investigation
copilot, AI-narrated risk scores) that authenticates its own API keys and
talks to its own model provider. Nothing in this repository imports it, calls
it, or depends on it — every feature here works standalone.

## Data-handling principles (worth knowing before you deploy)

- **No query logging.** Search terms aren't stored or tied to a visitor.
- **PII is masked or hashed at the point of storage**, not at display time —
  a credit card number is truncated to BIN + last 4 before it's ever written
  to Postgres; an email is only ever stored as a hash.
- **Safety ratings come from automatic classification, not manual review.**
  They're a strong signal, not a guarantee — the frontend labels them this
  way explicitly, and there's a `/reports` endpoint + admin review flow for
  disputing one.
- **Sensitive-content review**: any screenshot this platform captures itself
  (site previews, ransomware mirror screenshots) is passed through an
  NSFW/nudity classifier (NudeNet, self-hosted, no data leaves the machine)
  before being saved. A flagged image is discarded outright, not saved and
  hidden. This is not a CSAM detector — CSAM detection requires
  hash-matching against a database only an authorized partner (e.g.
  NCMEC/Thorn) can provide, and is out of scope for this project.
- **`csam` and `extremism-violence` are internal-only classification
  values** used for safety-rating precision. They are never exposed as a
  filterable search category or a browsable UI value, in either tier — see
  `crawler/darkweb_crawler/classification.py`'s `INTERNAL_ONLY_CATEGORIES`.
  A domain classified this way is fully suppressed from every public
  endpoint (`labels.is_suppressed()`), not merely gated behind a click like
  a Dangerous rating.
