# -*- coding: utf-8 -*-
"""
tests/test_updater.py
=====================
Unit tests for form_updater.py — all API calls mocked.

Priority order (most critical first):
  1. Snapshot enforcement — sys.exit if missing
  2. Stale snapshot warning — fires after 30 min
  3. Input validation — empty ops, missing form_id, bad op fields
  4. Each op dispatches the correct batchUpdate payload
  5. Unknown op is skipped gracefully
  6. set_publish failure is caught and continues
"""

import json
import os
import sys
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

import form_updater as updater

# ─── Helpers ──────────────────────────────────────────────────────────────────

FORM_ID = "FORM_TEST_001"


def _fresh_snapshot(items=None, offset_minutes=0):
    """Return a snapshot dict, fetched_at offset_minutes ago."""
    t = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return {
        "form_id": FORM_ID,
        "title": "Test Form",
        "revisionId": "revision-1",
        "item_count": len(items or []),
        "fetched_at": t.isoformat(),
        "items": items or [],
    }


def _snap_with_items():
    return _fresh_snapshot(
        items=[
            {
                "index": 0,
                "itemId": "item_A",
                "title": "Q1",
                "api_type": "questionItem",
                "question_type": "textQuestion",
            },
            {
                "index": 1,
                "itemId": "item_B",
                "title": "Q2",
                "api_type": "questionItem",
                "question_type": "choiceQuestion",
            },
        ]
    )


# ─── 1. Snapshot enforcement ──────────────────────────────────────────────────


class TestSnapshotEnforcement:

    def test_missing_snapshot_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        with pytest.raises(SystemExit) as exc:
            updater.load_snapshot("NONEXISTENT_FORM")
        assert exc.value.code == 1

    def test_existing_snapshot_loads(self, tmp_path, monkeypatch):
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        snap = _fresh_snapshot()
        path = os.path.join(tmp_path, f"{FORM_ID}_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        result = updater.load_snapshot(FORM_ID)
        assert result["form_id"] == FORM_ID


# ─── 2. Stale snapshot warning ────────────────────────────────────────────────


class TestStaleSnapshot:

    def _write_snap(self, tmp_path, offset_minutes):
        snap = _fresh_snapshot(offset_minutes=offset_minutes)
        path = os.path.join(tmp_path, f"{FORM_ID}_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f)

    def test_fresh_snapshot_no_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        self._write_snap(tmp_path, offset_minutes=5)
        updater.load_snapshot(FORM_ID)
        captured = capsys.readouterr()
        assert "WARNING" not in captured.out

    def test_stale_snapshot_prints_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        self._write_snap(tmp_path, offset_minutes=35)
        updater.load_snapshot(FORM_ID)
        captured = capsys.readouterr()
        assert "WARNING" in captured.out

    def test_stale_snapshot_does_not_exit(self, tmp_path, monkeypatch):
        """Stale snapshot is a warning, not a hard stop."""
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        self._write_snap(tmp_path, offset_minutes=60)
        with patch("builtins.print"):
            result = updater.load_snapshot(FORM_ID)  # must not raise
        assert result is not None


# ─── 3. Input validation ──────────────────────────────────────────────────────


class TestInputValidation:

    def test_empty_ops_exits(self, tmp_path, monkeypatch):
        """ops: [] must trigger sys.exit(1)."""
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        snap = _fresh_snapshot()
        path = os.path.join(tmp_path, f"{FORM_ID}_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f)

        spec = {"form_id": FORM_ID, "ops": []}
        spec_path = os.path.join(tmp_path, "update.json")
        with open(spec_path, "w") as f:
            json.dump(spec, f)

        with patch.object(sys, "argv", ["form_updater.py", spec_path]):
            with pytest.raises(SystemExit) as exc:
                updater.main()
            assert exc.value.code == 1

    def test_missing_form_id_exits(self, tmp_path):
        spec = {"ops": [{"op": "enable_quiz"}]}
        spec_path = os.path.join(tmp_path, "update.json")
        with open(spec_path, "w") as f:
            json.dump(spec, f)
        with patch.object(sys, "argv", ["form_updater.py", spec_path]):
            with pytest.raises(SystemExit) as exc:
                updater.main()
            assert exc.value.code == 1

    def test_update_info_without_fields_is_rejected(self):
        with pytest.raises(updater.OperationSpecError):
            updater.op_update_info("FORM_ID", {"op": "update_info"})

    def test_delete_without_item_id_is_rejected(self):
        with pytest.raises(updater.OperationSpecError):
            updater.op_delete_item("FORM_ID", {"op": "delete_item"}, {})

    def test_move_without_destination_is_rejected(self):
        with pytest.raises(updater.OperationSpecError):
            updater.op_move_item("FORM_ID", {"op": "move_item", "item_id": "X"}, {})

    def test_move_without_item_id_is_rejected(self):
        with pytest.raises(updater.OperationSpecError):
            updater.op_move_item("FORM_ID", {"op": "move_item", "to_index": 2}, {})

    def test_publish_without_state_is_rejected(self):
        with pytest.raises(updater.OperationSpecError):
            updater.op_set_publish("FORM_ID", {"op": "set_publish"})

    def test_add_without_item_is_rejected(self):
        snap = _fresh_snapshot()
        with pytest.raises(updater.OperationSpecError):
            updater.op_add_item("FORM_ID", {"op": "add_item"}, snap)


# ─── 4. Op dispatch — correct batchUpdate payloads ───────────────────────────


class TestOpDispatch:

    def test_update_info_calls_batch_update(self):
        with patch.object(updater, "batch_update") as mock_bu:
            updater.op_update_info("FID", {"op": "update_info", "title": "New"})
        mock_bu.assert_called_once()
        req = mock_bu.call_args[0][1][0]
        assert "updateFormInfo" in req
        assert req["updateFormInfo"]["info"]["title"] == "New"

    def test_update_info_description_only(self):
        with patch.object(updater, "batch_update") as mock_bu:
            updater.op_update_info("FID", {"op": "update_info", "description": "Desc"})
        req = mock_bu.call_args[0][1][0]
        assert req["updateFormInfo"]["info"].get("description") == "Desc"

    def test_update_info_document_title(self):
        with patch.object(updater, "batch_update") as mock_bu:
            updater.op_update_info(
                "FID", {"op": "update_info", "document_title": "Drive Title"}
            )
        req = mock_bu.call_args[0][1][0]
        assert req["updateFormInfo"]["info"]["documentTitle"] == "Drive Title"
        assert "documentTitle" in req["updateFormInfo"]["updateMask"]

    def test_delete_item_uses_index_from_snapshot(self):
        snap = _snap_with_items()  # item_A is at index 0
        with patch.object(updater, "batch_update") as mock_bu:
            updater.op_delete_item(
                "FID", {"op": "delete_item", "item_id": "item_A"}, snap
            )
        req = mock_bu.call_args[0][1][0]
        assert "deleteItem" in req
        assert mock_bu.call_args.kwargs["revision_id"] == "revision-1"
        location = req["deleteItem"]["location"]
        # Must use index, found from snapshot
        assert "index" in location
        assert location["index"] == 0
        assert "itemId" not in location

    def test_move_item_uses_indices(self):
        snap = _snap_with_items()  # item_B is at index 1
        with patch.object(updater, "batch_update") as mock_bu:
            updater.op_move_item(
                "FID", {"op": "move_item", "item_id": "item_B", "to_index": 0}, snap
            )
        req = mock_bu.call_args[0][1][0]
        assert "moveItem" in req
        orig = req["moveItem"]["originalLocation"]
        assert "index" in orig
        assert orig["index"] == 1
        dest = req["moveItem"]["newLocation"]
        assert dest["index"] == 0
        assert mock_bu.call_args.kwargs["revision_id"] == "revision-1"

    def test_enable_quiz_correct_payload(self):
        with patch.object(updater, "batch_update") as mock_bu:
            updater.op_enable_quiz("FID")
        req = mock_bu.call_args[0][1][0]
        assert "updateSettings" in req
        assert req["updateSettings"]["settings"]["quizSettings"]["isQuiz"] is True

    def test_add_item_appends_to_end_when_no_at_index(self):
        snap = _snap_with_items()  # item_count = 2
        with patch.object(updater, "batch_update"), patch(
            "form_updater.dispatch"
        ) as mock_dispatch:
            mock_dispatch.return_value = {"createItem": {}}
            updater.op_add_item(
                "FID", {"op": "add_item", "item": {"type": "short", "q": "Q?"}}, snap
            )
        # at_index should equal item_count (2)
        mock_dispatch.assert_called_once()
        _, called_index = mock_dispatch.call_args[0]
        assert called_index == 2

    def test_add_item_respects_at_index(self):
        snap = _snap_with_items()
        with patch.object(updater, "batch_update"), patch(
            "form_updater.dispatch"
        ) as mock_dispatch:
            mock_dispatch.return_value = {"createItem": {}}
            updater.op_add_item(
                "FID",
                {"op": "add_item", "item": {"type": "short", "q": "Q?"}, "at_index": 1},
                snap,
            )
        _, called_index = mock_dispatch.call_args[0]
        assert called_index == 1

    def test_set_publish_passes_correct_args(self):
        with patch.object(updater, "set_publish") as mock_sp:
            updater.op_set_publish(
                "FID", {"op": "set_publish", "published": True, "accepting": False}
            )
        mock_sp.assert_called_once_with("FID", published=True, accepting=False)

    def test_set_publish_default_accepting_true(self):
        with patch.object(updater, "set_publish") as mock_sp:
            updater.op_set_publish("FID", {"op": "set_publish", "published": False})
        mock_sp.assert_called_once_with("FID", published=False, accepting=True)

    def test_main_refreshes_before_and_after_add_item(self, tmp_path, monkeypatch):
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        snap = _fresh_snapshot()
        path = os.path.join(tmp_path, f"{FORM_ID}_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f)

        spec = {
            "form_id": FORM_ID,
            "ops": [{"op": "add_item", "item": {"type": "short", "q": "Q?"}}],
        }
        spec_path = os.path.join(tmp_path, "update.json")
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f)

        with patch.object(updater, "batch_update"), patch.object(
            updater, "refresh_snapshot", return_value=snap
        ) as mock_refresh, patch.object(sys, "argv", ["form_updater.py", spec_path]):
            updater.main()

        assert mock_refresh.call_count == 2

    def test_delete_resolves_index_from_live_snapshot(self):
        stale_snapshot = _snap_with_items()
        live_snapshot = _fresh_snapshot(
            items=[
                {"index": 0, "itemId": "item_B"},
                {"index": 1, "itemId": "item_A"},
            ]
        )
        live_snapshot["revisionId"] = "revision-live"
        operation = {"op": "delete_item", "item_id": "item_A"}

        with patch.object(
            updater,
            "refresh_snapshot",
            side_effect=[live_snapshot, live_snapshot],
        ), patch.object(updater, "batch_update") as batch_boundary:
            succeeded, _ = updater.execute_operation("FID", operation, stale_snapshot)

        delete_request = batch_boundary.call_args.args[1][0]
        assert succeeded is True
        assert delete_request["deleteItem"]["location"]["index"] == 1
        assert batch_boundary.call_args.kwargs["revision_id"] == "revision-live"


# ─── 5. Unknown op skipped ───────────────────────────────────────────────────


class TestUnknownOp:

    def test_unknown_op_does_not_exit(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(updater, "SNAPSHOTS_DIR", str(tmp_path))
        snap = _fresh_snapshot()
        path = os.path.join(tmp_path, f"{FORM_ID}_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f)

        spec = {"form_id": FORM_ID, "ops": [{"op": "fly_to_moon"}]}
        spec_path = os.path.join(tmp_path, "update.json")
        with open(spec_path, "w") as f:
            json.dump(spec, f)

        with patch.object(sys, "argv", ["form_updater.py", spec_path]):
            exit_code = updater.main()

        captured = capsys.readouterr()
        assert "Unknown op" in captured.err
        assert "0 completed, 1 failed" in captured.out
        assert exit_code == 1


# ─── 6. set_publish failure handled ─────────────────────────────────────────


class TestSetPublishFailure:

    def test_publish_api_failure_is_reported_as_failed(self, capsys):
        operation = {"op": "set_publish", "published": True}
        api_error = updater.GwsCommandError(1, "permission denied")
        with patch.object(updater, "set_publish", side_effect=api_error):
            succeeded, _ = updater.execute_operation("FID", operation, {})
        captured = capsys.readouterr()
        assert succeeded is False
        assert "permission denied" in captured.err

    def test_delete_unknown_item_is_reported_as_failed(self, capsys):
        snap = _snap_with_items()
        operation = {"op": "delete_item", "item_id": "GHOST_ID"}
        with patch.object(updater, "refresh_snapshot", return_value=snap):
            succeeded, _ = updater.execute_operation("FID", operation, snap)
        captured = capsys.readouterr()
        assert succeeded is False
        assert "not found" in captured.err
