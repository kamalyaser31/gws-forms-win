# -*- coding: utf-8 -*-
"""
form_reader.py — Read all responses from an existing Google Form.

Usage:
    python form_reader.py --id FORM_ID
    python form_reader.py --id FORM_ID --after "2026-01-01T00:00:00Z"
    python form_reader.py --id FORM_ID --output my_responses.json
    python form_reader.py --url "https://docs.google.com/forms/d/.../edit"

Output:
    <form_id>_responses.json  (or --output path)

Rules:
    - Fully paginates via nextPageToken — no response limit.
    - Rejects /e/ encoded viewform URLs (can't extract form_id).
    - Does NOT require a snapshot — completely independent.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# ── locate siblings ───────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_DIR.parent
sys.path.insert(0, str(SKILL_DIR))
from form_builder import run_gws  # noqa: E402

# ─── URL parsing (shared logic with form_fetcher) ─────────────────────────────
_EDIT_RE     = re.compile(r"/forms/d/([^/]+)/(?:edit|viewform)")
_ENCODED_RE  = re.compile(r"/forms/d/e/([^/]+)/viewform")


def extract_form_id(url: str) -> str:
    if _ENCODED_RE.search(url):
        print(
            "[ERROR] Encoded viewform URL (/e/...) does not expose the form_id.\n"
            "        Use the Edit URL or --id directly."
        )
        sys.exit(1)
    m = _EDIT_RE.search(url)
    if m:
        return m.group(1)
    print(
        "[ERROR] Could not extract form_id from URL.\n"
        "        Use: https://docs.google.com/forms/d/<ID>/edit  or --id <ID>"
    )
    sys.exit(1)


# ─── Response fetching with full pagination ───────────────────────────────────

def fetch_all_responses(form_id: str, after: str = "") -> list:
    """Fetch every response page until nextPageToken is exhausted."""
    all_responses = []
    page_token = None

    while True:
        params = {"formId": form_id, "pageSize": 100}
        if after:
            params["filter"] = f'timestamp > "{after}"'
        if page_token:
            params["pageToken"] = page_token

        data = run_gws(["forms", "forms", "responses", "list"], params=params)
        page = data.get("responses", [])
        all_responses.extend(page)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_responses


# ─── Response normalisation ───────────────────────────────────────────────────

def normalise_response(raw_resp: dict) -> dict:
    """Flatten a raw FormResponse into a clean dict."""
    answers = {}
    for q_id, ans_block in raw_resp.get("answers", {}).items():
        text_answers = ans_block.get("textAnswers", {}).get("answers", [])
        answers[q_id] = [a.get("value", "") for a in text_answers]

    return {
        "responseId":       raw_resp.get("responseId", ""),
        "createTime":       raw_resp.get("createTime", ""),
        "lastSubmittedTime": raw_resp.get("lastSubmittedTime", ""),
        "answers":          answers,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Read all responses from a Google Form and save as JSON."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id",  dest="form_id", help="Form ID")
    group.add_argument("--url", dest="url",     help="Edit URL or plain viewform URL")
    parser.add_argument(
        "--after",
        default="",
        metavar="RFC3339",
        help="Only fetch responses submitted after this timestamp (e.g. 2026-01-01T00:00:00Z)",
    )
    parser.add_argument(
        "--output",
        default="",
        metavar="PATH",
        help="Output file path (default: <form_id>_responses.json in cwd)",
    )
    args = parser.parse_args()

    form_id = args.form_id if args.form_id else extract_form_id(args.url)
    out_path = args.output or f"{form_id}_responses.json"

    print(f"  >> Fetching responses for form: {form_id}")
    if args.after:
        print(f"     Filter  : after {args.after}")

    raw_responses = fetch_all_responses(form_id, after=args.after)
    clean = [normalise_response(r) for r in raw_responses]

    output = {
        "form_id":    form_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filter_after": args.after or None,
        "total":      len(clean),
        "responses":  clean,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] {len(clean)} response(s) saved -> {out_path}")


if __name__ == "__main__":
    main()
