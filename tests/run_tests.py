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
  7. Spec validation, batch chunking, and failure reporting.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from form_builder import (  # noqa: E402
    GwsCommandError,
    PartialFormError,
    SpecError,
    _build_choice_grading,
    batch_update,
    build_form,
    build_item_request,
    build_requests_from_spec,
    chunk_requests,
    extract_form_id,
    list_responses,
    read_json,
    resolve_gws_js,
    resolve_node_exe,
    run_gws,
    update_form_info_request,
)
from form_fetcher import build_snapshot  # noqa: E402
from form_reader import normalise_response, question_titles  # noqa: E402
from form_updater import execute_operation  # noqa: E402
from json_runner import append_history, form_history_entry  # noqa: E402

FORM_ID = "1bgiLEanlWJZwPbBoCx2DygrR2raq9aRlEwm5JEWv28c"


class TestUrlExtraction(unittest.TestCase):
    def test_extract_form_id_edit_url(self):
        url = f"https://docs.google.com/forms/d/{FORM_ID}/edit"
        self.assertEqual(extract_form_id(url), FORM_ID)

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
        clean = normalise_response(raw_resp, {"q_1": "Pick one"})
        self.assertEqual(clean["answers"]["q_1"]["title"], "Pick one")
        self.assertEqual(clean["responseId"], "resp_99")
        self.assertEqual(clean["respondentEmail"], "student@example.com")
        self.assertEqual(clean["totalScore"], 10.0)
        self.assertEqual(clean["answers"]["q_1"]["textAnswers"], ["Chosen Answer"])
        self.assertTrue(clean["answers"]["q_1"]["grade"]["correct"])

    def test_list_responses_follows_pages(self):
        pages = [
            {"responses": [{"responseId": "r1"}], "nextPageToken": "t2"},
            {"responses": [{"responseId": "r2"}]},
        ]
        with patch("form_builder.run_gws", side_effect=pages) as mock_run_gws:
            resps = list_responses("dummy_form")
        self.assertEqual([r["responseId"] for r in resps], ["r1", "r2"])
        self.assertEqual(mock_run_gws.call_args.kwargs["params"]["pageToken"], "t2")

    def test_question_titles_labels_grid_rows(self):
        raw_form = {
            "items": [
                {"title": "Name", "questionItem": {"question": {"questionId": "a"}}},
                {
                    "title": "Habits",
                    "questionGroupItem": {
                        "questions": [
                            {"questionId": "b", "rowQuestion": {"title": "Prayer"}}
                        ]
                    },
                },
            ]
        }
        titles = question_titles(raw_form)
        self.assertEqual(titles, {"a": "Name", "b": "Habits — Prayer"})


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


class TestSpecValidation(unittest.TestCase):
    def mcq(self, **overrides):
        return {"type": "mcq", "q": "Pick", "options": ["A", "B", "C"], **overrides}

    def test_correct_must_match_an_option(self):
        with self.assertRaises(SpecError):
            build_item_request(self.mcq(correct="D"), 0)

    def test_correct_requires_quiz_mode(self):
        spec = {"title": "T", "items": [self.mcq(correct="A")]}
        with self.assertRaises(SpecError):
            build_requests_from_spec(spec)

    def test_missing_title_and_keys_are_named(self):
        with self.assertRaises(SpecError):
            build_requests_from_spec({"items": []})
        with self.assertRaisesRegex(SpecError, "options"):
            build_item_request({"type": "mcq", "q": "Pick"}, 3)

    def test_checkbox_accepts_several_correct_answers(self):
        req = build_item_request(self.mcq(qtype="CHECKBOX", correct=["A", "C"]), 0)
        question = req["createItem"]["item"]["questionItem"]["question"]
        answers = question["grading"]["correctAnswers"]["answers"]
        self.assertEqual([a["value"] for a in answers], ["A", "C"])

    def test_radio_rejects_several_correct_answers(self):
        with self.assertRaises(SpecError):
            build_item_request(self.mcq(correct=["A", "C"]), 0)

    def test_graded_question_keeps_requested_shuffle(self):
        req = build_item_request(self.mcq(correct="A", shuffle=True), 0)
        question = req["createItem"]["item"]["questionItem"]["question"]
        self.assertTrue(question["choiceQuestion"]["shuffle"])

    def test_invalid_spec_creates_no_form(self):
        spec = {"title": "T", "quiz": True, "items": [self.mcq(correct="Z")]}
        with patch("form_builder.create_form") as mock_create:
            with self.assertRaises(SpecError):
                build_form(spec)
        mock_create.assert_not_called()


class TestBatchingAndFailures(unittest.TestCase):
    def short_items(self, count):
        return [
            build_item_request({"type": "short", "q": "س" * 200}, idx)
            for idx in range(count)
        ]

    def test_chunks_keep_order_and_fit_budget(self):
        requests = self.short_items(40)
        chunks = chunk_requests(requests, budget=3_000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual([r for chunk in chunks for r in chunk], requests)

    def test_revision_guard_only_on_first_chunk(self):
        with patch("form_builder.run_gws", return_value={}) as mock_run_gws, patch(
            "form_builder.MAX_BATCH_ARG_CHARS", 3_000
        ):
            batch_update("f", self.short_items(40), revision_id="rev_1")
        bodies = [c.kwargs["json_body"] for c in mock_run_gws.call_args_list]
        self.assertGreater(len(bodies), 1)
        self.assertIn("writeControl", bodies[0])
        self.assertTrue(all("writeControl" not in b for b in bodies[1:]))

    def test_launch_failure_becomes_gws_error(self):
        with patch("form_builder.subprocess.run", side_effect=OSError("too long")):
            with self.assertRaises(GwsCommandError):
                run_gws(["forms", "forms", "get"], verbose=False)

    def test_failed_items_report_the_created_form(self):
        spec = {"title": "T", "items": [{"type": "short", "q": "Name?"}]}
        with patch(
            "form_builder.create_form", return_value=("f_id", "resp", "rev")
        ), patch("form_builder.batch_update", side_effect=GwsCommandError(1, "bad")):
            with self.assertRaises(PartialFormError) as caught:
                build_form(spec)
        self.assertIn("forms/d/f_id/edit", str(caught.exception))

    def test_refresh_failure_still_counts_applied_op(self):
        op = {"op": "update_info", "title": "New"}
        with patch("form_updater.batch_update", return_value={}), patch(
            "form_updater.get_form", side_effect=GwsCommandError(1, "net")
        ):
            succeeded, snap = execute_operation("f", op, {"items": []})
        self.assertTrue(succeeded)


class TestPortability(unittest.TestCase):
    def test_read_json_accepts_bom(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            spec_path = Path(tmp_dir) / "form.json"
            spec_path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"title": "T"}).encode())
            self.assertEqual(read_json(spec_path), {"title": "T"})

    def test_gws_js_found_beside_npm_shim(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            prefix = Path(tmp_dir)
            cli_dir = prefix / "node_modules" / "@googleworkspace" / "cli"
            cli_dir.mkdir(parents=True)
            (cli_dir / "run-gws.js").write_text("", encoding="utf-8")
            with patch.dict(os.environ, {"GWS_FORMS_GWS_JS": ""}), patch(
                "form_builder.shutil.which", return_value=str(prefix / "gws.cmd")
            ):
                found = resolve_gws_js()
        self.assertEqual(Path(found), (cli_dir / "run-gws.js").resolve())


if __name__ == "__main__":
    unittest.main()
