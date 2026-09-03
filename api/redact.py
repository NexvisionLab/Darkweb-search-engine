"""Masks PII in public-facing text. Applied to every snippet/title the
free-tier API returns to anonymous visitors - a leak-dump page is real
people's actual data, and showing it unmasked to anyone who searches
for it isn't something a public tool should default to."""
import re

EMAIL_RE = re.compile(r"\b([a-zA-Z0-9_.+-])([a-zA-Z0-9_.+-]*)(@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b")
PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\-\s().]{7,}\d)(?!\d)")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _mask_email(match: re.Match) -> str:
    first, rest, domain = match.group(1), match.group(2), match.group(3)
    return f"{first}{'*' * max(len(rest), 3)}{domain}"


def _mask_digits(match: re.Match) -> str:
    text = match.group(0)
    digit_positions = [i for i, c in enumerate(text) if c.isdigit()]
    if len(digit_positions) < 6:
        return text
    keep = set(digit_positions[:2]) | set(digit_positions[-2:])
    return "".join(c if (i not in digit_positions or i in keep) else "*" for i, c in enumerate(text))


def redact(text):
    if not text:
        return text
    text = EMAIL_RE.sub(_mask_email, text)
    text = SSN_RE.sub(_mask_digits, text)
    text = CREDIT_CARD_RE.sub(_mask_digits, text)
    text = PHONE_RE.sub(_mask_digits, text)
    return text
