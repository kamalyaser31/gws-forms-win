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
    - Requires a snapshot in SKILL_ROOT/snapshots/<form_id>_snapshot.json.
    - Each op runs in its own batchUpdate call (sequential, not batched together).
    - delete_item and move_item use item_id from the snapshot, never index.
    - Snapshot older than 30 min triggers a warning (execution continues).
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── locate siblings ───────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_DIR.parent
SNAPSHOTS_DIR = SKILL_ROOT / "snapshots"

sys.path.insert(0, str(SKILL_DIR))
from form_builder import (          # noqa: E402
    batch_update,
    update_form_info_request,
    enable_quiz_request,
    set_publish,
)
from json_runner import dispatch     # reuse item dispatcher  # noqa: E402

STALE_MINUTES = 30


# ─── Snapshot helpers ─────────────────────────────────────────────────────────

def load_snapshot(form_id: str) -> dict:
    path = os.path.join(SNAPSHOTS_DIR, f"{form_id}_snapshot.json")
    if not os.path.exists(path):
        print(
            f"[ERROR] Snapshot not found: {path}\n"
            f"        Run first:  python form_fetcher.py --id {form_id}"
        )
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)

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
        except ValueError:
            pass  # malformed timestamp — skip stale check

    return snap


def snapshot_item_ids(snap: dict) -> set:
    return {item["itemId"] for item in snap.get("items", [])}


# ─── Op handlers ──────────────────────────────────────────────────────────────

def op_update_info(form_id: str, op: dict) -> None:
    title = op.get("title")
    description = op.get("description")
    if title is None and description is None:
        print("[ERROR] 'update_info' requires at least 'title' or 'description'.")
        sys.exit(1)
    req = update_form_info_request(title=title, description=description)
    batch_update(form_id, [req])
    print("  [OK] update_info")


def op_add_item(form_id: str, op: dict, snap: dict) -> None:
    item_spec = op.get("item")
    if not item_spec:
        print("[ERROR] 'add_item' requires an 'item' object.")
        sys.exit(1)
    at_index = op.get("at_index", snap.get("item_count", 0))
    req = dispatch(item_spec, at_index)
    batch_update(form_id, [req])
    print(f"  [OK] add_item at index {at_index}")


def get_item_index(snap: dict, item_id: str) -> int:
    """Find the current index of an item_id in the snapshot."""
    for item in snap.get("items", []):
        if item["itemId"] == item_id:
            return item["index"]
    return None


def op_delete_item(form_id: str, op: dict, snap: dict) -> None:
    item_id = op.get("item_id")
    if not item_id:
        print("[ERROR] 'delete_item' requires 'item_id' (from snapshot).")
        sys.exit(1)
    
    idx = get_item_index(snap, item_id)
    if idx is None:
        print(
            f"[WARNING] item_id '{item_id}' not found in snapshot. "
            "It may have been already deleted or the snapshot is stale."
        )
        return

    req = {"deleteItem": {"location": {"index": idx}}}
    batch_update(form_id, [req])
    print(f"  [OK] delete_item '{item_id}' at index {idx}")


def op_move_item(form_id: str, op: dict, snap: dict) -> None:
    item_id = op.get("item_id")
    to_index = op.get("to_index")
    if not item_id or to_index is None:
        print("[ERROR] 'move_item' requires 'item_id' and 'to_index'.")
        sys.exit(1)
    
    idx = get_item_index(snap, item_id)
    if idx is None:
        print(
            f"[WARNING] item_id '{item_id}' not found in snapshot. "
            "Snapshot may be stale."
        )
        return

    req = {
        "moveItem": {
            "originalLocation": {"index": idx},
            "newLocation":      {"index": to_index},
        }
    }
    batch_update(form_id, [req])
    print(f"  [OK] move_item '{item_id}' (index {idx}) -> index {to_index}")


def op_enable_quiz(form_id: str) -> None:
    batch_update(form_id, [enable_quiz_request()])
    print("  [OK] enable_quiz")


def op_set_publish(form_id: str, op: dict) -> None:
    published = op.get("published")
    if published is None:
        print("[ERROR] 'set_publish' requires 'published' (true/false).")
        sys.exit(1)
    accepting = op.get("accepting", True)
    try:
        set_publish(form_id, published=published, accepting=accepting)
        print(f"  [OK] set_publish published={published} accepting={accepting}")
    except SystemExit:
        # set_publish calls sys.exit on non-zero gws exit code
        print(
            "[WARNING] set_publish failed — this form may not support "
            "publish settings (legacy forms). Continuing."
        )


# ─── Dispatcher ───────────────────────────────────────────────────────────────

OP_MAP = {
    "update_info":  lambda form_id, op, snap: op_update_info(form_id, op),
    "add_item":     op_add_item,
    "delete_item":  op_delete_item,
    "move_item":    op_move_item,
    "enable_quiz":  lambda form_id, op, snap: op_enable_quiz(form_id),
    "set_publish":  lambda form_id, op, snap: op_set_publish(form_id, op),
}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python form_updater.py <update_spec.json>")
        sys.exit(1)

    spec_path = sys.argv[1]
    if not os.path.exists(spec_path):
        print(f"[ERROR] Spec file not found: {spec_path}")
        sys.exit(1)

    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)

    form_id = spec.get("form_id", "").strip()
    if not form_id:
        print("[ERROR] 'form_id' is missing from the spec.")
        sys.exit(1)

    ops = spec.get("ops", [])
    if not ops:
        print("[ERROR] 'ops' list is missing or empty. Nothing to do.")
        sys.exit(1)

    snap = load_snapshot(form_id)

    print(f"\n>> Updating form: {form_id}  ({len(ops)} op(s))")
    completed = 0
    for i, op in enumerate(ops):
        op_name = op.get("op", "").strip()
        if op_name not in OP_MAP:
            print(f"  [ERROR] Unknown op '{op_name}' at index {i}. Skipping.")
            continue
        handler = OP_MAP[op_name]
        handler(form_id, op, snap)
        completed += 1

    print(f"\n[DONE] {completed}/{len(ops)} ops completed.")


if __name__ == "__main__":
    main()
