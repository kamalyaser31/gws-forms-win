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

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_SCRIPTS.parent
sys.path.insert(0, str(SKILL_SCRIPTS))

from form_builder import (  # noqa: E402
    GwsCommandError,
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
    update_form_info_request,
)
from json_files import write_json_atomic  # noqa: E402

# ─── dispatcher ───────────────────────────────────────────────────────────────


def _section_request(item: dict, index: int) -> dict:
    return make_page_break(item["title"], index, item.get("desc", ""))


def _text_request(item: dict, index: int) -> dict:
    return make_text_item(item["title"], index, item.get("desc", ""))


def _short_request(item: dict, index: int) -> dict:
    return make_short_answer(
        item["q"],
        index,
        paragraph=item.get("paragraph", True),
        required=item.get("required", True),
    )


def _mcq_request(item: dict, index: int) -> dict:
    if "correct" not in item:
        return make_mcq(
            item["q"],
            item["options"],
            index,
            question_type=item.get("qtype", "RADIO"),
            shuffle=item.get("shuffle", False),
            required=item.get("required", True),
        )
    return make_mcq_graded(
        item["q"],
        item["options"],
        index,
        correct=item["correct"],
        points=item.get("points", 1),
        feedback_right=item.get("right", "Correct!"),
        feedback_wrong=item.get("wrong", ""),
        question_type=item.get("qtype", "RADIO"),
        required=item.get("required", True),
    )


def _scale_request(item: dict, index: int) -> dict:
    return make_scale(
        item["q"],
        index,
        low=item.get("low", 1),
        high=item.get("high", 5),
        low_label=item.get("low_label", ""),
        high_label=item.get("high_label", ""),
        required=item.get("required", False),
    )


def _date_request(item: dict, index: int) -> dict:
    return make_date(
        item["q"],
        index,
        include_time=item.get("time", False),
        include_year=item.get("year", True),
        required=item.get("required", False),
    )


def _time_request(item: dict, index: int) -> dict:
    return make_time(
        item["q"],
        index,
        duration=item.get("duration", False),
        required=item.get("required", False),
    )


def _rating_request(item: dict, index: int) -> dict:
    return make_rating(
        item["q"],
        index,
        scale=item.get("scale", 5),
        icon=item.get("icon", "STAR"),
        required=item.get("required", False),
    )


def _grid_request(item: dict, index: int) -> dict:
    return make_grid(
        item["title"],
        item["rows"],
        item["cols"],
        index,
        col_type=item.get("col_type", "RADIO"),
        shuffle_rows=item.get("shuffle_rows", False),
        required=item.get("required", False),
    )


def _video_request(item: dict, index: int) -> dict:
    return make_video(
        item["title"],
        item["uri"],
        index,
        caption=item.get("caption", ""),
        alignment=item.get("align", "CENTER"),
        width=item.get("width", 640),
    )


def _image_request(item: dict, index: int) -> dict:
    return make_image(
        item["title"],
        item["uri"],
        index,
        alt_text=item.get("alt", ""),
        alignment=item.get("align", "CENTER"),
        width=item.get("width", 640),
    )


ITEM_REQUEST_BUILDERS = {
    "section": _section_request,
    "text": _text_request,
    "short": _short_request,
    "mcq": _mcq_request,
    "scale": _scale_request,
    "date": _date_request,
    "time": _time_request,
    "rating": _rating_request,
    "grid": _grid_request,
    "video": _video_request,
    "image": _image_request,
}


def dispatch(item: dict, index: int) -> dict:
    """Convert one JSON item specification into a createItem request."""
    item_type = item.get("type", "").lower()
    request_builder = ITEM_REQUEST_BUILDERS.get(item_type)
    if request_builder is None:
        raise ValueError(f"Unknown item type: '{item_type}'")
    return request_builder(item, index)


# ─── main ─────────────────────────────────────────────────────────────────────


def build_requests(spec: dict) -> list:
    requests = []
    description = spec.get("desc") or spec.get("description")
    if description:
        requests.append(update_form_info_request(description=description))
    for idx, item in enumerate(spec.get("items", [])):
        requests.append(dispatch(item, idx))
    return requests


def copy_responder_url(responder_url: str) -> None:
    subprocess.run(["clip"], input=responder_url, text=True, check=True, shell=False)


def append_history(history_path: Path, entry: dict) -> None:
    history = []
    if history_path.exists():
        with history_path.open(encoding="utf-8") as history_file:
            history = json.load(history_file)
        if not isinstance(history, list):
            raise ValueError("history.json must contain a JSON array")
    history.append(entry)
    write_json_atomic(history_path, history)


def form_history_entry(title: str, created_form: dict) -> dict:
    return {
        "title": title,
        "formId": created_form["formId"],
        "responderUri": created_form["responderUri"],
        "editUrl": created_form["editUrl"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def record_local_outputs(title: str, created_form: dict) -> None:
    try:
        copy_responder_url(created_form["responderUri"])
        print("[OK] Responder URL copied to clipboard.")
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"[WARN] Failed to copy to clipboard: {error}", file=sys.stderr)

    try:
        history_path = SKILL_ROOT / "history.json"
        append_history(history_path, form_history_entry(title, created_form))
        print("[OK] Form saved to local history log.")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[WARN] Failed to write history log: {error}", file=sys.stderr)


def print_created_form(created_form: dict) -> None:
    print("\n" + "=" * 60)
    print(f"Form ID   : {created_form['formId']}")
    print(f"Responder : {created_form['responderUri']}")
    print(f"Edit URL  : {created_form['editUrl']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Create a Google Form from JSON.")
    parser.add_argument("spec", type=Path, help="Path to the form JSON spec")
    args = parser.parse_args()

    with args.spec.open(encoding="utf-8") as spec_file:
        spec = json.load(spec_file)

    title = spec["title"]
    created_form = build_form(
        title,
        build_requests(spec),
        document_title=spec.get("doc_title", title),
        quiz_mode=spec.get("quiz", False),
    )

    print_created_form(created_form)
    record_local_outputs(title, created_form)


if __name__ == "__main__":
    try:
        main()
    except GwsCommandError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(error.returncode)
