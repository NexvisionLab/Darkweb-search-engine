"""Heuristic price-mention extraction for marketplace-category pages.
Not per-listing structured extraction (vendor/product/price triples) -
every dark-web marketplace uses a different template, so that would
need a site-specific scraper per marketplace, not a generic one. This
extracts every currency-amount mention on the page instead, which is
still enough to track price trends per domain/category over time."""
import re

_CURRENCY_MAP = {"$": "USD", "€": "EUR", "£": "GBP"}
_CURRENCIES = r"\$|USD|EUR|€|£|GBP|BTC|XMR|ETH"

PRICE_RE = re.compile(
    rf"(?:(?P<cur1>{_CURRENCIES})\s*(?P<amt1>\d{{1,3}}(?:[,.]\d{{3}})*(?:\.\d+)?))"
    rf"|(?:(?P<amt2>\d{{1,3}}(?:[,.]\d{{3}})*(?:\.\d+)?)\s*(?P<cur2>{_CURRENCIES}))",
    re.IGNORECASE,
)

MAX_RESULTS = 20
MAX_AMOUNT = 10_000_000


def _normalize_currency(raw):
    raw = raw.upper()
    return _CURRENCY_MAP.get(raw, raw)


def extract_prices(text):
    if not text:
        return []
    results = []
    for match in PRICE_RE.finditer(text[:20000]):
        currency_raw = match.group("cur1") or match.group("cur2")
        amount_raw = match.group("amt1") or match.group("amt2")
        if not currency_raw or not amount_raw:
            continue
        try:
            amount = float(amount_raw.replace(",", ""))
        except ValueError:
            continue
        if not (0 < amount <= MAX_AMOUNT):
            continue
        results.append(
            {
                "amount": amount,
                "currency": _normalize_currency(currency_raw),
                "raw_text": match.group(0).strip(),
            }
        )
        if len(results) >= MAX_RESULTS:
            break
    return results
