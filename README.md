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
- **Clone clusters** — the biggest groups of pages whose opening text is
  identical on many onion sites: a hosting placeholder, a copied scam or
  phishing kit, a mirrored market. Each cluster shows how many pages and
  sites carry it, a sample title, its categories and the safety mix of the
  sites; search `clone:<id>` to list every copy. Host addresses are never
  shown in the list.
- **Free OSINT safety tools** — see [below](#free-osint-safety-tools) for what
  each one actually does.
- **Watchlist alerts** — a webhook fires the moment a keyword or regex is
  matched on a new ransomware victim, plus an immediate retro-hunt against
  the existing corpus.
- **A local, on-demand AI page summarizer** (llama.cpp + Qwen3.5-4B) — zero
  external API calls, zero per-query cost.

## Architecture

```
                          ┌───────────┐
                          │   web/    │  static single-page frontend
                          └─────┬─────┘
                                │ HTTPS, /api/*
                          ┌─────▼─────┐
                          │   api/    │  FastAPI public API
                          └─────┬─────┘
                   ┌────────────┼─────────────┐
                   ▼            ▼             ▼
              ┌─────────┐ ┌───────────┐  ┌─────────┐
              │Postgres │ │OpenSearch │  │ Valkey  │  rate limiting
              └────┬────┘ └─────┬─────┘  └─────────┘
                   ▲            ▲
                   │ writes     │ indexes
              ┌────┴────────────┴──┐        ┌───────────────┐
              │      crawler/      │───────▶│ Tor + Privoxy │ outbound .onion access
              │      (Scrapy)      │        └───────────────┘
              └────────────────────┘
```

The crawler stores every page in Postgres and indexes it into OpenSearch as it
goes. The API reads both, and uses Valkey for per-IP rate limits. The optional
on-demand summarizer is a separate llama.cpp server that the API calls over HTTP
(`SUMMARIZER_URL`); it is not part of `docker-compose.yml`.

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
6. **Serving.** The `api/` FastAPI app only reads the search index, and it has
   no crawling code, so it can be deployed and scaled independently of the
   crawler. Its writes to Postgres are limited to the small user and
   moderation tables (watchlists, site reports, domain-verification claims,
   digest subscriptions) and a moderator's safety-rating override.

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

By the end of this guide you will have your own copy of the search engine running on your computer,
and you will be able to search it in your browser at <http://127.0.0.1:8080>. Most of the time is spent
waiting for downloads. You do not need to know how the code works.

### What you are installing

The engine is a handful of small programs that work together. Four of them run inside Docker (one
command starts all four), and three are ordinary programs you start yourself.

**Four services that run in Docker.** You do not install these separately.

| Service | What it does, in plain words |
|---|---|
| **Postgres** | The database. It remembers every site and page the crawler has read, the details pulled out of them (Bitcoin addresses, IP addresses, prices) and each site's safety rating. |
| **OpenSearch** | The search index. It is what makes searching fast, and lets you search by words and by meaning. |
| **Valkey** | A small, very fast memory store (it works like Redis). The API uses it to count requests, so one visitor cannot flood the service. |
| **Tor + Privoxy** | The door to the dark web. Tor is the network that `.onion` addresses live on. Privoxy turns Tor's connection into an ordinary web proxy that the crawler can use. |

**Three programs you start yourself.**

| Program | What it does | Folder |
|---|---|---|
| **Crawler** | Visits `.onion` sites through Tor, reads each page, sorts it into a category, rates the site's safety, and saves the result in Postgres and OpenSearch. | `crawler/` |
| **API** | Answers searches. It only reads what the crawler has saved in Postgres and OpenSearch; it does not crawl anything. | `api/` |
| **Web page** | The search page you see in your browser. It asks the API for everything it shows. | `web/` |

So the flow is: the **crawler** fills the **database** and the **search index**, the **API** reads
them, and the **web page** asks the API. Until the crawler has saved some pages there is nothing to
search.

Some features are optional and you can ignore them for now: the AI page summarizer (needs a separate
language-model server), the weekly email digest, the `/admin/*` moderation endpoints, and crawling
ordinary (non-onion) websites.

### What you need first

| You need | Why | Check that you have it | Where to get it |
|---|---|---|---|
| **Git** | To download the code | `git --version` | <https://git-scm.com/downloads> |
| **Docker** with Compose | To run the four services | `docker compose version` | <https://docs.docker.com/get-docker/> (Docker Desktop on Windows and macOS) |
| **Python 3.11 or newer** | To run the crawler, the API and the web page | `python3 --version` (on Windows: `python --version`) | <https://www.python.org/downloads/> |
| **A terminal** | To type the commands below | macOS and Linux have one. On Windows use **Git Bash** (installed with Git) or **WSL**. | |

Your computer should have about 8 GB of memory and several GB of free disk space, and it needs an
internet connection. Linux and macOS users also need one small library for the QR-code checker:
`sudo apt install libzbar0` on Debian or Ubuntu, or `brew install zbar` on macOS.

**The Python packages** (the libraries the programs are built from) are installed for you in steps 4
and 5. Each program gets its own private folder called a *virtual environment* (`.venv`), so nothing
is installed system-wide and you can delete it at any time. The main ones:

| Package | Used by | What for |
|---|---|---|
| Scrapy | Crawler | The crawling framework |
| FastAPI and Uvicorn | API | The web service and the server that runs it |
| psycopg | Crawler, API | Talking to Postgres |
| opensearch-py | Crawler, API | Talking to OpenSearch |
| redis | API | Talking to Valkey |
| sentence-transformers | Crawler, API | The small AI model that sorts pages into categories and powers search by meaning. It brings in PyTorch, which is the biggest download. |
| Pillow, pyzbar | Crawler, API | Reading images and QR codes |

The first time a program needs the AI model (`all-MiniLM-L6-v2`), it downloads it once from Hugging
Face and keeps it.

### Install, step by step

Type each command exactly as shown. Lines that start with `#` are explanations, not commands.

**1. Get the code and create your settings file**

```bash
git clone https://github.com/NexvisionLab/Darkweb-search-engine.git
cd Darkweb-search-engine
cp .env.example .env
```

`.env` is a plain text file that holds your settings. Open it in any text editor and change
`POSTGRES_PASSWORD` to a password of your own. Leave the rest as it is: the defaults already point at
the services you are about to start. (`ADMIN_TOKEN` and the summarizer, email and surface-web settings
only matter for the optional features above.)

**2. Start the four services**

```bash
docker compose up -d postgres opensearch redis tor-privoxy-0
docker compose ps
```

The first run downloads and builds the images, which takes a few minutes. Run `docker compose ps`
again until `postgres` says `healthy`. All four should show as running. On Linux, if `opensearch`
stops straight away, raise the memory-map limit it needs: `sudo sysctl -w vm.max_map_count=262144`.

**3. Create the database tables**

Postgres starts empty. This command fills it with the tables the engine needs, and it is safe to run
twice:

```bash
set -a; . ./.env; set +a
docker exec -i darkweb-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < db/schema.sql
```

You will see a list of `CREATE TABLE` lines. The first command copies your settings from `.env` into
the current terminal. **The Python programs do not read `.env` themselves**, so every terminal that
runs step 4, 5 or 6 must have had that line typed in it first. (PowerShell does not understand it; use
this instead: `Get-Content .env | Where-Object { $_ -match '^\s*[^#\s].*=' } | ForEach-Object { $k, $v = $_ -split '=', 2; Set-Item "env:$k" $v.Trim('"') }`.)

**4. Run the crawler**

```bash
cd crawler
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl onion -a seeds_file=../onions_list/onions.txt -s DEPTH_LIMIT=1
```

The first two commands create the private environment and install the packages (this is the slow
part, often several minutes). The last starts the crawl. On Windows the programs are in
`.venv\Scripts\` instead of `.venv/bin/`.

The seed list has about 19,000 `.onion` addresses, and most of them are no longer online, so you will
see many timeouts and errors. That is normal. Let it run for a few minutes, then press **Ctrl+C** to
stop it. To see how many pages it saved, open a second terminal in the repository folder and run:

```bash
set -a; . ./.env; set +a
docker exec -i darkweb-postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM pages;"
```

Any number above zero means the crawler works. (The crawler also creates the search index the first
time it starts, and indexes every page as it saves it.)

**5. Run the API** (a terminal in the repository folder, with the `set -a` line typed in it)

```bash
python3 -m venv api/.venv
api/.venv/bin/pip install -r api/requirements.txt
api/.venv/bin/uvicorn api.main:app --reload --port 8000
```

Leave it running. Start it from the repository folder, not from inside `api/`, or it fails with
`No module named 'api'`. To check it, open <http://127.0.0.1:8000/stats> in a browser, or run
`curl "http://127.0.0.1:8000/stats"` in another terminal. You should get a short block of counts
(sites, pages, categories) back, not an error.

**6. Open the web page** (another terminal, in the repository folder)

```bash
python3 ops/dev_server.py
```

Then go to <http://127.0.0.1:8080> and try a search. The page asks for its data at `/api/...`. In a
real deployment the nginx web server forwards that to the API, and `ops/dev_server.py` does the same
job on your computer. Use it instead of a plain `python3 -m http.server`, which has no `/api`, so
every search would fail. If your API runs on another port, add `--api http://127.0.0.1:PORT`.

### Stopping, restarting and starting over

- **Stop a program** (crawler, API or web page): click its terminal and press **Ctrl+C**.
- **Stop the four services** but keep your data: `docker compose stop`.
- **Start again another day:** `docker compose up -d postgres opensearch redis tor-privoxy-0`, then
  steps 5 and 6 (and step 4 to crawl more). Each new terminal needs the `set -a; . ./.env; set +a`
  line again. Your pages are still there. You only repeat steps 1 to 3
  on a new computer.
- **Erase everything and start over:** `docker compose down -v`. **This deletes all stored pages and
  the search index.** The next start is empty again.

### If something does not work

| What you see | Likely cause and fix |
|---|---|
| `KeyError: 'POSTGRES_USER'` | The settings were not loaded into this terminal. Type the `set -a; . ./.env; set +a` line again (step 3). |
| A search gives a 500 error or no results | OpenSearch is not running, or the crawler has not saved a page yet, so the search index does not exist. Run `docker compose ps`, then run step 4 until it has saved some pages. |
| `connection refused` on port 5432, 9200 or 6379 | A service is not running. Run `docker compose ps`, then `docker compose logs postgres` (or `opensearch`, `redis`) to see why. |
| `No module named 'api'` | The API was started from inside `api/`. Start it from the repository folder. |
| The page loads but every request fails with 502 | The API is not running on port 8000, or `dev_server.py` was given a different `--api`. |
| The crawler finds nothing for a long time | Normal for the first minutes: Tor is slow and most seed addresses are dead. Check the tor service with `docker compose logs tor-privoxy-0`. |

To rebuild the search index from Postgres (after changing the classifier or the index fields), run
`cd crawler && .venv/bin/python scripts/reindex_opensearch.py`. **It deletes the existing index and
rebuilds it**, so searches are empty while it runs. A normal crawl does not need it.

### Before you crawl

Dark-web sites include scams, adult material and content that is illegal in many countries. The
crawler reads the text of whatever it reaches. The engine rates sites, gates results, and treats
child-abuse material specially (see "Safety rating" above), but nothing guarantees you will not store
something disturbing. Run it on a machine and network you are comfortable using, and check the laws
that apply to you.

## Repository layout

| Path | What it is |
|---|---|
| `api/` | FastAPI app — the public read-only API. No crawling code, deployable independently. |
| `crawler/` | Scrapy crawler + enrichment pipeline (classification, entity extraction, PII masking, safety rating) + operational scripts (`crawler/scripts/`). |
| `web/` | The frontend — one static HTML file, no build step. |
| `db/schema.sql` | Full Postgres schema, idempotent (`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — safe to re-run. |
| `tor-proxy/` | Docker image for the Tor + Privoxy HTTP-proxy bridge the crawler routes through. |
| `ops/` | systemd units, nginx config, and TLS/networking fixes for a real production deployment (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)), plus `dev_server.py` for local development. |
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
