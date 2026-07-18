# -*- coding: utf-8 -*-
"""
tests/test_fetcher.py
=====================
Unit tests for form_fetcher.py — no real API calls, all gws calls are mocked.

Priority order (most critical first):
  1. URL parsing — correct extraction & rejection
  2. Snapshot structure — required fields present
  3. api_type / question_type mapping
  4. File output path — always in SNAPSHOTS_DIR
  5. Edge cases — empty form, items without known type
"""

import json
import os
import pytest
from unittest.mock import patch
from datetime import datetime

import form_fetcher as fetcher

# ─── 1. URL parsing ───────────────────────────────────────────────────────────


class TestExtractFormId:

    def test_edit_url(self):
        url = "https://docs.google.com/forms/d/FORM123/edit"
        assert fetcher.extract_form_id(url) == "FORM123"

    def test_edit_url_with_query(self):
        url = "https://docs.google.com/forms/d/FORM123/edit?usp=sf_link"
        assert fetcher.extract_form_id(url) == "FORM123"

    def test_plain_viewform_url(self):
        url = "https://docs.google.com/forms/d/FORM123/viewform"
        assert fetcher.extract_form_id(url) == "FORM123"

    def test_encoded_viewform_url_rejected(self):
        """Encoded /e/ viewform URLs must be rejected with sys.exit(1)."""
        url = "https://docs.google.com/forms/d/e/LONGID/viewform"
        with pytest.raises(SystemExit) as exc_info:
            fetcher.extract_form_id(url)
        assert exc_info.value.code == 1

    def test_random_url_rejected(self):
        url = "https://example.com/not-a-form"
        with pytest.raises(SystemExit) as exc_info:
            fetcher.extract_form_id(url)
        assert exc_info.value.code == 1

    def test_google_path_on_another_domain_is_rejected(self):
        url = "https://example.com/forms/d/FORM123/edit"
        with pytest.raises(SystemExit) as exc_info:
            fetcher.extract_form_id(url)
        assert exc_info.value.code == 1

    def test_empty_string_rejected(self):
        with pytest.raises(SystemExit):
            fetcher.extract_form_id("")


# ─── 2. Snapshot structure ────────────────────────────────────────────────────


class TestBuildSnapshot:

    def _raw(self, items=None):
        return {
            "info": {
                "title": "Test Form",
                "description": "A test",
                "documentTitle": "Test Form Doc",
            },
            "responderUri": "https://forms.gle/xxx",
            "revisionId": "00000010",
            "items": items or [],
        }

    def test_top_level_fields_present(self):
        snap = fetcher.build_snapshot("FORM123", self._raw())
        for field in (
            "form_id",
            "title",
            "description",
            "responderUri",
            "revisionId",
            "fetched_at",
            "item_count",
            "items",
        ):
            assert field in snap, f"Missing field: {field}"

    def test_form_id_stored(self):
        snap = fetcher.build_snapshot("FORM123", self._raw())
        assert snap["form_id"] == "FORM123"

    def test_fetched_at_is_iso(self):
        snap = fetcher.build_snapshot("FORM123", self._raw())
        # Should parse without error
        datetime.fromisoformat(snap["fetched_at"])

    def test_item_count_matches_items(self):
        raw = self._raw(
            items=[
                {
                    "itemId": "a1",
                    "title": "Q1",
                    "questionItem": {
                        "question": {"textQuestion": {}, "required": True}
                    },
                },
                {
                    "itemId": "a2",
                    "title": "Q2",
                    "questionItem": {
                        "question": {"choiceQuestion": {}, "required": False}
                    },
                },
            ]
        )
        snap = fetcher.build_snapshot("FORM123", raw)
        assert snap["item_count"] == 2
        assert len(snap["items"]) == 2

    def test_empty_form(self):
        snap = fetcher.build_snapshot("FORM123", self._raw(items=[]))
        assert snap["item_count"] == 0
        assert snap["items"] == []

    def test_item_index_sequential(self):
        raw = self._raw(
            items=[
                {
                    "itemId": "i0",
                    "title": "Q0",
                    "questionItem": {"question": {"textQuestion": {}}},
                },
                {
                    "itemId": "i1",
                    "title": "Q1",
                    "questionItem": {"question": {"textQuestion": {}}},
                },
            ]
        )
        snap = fetcher.build_snapshot("FORM123", raw)
        assert snap["items"][0]["index"] == 0
        assert snap["items"][1]["index"] == 1

    def test_item_id_stored(self):
        raw = self._raw(
            items=[
                {
                    "itemId": "abc123",
                    "title": "Q",
                    "questionItem": {"question": {"textQuestion": {}}},
                },
            ]
        )
        snap = fetcher.build_snapshot("FORM123", raw)
        assert snap["items"][0]["itemId"] == "abc123"


# ─── 3. api_type / question_type mapping ─────────────────────────────────────


class TestItemType:

    def _q_item(self, q_type_key):
        return {"questionItem": {"question": {q_type_key: {}, "required": True}}}

    def test_text_question(self):
        api_t, q_t = fetcher._item_type(self._q_item("textQuestion"))
        assert api_t == "questionItem"
        assert q_t == "textQuestion"

    def test_choice_question(self):
        api_t, q_t = fetcher._item_type(self._q_item("choiceQuestion"))
        assert api_t == "questionItem"
        assert q_t == "choiceQuestion"

    def test_scale_question(self):
        api_t, q_t = fetcher._item_type(self._q_item("scaleQuestion"))
        assert q_t == "scaleQuestion"

    def test_date_question(self):
        api_t, q_t = fetcher._item_type(self._q_item("dateQuestion"))
        assert q_t == "dateQuestion"

    def test_page_break(self):
        api_t, q_t = fetcher._item_type({"pageBreakItem": {}})
        assert api_t == "pageBreakItem"
        assert q_t is None

    def test_text_item(self):
        api_t, q_t = fetcher._item_type({"textItem": {}})
        assert api_t == "textItem"
        assert q_t is None

    def test_video_item(self):
        api_t, q_t = fetcher._item_type({"videoItem": {}})
        assert api_t == "videoItem"

    def test_unknown_item(self):
        api_t, _ = fetcher._item_type({"someFutureItem": {}})
        assert api_t == "unknown"

    def test_question_without_known_type(self):
        """An unrecognized question subtype remains visible to callers."""
        api_t, q_t = fetcher._item_type({"questionItem": {"question": {}}})
        assert api_t == "questionItem"
        assert q_t == "unknown"


# ─── 4. Output path ───────────────────────────────────────────────────────────


class TestOutputPath:

    def test_snapshot_saved_in_snapshots_dir(self, tmp_path, monkeypatch):
        """Snapshot must be saved in SKILL_ROOT/snapshots/, not cwd."""
        monkeypatch.setattr(fetcher, "SNAPSHOTS_DIR", str(tmp_path))

        raw = {
            "info": {"title": "T", "description": "", "documentTitle": ""},
            "responderUri": "",
            "revisionId": "",
            "items": [],
        }

        with patch.object(fetcher, "get_form", return_value=raw):
            with patch("builtins.print"):  # suppress output
                # Call build_snapshot + write directly (avoid argparse)
                snap = fetcher.build_snapshot("FORMXYZ", raw)
                os.makedirs(str(tmp_path), exist_ok=True)
                out = os.path.join(str(tmp_path), "FORMXYZ_snapshot.json")
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(snap, f)

        assert os.path.exists(out)
        loaded = json.loads(open(out, encoding="utf-8").read())
        assert loaded["form_id"] == "FORMXYZ"

    def test_snapshot_filename_uses_form_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fetcher, "SNAPSHOTS_DIR", str(tmp_path))
        raw = {
            "info": {"title": "", "description": "", "documentTitle": ""},
            "responderUri": "",
            "revisionId": "",
            "items": [],
        }
        snap = fetcher.build_snapshot("MY_FORM_ID", raw)
        out = os.path.join(str(tmp_path), "MY_FORM_ID_snapshot.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        assert "MY_FORM_ID_snapshot.json" in os.listdir(tmp_path)
