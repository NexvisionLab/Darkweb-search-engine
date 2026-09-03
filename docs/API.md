# API Reference

Base URL in production: `https://yourdomain.com/api` (nginx proxies `/api/*`
to the FastAPI app — see [DEPLOYMENT.md](DEPLOYMENT.md)). All examples below
use the app's own path (no `/api` prefix), matching what you'd call directly
against `uvicorn` in development.

All endpoints are `GET` unless noted. Every endpoint is rate-limited per
source IP (Valkey-backed); a `429` response includes a `detail` message.
Responses are JSON. An error response is `{"error": "..."}` with a `200`
status unless otherwise noted (this API predates strict HTTP-status-per-error
discipline — check for an `error` key, don't rely solely on status code,
except where a status code is explicitly documented below).

## Search

### `GET /search`
The core search endpoint.

| Param | Required | Notes |
|---|---|---|
| `q` | one of `q`/`category`/`domain` | Free-text query. |
| `category` | see above | One of the values in `VALID_CATEGORIES` (see `api/main.py`) — `marketplace`, `forum`, `leak-dump`, `fraud`, `carding`, `crypto-services`, `counterfeits`, `drugs`, `legitimate-mirror`, `ransomware`, `hacking-services`, `weapons`, `breach-forum`, `other`. |
| `domain` | see above | Filter to a specific `.onion` host. |
| `limit` | no | 1–100, default 20. |
| `offset` | no | default 0. |
| `semantic` | no | `true` for embedding-similarity search instead of keyword match (requires `q`). |

Each result includes a `safety_rating` object (`{"label": "...", "severity": "good"\|"neutral"\|"warn"\|"bad"}`). A result whose domain safety rating is `csam-confirmed` is silently excluded from the result set entirely — not gated, not shown at all.

### `GET /entities/search`
Search by a structured entity type extracted from crawled pages.

| Param | Required | Notes |
|---|---|---|
| `type` | yes | One of `VALID_ENTITY_TYPES` (see `api/main.py`) — 37 types including `btc`, `eth`, `xmr`, `ip`, `email`, `cve`, `api_key`, `iban`, `pgp_key`, `onion_link`, `bitcoin_private_key`, `crypto_wallet_seed_phrase`, `file_hash`, `crypto_tx_hash`, `altcoin_address`, `swift_bic`, `postcode_us`, `postcode_uk`, `gps_coordinates`, `mac_address`, `domain_mention`, `discord_id`, `whatsapp_link`, `ransom_amount`. |
| `value` | yes | 3–254 chars. For `type=email`, this is checked against a hashed breach corpus only (see below) — the raw value is never looked up directly. |
| `limit` / `offset` | no | Same as `/search`. |

`type=email` returns `{"type": "email", "found": bool, "first_seen_at": ..., "sighting_count": ...}` instead of a result list — raw emails are never stored, only hashes.

### `GET /cves/recent`
Recently-mentioned CVEs across crawled pages. `limit` (1–100, default 20).

### `GET /domains/{host}`
Summary info for one domain: title, safety rating, first/last seen, up/down status, page count.

## Safety tools (all free, no account)

### `POST /tools/check-breach`
Body: `{"email": "..."}`. Hashes the email, checks against hashes extracted from PII-flagged crawled pages. Returns `{"found": bool, "sighting_count": ..., "confidence": "High"|"Medium"|"Low"}` — confidence is High at 3+ sightings, Medium at 2 or a sighting within 30 days, Low otherwise. Never reveals which page/domain matched.

### `POST /tools/scrub-image`
Multipart file upload (`file`, max 10MB). Strips EXIF/metadata and returns the cleaned image. Response header `X-Metadata-Found: true|false`.

### `POST /tools/check-url`
Body: `{"url": "..."}`. Checks the platform's own crawl index first; falls back to a live fetch + classification for anything not indexed. Backs both the general URL checker and the fake-shop checker in the UI.

### `POST /tools/check-scam-text`
Body: `{"text": "..."}`, max 8000 chars. Returns a scam-category verdict (phishing, romance, crypto/investment, fake-delivery, tech-support, job, lottery/inheritance) with a confidence score.

### `POST /tools/check-email`
Body: `{"text": "..."}` — the full email content. Classifies it with the same engine as `check-scam-text` and separately checks up to 3 embedded links via `check-url`'s logic.

### `POST /tools/check-qr`
Multipart file upload (`file`, max 5MB). Decodes the QR code; if it points to a URL, also runs it through the URL safety check.

### `POST /tools/summarize`
Body: `{"url": "..."}`. On-demand only — runs the local Qwen3.5 summarizer against an already-crawled page's stored text. Rate-limited tighter than other tools (6/min) since each call is a real local-model inference.

## Ransomware tracking

### `GET /ransomware/victims`
| Param | Notes |
|---|---|
| `group` | optional, filter to one ransomware group |
| `limit` | 1–200, default 50 |
| `offset` | default 0 |

Returns `{"total", "count", "victims": [...], "groups": [{"group_name", "victim_count"}, ...]}`.

### `GET /ransomware/group-info`
`group` (required). Live data from RansomLook's public API: known mirrors per group, each with `available` (up/down), `has_chat`, `has_admin_panel`, `has_file_share`, `last_scraped_at`, and `has_preview` (whether a safety-reviewed screenshot exists — see below). Cached in-process for 1 hour.

### `GET /ransomware/mirror-preview/{fqdn}`
Serves a ransomware mirror's screenshot — only if `capture_ransomware_mirror_previews.py` has already captured and safety-reviewed it (NudeNet-gated; a flagged image is never saved). `404` if none exists. Always meant to be shown behind a click-to-reveal in the UI, never auto-loaded.

### `GET /preview/{host}`
Serves a Suspicious/Dangerous-rated domain's homepage screenshot. Re-checks the domain's current safety rating server-side before returning bytes (never for a `csam-confirmed` domain, regardless of caller).

## Marketplace

### `GET /marketplace/trends`
`domain` (optional, filter to one). Price-trend data extracted from marketplace-category pages.

## Watchlist alerts

### `POST /watchlist`
Body: `{"keyword": "...", "webhook_url": "https://..."}`. `keyword` is a plain word or regex (2–200 chars, ReDoS-guarded with a 1-second match timeout). Immediately retro-hunts against up to 2,000 existing ransomware victims (bounded to 20 webhook fires) in addition to matching future ones. Returns `{"id", "unsubscribe_token", "retro_hunt_matches"}`.

### `DELETE /watchlist/{unsubscribe_token}`

## Digest

### `POST /digest/subscribe`
Body: `{"email": "..."}`. Subscribes to a weekly email (new ransomware victims + newly-flagged Suspicious/Dangerous sites) — requires `SMTP_*` env vars configured and `scripts/send_weekly_digest.py` run on a schedule; subscribing here doesn't send anything itself.

### `DELETE /digest/unsubscribe/{unsubscribe_token}`

## Site reports & verification

### `POST /reports`
Body: `{"host": "...", "reason": "..."}` (reason max 2000 chars). Flags a site for manual review — the mechanism for disputing a safety rating.

### `POST /verify/claim`
Body: `{"host": "..."}` (must end in `.onion`). Starts an ownership-verification claim; returns a token to place on the site's homepage, checked on the next crawl pass (~every 12h).

### `GET /verify/status/{host}`

## Admin (requires `X-Admin-Token` header matching `ADMIN_TOKEN`)

### `GET /admin/reports`
Pending site reports.

### `POST /admin/reports/{report_id}/resolve`
Body: `{"note": "...", "override_rating": "..." (optional)}`.

## Meta

### `GET /health` → `{"status": "ok"}`
### `GET /stats` → domain/page counts, category counts, safety-rating counts, discovery-candidate counts. Internal-only categories/ratings (`csam`, `extremism-violence`, `csam-confirmed`) are excluded from every count here — never just filterable, genuinely absent from the payload.
### `GET /transparency` → aggregate accountability stats for the safety-rating system (how many disputes, resolutions, etc).
