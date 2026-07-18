# -*- coding: utf-8 -*-
"""
tests/test_reader.py
====================
Unit tests for form_reader.py — all API calls mocked.

Priority order (most critical first):
  1. Pagination — nextPageToken loop fetches all pages
  2. URL parsing — rejects /e/ URLs, accepts edit & plain viewform
  3. Response normalisation — answers flattened correctly
  4. Filter --after passed to API correctly
  5. Output file written correctly
  6. Edge cases — zero responses, missing answers field
"""

import json
import os
import sys
import pytest
from unittest.mock import patch

import form_reader as reader

# ─── 1. Pagination ────────────────────────────────────────────────────────────


class TestPagination:

    def _make_page(self, ids, next_token=None):
        page = {"responses": [{"responseId": i, "answers": {}} for i in ids]}
        if next_token:
            page["nextPageToken"] = next_token
        return page

    def test_single_page_no_token(self):
        pages = [self._make_page(["r1", "r2"])]
        with patch.object(reader, "run_gws", side_effect=pages):
            result = reader.fetch_all_responses("FORM_ID")
        assert len(result) == 2

    def test_two_pages_collected(self):
        pages = [
            self._make_page(["r1", "r2"], next_token="TOKEN_1"),
            self._make_page(["r3", "r4"]),
        ]
        with patch.object(reader, "run_gws", side_effect=pages):
            result = reader.fetch_all_responses("FORM_ID")
        assert len(result) == 4

    def test_three_pages_all_collected(self):
        pages = [
            self._make_page(["r1"], next_token="T1"),
            self._make_page(["r2"], next_token="T2"),
            self._make_page(["r3"]),
        ]
        with patch.object(reader, "run_gws", side_effect=pages):
            result = reader.fetch_all_responses("FORM_ID")
        assert len(result) == 3

    def test_page_token_sent_in_second_call(self):
        pages = [
            self._make_page(["r1"], next_token="MY_TOKEN"),
            self._make_page(["r2"]),
        ]
        with patch.object(reader, "run_gws", side_effect=pages) as mock_gws:
            reader.fetch_all_responses("FORM_ID")
        second_call_params = mock_gws.call_args_list[1][1]["params"]
        assert second_call_params.get("pageToken") == "MY_TOKEN"

    def test_after_filter_included_in_params(self):
        with patch.object(
            reader, "run_gws", return_value={"responses": []}
        ) as mock_gws:
            reader.fetch_all_responses("FORM_ID", after="2026-01-01T00:00:00Z")
        params = mock_gws.call_args[1]["params"]
        assert "filter" in params
        assert "2026-01-01T00:00:00Z" in params["filter"]

    def test_no_after_no_filter_key(self):
        with patch.object(
            reader, "run_gws", return_value={"responses": []}
        ) as mock_gws:
            reader.fetch_all_responses("FORM_ID", after="")
        params = mock_gws.call_args[1]["params"]
        assert "filter" not in params

    def test_empty_responses_returns_empty_list(self):
        with patch.object(reader, "run_gws", return_value={}):
            result = reader.fetch_all_responses("FORM_ID")
        assert result == []


# ─── 2. URL parsing ───────────────────────────────────────────────────────────


class TestUrlParsing:

    def test_edit_url_extracted(self):
        url = "https://docs.google.com/forms/d/FORM999/edit"
        assert reader.extract_form_id(url) == "FORM999"

    def test_plain_viewform_extracted(self):
        url = "https://docs.google.com/forms/d/FORM999/viewform"
        assert reader.extract_form_id(url) == "FORM999"

    def test_encoded_viewform_rejected(self):
        url = "https://docs.google.com/forms/d/e/LONG_ENCODED_ID/viewform"
        with pytest.raises(SystemExit) as exc:
            reader.extract_form_id(url)
        assert exc.value.code == 1

    def test_arbitrary_url_rejected(self):
        with pytest.raises(SystemExit) as exc:
            reader.extract_form_id("https://google.com")
        assert exc.value.code == 1


# ─── 3. Response normalisation ───────────────────────────────────────────────


class TestNormalisation:

    def _raw(self, **kwargs):
        base = {
            "responseId": "RESP_001",
            "createTime": "2026-01-01T10:00:00Z",
            "lastSubmittedTime": "2026-01-01T10:01:00Z",
            "answers": {},
        }
        base.update(kwargs)
        return base

    def test_response_id_preserved(self):
        n = reader.normalise_response(self._raw())
        assert n["responseId"] == "RESP_001"

    def test_create_time_preserved(self):
        n = reader.normalise_response(self._raw())
        assert n["createTime"] == "2026-01-01T10:00:00Z"

    def test_text_answer_flattened(self):
        raw = self._raw(
            answers={
                "Q_001": {
                    "textAnswers": {"answers": [{"value": "Hello"}, {"value": "World"}]}
                }
            }
        )
        n = reader.normalise_response(raw)
        assert n["answers"]["Q_001"]["textAnswers"] == ["Hello", "World"]

    def test_multiple_questions(self):
        raw = self._raw(
            answers={
                "Q_001": {"textAnswers": {"answers": [{"value": "A"}]}},
                "Q_002": {"textAnswers": {"answers": [{"value": "B"}]}},
            }
        )
        n = reader.normalise_response(raw)
        assert len(n["answers"]) == 2
        assert n["answers"]["Q_001"]["textAnswers"] == ["A"]
        assert n["answers"]["Q_002"]["textAnswers"] == ["B"]

    def test_missing_answers_field(self):
        """Response with no 'answers' key must not crash."""
        raw = {
            "responseId": "R1",
            "createTime": "2026-01-01T00:00:00Z",
            "lastSubmittedTime": "",
        }
        n = reader.normalise_response(raw)
        assert n["answers"] == {}

    def test_empty_text_answers(self):
        raw = self._raw(answers={"Q_001": {"textAnswers": {"answers": []}}})
        n = reader.normalise_response(raw)
        assert n["answers"]["Q_001"]["textAnswers"] == []

    def test_rich_fields_preserved(self):
        raw = self._raw(
            respondentEmail="person@example.com",
            totalScore=3,
            answers={
                "Q_001": {
                    "questionId": "Q_001",
                    "grade": {"score": 3, "correct": True},
                    "fileUploadAnswers": {
                        "answers": [{"fileId": "F1", "fileName": "a.pdf"}]
                    },
                }
            },
        )
        n = reader.normalise_response(raw)
        assert n["respondentEmail"] == "person@example.com"
        assert n["totalScore"] == 3
        assert n["answers"]["Q_001"]["grade"]["score"] == 3
        assert n["answers"]["Q_001"]["fileUploadAnswers"][0]["fileId"] == "F1"


# ─── 4. Output file ───────────────────────────────────────────────────────────


class TestOutputFile:

    def test_output_written_with_correct_structure(self, tmp_path):
        out_path = os.path.join(tmp_path, "out.json")
        pages = [
            {
                "responseId": "R1",
                "createTime": "",
                "lastSubmittedTime": "",
                "answers": {},
            }
        ]
        with patch.object(
            reader, "run_gws", return_value={"responses": pages}
        ), patch.object(
            sys, "argv", ["form_reader.py", "--id", "FORMXYZ", "--output", out_path]
        ):
            reader.main()

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["form_id"] == "FORMXYZ"
        assert data["total"] == 1
        assert "fetched_at" in data
        assert isinstance(data["responses"], list)

    def test_default_output_filename(self, tmp_path, monkeypatch):
        """Without --output, file should be named <form_id>_responses.json."""
        monkeypatch.chdir(tmp_path)
        with patch.object(
            reader, "run_gws", return_value={"responses": []}
        ), patch.object(sys, "argv", ["form_reader.py", "--id", "MYFORM"]):
            reader.main()
        assert os.path.exists(os.path.join(tmp_path, "MYFORM_responses.json"))

    def test_zero_responses_file_written(self, tmp_path):
        out_path = os.path.join(tmp_path, "zero.json")
        with patch.object(reader, "run_gws", return_value={}), patch.object(
            sys, "argv", ["form_reader.py", "--id", "F", "--output", out_path]
        ):
            reader.main()
        data = json.loads(open(out_path, encoding="utf-8").read())
        assert data["total"] == 0
        assert data["responses"] == []
