# -*- coding: utf-8 -*-
"""
json_runner.py — Data-driven Google Forms builder.

Usage:
    python json_runner.py path/to/form.json

The agent writes ONLY a compact JSON file (form spec).
This script does ALL the heavy lifting: parses the spec,
calls form_builder, and prints the URLs.

# JSON spec format -> see REFERENCE.md § JSON Spec
"""

import sys
import json
import os

SKILL_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SKILL_SCRIPTS)
sys.path.insert(0, SKILL_SCRIPTS)

from form_builder import (
    build_form,
    make_page_break,
    make_text_item,
    make_short_answer,
    make_mcq,
    make_mcq_graded,
    make_scale,
    make_date,
    make_time,
    make_rating,
    make_grid,
    make_video,
    make_image,
)

# ─── dispatcher ───────────────────────────────────────────────────────────────

def dispatch(item: dict, index: int) -> dict:
    """Convert one JSON item spec -> a createItem request dict."""
    t = item.get("type", "").lower()

    if t == "section":
        return make_page_break(item["title"], index, item.get("desc", ""))

    if t == "text":
        return make_text_item(item["title"], index, item.get("desc", ""))

    if t == "short":
        return make_short_answer(
            item["q"], index,
            paragraph=item.get("paragraph", True),
            required=item.get("required", True),
        )

    if t == "mcq":
        if "correct" in item:
            return make_mcq_graded(
                item["q"], item["options"], index,
                correct=item["correct"],
                points=item.get("points", 1),
                feedback_right=item.get("right", "Correct!"),
                feedback_wrong=item.get("wrong", ""),
                question_type=item.get("qtype", "RADIO"),
                required=item.get("required", True),
            )
        return make_mcq(
            item["q"], item["options"], index,
            question_type=item.get("qtype", "RADIO"),
            shuffle=item.get("shuffle", False),
            required=item.get("required", True),
        )

    if t == "scale":
        return make_scale(
            item["q"], index,
            low=item.get("low", 1), high=item.get("high", 5),
            low_label=item.get("low_label", ""),
            high_label=item.get("high_label", ""),
            required=item.get("required", False),
        )

    if t == "date":
        return make_date(item["q"], index,
                         include_time=item.get("time", False),
                         include_year=item.get("year", True),
                         required=item.get("required", False))

    if t == "time":
        return make_time(item["q"], index,
                         duration=item.get("duration", False),
                         required=item.get("required", False))

    if t == "rating":
        return make_rating(item["q"], index,
                           scale=item.get("scale", 5),
                           icon=item.get("icon", "STAR"),
                           required=item.get("required", False))

    if t == "grid":
        return make_grid(item["title"], item["rows"], item["cols"], index,
                         col_type=item.get("col_type", "RADIO"),
                         shuffle_rows=item.get("shuffle_rows", False),
                         required=item.get("required", False))

    if t == "video":
        return make_video(item["title"], item["uri"], index,
                          caption=item.get("caption", ""),
                          alignment=item.get("align", "CENTER"),
                          width=item.get("width", 640))

    if t == "image":
        return make_image(item["title"], item["uri"], index,
                          alt_text=item.get("alt", ""),
                          alignment=item.get("align", "CENTER"),
                          width=item.get("width", 640))

    raise ValueError(f"Unknown item type: '{t}'")


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python json_runner.py <form_spec.json>")
        sys.exit(1)

    spec_path = sys.argv[1]
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    title      = spec["title"]
    doc_title  = spec.get("doc_title", title)
    quiz_mode  = spec.get("quiz", False)
    raw_items  = spec.get("items", [])

    requests = []
    for idx, item in enumerate(raw_items):
        requests.append(dispatch(item, idx))

    result = build_form(title, requests,
                        document_title=doc_title,
                        quiz_mode=quiz_mode)

    print("\n" + "=" * 60)
    print(f"Form ID   : {result['formId']}")
    print(f"Responder : {result['responderUri']}")
    print(f"Edit URL  : {result['editUrl']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
