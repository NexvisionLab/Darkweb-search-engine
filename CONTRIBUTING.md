# Contributing

Contributions are welcome — bug fixes, new safety tools, additional entity
types, better classification, documentation improvements.

## Ground rules

- **`api/` and `crawler/` don't import each other.** They're deployed and
  scaled independently; keep it that way. If a script genuinely needs both,
  it belongs in `crawler/scripts/` calling the crawler's own `db.py`, not
  reaching into `api/`.
- **No raw secrets, ever, in code.** Every credential is read from an
  environment variable (see `.env.example`) — never hardcoded, never given
  a real-looking default.
- **PII discipline**: if you're adding anything that touches personal data
  (emails, card numbers, names), match the existing pattern — hash or mask
  at the point of storage, not at display time. Look at `pii.py` and
  `email_extract.py` before adding a new field that might carry PII.
- **New entity types**: `entity_extract.py`'s existing types are all narrow,
  labeled, or format-validated on purpose (an IBAN is MOD-97 checksummed, a
  BIN only matches an explicitly-labeled `BIN: 123456` pattern, not a bare
  digit run) — this keeps false positives low without needing an LLM call.
  Follow the same discipline for anything new.
- **New content categories**: add to `classification.py`'s
  `CATEGORY_DESCRIPTIONS` (zero-shot, no retraining needed) *and* to
  `safety_rating.py`'s `CATEGORY_PRIORITY`/`RATING_BY_CATEGORY` — a category
  with no rating mapping silently falls through to "unclassified"
  regardless of how serious it actually is. This has been a real bug here
  before; don't repeat it.
- **Sensitive-content classification is internal-only by convention.**
  If you add a category like `csam`/`extremism-violence` that exists purely
  for safety-rating precision, add it to `INTERNAL_ONLY_CATEGORIES` and
  make sure it's excluded from `VALID_CATEGORIES` in `api/main.py` and from
  `/stats`' counts — never just "not shown in the UI," genuinely absent
  from every public response.

## Running tests / verifying a change

There's no CI pipeline bundled with this repo yet — verify manually:

```bash
# syntax + import check
python3 -m py_compile api/*.py crawler/darkweb_crawler/*.py

# a real classification/entity-extraction smoke test
cd crawler && python3 -c "
from darkweb_crawler.entity_extract import extract_entities
print(extract_entities('Contact: t.me/example, BTC: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'))
"
```

For anything touching the API, run it locally (`uvicorn api.main:app
--reload`) and hit the endpoint with `curl` before opening a PR.

## Pull requests

- Keep PRs scoped to one change. A bug fix doesn't need surrounding cleanup.
- Describe *why*, not just *what* — the diff already shows what changed.
- If you're adding a new environment variable, update `.env.example` and
  `docs/DEPLOYMENT.md` in the same PR.
