# -*- coding: utf-8 -*-
"""
form_updater.py — Apply a list of operations to an existing Google Form.

Usage:
    # Step 1 — MANDATORY
    python form_fetcher.py --id FORM_ID

    # Step 2
    python form_updater.py update.json

JSON spec:
    {
      "form_id": "1abc...XYZ",
      "ops": [
        {"op": "update_info",  "title": "New Title", "description": "New desc"},
        {"op": "add_item",     "item": {"type": "short", "q": "New Q?"}, "at_index": 3},
        {"op": "delete_item",  "item_id": "3f2a"},
        {"op": "move_item",    "item_id": "7c1b", "to_index": 5},
        {"op": "enable_quiz"},
        {"op": "set_publish",  "published": true, "accepting": true}
      ]
    }

Rules:
    - Requires a snapshot (<form_id>_snapshot.json in the current directory,
      or a path given with -s).
    - Each op runs in its own batchUpdate call (sequential, not batched together).
    - delete_item and move_item use item_id from the snapshot, never index.
    - Every successful op refreshes the snapshot; a failed refresh is a warning,
      not a failed op, because the change itself was already applied.
    - Snapshot older than 30 min triggers a warning (execution continues).
"""

import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── locate siblings ───────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))
from form_builder import (  # noqa: E402
    GwsCommandError,
    batch_update,
    build_item_request,
    enable_quiz,
    get_form,
    read_json,
    set_publish,
    update_form_info_request,
    write_json_atomic,
)
from form_fetcher import build_snapshot  # noqa: E402

STALE_MINUTES = 30


class OperationSpecError(ValueError):
    """An update operation is missing a required field or target."""


# ─── Snapshot helpers ─────────────────────────────────────────────────────────


def load_snapshot(form_id: str, snapshot_path: Path) -> dict:
    if not snapshot_path.exists():
        print(
            f"[ERROR] Snapshot not found: {snapshot_path}\n"
            f"        Run first:  python scripts/form_fetcher.py --id {form_id}",
            file=sys.stderr,
        )
        sys.exit(1)
    snap = read_json(snapshot_path)

    # Stale check
    fetched_at_str = snap.get("fetched_at", "")
    if fetched_at_str:
        try:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            age = datetime.now(timezone.utc) - fetched_at
            if age > timedelta(minutes=STALE_MINUTES):
                mins = int(age.total_seconds() / 60)
                print(
                    f"[WARNING] Snapshot is {mins} minutes old "
                    f"(threshold: {STALE_MINUTES} min).\n"
                    f"          Re-run form_fetcher.py to get the latest state."
                )
        except (TypeError, ValueError):
            print("[WARNING] Snapshot has an invalid fetched_at timestamp.")

    return snap


def refresh_snapshot(form_id: str, snapshot_path: Path) -> dict:
    """Fetch the current form state and save it over the snapshot."""
    snap = build_snapshot(form_id, get_form(form_id))
    write_json_atomic(snapshot_path, snap)
    print(f"  [OK] snapshot refreshed ({snap['item_count']} item(s))")
    return snap


# ─── Op handlers ──────────────────────────────────────────────────────────────


def op_update_info(form_id: str, op: dict, snap: dict) -> None:
    title = op.get("title")
    description = op.get("description")
    document_title = op.get("document_title")
    if title is None and description is None and document_title is None:
        raise OperationSpecError(
            "'update_info' requires title, description, or document_title."
        )
    req = update_form_info_request(
        title=title,
        description=description,
        document_title=document_title,
    )
    batch_update(form_id, [req])
    print("  [OK] update_info")


def op_add_item(form_id: str, op: dict, snap: dict) -> None:
    item_spec = op.get("item")
    if not item_spec:
        raise OperationSpecError("'add_item' requires an 'item' object.")
    at_index = op.get("at_index", snap.get("item_count", 0))
    try:
        req = build_item_request(item_spec, at_index)
    except ValueError as error:
        raise OperationSpecError(str(error)) from error
    batch_update(form_id, [req], revision_id=snap.get("revisionId", ""))
    print(f"  [OK] add_item at index {at_index}")


def get_item_index(snap: dict, item_id: str) -> int | None:
    """Find the current index of an item_id in the snapshot."""
    for item in snap.get("items", []):
        if item["itemId"] == item_id:
            return item["index"]
    return None


def op_delete_item(form_id: str, op: dict, snap: dict) -> None:
    item_id = op.get("item_id")
    if not item_id:
        raise OperationSpecError("'delete_item' requires 'item_id' from the snapshot.")

    idx = get_item_index(snap, item_id)
    if idx is None:
        raise OperationSpecError(
            f"item_id '{item_id}' was not found in the current form."
        )

    req = {"deleteItem": {"location": {"index": idx}}}
    batch_update(form_id, [req], revision_id=snap.get("revisionId", ""))
    print(f"  [OK] delete_item '{item_id}' at index {idx}")


def op_move_item(form_id: str, op: dict, snap: dict) -> None:
    item_id = op.get("item_id")
    to_index = op.get("to_index")
    if not item_id or to_index is None:
        raise OperationSpecError("'move_item' requires 'item_id' and 'to_index'.")

    idx = get_item_index(snap, item_id)
    if idx is None:
        raise OperationSpecError(
            f"item_id '{item_id}' was not found in the current form."
        )

    req = {
        "moveItem": {
            "originalLocation": {"index": idx},
            "newLocation": {"index": to_index},
        }
    }
    batch_update(form_id, [req], revision_id=snap.get("revisionId", ""))
    print(f"  [OK] move_item '{item_id}' (index {idx}) -> index {to_index}")


def op_enable_quiz(form_id: str, op: dict, snap: dict) -> None:
    enable_quiz(form_id)
    print("  [OK] enable_quiz")


def op_set_publish(form_id: str, op: dict, snap: dict) -> None:
    published = op.get("published")
    if published is None:
        raise OperationSpecError("'set_publish' requires 'published' (true/false).")
    accepting = op.get("accepting", True)
    set_publish(form_id, published=published, accepting=accepting)
    print(f"  [OK] set_publish published={published} accepting={accepting}")


# ─── Dispatcher ───────────────────────────────────────────────────────────────

# Every handler takes (form_id, op, snap), even if it ignores some of them.
OP_MAP = {
    "update_info": op_update_info,
    "add_item": op_add_item,
    "delete_item": op_delete_item,
    "move_item": op_move_item,
    "enable_quiz": op_enable_quiz,
    "set_publish": op_set_publish,
}


def execute_operation(
    form_id: str, op: dict, snap: dict, snapshot_path: Path
) -> tuple[bool, dict]:
    """Execute one operation and return its success plus current snapshot."""
    op_name = op.get("op", "").strip()
    if op_name not in OP_MAP:
        print(f"  [ERROR] Unknown op '{op_name}'.", file=sys.stderr)
        return False, snap

    try:
        OP_MAP[op_name](form_id, op, snap)
    except (GwsCommandError, OperationSpecError) as error:
        print(f"  [ERROR] {op_name}: {error}", file=sys.stderr)
        return False, snap

    # The op is already applied; reporting it as failed would invite a retry
    # that duplicates the change.
    try:
        snap = refresh_snapshot(form_id, snapshot_path=snapshot_path)
    except GwsCommandError as error:
        print(
            f"  [WARN] {op_name} was applied, but refreshing the snapshot failed: "
            f"{error}\n         Re-run form_fetcher.py before more index operations.",
            file=sys.stderr,
        )
    return True, snap


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply update operations to an existing Google Form."
    )
    parser.add_argument("spec", type=Path, help="Path to update spec JSON")
    parser.add_argument(
        "-s",
        "--snapshot",
        type=Path,
        default=None,
        help=(
            "Path to snapshot JSON "
            "(default: <form_id>_snapshot.json in current directory)"
        ),
    )
    args = parser.parse_args()

    if not args.spec.exists():
        print(f"[ERROR] Spec file not found: {args.spec}", file=sys.stderr)
        sys.exit(1)

    spec = read_json(args.spec)

    form_id = spec.get("form_id", "").strip()
    if not form_id:
        print("[ERROR] 'form_id' is missing from the spec.", file=sys.stderr)
        sys.exit(1)

    ops = spec.get("ops", [])
    if not ops:
        print("[ERROR] 'ops' list is missing or empty. Nothing to do.", file=sys.stderr)
        sys.exit(1)

    snapshot_path = (
        args.snapshot
        or (Path(spec["snapshot_path"]) if "snapshot_path" in spec else None)
        or Path.cwd() / f"{form_id}_snapshot.json"
    )
    snap = load_snapshot(form_id, snapshot_path)

    print(f"\n>> Updating form: {form_id}  ({len(ops)} op(s))")
    completed = 0
    for op in ops:
        succeeded, snap = execute_operation(form_id, op, snap, snapshot_path)
        completed += int(succeeded)

    failed = len(ops) - completed
    print(f"\n[DONE] {completed} completed, {failed} failed.")
    return int(failed > 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(1)
