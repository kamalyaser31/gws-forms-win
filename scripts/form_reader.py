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
    - Does NOT require a snapshot: it fetches the form itself to label each
      answer with its question title.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── locate siblings ───────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from form_builder import (  # noqa: E402
    GwsCommandError,
    extract_form_id,
    get_form,
    list_responses,
    write_json_atomic,
)

# ─── Response normalisation ───────────────────────────────────────────────────


def question_titles(raw_form: dict) -> dict:
    """Map each questionId to a readable title; grid rows get 'Grid — Row'."""
    titles = {}
    for item in raw_form.get("items", []):
        item_title = item.get("title", "")
        question = item.get("questionItem", {}).get("question", {})
        if "questionId" in question:
            titles[question["questionId"]] = item_title
        for row in item.get("questionGroupItem", {}).get("questions", []):
            row_title = row.get("rowQuestion", {}).get("title", "")
            titles[row.get("questionId", "")] = f"{item_title} — {row_title}"
    return titles


def normalise_response(raw_resp: dict, titles: dict) -> dict:
    """Flatten a raw FormResponse into a clean dict."""
    answers = {}
    for q_id, ans_block in raw_resp.get("answers", {}).items():
        answer = {
            "questionId": ans_block.get("questionId", q_id),
            "title": titles.get(q_id, ""),
            "textAnswers": [
                a.get("value", "")
                for a in ans_block.get("textAnswers", {}).get("answers", [])
            ],
            "fileUploadAnswers": ans_block.get("fileUploadAnswers", {}).get(
                "answers", []
            ),
        }
        if "grade" in ans_block:
            answer["grade"] = ans_block["grade"]
        answers[q_id] = answer

    normalised = {
        "responseId": raw_resp.get("responseId", ""),
        "createTime": raw_resp.get("createTime", ""),
        "lastSubmittedTime": raw_resp.get("lastSubmittedTime", ""),
        "respondentEmail": raw_resp.get("respondentEmail", ""),
        "answers": answers,
    }
    if "totalScore" in raw_resp:
        normalised["totalScore"] = raw_resp["totalScore"]
    return normalised


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Read all responses from a Google Form and save as JSON."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", dest="form_id", help="Form ID")
    group.add_argument("--url", dest="url", help="Edit URL or plain viewform URL")
    parser.add_argument(
        "--after",
        default="",
        metavar="RFC3339",
        help=(
            "Only fetch responses submitted after this timestamp "
            "(e.g. 2026-01-01T00:00:00Z)"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default="",
        metavar="PATH",
        help=(
            "Output file path "
            "(default: <form_id>_responses.json in current directory)"
        ),
    )
    args = parser.parse_args()

    try:
        form_id = args.form_id if args.form_id else extract_form_id(args.url)
    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(1)
    out_path = (
        Path(args.output) if args.output else Path.cwd() / f"{form_id}_responses.json"
    )

    print(f"  >> Fetching responses for form: {form_id}")
    if args.after:
        print(f"     Filter  : after {args.after}")

    titles = question_titles(get_form(form_id))
    raw_responses = list_responses(form_id, after=args.after)
    clean = [normalise_response(r, titles) for r in raw_responses]

    output = {
        "form_id": form_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filter_after": args.after or None,
        "total": len(clean),
        "responses": clean,
    }

    write_json_atomic(Path(out_path), output)

    print(f"\n[OK] {len(clean)} response(s) saved -> {out_path}")


if __name__ == "__main__":
    try:
        main()
    except GwsCommandError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(error.returncode)
    except OSError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(1)
