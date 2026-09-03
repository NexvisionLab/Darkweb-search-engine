"""Captures a homepage screenshot for each known onion domain that
doesn't have a recent one, via Playwright/Chromium routed through the
same Tor/Privoxy proxy the crawler itself uses. One screenshot per
domain (a result thumbnail, not a full-site preview), capped per run
so a single pipeline pass doesn't spend unbounded time in headless
Chromium.

Security note: unlike the text-only Scrapy crawler (which never
executes JavaScript or renders anything), this launches a real browser
against untrusted, adversarial content - a materially different risk
profile. Mitigated by Chromium's default sandboxing (not disabled
here), running as an unprivileged user, and a hard page-load timeout -
not a fully isolated render-per-page, which would need its own
sandboxed VM to do properly.

Sensitive-content gate: every rendered screenshot passes through
NudeNet (a self-hosted classifier, no data leaves this machine) before
it's saved anywhere. A flagged image is discarded outright, not saved
and hidden - the point is that it never exists as a file at all, not
just that the UI declines to show it. This only catches exposed
nudity/adult content, not a general graphic-content or CSAM check -
NudeNet is not a CSAM classifier, and building one in-house would
require possessing the training material, which is illegal; real CSAM
detection needs hash-matching via an authorized partner (NCMEC/Thorn)
and doesn't exist in this pipeline yet.

Gated domains (Suspicious/Dangerous safety_rating) save to
GATED_PREVIEW_DIR instead of the public web/previews/ - that directory
sits outside nginx's web root entirely and is only ever served through
api/main.py's /preview/{host} endpoint, which re-checks the domain's
rating server-side before returning bytes. web/previews/ (nginx static,
no gating) is for ungated domains only - a Dangerous-rated screenshot
must never be reachable as a bare guessable static file.

Description generation: Qwen3.5 (the local model already running for
page summarization, see api/summarize.py) has no vision variant - only
the text model is downloaded, and pulling in a separate vision-language
model wasn't justified for what's overwhelmingly text-heavy dark-web
UI. Instead, the screenshot is OCR'd (RapidOCR, the same engine used
for crawled-page images in process_page_images.py) and that text, plus
the domain host, is synthesized into a short description by the same
local text model - not true multimodal image understanding, but a
genuinely useful "what does this look like" description for something
that's mostly rendered text and UI chrome anyway. Calls the local
llama-server directly over HTTP rather than importing api/summarize.py,
since crawler/ and api/ deliberately don't import each other."""
import io
import os
import re
import sys

import httpx

sys.path.insert(0, ".")
from darkweb_crawler import db
from PIL import Image
from playwright.sync_api import sync_playwright

TOR_PROXY = os.environ.get("TOR_PROXY", "http://127.0.0.1:8118")
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREVIEW_DIR = os.path.join(_REPO_ROOT, "web", "previews")
GATED_PREVIEW_DIR = os.path.join(_REPO_ROOT, "previews_gated")
MAX_PER_RUN = 30
STALE_DAYS = 7
PAGE_TIMEOUT_MS = 25000
THUMB_SIZE = (480, 300)
NUDITY_SCORE_THRESHOLD = 0.5

SUMMARIZER_URL = os.environ.get("SUMMARIZER_URL", "http://127.0.0.1:8081/v1/completions")
DESCRIPTION_TIMEOUT_SECONDS = 30
DESCRIPTION_SYSTEM_PROMPT = (
    "You describe a screenshot of a dark-web page for a search result caption. "
    "You are given the site's address and text read off the screenshot via OCR (it may be "
    "messy or fragmentary). Write one short factual sentence describing what the page appears "
    "to be. Never invent details the text doesn't support. If the OCR text is too sparse to say "
    "anything meaningful, say only that a preview is available."
)

# Matches api/labels.py's severity mapping - duplicated here deliberately
# rather than importing across the crawler/api package boundary those two
# packages otherwise keep independent.
GATED_RATINGS = {
    "illicit-marketplace", "fraud-risk", "confirmed-leak",
    "malware-risk", "phishing-clone-suspect", "exit-scam-suspect",
}

_detector = None
_ocr_engine = None


def _get_detector():
    global _detector
    if _detector is None:
        from nudenet import NudeDetector
        _detector = NudeDetector()
    return _detector


def is_sensitive(image_path):
    result = _get_detector().detect(image_path)
    return any(r["score"] > NUDITY_SCORE_THRESHOLD for r in result)


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_screenshot(image_path):
    try:
        import numpy as np
        img = Image.open(image_path).convert("RGB")
        result, _ = _get_ocr_engine()(np.array(img))
        if not result:
            return ""
        return " ".join(r[1] for r in result)
    except Exception as e:
        print(f"  OCR failed on screenshot: {e}")
        return ""


def _build_description_prompt(host, ocr_text):
    user_content = f"Site: {host}\n\nText read from the screenshot:\n{ocr_text[:2000] or '(none found)'}"
    return (
        "<|im_start|>system\n"
        f"{DESCRIPTION_SYSTEM_PROMPT}<|im_end|>\n"
        "<|im_start|>user\n"
        f"{user_content}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def generate_description(host, ocr_text):
    prompt = _build_description_prompt(host, ocr_text)
    try:
        with httpx.Client(timeout=DESCRIPTION_TIMEOUT_SECONDS) as client:
            response = client.post(
                SUMMARIZER_URL,
                json={
                    "prompt": prompt,
                    "temperature": 0.2,
                    "max_tokens": 100,
                    "stop": ["<|im_end|>", "<|im_start|>"],
                },
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["text"].strip()
    except Exception as e:
        print(f"  description generation failed: {e}")
        return None


def safe_filename(host):
    return re.sub(r"[^a-z0-9.]", "_", host.lower()) + ".png"


def main():
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    os.makedirs(GATED_PREVIEW_DIR, exist_ok=True)
    conn = db.get_connection()
    domains = db.get_domains_needing_preview(conn, STALE_DAYS, MAX_PER_RUN)
    if not domains:
        print("No domains need a preview capture")
        conn.close()
        return

    captured = 0
    withheld = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(proxy={"server": TOR_PROXY})
        for domain_id, host, safety_rating in domains:
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 640})
                page.goto(f"http://{host}/", timeout=PAGE_TIMEOUT_MS, wait_until="load")
                raw_bytes = page.screenshot()
                page.close()

                img = Image.open(io.BytesIO(raw_bytes))
                img.thumbnail(THUMB_SIZE)
                tmp_path = os.path.join(GATED_PREVIEW_DIR, ".tmp_" + safe_filename(host))
                img.save(tmp_path, optimize=True)

                if is_sensitive(tmp_path):
                    os.remove(tmp_path)
                    withheld += 1
                    print(f"withheld (sensitive content): {host}")
                else:
                    dest_dir = GATED_PREVIEW_DIR if safety_rating in GATED_RATINGS else PREVIEW_DIR
                    final_path = os.path.join(dest_dir, safe_filename(host))
                    os.replace(tmp_path, final_path)
                    captured += 1

                    ocr_text = _ocr_screenshot(final_path)
                    description = generate_description(host, ocr_text)
                    if description:
                        db.update_domain_preview_description(conn, domain_id, description)

                    print(f"captured ({'gated' if dest_dir == GATED_PREVIEW_DIR else 'public'}): {host}"
                          f"{' - ' + description if description else ''}")
                db.update_domain_preview_captured(conn, domain_id)
            except Exception as e:
                print(f"failed: {host} ({e})")
                db.update_domain_preview_captured(conn, domain_id)  # don't retry every run
        browser.close()

    print(f"Captured {captured}/{len(domains)} previews, withheld {withheld} for sensitive content")
    conn.close()


if __name__ == "__main__":
    main()
