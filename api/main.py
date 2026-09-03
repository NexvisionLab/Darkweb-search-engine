"""Minimal read-only search API over crawled dark-web pages - the
public-facing surface for the free tier. Deliberately thin: OpenSearch
does the full-text ranking, Postgres supplies each result's domain
safety rating, and this layer just shapes the response - including
masking PII in anything returned to an anonymous caller, since a
leak-dump result is real people's actual data. Kept as its own package
(not importing the crawler) so it can be deployed and scaled
independently of Scrapy."""
import io
import threading
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image
from pydantic import BaseModel
import requests

from . import db, hashutil, labels, qr_check, ransomlook_group, ratelimit, redact, scam_classifier, search, summarize, url_check

_URL_RE = re.compile(r"https?://[^\s<>\"']+|(?:[a-z0-9-]+\.)+[a-z0-9-]+\.onion(?:/[^\s<>\"']*)?", re.IGNORECASE)
_STRICT_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]{1,64}@[a-zA-Z0-9-]{1,63}(\.[a-zA-Z0-9-]{1,63})+$")

ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")


def _require_admin(x_admin_token: Optional[str] = Header(None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="invalid or missing admin token")

app = FastAPI(title="Dark Web Intel Search API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# extremism-violence and csam deliberately excluded - see
# darkweb_crawler.classification.INTERNAL_ONLY_CATEGORIES. They're real
# classifier outputs used for safety-rating precision, but never a
# value a caller can filter search by, in either tier.
VALID_CATEGORIES = {
    "marketplace",
    "forum",
    "leak-dump",
    "fraud",
    "carding",
    "crypto-services",
    "counterfeits",
    "drugs",
    "legitimate-mirror",
    "ransomware",
    "hacking-services",
    "weapons",
    "breach-forum",
    "other",
}

VALID_ENTITY_TYPES = {
    "btc", "eth", "xmr", "ip", "email", "cve", "session_token", "phone", "api_key", "iban",
    "certificate", "private_key", "bin", "price", "telegram_handle", "vendor_handle", "card_type",
    "bitcoin_private_key", "crypto_wallet_seed_phrase", "pgp_key", "sql_injection", "onion_link",
    "social_handle", "company_identifier", "encoded_blob",
}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit(bucket: str, limit: int, window_seconds: int):
    def dependency(request: Request):
        ip = _client_ip(request)
        try:
            allowed = ratelimit.check_rate_limit(ip, bucket, limit, window_seconds)
        except Exception:
            # Valkey being unreachable shouldn't take the whole API down -
            # fail open rather than 500 every request.
            return
        if not allowed:
            raise HTTPException(status_code=429, detail="Rate limit exceeded - try again shortly.")

    return dependency


_VID_COOKIE = "dnx_vid"
_VID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
FREE_DAILY_SEARCH_LIMIT = 10
_DAY_SECONDS = 24 * 60 * 60


def _visitor_id(request: Request, response: Response) -> str:
    """A long-lived anonymous id, separate from IP, so a daily quota isn't
    only as strong as one shared-NAT/VPN IP bucket. Not used for anything
    but counting - no profile is built from it."""
    vid = request.cookies.get(_VID_COOKIE)
    if not vid or not _VID_RE.match(vid):
        vid = secrets.token_urlsafe(24)
        response.set_cookie(
            _VID_COOKIE, vid, max_age=365 * _DAY_SECONDS,
            httponly=True, secure=True, samesite="lax",
        )
    return vid


def _daily_search_limit(request: Request, response: Response):
    """Free tier's search quota: capped by IP and by visitor cookie
    together, blocked the moment either is exhausted. Deliberately
    stricter than the plain _rate_limit burst guard above (30/60s, still
    applied separately on /search) - that one stops scripted hammering,
    this one is the actual Free-tier daily allowance."""
    ip = _client_ip(request)
    vid = _visitor_id(request, response)
    try:
        ip_ok = ratelimit.check_rate_limit(ip, "search-daily", FREE_DAILY_SEARCH_LIMIT, _DAY_SECONDS)
        vid_ok = ratelimit.check_rate_limit(vid, "search-daily", FREE_DAILY_SEARCH_LIMIT, _DAY_SECONDS)
    except Exception:
        return
    if not ip_ok or not vid_ok:
        raise HTTPException(
            status_code=429,
            detail=f"Free tier is limited to {FREE_DAILY_SEARCH_LIMIT} searches per day. Try again tomorrow.",
        )


_HOST_RE = re.compile(r"^[a-z2-7]{16,60}\.onion$", re.IGNORECASE)
_GATED_PREVIEW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "previews_gated")


def _preview_filename(host: str) -> str:
    return re.sub(r"[^a-z0-9.]", "_", host.lower()) + ".png"


@app.get("/preview/{host}", dependencies=[Depends(_rate_limit("preview", 60, 60))])
def gated_preview_endpoint(host: str):
    """Serves a Suspicious/Dangerous domain's homepage screenshot - the
    only path that can, since previews_gated/ sits outside nginx's web
    root and web/previews/ (nginx static, no gating) is for ungated
    domains only. Re-checks the rating server-side rather than trusting
    the caller, so this can't be used to fetch a gated image for a
    domain that was reclassified since the file was written."""
    if not _HOST_RE.match(host):
        raise HTTPException(status_code=404)
    conn = db.get_connection()
    try:
        meta = db.get_domain_meta(conn, [host])
    finally:
        conn.close()
    info = meta.get(host)
    if not info:
        raise HTTPException(status_code=404)
    if labels.is_suppressed(info["safety_rating"]):
        # Suppressed ratings (csam-confirmed) never serve a preview,
        # full stop - not even behind the gate the Dangerous label
        # below normally applies.
        raise HTTPException(status_code=404)
    if labels.public_label(info["safety_rating"])["severity"] not in ("warn", "bad"):
        # Ungated domains aren't served from here - their previews are
        # plain nginx static files under /previews/.
        raise HTTPException(status_code=404)
    path = os.path.join(_GATED_PREVIEW_DIR, _preview_filename(host))
    if not os.path.exists(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


# Deliberately broader than _HOST_RE above - a ransomware group's mirrors
# include ordinary clearnet domains (incapt.blog, incapt.su) as well as
# onion addresses, per RansomLook's own data. Just a sanity check for
# early rejection of junk; fqdn is hashed before touching the filesystem
# either way (see ransomlook_group.mirror_preview_filename), so this
# isn't the thing standing between a bad fqdn and a path-traversal bug.
_FQDN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$", re.IGNORECASE)


@app.get("/ransomware/mirror-preview/{fqdn}", dependencies=[Depends(_rate_limit("preview", 60, 60))])
def ransomware_mirror_preview_endpoint(fqdn: str):
    """Serves a ransomware group mirror's screenshot - always gated
    behind the frontend's click-to-reveal, same as /preview/{host}, but
    with no rating to re-check server-side (there's no domains-table
    entry for a RansomLook mirror) - the file's mere existence in
    ransomware_mirrors_gated/ (only ever written by
    capture_ransomware_mirror_previews.py after a NudeNet pass) is the
    whole gate. fqdn isn't secret - it's shown as plain text in the
    Known Mirrors panel already - the gate is a UX consent step before
    fetching the image, not access control."""
    if len(fqdn) > 253 or not _FQDN_RE.match(fqdn):
        raise HTTPException(status_code=404)
    path = os.path.join(ransomlook_group.MIRROR_PREVIEW_DIR, ransomlook_group.mirror_preview_filename(fqdn))
    if not os.path.exists(path):
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def stats_endpoint():
    conn = db.get_connection()
    try:
        return db.get_stats(conn)
    finally:
        conn.close()


# _daily_search_limit is temporarily disabled - kept defined above so it's
# a one-line change to re-enable, not a rebuild.
@app.get("/search", dependencies=[Depends(_rate_limit("search", 30, 60))])
def search_endpoint(
    q: Optional[str] = Query(None, max_length=200),
    category: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    semantic: bool = Query(False, description="Find conceptually similar pages instead of keyword matches"),
):
    if category is not None and category not in VALID_CATEGORIES:
        return {"error": f"invalid category, must be one of {sorted(VALID_CATEGORIES)}"}
    if not (q or "").strip() and not category and not domain:
        return {"error": "provide a search term q, or at least a category/domain to browse"}

    client = search.get_client()
    if semantic:
        if not (q or "").strip():
            return {"error": "semantic search needs a query term q"}
        hits, total = search.semantic_search(client, q, category=category, limit=limit)
    else:
        hits, total = search.search_pages(
            client, q, category=category, domain=domain, limit=limit, offset=offset
        )

    hosts = sorted({hit["domain"] for hit in hits if hit.get("domain")})
    conn = db.get_connection()
    try:
        meta = db.get_domain_meta(conn, hosts)
    finally:
        conn.close()

    results = []
    for hit in hits:
        host_meta = meta.get(hit.get("domain"), {})
        if labels.is_suppressed(host_meta.get("safety_rating")):
            # csam-confirmed domains are dropped from every public result
            # set entirely - not returned gated/blurred like Dangerous,
            # not returned at all. See labels.py's module docstring.
            continue
        results.append(
            {
                **hit,
                "title": redact.redact(hit.get("title")),
                "snippet": redact.redact(hit.get("snippet")),
                "safety_rating": labels.public_label(host_meta.get("safety_rating", "unrated")),
                "is_up": host_meta.get("is_up"),
                "last_seen_at": host_meta.get("last_seen_at"),
                "preview_description": host_meta.get("preview_description"),
            }
        )

    return {"query": q or "", "total": total, "count": len(results), "results": results}


@app.get("/entities/search", dependencies=[Depends(_rate_limit("entities", 30, 60))])
def entities_search_endpoint(
    type: str = Query(..., min_length=2, max_length=20),
    value: str = Query(..., min_length=3, max_length=254),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Search by entity type - email, Bitcoin/Ethereum/Monero address, or
    IP - as a first-class query, free-tier from day one (not gated behind
    a paid plan). Email is the one exception to a raw-value lookup: it
    reuses the same hash-match path as /tools/check-breach, since a raw
    email is never stored anywhere in this platform - only its hash -
    so an email "search" here is really a hashed presence check, not a
    browsable list of pages. Crypto addresses and IPs aren't personal
    identifiers in that same sense, so those are searched by real value
    against the crawled index."""
    entity_type = type.strip().lower()
    if entity_type not in VALID_ENTITY_TYPES:
        return {"error": f"invalid type, must be one of {sorted(VALID_ENTITY_TYPES)}"}
    value = value.strip()

    if entity_type == "email":
        if "@" not in value:
            return {"error": "provide a valid email address"}
        email_hash = hashutil.hash_email(value)
        conn = db.get_connection()
        try:
            result = db.check_breach_email(conn, email_hash)
        finally:
            conn.close()
        if result is None:
            return {"type": "email", "found": False, "total": 0, "count": 0, "results": []}
        return {
            "type": "email",
            "found": True,
            "first_seen_at": result["first_seen_at"],
            "sighting_count": result["sighting_count"],
            "total": 0,
            "count": 0,
            "results": [],
        }

    conn = db.get_connection()
    try:
        results, total = db.search_entities(conn, entity_type, value, limit=limit, offset=offset)
    finally:
        conn.close()
    results = [r for r in results if not labels.is_suppressed(r.get("safety_rating"))]
    for r in results:
        r["title"] = redact.redact(r.get("title"))
        r["safety_rating"] = labels.public_label(r.get("safety_rating", "unrated"))
    return {
        "type": entity_type,
        "found": total > 0,
        "total": total,
        "count": len(results),
        "results": results,
    }


@app.get("/cves/recent", dependencies=[Depends(_rate_limit("cves", 30, 60))])
def recent_cves_endpoint(limit: int = Query(20, ge=1, le=100)):
    """A public "what's being discussed on the dark web" CVE feed -
    regex-extracted mentions from crawled forum/marketplace text (see
    entity_extract.py), not cross-referenced against NVD/KEV yet. That
    cross-reference is a real future enhancement, not attempted here -
    shipping the extraction alone, with no external API dependency,
    was the actual cheap win identified in the competitor research."""
    conn = db.get_connection()
    try:
        cves = db.get_recent_cve_mentions(conn, limit=limit)
    finally:
        conn.close()
    return {"count": len(cves), "cves": cves}


@app.get("/transparency", dependencies=[Depends(_rate_limit("transparency", 30, 60))])
def transparency_endpoint():
    """Public accountability for the safety-rating system - a wrong
    Suspicious/Dangerous label can genuinely harm a legitimate operator,
    so the review process behind it should be visible, not just trusted
    on faith. Disputing a rating uses the same /reports mechanism as
    reporting a site - "otherwise mislabeled" was always meant to cover
    disputes, not a separate flow to duplicate."""
    conn = db.get_connection()
    try:
        stats = db.get_transparency_stats(conn)
    finally:
        conn.close()
    return stats


class DigestSubscribeRequest(BaseModel):
    email: str


@app.post("/digest/subscribe", dependencies=[Depends(_rate_limit("digest", 10, 60))])
def digest_subscribe_endpoint(body: DigestSubscribeRequest):
    """Stores the email in plain text, deliberately unlike the breach
    checker's hash-only handling - this is self-provided contact info
    for a service being actively requested (an ordinary newsletter
    signup), not someone else's leaked data, so the privacy model is
    different on purpose. Actual sending is scripts/send_weekly_digest.py,
    run on a schedule - subscribing here doesn't send anything itself."""
    email = (body.email or "").strip().lower()
    # Full-match against a strict shape, not a loose "@" in email
    # substring check - this value is later used as both the SMTP
    # envelope recipient and the message's To: header in
    # scripts/send_weekly_digest.py, so anything permitting an
    # embedded \r\n would be a real SMTP header/command injection
    # vector, not just a cosmetic validation gap. Found during a
    # security audit, not hypothetical.
    if len(email) > 254 or not _STRICT_EMAIL_RE.match(email):
        return {"error": "provide a valid email address"}

    unsubscribe_token = secrets.token_urlsafe(24)
    conn = db.get_connection()
    try:
        db.create_digest_subscription(conn, email, unsubscribe_token)
    finally:
        conn.close()
    return {"subscribed": True, "unsubscribe_token": unsubscribe_token}


@app.delete("/digest/unsubscribe/{unsubscribe_token}")
def digest_unsubscribe_endpoint(unsubscribe_token: str):
    conn = db.get_connection()
    try:
        removed = db.delete_digest_subscription(conn, unsubscribe_token)
    finally:
        conn.close()
    return {"removed": removed}


@app.get("/domains/{host}")
def domain_endpoint(host: str):
    conn = db.get_connection()
    try:
        info = db.get_domain_summary(conn, host)
    finally:
        conn.close()
    if info is None or labels.is_suppressed(info.get("safety_rating")):
        # Same "not found" response either way - confirming a
        # csam-confirmed domain exists in the index at all is exactly
        # the information this suppression is meant to withhold.
        return {"error": "domain not found"}
    info["title"] = redact.redact(info.get("title"))
    info["safety_rating"] = labels.public_label(info["safety_rating"])
    return info


@app.get("/ransomware/victims", dependencies=[Depends(_rate_limit("ransomware", 30, 60))])
def ransomware_victims_endpoint(
    group: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = db.get_connection()
    try:
        victims, total = db.get_ransomware_victims(conn, group=group, limit=limit, offset=offset)
        group_counts = db.get_ransomware_group_counts(conn)
    finally:
        conn.close()
    for v in victims:
        v["victim_name"] = redact.redact(v["victim_name"])
        v["description"] = redact.redact(v.get("description"))
    return {"total": total, "count": len(victims), "victims": victims, "groups": group_counts}


@app.get("/ransomware/group-info", dependencies=[Depends(_rate_limit("ransomware", 30, 60))])
def ransomware_group_info_endpoint(group: str = Query(..., min_length=1, max_length=100)):
    """Live group-level intel from RansomLook's own API - known onion
    mirrors, whether each is currently reachable, whether it exposes a
    chat or admin panel - shown on the Ransomware Activity tab instead
    of just an outbound link, since RansomLook's per-post link field is
    currently dead across every pattern seen in our own data (see
    db.get_ransomware_victims). A miss (unknown group, RansomLook
    unreachable) returns mirrors: null, not an error - the victim list
    itself still works either way."""
    mirrors = ransomlook_group.get_group_info(group)
    return {"group": group, "mirrors": mirrors}


@app.get("/marketplace/trends", dependencies=[Depends(_rate_limit("marketplace", 30, 60))])
def marketplace_trends_endpoint(domain: Optional[str] = Query(None)):
    conn = db.get_connection()
    try:
        trends = db.get_marketplace_trends(conn, domain=domain)
    finally:
        conn.close()
    return {"count": len(trends), "trends": trends}


class BreachCheckRequest(BaseModel):
    email: str


def _breach_confidence(sighting_count, last_seen_at):
    """A corroborated, repeated, or recent sighting is meaningfully more
    trustworthy than a single old one - surfacing that distinction (per
    Constella's "verified context over raw dumps" positioning from the
    competitor research) rather than treating every match the same."""
    if sighting_count >= 3:
        return "High"
    if sighting_count == 2:
        return "Medium"
    if last_seen_at:
        now = datetime.now(last_seen_at.tzinfo) if last_seen_at.tzinfo else datetime.now(timezone.utc)
        if (now - last_seen_at).days <= 30:
            return "Medium"
    return "Low"


@app.post("/tools/check-breach", dependencies=[Depends(_rate_limit("breach-check", 10, 60))])
def check_breach_endpoint(body: BreachCheckRequest):
    """Ephemeral by design: the email is hashed and never stored or
    logged here - only ever compared against hashes already on file
    from PII-flagged crawled pages. Never reveals which page/domain a
    match came from, only that one exists."""
    email = (body.email or "").strip()
    if "@" not in email or len(email) > 254:
        return {"error": "provide a valid email address"}

    email_hash = hashutil.hash_email(email)
    conn = db.get_connection()
    try:
        result = db.check_breach_email(conn, email_hash)
    finally:
        conn.close()

    if result is None:
        return {"found": False}
    return {
        "found": True,
        "first_seen_at": result["first_seen_at"],
        "last_seen_at": result["last_seen_at"],
        "sighting_count": result["sighting_count"],
        "confidence": _breach_confidence(result["sighting_count"], result["last_seen_at"]),
    }


MAX_IMAGE_BYTES = 10 * 1024 * 1024


@app.post("/tools/scrub-image", dependencies=[Depends(_rate_limit("scrub-image", 10, 60))])
async def scrub_image_endpoint(file: UploadFile = File(...)):
    """Strips EXIF/metadata from an uploaded image and returns a clean
    copy - the protective mirror of the forensics work this platform
    otherwise does to *find* that kind of metadata in the wild."""
    contents = await file.read()
    if len(contents) > MAX_IMAGE_BYTES:
        return {"error": "file too large - max 10MB"}

    try:
        img = Image.open(io.BytesIO(contents))
        img.load()
    except Exception:
        return {"error": "not a readable image"}

    had_metadata = bool(img.getexif()) or bool(img.info)
    fmt = (img.format or "PNG").upper()

    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))

    buf = io.BytesIO()
    save_kwargs = {"quality": 95} if fmt in ("JPEG", "JPG") else {}
    clean.save(buf, format=fmt, **save_kwargs)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type=f"image/{fmt.lower()}",
        headers={
            "Content-Disposition": f"attachment; filename=scrubbed.{fmt.lower()}",
            "X-Metadata-Found": "true" if had_metadata else "false",
        },
    )


class WatchlistRequest(BaseModel):
    keyword: str
    webhook_url: str


RETROHUNT_MAX_VICTIMS = 2000
RETROHUNT_MAX_WEBHOOK_FIRES = 20
REGEX_MATCH_TIMEOUT_SECONDS = 1.0


def _regex_search_safe(pattern, haystack):
    """Runs pattern.search() with a hard wall-clock timeout in a
    separate thread - Python's re module has no built-in timeout, and
    this pattern comes from an anonymous public form, so a crafted
    catastrophic-backtracking pattern needs a hard ceiling rather than
    a chance to hang the process. A timeout is treated as no match,
    never as an error."""
    outcome = {}

    def run():
        outcome["hit"] = pattern.search(haystack) is not None

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(REGEX_MATCH_TIMEOUT_SECONDS)
    if t.is_alive():
        return False
    return outcome.get("hit", False)


@app.post("/watchlist", dependencies=[Depends(_rate_limit("watchlist", 10, 60))])
def create_watchlist_endpoint(body: WatchlistRequest):
    keyword = (body.keyword or "").strip()
    webhook_url = (body.webhook_url or "").strip()
    if not keyword or len(keyword) < 2 or len(keyword) > 200:
        return {"error": "keyword must be 2-200 characters"}
    if not (webhook_url.startswith("http://") or webhook_url.startswith("https://")):
        return {"error": "webhook_url must be a valid http(s) URL"}
    try:
        pattern = re.compile(keyword, re.IGNORECASE)
    except re.error as e:
        return {"error": f"invalid regex pattern: {e}"}

    unsubscribe_token = secrets.token_urlsafe(24)
    conn = db.get_connection()
    try:
        watchlist_id = db.create_watchlist(conn, keyword, webhook_url, unsubscribe_token)

        # Retro-hunt: a brand-new rule should also catch matches already
        # sitting in the historical corpus, not just victims discovered
        # from here on - bounded on both ends (victims scanned, webhooks
        # fired) so one broad pattern can't turn watchlist creation into
        # an unbounded scan or flood someone's webhook endpoint.
        retro_hits = 0
        for victim_id, group_name, victim_name in db.get_all_victim_names(conn, RETROHUNT_MAX_VICTIMS):
            if retro_hits >= RETROHUNT_MAX_WEBHOOK_FIRES:
                break
            if not _regex_search_safe(pattern, victim_name):
                continue
            try:
                requests.post(
                    webhook_url,
                    json={"keyword": keyword, "group_name": group_name, "victim_name": victim_name, "retro_hunt": True},
                    timeout=10,
                )
                retro_hits += 1
            except requests.RequestException:
                pass
        if retro_hits:
            db.touch_watchlist(conn, watchlist_id)
    finally:
        conn.close()
    return {
        "id": watchlist_id,
        "keyword": keyword,
        "unsubscribe_token": unsubscribe_token,
        "retro_hunt_matches": retro_hits,
    }


@app.delete("/watchlist/{unsubscribe_token}")
def delete_watchlist_endpoint(unsubscribe_token: str):
    conn = db.get_connection()
    try:
        removed = db.delete_watchlist(conn, unsubscribe_token)
    finally:
        conn.close()
    return {"removed": removed}


class ReportRequest(BaseModel):
    host: str
    reason: str


@app.post("/reports", dependencies=[Depends(_rate_limit("reports", 10, 60))])
def create_report_endpoint(body: ReportRequest):
    host = (body.host or "").strip()
    reason = (body.reason or "").strip()
    if not host or not reason or len(reason) > 2000:
        return {"error": "provide a host and a reason (max 2000 chars)"}
    conn = db.get_connection()
    try:
        report_id = db.create_site_report(conn, host, reason)
    finally:
        conn.close()
    return {"id": report_id, "status": "pending"}


@app.get("/admin/reports", dependencies=[Depends(_require_admin)])
def admin_list_reports():
    conn = db.get_connection()
    try:
        reports = db.get_pending_reports(conn)
    finally:
        conn.close()
    return {"count": len(reports), "reports": reports}


class ResolveReportRequest(BaseModel):
    note: str = ""
    override_rating: Optional[str] = None


@app.post("/admin/reports/{report_id}/resolve", dependencies=[Depends(_require_admin)])
def admin_resolve_report(report_id: int, body: ResolveReportRequest):
    conn = db.get_connection()
    try:
        ok = db.resolve_site_report(conn, report_id, body.note, body.override_rating)
    finally:
        conn.close()
    if not ok:
        return {"error": "report not found"}
    return {"resolved": True}


class VerifyClaimRequest(BaseModel):
    host: str


@app.post("/verify/claim", dependencies=[Depends(_rate_limit("verify", 5, 60))])
def create_verification_claim_endpoint(body: VerifyClaimRequest):
    host = (body.host or "").strip()
    if not host.endswith(".onion"):
        return {"error": "provide a .onion host"}
    random_suffix = secrets.token_hex(12)
    verify_token = f"darknyx-verify-{random_suffix}"
    conn = db.get_connection()
    try:
        claim_id = db.create_verification_claim(conn, host, verify_token)
    finally:
        conn.close()
    return {
        "id": claim_id,
        "token": verify_token,
        "instructions": f"Add the text '{verify_token}' anywhere on your site's homepage. "
        "It's checked against already-crawled pages on the next scheduled crawl pass "
        "(roughly every 12 hours), not instantly.",
    }


@app.get("/verify/status/{host}")
def verification_status_endpoint(host: str):
    conn = db.get_connection()
    try:
        status = db.get_verification_status(conn, host)
    finally:
        conn.close()
    if status is None:
        return {"error": "no verification claim found for this host"}
    return status


class CheckUrlRequest(BaseModel):
    url: str


@app.post("/tools/check-url", dependencies=[Depends(_rate_limit("check-url", 15, 60))])
def check_url_endpoint(body: CheckUrlRequest):
    """Backs both the general URL/site safety checker and the fake-shop
    checker - same engine, different framing on the frontend. Checks
    the platform's own crawled index first; only falls back to a live
    fetch for a host that hasn't been crawled."""
    raw = (body.url or "").strip()
    if not raw:
        return {"error": "provide a URL"}
    host = raw.split("://", 1)[-1].split("/", 1)[0]

    conn = db.get_connection()
    try:
        known = db.get_domain_summary(conn, host)
    finally:
        conn.close()

    if known is not None:
        if labels.is_suppressed(known.get("safety_rating")):
            # Never live-fetch a suppressed (csam-confirmed) host just
            # because it fell through the block below, and never
            # describe the specific reason - a flat refusal, no oracle.
            return {"error": "this URL cannot be checked"}
        return {
            "host": host,
            "source": "crawled_index",
            "safety_rating": labels.public_label(known["safety_rating"]),
            "page_count": known["page_count"],
        }

    result = url_check.fetch_and_classify(raw)
    if "reachable" not in result:
        # validation failed before any request was attempted (e.g. not a valid URL)
        return {"error": result.get("error", "could not check this URL")}
    result["source"] = "live_check"
    return result


class CheckScamTextRequest(BaseModel):
    text: str


@app.post("/tools/check-scam-text", dependencies=[Depends(_rate_limit("check-scam-text", 15, 60))])
def check_scam_text_endpoint(body: CheckScamTextRequest):
    """Backs both the scam-message checker and the job/investment-scam
    checker - one shared classifier, two thin frontends over it, per
    the original design: most scam-pattern detection is one model
    applied to whatever text a user pastes in."""
    text = (body.text or "").strip()
    if not text:
        return {"error": "paste some text to check"}
    if len(text) > 8000:
        text = text[:8000]
    return scam_classifier.classify_scam_text(text)


class CheckEmailRequest(BaseModel):
    text: str


@app.post("/tools/check-email", dependencies=[Depends(_rate_limit("check-email", 10, 60))])
def check_email_endpoint(body: CheckEmailRequest):
    """Phishing email analyzer: classifies the pasted email content with
    the same scam-text engine, and separately checks up to 3 embedded
    links against the URL checker. Does not verify SPF/DKIM/DMARC -
    that needs live DNS lookups against the sender's domain, which is
    a distinct, not-yet-built capability."""
    text = (body.text or "").strip()
    if not text:
        return {"error": "paste the email content to check"}

    verdict = scam_classifier.classify_scam_text(text[:8000])

    urls = list(dict.fromkeys(_URL_RE.findall(text)))[:3]
    link_results = []
    for u in urls:
        try:
            r = check_url_endpoint(CheckUrlRequest(url=u))
        except Exception:
            r = {"error": "could not check this link"}
        r["url"] = u
        link_results.append(r)

    return {"verdict": verdict, "links_checked": link_results}


MAX_QR_BYTES = 5 * 1024 * 1024


@app.post("/tools/check-qr", dependencies=[Depends(_rate_limit("check-qr", 10, 60))])
async def check_qr_endpoint(file: UploadFile = File(...)):
    """Decodes an uploaded QR code and safety-checks whatever URL it
    points to via the same engine as the URL checker, before anyone
    opens it blind - "quishing" (malicious QR codes) is exactly the
    kind of thing a person can't eyeball before scanning."""
    contents = await file.read()
    if len(contents) > MAX_QR_BYTES:
        return {"error": "file too large - max 5MB"}

    try:
        decoded = qr_check.decode_qr(contents)
    except Exception:
        return {"error": "could not read this image"}

    if not decoded:
        return {"error": "no QR code found in this image"}

    value = decoded[0]
    if value.startswith("http://") or value.startswith("https://") or ".onion" in value:
        check = check_url_endpoint(CheckUrlRequest(url=value))
        return {"decoded": value, "is_url": True, "check": check}

    return {"decoded": value, "is_url": False}


class SummarizeRequest(BaseModel):
    url: str


@app.post("/tools/summarize", dependencies=[Depends(_rate_limit("summarize", 6, 60))])
def summarize_endpoint(body: SummarizeRequest):
    """On-demand only - see summarize.py's docstring. Rate-limited tighter
    than the other free tools since each call is a real local-model
    inference call (seconds, CPU-bound), not just a database lookup."""
    url = (body.url or "").strip()
    if not url:
        return {"error": "provide a URL"}

    conn = db.get_connection()
    try:
        page = db.get_page_by_url(conn, url)
    finally:
        conn.close()

    if page is None:
        return {"error": "this URL hasn't been crawled/indexed"}

    try:
        summary = summarize.summarize(page["title"], page["body_text"])
    except Exception:
        return {"error": "summarizer is temporarily unavailable"}

    if summary is None:
        return {"error": "no text content available to summarize"}

    return {"url": url, "summary": redact.redact(summary)}
