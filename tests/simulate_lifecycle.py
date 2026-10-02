# -*- coding: utf-8 -*-
"""
tests/simulate_lifecycle.py — Complete offline lifecycle simulation for gws-forms-win.

Simulates all 4 stages of the skill's workflow:
  Stage 1: Creation & request serialization (11 item types + quiz grading).
  Stage 2: Snapshot building & structure inspection.
  Stage 3: Incremental updates & operations dispatch.
  Stage 4: Response retrieval & grade normalization.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
OUTPUT_DIR = SKILL_ROOT / "output" / "simulation"
sys.path.insert(0, str(SCRIPTS_DIR))

from form_builder import (  # noqa: E402
    build_requests_from_spec,
    write_json_atomic,
)
from form_fetcher import build_snapshot  # noqa: E402
from form_reader import normalise_response, question_titles  # noqa: E402
from form_updater import execute_operation, load_snapshot  # noqa: E402


def run_simulation() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    spec_path = Path(__file__).resolve().parent / "comprehensive_form.json"

    print("=" * 70)
    print(" GWS-FORMS-WIN — SIMULATING COMPLETE LIFECYCLE (ALL 11 ITEM TYPES)")
    print("=" * 70)

    # ── STAGE 1: Form Creation & Payload Serialization ──────────────────────
    print("\n[STAGE 1] Loading comprehensive JSON spec and serializing API requests...")
    with spec_path.open(encoding="utf-8") as f:
        spec = json.load(f)

    requests = build_requests_from_spec(spec)
    print(f"  ✓ Successfully serialized {len(requests)} Google Forms API requests.")

    # Count item categories
    type_counts = {}
    for item in spec["items"]:
        t = item["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"  ✓ Item types covered ({len(type_counts)} types): {type_counts}")

    mock_form_id = "1AbC_Simulation_Form_ID_xyz789"
    mock_responder_uri = f"https://docs.google.com/forms/d/e/{mock_form_id}/viewform"

    # Save serialized requests for audit
    serialized_path = OUTPUT_DIR / "stage1_serialized_requests.json"
    write_json_atomic(
        serialized_path, {"total_requests": len(requests), "requests": requests}
    )
    print(f"  ✓ Stage 1 payload saved -> {serialized_path}")

    # ── STAGE 2: Snapshot Generation ────────────────────────────────────────
    print(
        "\n[STAGE 2] Building form snapshot from simulated Google Forms API response..."
    )
    # Build simulated raw API form object based on requests
    mock_raw_items = []
    for idx, req in enumerate(requests):
        if "createItem" in req:
            item_payload = req["createItem"]["item"].copy()
            item_payload["itemId"] = f"item_{idx:03d}"
            mock_raw_items.append(item_payload)

    mock_raw_form = {
        "formId": mock_form_id,
        "info": {
            "title": spec["title"],
            "description": spec["desc"],
            "documentTitle": spec.get("doc_title", spec["title"]),
        },
        "settings": {"quizSettings": {"isQuiz": spec.get("quiz", False)}},
        "items": mock_raw_items,
        "revisionId": "rev_00001",
        "responderUri": mock_responder_uri,
    }

    snapshot = build_snapshot(mock_form_id, mock_raw_form)
    snapshot_path = OUTPUT_DIR / f"{mock_form_id}_snapshot.json"
    write_json_atomic(snapshot_path, snapshot)
    print(f"  ✓ Snapshot created with {snapshot['item_count']} items.")
    print(f"  ✓ Stage 2 snapshot saved -> {snapshot_path}")

    # ── STAGE 3: Form Updating (Incremental Operations) ─────────────────────
    print("\n[STAGE 3] Executing update operations against snapshot...")
    update_spec = {
        "form_id": mock_form_id,
        "ops": [
            {
                "op": "update_info",
                "title": "الاختبار الشامل للعلوم والتقنية — بعد التحديث والمراجعة",
                "description": "تم تحديث وصف الاختبار وتعليمات التقييم الإلكتروني.",
            },
            {
                "op": "add_item",
                "item": {
                    "type": "short",
                    "q": "الرقم الأكاديمي للطالب (إلزامي):",
                    "paragraph": False,
                    "required": True,
                },
                "at_index": 2,
            },
        ],
    }
    update_spec_path = OUTPUT_DIR / "stage3_update_spec.json"
    write_json_atomic(update_spec_path, update_spec)

    current_snap = load_snapshot(mock_form_id, snapshot_path=snapshot_path)
    with patch("form_updater.batch_update") as mock_batch:
        mock_batch.return_value = {"form": mock_raw_form}
        with patch("form_updater.get_form") as mock_get:
            # Add new item into simulated raw for refreshed snapshot
            updated_raw = mock_raw_form.copy()
            updated_raw["items"] = list(mock_raw_form["items"])
            updated_raw["items"].insert(
                2,
                {
                    "itemId": "item_new_099",
                    "title": "الرقم الأكاديمي للطالب (إلزامي):",
                    "questionItem": {
                        "question": {
                            "required": True,
                            "textQuestion": {"paragraph": False},
                        }
                    },
                },
            )
            mock_get.return_value = updated_raw

            for op in update_spec["ops"]:
                succeeded, current_snap = execute_operation(
                    mock_form_id, op, current_snap, snapshot_path=snapshot_path
                )
                print(
                    f"  ✓ Executed op '{op['op']}': "
                    f"{'SUCCESS' if succeeded else 'FAILED'}"
                )

    print(f"  ✓ Form items count after update: {current_snap['item_count']}")

    # ── STAGE 4: Response Normalization ─────────────────────────────────────
    print("\n[STAGE 4] Normalizing respondent answers and calculating scores...")
    mock_raw_response = {
        "responseId": "resp_std_2026_001",
        "createTime": "2026-09-29T21:00:00Z",
        "lastSubmittedTime": "2026-09-29T21:25:30Z",
        "respondentEmail": "kamal@example.com",
        "totalScore": 5.0,
        "answers": {
            "item_002": {
                "questionId": "item_002",
                "textAnswers": {"answers": [{"value": "كمال ياسر"}]},
            },
            "item_005": {
                "questionId": "item_005",
                "textAnswers": {"answers": [{"value": "O(log n)"}]},
                "grade": {
                    "score": 5.0,
                    "correct": True,
                    "feedback": {
                        "text": (
                            "إجابة صحيحة ومتقنة! البحث الثنائي يقسم "
                            "فضاء البحث إلى النصف في كل خطوة."
                        )
                    },
                },
            },
            "item_008": {
                "questionId": "item_008",
                "textAnswers": {"answers": [{"value": "5"}]},
            },
            "item_015": {
                "questionId": "item_015",
                "textAnswers": {
                    "answers": [
                        {
                            "value": (
                                "تسهم الشفرة النظيفة في تسهيل فهم النظام "
                                "وخفض تكلفة التعديل المستقبلي."
                            )
                        }
                    ]
                },
            },
        },
    }

    clean_resp = normalise_response(mock_raw_response, question_titles(mock_raw_form))
    final_output = {
        "form_id": mock_form_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total": 1,
        "responses": [clean_resp],
    }
    responses_path = OUTPUT_DIR / f"{mock_form_id}_responses.json"
    write_json_atomic(responses_path, final_output)
    print(f"  ✓ Normalized response for: {clean_resp['respondentEmail']}")
    print(f"  ✓ Total Student Score: {clean_resp['totalScore']} pts")
    print(f"  ✓ Stage 4 output saved -> {responses_path}")

    print("\n" + "=" * 70)
    print(" [COMPLETED] ALL 4 LIFECYCLE STAGES SIMULATED SUCCESSFULLY!")
    print(f" Output directory: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    run_simulation()
