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
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_SCRIPTS.parent
sys.path.insert(0, str(SKILL_SCRIPTS))

from form_builder import (  # noqa: E402
    GwsCommandError,
    build_form,
    write_json_atomic,
)

# ─── main ─────────────────────────────────────────────────────────────────────


def append_history(history_path: Path, entry: dict) -> None:
    history = []
    if history_path.exists():
        with history_path.open(encoding="utf-8") as history_file:
            history = json.load(history_file)
        if not isinstance(history, list):
            raise ValueError("history file must contain a JSON array")
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


def record_local_outputs(
    title: str, created_form: dict, history_path: Path | None = None
) -> None:
    if not history_path:
        return
    try:
        append_history(history_path, form_history_entry(title, created_form))
        print(f"[OK] Form saved to history log -> {history_path}")
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
    parser.add_argument(
        "--history",
        nargs="?",
        const="forms_history.json",
        default=None,
        metavar="PATH",
        help="Record form creation metadata to history file (default: forms_history.json in current directory)",
    )
    args = parser.parse_args()

    with args.spec.open(encoding="utf-8") as spec_file:
        spec = json.load(spec_file)

    title = spec["title"]
    created_form = build_form(spec)

    print_created_form(created_form)

    history_target = (
        Path(args.history)
        if args.history
        else (Path(spec["history_path"]) if "history_path" in spec else None)
    )
    record_local_outputs(title, created_form, history_path=history_target)


if __name__ == "__main__":
    try:
        main()
    except GwsCommandError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(error.returncode)
