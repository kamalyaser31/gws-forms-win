# -*- coding: utf-8 -*-
"""
tests/test_json_runner.py
=========================
Unit tests for json_runner.py — the data-driven form builder.

Priority order (most critical first):
  1. dispatch() — all 12 item types produce valid createItem payloads
  2. MCQ grading — correct/wrong answers wired correctly
  3. Location index — every item has location.index set
  4. Required fields — missing type raises ValueError
  5. build_form integration — calls create_form then batch_update
  6. Quiz mode — enable_quiz_request included when quiz=True
"""

import json
import os
import sys
import pytest
from unittest.mock import patch

import json_runner as runner

# ─── 1. dispatch() — all item types ─────────────────────────────────────────


class TestDispatch:

    def _req(self, spec, index=0):
        return runner.dispatch(spec, index)

    def _assert_create_item(self, req):
        assert "createItem" in req
        assert "item" in req["createItem"]
        assert "location" in req["createItem"]

    def test_section(self):
        req = self._req({"type": "section", "title": "Part 1"})
        self._assert_create_item(req)
        assert "pageBreakItem" in req["createItem"]["item"]

    def test_section_with_desc(self):
        req = self._req({"type": "section", "title": "P", "desc": "Details"})
        assert req["createItem"]["item"].get("description") == "Details"

    def test_text_item(self):
        req = self._req({"type": "text", "title": "Note"})
        self._assert_create_item(req)
        assert "textItem" in req["createItem"]["item"]

    def test_short_paragraph(self):
        req = self._req({"type": "short", "q": "Describe yourself."})
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "textQuestion" in q
        assert q["textQuestion"]["paragraph"] is True

    def test_short_single_line(self):
        req = self._req({"type": "short", "q": "Name?", "paragraph": False})
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert q["textQuestion"]["paragraph"] is False

    def test_mcq_ungraded(self):
        req = self._req({"type": "mcq", "q": "Choose:", "options": ["A", "B", "C"]})
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "choiceQuestion" in q
        assert "grading" not in q

    def test_mcq_graded_correct_answer(self):
        req = self._req(
            {
                "type": "mcq",
                "q": "Choose:",
                "options": ["A", "B"],
                "correct": "B",
                "wrong": "It is B.",
            }
        )
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "grading" in q
        assert q["grading"]["correctAnswers"]["answers"][0]["value"] == "B"

    def test_mcq_graded_feedback_right(self):
        req = self._req(
            {
                "type": "mcq",
                "q": "Q",
                "options": ["A"],
                "correct": "A",
                "right": "Well done!",
            }
        )
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert q["grading"]["whenRight"]["text"] == "Well done!"

    def test_mcq_graded_wrong_feedback(self):
        req = self._req(
            {
                "type": "mcq",
                "q": "Q",
                "options": ["A", "B"],
                "correct": "A",
                "wrong": "Nope.",
            }
        )
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert q["grading"]["whenWrong"]["text"] == "Nope."

    def test_scale(self):
        req = self._req(
            {
                "type": "scale",
                "q": "Rate:",
                "low": 1,
                "high": 5,
                "low_label": "Bad",
                "high_label": "Good",
            }
        )
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "scaleQuestion" in q
        assert q["scaleQuestion"]["low"] == 1
        assert q["scaleQuestion"]["high"] == 5

    def test_date(self):
        req = self._req({"type": "date", "q": "DOB:", "year": True, "time": False})
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "dateQuestion" in q
        assert q["dateQuestion"]["includeYear"] is True

    def test_time(self):
        req = self._req({"type": "time", "q": "What time?"})
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "timeQuestion" in q

    def test_rating(self):
        req = self._req({"type": "rating", "q": "Rate", "scale": 5, "icon": "STAR"})
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert "ratingQuestion" in q
        assert q["ratingQuestion"]["ratingScaleLevel"] == 5

    def test_grid(self):
        req = self._req(
            {
                "type": "grid",
                "title": "Grid Q",
                "rows": ["Row1", "Row2"],
                "cols": ["Col1", "Col2"],
            }
        )
        self._assert_create_item(req)
        assert "questionGroupItem" in req["createItem"]["item"]

    def test_video(self):
        req = self._req(
            {
                "type": "video",
                "title": "Watch this",
                "uri": "https://youtu.be/abc",
            }
        )
        assert "videoItem" in req["createItem"]["item"]

    def test_image(self):
        req = self._req(
            {
                "type": "image",
                "title": "Look at this",
                "uri": "https://example.com/img.png",
            }
        )
        assert "imageItem" in req["createItem"]["item"]

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown item type"):
            runner.dispatch({"type": "teleporter"}, 0)


# ─── 2. Location index ───────────────────────────────────────────────────────


class TestLocationIndex:

    def test_index_zero(self):
        req = runner.dispatch({"type": "section", "title": "S"}, 0)
        assert req["createItem"]["location"]["index"] == 0

    def test_index_seven(self):
        req = runner.dispatch({"type": "short", "q": "Q?"}, 7)
        assert req["createItem"]["location"]["index"] == 7

    def test_index_propagated_for_mcq(self):
        req = runner.dispatch({"type": "mcq", "q": "Q", "options": ["A"]}, 4)
        assert req["createItem"]["location"]["index"] == 4


# ─── 3. Required field defaults ──────────────────────────────────────────────


class TestRequiredDefaults:

    def test_short_required_true_by_default(self):
        req = runner.dispatch({"type": "short", "q": "Q?"}, 0)
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert q["required"] is True

    def test_short_required_false_when_set(self):
        req = runner.dispatch({"type": "short", "q": "Q?", "required": False}, 0)
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert q["required"] is False

    def test_mcq_required_true_by_default(self):
        req = runner.dispatch({"type": "mcq", "q": "Q", "options": ["A"]}, 0)
        q = req["createItem"]["item"]["questionItem"]["question"]
        assert q["required"] is True


# ─── 4. build_form integration ───────────────────────────────────────────────


class TestBuildForm:
    def test_main_calls_build_form_with_all_items(self, tmp_path):
        spec = {
            "title": "Test Form",
            "quiz": False,
            "items": [
                {"type": "section", "title": "S1"},
                {"type": "short", "q": "What?"},
            ],
        }
        spec_path = os.path.join(tmp_path, "form.json")
        with open(spec_path, "w", encoding="utf-8") as f:
            import json

            json.dump(spec, f)

        with patch("json_runner.build_form") as mock_bf, patch(
            "json_runner.record_local_outputs"
        ):
            mock_bf.return_value = {
                "formId": "X",
                "responderUri": "",
                "editUrl": "",
            }
            with patch.object(sys, "argv", ["json_runner.py", spec_path]):
                runner.main()

        assert mock_bf.called
        _, called_items = mock_bf.call_args[0]
        assert len(called_items) == 2

    def test_quiz_mode_flag_passed(self, tmp_path):
        spec = {"title": "Q", "quiz": True, "items": [{"type": "short", "q": "Q?"}]}
        spec_path = os.path.join(tmp_path, "form.json")
        with open(spec_path, "w") as f:
            import json

            json.dump(spec, f)

        with patch("json_runner.build_form") as mock_bf, patch(
            "json_runner.record_local_outputs"
        ):
            mock_bf.return_value = {"formId": "X", "responderUri": "", "editUrl": ""}
            with patch.object(sys, "argv", ["json_runner.py", spec_path]):
                runner.main()

        _, kwargs = mock_bf.call_args
        assert kwargs.get("quiz_mode") is True


class TestDescriptionAndHistory:
    def test_description_is_sent_before_items(self):
        requests = runner.build_requests(
            {
                "description": "Form details",
                "items": [{"type": "short", "q": "Question?"}],
            }
        )
        assert requests[0]["updateFormInfo"]["info"]["description"] == "Form details"
        assert requests[1]["createItem"]["location"]["index"] == 0

    def test_existing_history_is_preserved_when_entry_is_appended(self, tmp_path):
        history_path = tmp_path / "history.json"
        history_path.write_text('[{"formId": "old"}]', encoding="utf-8")

        runner.append_history(history_path, {"formId": "new"})

        saved_history = json.loads(history_path.read_text(encoding="utf-8"))
        assert [entry["formId"] for entry in saved_history] == ["old", "new"]

    @pytest.mark.parametrize("invalid_history", ["{", '{"formId": "old"}'])
    def test_invalid_history_is_never_overwritten(self, tmp_path, invalid_history):
        history_path = tmp_path / "history.json"
        history_path.write_text(invalid_history, encoding="utf-8")

        with pytest.raises((json.JSONDecodeError, ValueError)):
            runner.append_history(history_path, {"formId": "new"})

        assert history_path.read_text(encoding="utf-8") == invalid_history

    def test_clipboard_command_never_uses_a_shell(self):
        with patch("json_runner.subprocess.run") as clipboard_process:
            runner.copy_responder_url("https://example.test/form")
        assert clipboard_process.call_args.kwargs["shell"] is False
