"""Regex-based PII presence detection - deliberately not an LLM judgment
call. Plain pattern matching is more precise and reliable for a narrow,
well-defined task like this, not just cheaper."""
import re

EMAIL_RE = re.compile(r"\b[a-zA-Z0-9_.+-]{1,50}@[a-zA-Z0-9-]{1,50}\.[a-zA-Z0-9-.]{1,50}[a-zA-Z0-9]\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
CREDENTIAL_HINT_RE = re.compile(r"\b(password|passwd|api[_-]?key|secret[_-]?key)\s*[:=]", re.IGNORECASE)


def _luhn_valid(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def detect(text: str) -> bool:
    """True if the text plausibly contains PII - emails, a Luhn-valid card
    number, an SSN-shaped number, or an exposed credential."""
    if not text:
        return False
    if EMAIL_RE.search(text):
        return True
    if SSN_RE.search(text):
        return True
    if CREDENTIAL_HINT_RE.search(text):
        return True
    for match in CREDIT_CARD_RE.findall(text):
        if _luhn_valid(match):
            return True
    return False


def mask_card_numbers(text: str) -> str:
    """Truncates every Luhn-valid card number found in text down to PCI
    DSS Requirement 3.3's own display ceiling - at most the first six
    and last four digits, the rest replaced with X. This is stricter
    than redact.py's existing PII handling (which masks at display
    time, keeping the raw text in Postgres for Pro/breach-checker
    matching): a live card number is different in kind from an email
    or a name, so it never gets stored unmasked at all - this runs on
    body_text before a surface-web carding-site page is ever written
    to the database, not as a later display filter something could
    slip past. BIN (the first 6-8 digits alone) stays visible - PCI
    DSS explicitly treats it as non-sensitive on its own, since it only
    identifies the issuing bank/program, not an account."""
    if not text:
        return text

    def _mask(match):
        raw = match.group(0)
        digits = [c for c in raw if c.isdigit()]
        if not _luhn_valid(raw):
            return raw
        masked_digits = digits[:6] + ["X"] * (len(digits) - 10) + digits[-4:]
        out = []
        di = 0
        for c in raw:
            if c.isdigit():
                out.append(masked_digits[di])
                di += 1
            else:
                out.append(c)
        return "".join(out)

    return CREDIT_CARD_RE.sub(_mask, text)
