"""Heuristic extraction of crypto addresses, IPs, CVE mentions, and
exposed session tokens for entity search - same honest-heuristic scope
as price_extract.py: format-shaped pattern matching, not a full
protocol-level validator. Email is deliberately excluded here - it
stays in email_extract.py, where only a hash is ever stored (see that
module's docstring); the entity types here don't carry the same
raw-PII sensitivity, so they're stored and searched by real value.

CVE and session-token support added during a Free-tier feature-
completeness pass - both reuse the existing page_entities/entity-search
infrastructure (a new entity_type is the entire cost) rather than new
tables or endpoints. Session-token detection is deliberately narrow:
only the JWT shape (a clean, low-false-positive pattern), not generic
"sessionid=", "PHPSESSID=" name=value pairs, which are common enough
in ordinary page markup to produce a lot of noise for not much signal.
This is a detection/search capability only - there's no "paste your
own token to check" tool, since encouraging anyone to paste a live
secret into a public web form would be actively unsafe advice.

Phone/API-key/IBAN/certificate/private-key support added in a later
pass, same discipline throughout: phone numbers only in clean E.164
international form (a leading + avoids the enormous false-positive
surface of matching bare local-format digit runs); API keys only
match known vendor prefix formats (AWS/GitHub/Slack/Google/Stripe),
not "any long random-looking string"; IBAN is MOD-97 checksum
validated, the same reasoning pii.py already applies via Luhn for
credit cards - genuinely more precise, not just cheaper. Certificates
and private keys are detected by their PEM armor (a fixed, zero-
false-positive marker) - the entity_value stored is a short SHA-256
fingerprint of the block, never the raw key material itself, so
neither this module nor entity search ever surfaces actual secret
bytes.
Private keys stay strictly detection-only like session tokens above -
no tool anywhere accepts a user-submitted key to check.

Base64/hex decoding added in the same pass: most base64/hex-looking
runs on a real page are asset hashes or data-URI images, not hidden
content, so a decode is only re-scanned for entities when it comes
back as genuinely readable UTF-8 text - not surfaced as its own
entity, just a second pass at finding the same plain-value types.

Carding-listing fields (bin/card_type/price/telegram_handle/
vendor_handle) added for surface-web carding-site coverage. bin only
matches an explicitly labeled "BIN: 123456" pattern, never a bare
6-8 digit run - a labeled BIN is safe to store and search (PCI DSS
treats it as non-sensitive), but nothing here ever extracts or stores
more of a card number than that; pii.mask_card_numbers() truncates any
full card number in body_text to the same BIN+last4 ceiling before
this module (or anything else) ever sees the page's text at all.
vendor_handle only matches an explicitly labeled "seller:"/"vendor:"
pattern for the same reason phone/API-key patterns stay narrow -
extracting a bare username from free text would be far too noisy to
be useful signal.

Eight more types added during the 2026-09-03 classification-taxonomy
pass, taken almost directly from AIL Framework's more granular
infoleak taxonomy (the direct precedent for this module):
bitcoin_private_key (WIF format - a leaked private key drains funds,
categorically worse than a leaked address, so it's tracked as its own
type) and crypto_wallet_seed_phrase (a labeled BIP-39 mnemonic, same
"require an explicit label" discipline as bin/vendor_handle rather
than a bare 12-word heuristic that would false-positive constantly)
both stay strictly fingerprint-only like certificate/private_key above
- the actual key/phrase is never stored. pgp_key covers all four PGP
armor block types (public/private/signature/message) under one type,
fingerprint-only, same reasoning as certificate. sql_injection stores
the matched attack-string snippet itself, which is safe to keep as
plain text (it's not personal data). onion_link and social_handle
(Discord invite links, X/Twitter profile URLs, Session messenger IDs)
are stored by real value like the crypto-address types above - public
identifiers, not secrets. company_identifier is a plain-value type
too: a capitalized name run immediately followed by a legal-entity
suffix (Inc/LLC/Ltd/GmbH/Corp/PLC/S.A./B.V.) - an honest heuristic in
the same spirit as everything else here, not a company-registry
lookup. encoded_blob flags that a page contained a base64/hex-shaped
run at all (fingerprinted, not the blob itself) even when it never
decoded to readable text - AIL tags Base64/Hex/Binary as their own
infoleak types for exactly this reason: a hidden blob is itself a
signal worth surfacing before anyone knows what's inside it."""
import base64
import binascii
import hashlib
import re

_BTC_LEGACY_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
_BTC_BECH32_RE = re.compile(r"\bbc1[a-z0-9]{25,60}\b", re.IGNORECASE)
_ETH_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_XMR_RE = re.compile(r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b")
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])\b"
)
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_PHONE_RE = re.compile(r"\+[1-9]\d{7,14}\b")
_API_KEY_RE = re.compile(
    r"\b(?:"
    r"AKIA[0-9A-Z]{16}"                       # AWS access key
    r"|gh[pousr]_[A-Za-z0-9]{36}"              # GitHub token
    r"|xox[baprs]-[0-9A-Za-z-]{10,48}"         # Slack token
    r"|AIza[0-9A-Za-z_-]{35}"                  # Google API key
    r"|[sr]k_live_[0-9a-zA-Z]{24,}"            # Stripe live key
    r")\b"
)
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_CERT_BLOCK_RE = re.compile(
    r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----",
    re.DOTALL,
)
_BASE64_CANDIDATE_RE = re.compile(r"\b[A-Za-z0-9+/]{20,}={0,2}")
_HEX_CANDIDATE_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){10,}\b")

_BIN_RE = re.compile(r"\bBIN[:\s]{1,3}(\d{6,8})\b", re.IGNORECASE)
_PRICE_RE = re.compile(
    r"\$\s?\d+(?:\.\d+)?\b"
    r"|\b\d+(?:\.\d+)?\s?(?:USD|BTC|XMR|EUR|GBP)\b",
    re.IGNORECASE,
)
_TELEGRAM_RE = re.compile(r"\bt\.me/[A-Za-z0-9_]{5,32}\b", re.IGNORECASE)
_VENDOR_HANDLE_RE = re.compile(r"\b(?:seller|vendor)[:\s]{1,3}([A-Za-z0-9_-]{3,20})\b", re.IGNORECASE)
_CARD_TYPE_KEYWORDS = {
    "cvv": re.compile(r"\bcvv2?\b", re.IGNORECASE),
    "dump": re.compile(r"\bdumps?\b", re.IGNORECASE),
    "fullz": re.compile(r"\bfullz\b", re.IGNORECASE),
}

_BTC_PRIVATE_KEY_WIF_RE = re.compile(r"\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b")
_SEED_PHRASE_RE = re.compile(
    r"\b(?:seed phrase|recovery phrase|mnemonic)[:\s]{1,3}((?:[a-z]{3,8}\s+){11,23}[a-z]{3,8})\b",
    re.IGNORECASE,
)
_PGP_BLOCK_RE = re.compile(
    r"-----BEGIN PGP (?:PUBLIC KEY BLOCK|PRIVATE KEY BLOCK|SIGNATURE|MESSAGE)-----"
    r".*?-----END PGP (?:PUBLIC KEY BLOCK|PRIVATE KEY BLOCK|SIGNATURE|MESSAGE)-----",
    re.DOTALL,
)
_SQL_INJECTION_RE = re.compile(
    r"(?:\bUNION\s+SELECT\b|\bOR\s+1\s*=\s*1\b|'\s*OR\s*'1'\s*=\s*'1|\bDROP\s+TABLE\b|;\s*--)",
    re.IGNORECASE,
)
_ONION_LINK_RE = re.compile(r"\b[a-z2-7]{56}\.onion\b", re.IGNORECASE)
_DISCORD_RE = re.compile(r"\bdiscord(?:\.gg|\.com/invite)/[A-Za-z0-9-]{2,32}\b", re.IGNORECASE)
_X_HANDLE_RE = re.compile(r"\b(?:twitter\.com|x\.com)/[A-Za-z0-9_]{1,15}\b", re.IGNORECASE)
_SESSION_ID_RE = re.compile(r"\b05[0-9a-f]{64}\b", re.IGNORECASE)
_COMPANY_RE = re.compile(
    r"\b(?:[A-Z][a-zA-Z&,.'-]{1,30}\s){1,4}(?:Inc\.?|LLC|Ltd\.?|GmbH|Corp\.?|PLC|S\.A\.|B\.V\.)\b"
)

MAX_PER_TYPE = 10
MAX_DECODE_CANDIDATES = 40

_IBAN_COUNTRY_LENGTHS = {
    "AD": 24, "AE": 23, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28,
    "CZ": 24, "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27,
    "GB": 22, "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27,
    "LI": 21, "LT": 20, "LU": 20, "LV": 21, "MT": 31, "NL": 18, "NO": 15,
    "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27,
}


def _is_valid_iban(candidate):
    """MOD-97 checksum, per the ISO 13616 algorithm - the same kind of
    real validation pii.py applies to credit cards via Luhn, so a
    random uppercase-alphanumeric string that merely fits IBAN's shape
    doesn't get treated as a real one."""
    expected_len = _IBAN_COUNTRY_LENGTHS.get(candidate[:2])
    if expected_len is None or len(candidate) != expected_len:
        return False
    rearranged = candidate[4:] + candidate[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def _fingerprint(block):
    return hashlib.sha256(block.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _is_mostly_printable(decoded):
    allowed_whitespace = (chr(9), chr(10), chr(13))
    printable_count = sum(1 for c in decoded if c.isprintable() or c in allowed_whitespace)
    return printable_count / len(decoded) >= 0.9


def _decode_embedded_content(text):
    """Finds base64/hex-shaped substrings, decodes them, and keeps only
    decodes that come back as genuinely readable text - most base64-
    looking runs on a real web page are asset hashes, JS bundle IDs, or
    data-URI images, not hidden content, so this only surfaces a decode
    when it plausibly IS text worth re-scanning for entities."""
    decoded_texts = []
    candidates = (_BASE64_CANDIDATE_RE.findall(text) + _HEX_CANDIDATE_RE.findall(text))[
        :MAX_DECODE_CANDIDATES
    ]
    for candidate in candidates:
        raw = None
        try:
            raw = base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError):
            pass
        if raw is None:
            try:
                raw = bytes.fromhex(candidate)
            except ValueError:
                continue
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(decoded) < 8:
            continue
        if not _is_mostly_printable(decoded):
            continue
        decoded_texts.append(decoded)
    return decoded_texts


def extract_entities(text):
    if not text:
        return []
    text = text[:20000]
    found = []
    seen = set()
    counts = {}

    def add(entity_type, matches):
        for value in matches:
            if counts.get(entity_type, 0) >= MAX_PER_TYPE:
                break
            key = (entity_type, value)
            if key in seen:
                continue
            seen.add(key)
            found.append({"entity_type": entity_type, "entity_value": value})
            counts[entity_type] = counts.get(entity_type, 0) + 1

    add("btc", _BTC_LEGACY_RE.findall(text))
    add("btc", _BTC_BECH32_RE.findall(text))
    add("eth", _ETH_RE.findall(text))
    add("xmr", _XMR_RE.findall(text))
    add("ip", _IPV4_RE.findall(text))
    add("cve", [m.upper() for m in _CVE_RE.findall(text)])
    add("session_token", _JWT_RE.findall(text))
    add("phone", _PHONE_RE.findall(text))
    add("api_key", _API_KEY_RE.findall(text))
    add("iban", [m for m in _IBAN_RE.findall(text) if _is_valid_iban(m)])
    add("certificate", [_fingerprint(m) for m in _CERT_BLOCK_RE.findall(text)])
    add("private_key", [_fingerprint(m) for m in _PRIVATE_KEY_BLOCK_RE.findall(text)])
    add("bin", _BIN_RE.findall(text))
    add("price", _PRICE_RE.findall(text))
    add("telegram_handle", _TELEGRAM_RE.findall(text))
    add("vendor_handle", _VENDOR_HANDLE_RE.findall(text))
    add("card_type", [name for name, pattern in _CARD_TYPE_KEYWORDS.items() if pattern.search(text)])
    add("bitcoin_private_key", [_fingerprint(m) for m in _BTC_PRIVATE_KEY_WIF_RE.findall(text)])
    add("crypto_wallet_seed_phrase", [_fingerprint(m) for m in _SEED_PHRASE_RE.findall(text)])
    add("pgp_key", [_fingerprint(m) for m in _PGP_BLOCK_RE.findall(text)])
    add("sql_injection", [m.strip() for m in _SQL_INJECTION_RE.findall(text)])
    add("onion_link", [m.lower() for m in _ONION_LINK_RE.findall(text)])
    add("social_handle", _DISCORD_RE.findall(text) + _X_HANDLE_RE.findall(text) + [m.lower() for m in _SESSION_ID_RE.findall(text)])
    add("company_identifier", [m.strip() for m in _COMPANY_RE.findall(text)])
    add("encoded_blob", [_fingerprint(c) for c in (_BASE64_CANDIDATE_RE.findall(text) + _HEX_CANDIDATE_RE.findall(text))[:MAX_DECODE_CANDIDATES]])

    # Re-scan anything that decoded to genuine readable text for the same
    # plain-value entity types - a hidden BTC address or email inside a
    # base64 blob is exactly the kind of thing worth surfacing. Certs/
    # keys (and the other fingerprint-only types added alongside them)
    # aren't re-scanned again from here - one decode layer is enough.
    for decoded in _decode_embedded_content(text):
        add("btc", _BTC_LEGACY_RE.findall(decoded))
        add("btc", _BTC_BECH32_RE.findall(decoded))
        add("eth", _ETH_RE.findall(decoded))
        add("xmr", _XMR_RE.findall(decoded))
        add("ip", _IPV4_RE.findall(decoded))
        add("cve", [m.upper() for m in _CVE_RE.findall(decoded)])
        add("session_token", _JWT_RE.findall(decoded))
        add("phone", _PHONE_RE.findall(decoded))
        add("api_key", _API_KEY_RE.findall(decoded))
        add("iban", [m for m in _IBAN_RE.findall(decoded) if _is_valid_iban(m)])
        add("onion_link", [m.lower() for m in _ONION_LINK_RE.findall(decoded)])
        add("sql_injection", [m.strip() for m in _SQL_INJECTION_RE.findall(decoded)])

    return found
