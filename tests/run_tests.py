# -*- coding: utf-8 -*-
"""
tests/run_tests.py — Offline test suite for gws-forms-win.

Verifies:
  1. Dynamic Node and GWS runner resolution.
  2. URL parsing and form ID extraction.
  3. All 11 item request builders and quiz grading payloads.
  4. Snapshot parsing from raw API payloads.
  5. Response normalization from FormResponse objects.
  6. Atomic JSON writes and history logging.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from form_builder import (  # noqa: E402
    _build_choice_grading,
    build_form,
    build_item_request,
    build_requests_from_spec,
    extract_form_id,
    resolve_node_exe,
    update_form_info_request,
)
from form_fetcher import build_snapshot  # noqa: E402
from form_reader import fetch_all_responses, normalise_response  # noqa: E402
from json_runner import append_history, form_history_entry  # noqa: E402


class TestUrlExtraction(unittest.TestCase):
    def test_extract_form_id_edit_url(self):
        url = "https://docs.google.com/forms/d/1bgiLEanlWJZwPbBoCx2DygrR2raq9aRlEwm5JEWv28c/edit"
        self.assertEqual(
            extract_form_id(url), "1bgiLEanlWJZwPbBoCx2DygrR2raq9aRlEwm5JEWv28c"
        )

    def test_extract_form_id_viewform_url(self):
        url = "https://docs.google.com/forms/d/xyz123abc/viewform"
        self.assertEqual(extract_form_id(url), "xyz123abc")

    def test_extract_form_id_rejects_encoded(self):
        encoded = "https://docs.google.com/forms/d/e/1FAIpQLScVCl_1jz/viewform"
        with self.assertRaises(ValueError):
            extract_form_id(encoded)

    def test_extract_form_id_rejects_other_domain(self):
        with self.assertRaises(ValueError):
            extract_form_id("https://evil.com/forms/d/123/edit")


class TestItemBuilders(unittest.TestCase):
    def test_all_eleven_item_types(self):
        specs = [
            {"type": "section", "title": "Sec", "desc": "Desc"},
            {"type": "text", "title": "Txt", "desc": "Desc"},
            {"type": "short", "q": "Name?", "paragraph": False},
            {"type": "mcq", "q": "Choice?", "options": ["A", "B"], "correct": "A"},
            {"type": "scale", "q": "Rate", "low": 1, "high": 5},
            {"type": "date", "q": "Date", "year": True},
            {"type": "time", "q": "Time", "duration": False},
            {"type": "rating", "q": "Stars", "scale": 5, "icon": "STAR"},
            {"type": "grid", "title": "Grid", "rows": ["R1"], "cols": ["C1"]},
            {"type": "video", "title": "Vid", "uri": "https://youtube.com/watch?v=1"},
            {"type": "image", "title": "Img", "uri": "https://img.test/pic.png"},
        ]
        built = [build_item_request(spec, idx) for idx, spec in enumerate(specs)]
        self.assertEqual(len(built), 11)
        for idx, req in enumerate(built):
            self.assertIn("createItem", req)
            self.assertEqual(req["createItem"]["location"]["index"], idx)

    def test_unknown_item_type_raises(self):
        with self.assertRaises(ValueError):
            build_item_request({"type": "unsupported"}, 0)

    def test_mcq_grading(self):
        grading = _build_choice_grading(
            {
                "correct": "Opt A",
                "points": 5,
                "right": "Well done",
                "wrong": "Try again",
            }
        )
        self.assertEqual(grading["pointValue"], 5)
        self.assertEqual(grading["correctAnswers"]["answers"][0]["value"], "Opt A")
        self.assertEqual(grading["whenRight"]["text"], "Well done")
        self.assertEqual(grading["whenWrong"]["text"], "Try again")


class TestFormInfoRequest(unittest.TestCase):
    def test_update_form_info_request_masks(self):
        req = update_form_info_request(title="T", description="D", document_title="Doc")
        info = req["updateFormInfo"]["info"]
        mask = req["updateFormInfo"]["updateMask"]
        self.assertEqual(info["title"], "T")
        self.assertEqual(info["description"], "D")
        self.assertEqual(info["documentTitle"], "Doc")
        self.assertIn("title", mask)
        self.assertIn("description", mask)
        self.assertIn("documentTitle", mask)


class TestSnapshotBuilder(unittest.TestCase):
    def test_build_snapshot_structure(self):
        raw = {
            "info": {"title": "Sample Form", "description": "Sample Desc"},
            "revisionId": "rev_001",
            "responderUri": "https://docs.google.com/forms/d/e/.../viewform",
            "items": [
                {
                    "itemId": "item_1",
                    "title": "Question 1",
                    "questionItem": {
                        "question": {
                            "required": True,
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [{"value": "Yes"}],
                            },
                        }
                    },
                }
            ],
        }
        snap = build_snapshot("form_123", raw)
        self.assertEqual(snap["form_id"], "form_123")
        self.assertEqual(snap["title"], "Sample Form")
        self.assertEqual(snap["item_count"], 1)
        self.assertEqual(snap["items"][0]["question_type"], "choiceQuestion")
        self.assertTrue(snap["items"][0]["required"])


class TestResponseNormalizer(unittest.TestCase):
    def test_normalise_response(self):
        raw_resp = {
            "responseId": "resp_99",
            "respondentEmail": "student@example.com",
            "totalScore": 10.0,
            "answers": {
                "q_1": {
                    "questionId": "q_1",
                    "textAnswers": {"answers": [{"value": "Chosen Answer"}]},
                    "grade": {"score": 10.0, "correct": True},
                }
            },
        }
        clean = normalise_response(raw_resp)
        self.assertEqual(clean["responseId"], "resp_99")
        self.assertEqual(clean["respondentEmail"], "student@example.com")
        self.assertEqual(clean["totalScore"], 10.0)
        self.assertEqual(clean["answers"]["q_1"]["textAnswers"], ["Chosen Answer"])
        self.assertTrue(clean["answers"]["q_1"]["grade"]["correct"])

    def test_fetch_all_responses_delegates_to_list_responses(self):
        from unittest.mock import patch

        with patch("form_builder.run_gws") as mock_run_gws:
            mock_run_gws.return_value = {
                "responses": [{"responseId": "r1"}],
                "nextPageToken": None,
            }
            resps = fetch_all_responses("dummy_form")
            self.assertEqual(len(resps), 1)
            self.assertEqual(resps[0]["responseId"], "r1")


class TestStorageAndNodeResolution(unittest.TestCase):
    def test_atomic_write_and_history(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_history.json"
            entry = form_history_entry(
                "Test Form",
                {
                    "formId": "form_abc",
                    "responderUri": "https://example.com/resp",
                    "editUrl": "https://example.com/edit",
                },
            )
            append_history(file_path, entry)
            self.assertTrue(file_path.exists())

            with file_path.open(encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["formId"], "form_abc")

    def test_node_resolution_env_override(self):
        old_val = os.environ.get("GWS_FORMS_NODE_EXE")
        try:
            os.environ["GWS_FORMS_NODE_EXE"] = "custom_node.exe"
            self.assertEqual(resolve_node_exe(), "custom_node.exe")
        finally:
            if old_val is not None:
                os.environ["GWS_FORMS_NODE_EXE"] = old_val
            else:
                os.environ.pop("GWS_FORMS_NODE_EXE", None)

    def test_build_requests_from_spec(self):
        spec = {
            "title": "Quiz",
            "desc": "Instructions",
            "items": [
                {"type": "short", "q": "Name?"},
            ],
        }
        reqs = build_requests_from_spec(spec)
        self.assertEqual(len(reqs), 2)
        self.assertIn("updateFormInfo", reqs[0])
        self.assertIn("createItem", reqs[1])

    def test_build_form_with_spec_dict(self):
        from unittest.mock import patch

        spec = {
            "title": "Complete Quiz",
            "desc": "Exam notes",
            "quiz": True,
            "items": [{"type": "short", "q": "Your ID?"}],
        }
        with patch("form_builder.create_form") as mock_create, patch(
            "form_builder.batch_update"
        ) as mock_batch:
            mock_create.return_value = ("f_id", "https://resp", "rev_1")
            mock_batch.return_value = {}
            res = build_form(spec)

            self.assertEqual(res["formId"], "f_id")
            mock_create.assert_called_once_with("Complete Quiz", "Complete Quiz")
            mock_batch.assert_called_once()
            called_requests = mock_batch.call_args[0][1]
            self.assertEqual(len(called_requests), 3)


if __name__ == "__main__":
    unittest.main()
