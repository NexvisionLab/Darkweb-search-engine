"""Zero-shot content-category classification via sentence embeddings -
no training data needed, no external API, fully local after the
one-time model download. Cosine similarity between the page's embedding
and each category's description embedding; falls back to "other" when
nothing matches confidently.

Semantic similarity alone misses raw tabular dumps (e.g. a leaked CSV of
names/emails/phone numbers): a comma-delimited data table doesn't read
as language, so it scores low against every category's prose
description regardless of wording or threshold - confirmed by direct
measurement, not assumption. looks_tabular() gives enrichment.py a
second, non-semantic signal for that specific blind spot."""
import re
from statistics import median

from sentence_transformers import SentenceTransformer, util

CATEGORY_DESCRIPTIONS = {
    "marketplace": "An online marketplace or shop selling physical or digital goods, with product listings, prices, vendor ratings, or a shopping cart.",
    "forum": "A discussion forum or message board with threads, posts, and replies between users.",
    "leak-dump": "A page listing or offering leaked, stolen, or breached data such as databases, credentials, or personal records for download.",
    "fraud": "A page related to financial fraud, scams, phishing, fake documents, or stolen financial instruments.",
    "carding": "A page selling or discussing stolen credit or debit card data, such as card dumps, fullz, CVV shops, or BIN checkers.",
    "crypto-services": "A page offering cryptocurrency exchange, mixing, tumbling, or wallet services rather than a general marketplace listing.",
    "counterfeits": "A page selling counterfeit or forged physical goods such as fake passports, ID cards, certificates, currency, or branded products.",
    "drugs": "A page advertising or discussing illegal drugs or controlled substances for sale.",
    "legitimate-mirror": "An official mirror or onion service of a legitimate, well-known organization, news outlet, or privacy tool.",
    "ransomware": "A ransomware group's leak site listing extortion victims, stolen files, or ransom negotiation details.",
    "hacking-services": "A page offering hacking-for-hire, DDoS attack services, exploit sales, malware-as-a-service, or initial network access for sale.",
    "weapons": "A page advertising or discussing firearms, explosives, or other weapons for sale.",
    "breach-forum": "A discussion forum specifically dedicated to sharing, trading, or discussing data breaches and leaked databases.",
    "extremism-violence": "A page containing extremist propaganda, incitement to violence, or content promoting terrorism or hate-motivated violence. Internal safety-classification use only, never a browsable search category.",
    "csam": "A page containing child sexual abuse material or content sexualizing minors. Internal safety-classification use only, never a browsable search category - triggers a hard content block, not a rating label.",
    "other": "Informational, personal, or miscellaneous content that doesn't fit any specific category above.",
}

# Categories that exist purely for internal safety-rating precision -
# never exposed as a filter value in the public API (VALID_CATEGORIES in
# api/main.py deliberately omits them) and never shown as a browsable
# chip in the UI, regardless of tier. Kept in one place so anything that
# needs to exclude them (API validation, UI category lists, future admin
# tooling) reads from the same source instead of re-deriving the list.
INTERNAL_ONLY_CATEGORIES = {"extremism-violence", "csam"}

MODEL_NAME = "all-MiniLM-L6-v2"
CONFIDENCE_THRESHOLD = 0.25  # below this, the match isn't confident enough to trust

_DELIMITER_RE = re.compile(r"[,\t]")
_TABULAR_MIN_LINES = 5
_TABULAR_MIN_FIELDS = 3  # a row needs at least this many delimiters to count as "row-shaped"
_TABULAR_MIN_CONSISTENT_RATIO = 0.6  # this fraction of sampled lines must share a similar field count

_model = None
_category_embeddings = None
_category_names = list(CATEGORY_DESCRIPTIONS.keys())


def _get_model():
    global _model, _category_embeddings
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        _category_embeddings = _model.encode(
            list(CATEGORY_DESCRIPTIONS.values()), convert_to_tensor=True
        )
    return _model


def classify(title: str, body_text: str) -> str:
    model = _get_model()
    text = f"{title or ''}. {(body_text or '')[:2000]}".strip()
    if not text or text == ".":
        return "other"
    page_embedding = model.encode(text, convert_to_tensor=True)
    scores = util.cos_sim(page_embedding, _category_embeddings)[0]
    best_idx = int(scores.argmax())
    if float(scores[best_idx]) < CONFIDENCE_THRESHOLD:
        return "other"
    return _category_names[best_idx]


def looks_tabular(text: str) -> bool:
    """True if the text looks like rows of a delimited table (CSV/TSV-style
    export) rather than prose - many lines with a similar, nontrivial
    number of delimiters."""
    if not text:
        return False
    lines = [line for line in text.splitlines() if line.strip()][:30]
    if len(lines) < _TABULAR_MIN_LINES:
        return False
    counts = [len(_DELIMITER_RE.findall(line)) for line in lines]
    qualifying = [c for c in counts if c >= _TABULAR_MIN_FIELDS]
    if len(qualifying) < _TABULAR_MIN_LINES:
        return False
    typical = median(qualifying)
    consistent = sum(1 for c in counts if typical * 0.5 <= c <= typical * 1.5)
    return consistent / len(lines) >= _TABULAR_MIN_CONSISTENT_RATIO


def embed(text):
    """A real embedding vector for semantic search - reuses the same
    already-loaded model as classify(), not a second model, since
    all-MiniLM-L6-v2 is perfectly usable for this too. Added during a
    Free-tier feature-completeness pass: the OpenSearch index has
    carried an unused "embedding" placeholder field since the schema
    was first written ("adjust once model is chosen") - this is that
    model, chosen because it is already resident in memory for
    classification, not a new dependency."""
    if not text or not text.strip():
        return None
    model = _get_model()
    vector = model.encode(text[:2000], convert_to_tensor=False)
    return vector.tolist()
