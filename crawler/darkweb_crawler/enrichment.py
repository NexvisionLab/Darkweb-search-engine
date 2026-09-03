"""Page enrichment: content category, language, and a PII-presence flag -
all computed by local, free, lightweight models. No external API, no
API key, no per-call cost, and nothing here depends on any specific LLM
vendor - deliberately so, since this code is meant for a public repo."""
from . import classification, language, pii


def classify_page(title, body_text):
    category = classification.classify(title, body_text)
    pii_present = pii.detect(body_text)

    # Semantic similarity can't recognize a raw data table as "leaked data" -
    # a CSV of names/emails doesn't read as language, so it scores low
    # against every category regardless of wording. A table-shaped page that
    # also contains PII is a strong, independent signal this pass alone
    # would otherwise miss.
    if category == "other" and pii_present and classification.looks_tabular(body_text or ""):
        category = "leak-dump"

    return {
        "category": category,
        "language": language.detect(body_text),
        "pii_present": pii_present,
    }
