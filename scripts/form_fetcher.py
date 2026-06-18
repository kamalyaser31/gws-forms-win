# -*- coding: utf-8 -*-
"""
form_fetcher.py — Fetch an existing Google Form and save a local snapshot.

Usage:
    python form_fetcher.py --id FORM_ID
    python form_fetcher.py --url "https://docs.google.com/forms/d/.../edit"

Output:
    SKILL_DIR/snapshots/<form_id>_snapshot.json

Rules:
    - Viewform URLs containing /e/ are rejected (they don't expose form_id).
    - Snapshots older than 30 minutes trigger a warning in form_updater.
    - api_type and question_type are stored verbatim from the API response.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

# ── locate siblings ───────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent  # scripts/
SKILL_ROOT = SKILL_DIR.parent                # skill root
SNAPSHOTS_DIR = SKILL_ROOT / "snapshots"

sys.path.insert(0, str(SKILL_DIR))
from form_builder import get_form  # noqa: E402


# ─── URL parsing ──────────────────────────────────────────────────────────────

# Matches: /forms/d/<form_id>/edit  or  /forms/d/<form_id>/viewform (no /e/)
_EDIT_RE = re.compile(r"/forms/d/([^/]+)/(?:edit|viewform)")
# Matches the encoded responder URL /forms/d/e/LONG_ID/viewform
_ENCODED_RE = re.compile(r"/forms/d/e/([^/]+)/viewform")


def extract_form_id(url: str) -> str:
    """
    Extract form_id from an Edit URL or a plain viewform URL.
    Raises SystemExit for encoded /e/ responder URLs.
    """
    if _ENCODED_RE.search(url):
        print(
            "[ERROR] Encoded viewform URL (/e/...) does not expose the form_id.\n"
            "        Use the Edit URL (opens in Google Forms editor) or --id directly."
        )
        sys.exit(1)

    m = _EDIT_RE.search(url)
    if m:
        return m.group(1)

    print(
        "[ERROR] Could not extract form_id from URL.\n"
        "        Provide an Edit URL: https://docs.google.com/forms/d/<ID>/edit\n"
        "        or use --id <FORM_ID> directly."
    )
    sys.exit(1)


# ─── Snapshot building ────────────────────────────────────────────────────────

def _item_type(raw_item: dict) -> tuple:
    """Return (api_type, question_type) from a raw API item dict."""
    for api_type in ("questionItem", "questionGroupItem", "pageBreakItem",
                     "textItem", "imageItem", "videoItem"):
        if api_type in raw_item:
            if api_type == "questionItem":
                q = raw_item["questionItem"].get("question", {})
                for qt in ("textQuestion", "choiceQuestion", "scaleQuestion",
                            "dateQuestion", "timeQuestion", "ratingQuestion",
                            "fileUploadQuestion"):
                    if qt in q:
                        return api_type, qt
                return api_type, "unknown"
            return api_type, None
    return "unknown", None


def build_snapshot(form_id: str, raw: dict) -> dict:
    """Convert raw API response into a clean, agent-readable snapshot."""
    items = []
    for idx, raw_item in enumerate(raw.get("items", [])):
        api_type, question_type = _item_type(raw_item)
        entry = {
            "index": idx,
            "itemId": raw_item.get("itemId", ""),
            "title": raw_item.get("title", ""),
            "description": raw_item.get("description", ""),
            "api_type": api_type,
        }
        if question_type is not None:
            entry["question_type"] = question_type
        if api_type == "questionItem":
            q = raw_item["questionItem"].get("question", {})
            entry["required"] = q.get("required", False)
        items.append(entry)

    return {
        "form_id": form_id,
        "title": raw.get("info", {}).get("title", ""),
        "description": raw.get("info", {}).get("description", ""),
        "document_title": raw.get("info", {}).get("documentTitle", ""),
        "responderUri": raw.get("responderUri", ""),
        "revisionId": raw.get("revisionId", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items),
        "items": items,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch a Google Form and save a local snapshot JSON."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id",  dest="form_id", help="Form ID")
    group.add_argument("--url", dest="url",     help="Edit URL or plain viewform URL")
    args = parser.parse_args()

    form_id = args.form_id if args.form_id else extract_form_id(args.url)

    print(f"  >> Fetching form: {form_id}")
    raw = get_form(form_id)

    snapshot = build_snapshot(form_id, raw)

    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    out_path = SNAPSHOTS_DIR / f"{form_id}_snapshot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Snapshot saved")
    print(f"     Items    : {snapshot['item_count']}")
    print(f"     Title    : {snapshot['title']}")
    print(f"     Path     : {out_path}")


if __name__ == "__main__":
    main()
