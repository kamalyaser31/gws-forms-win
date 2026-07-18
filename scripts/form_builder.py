# -*- coding: utf-8 -*-
"""
form_builder.py — Reusable Google Forms builder for Windows via gws (npm).

Key design: calls node.exe + run-gws.js directly to avoid PowerShell/cmd
escaping issues with JSON containing special chars (&, ", ', —).

Full API reference: see REFERENCE.md in this skill folder.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────

SKILL_SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_SCRIPTS.parent

NODE_EXE = os.environ.get("GWS_FORMS_NODE_EXE", r"C:\Program Files\nodejs\node.exe")
GWS_JS = os.environ.get(
    "GWS_FORMS_GWS_JS",
    str(
        Path.home()
        / "AppData"
        / "Roaming"
        / "npm"
        / "node_modules"
        / "@googleworkspace"
        / "cli"
        / "run-gws.js"
    ),
)


class GwsCommandError(RuntimeError):
    """A gws process completed with a non-zero exit code."""

    def __init__(self, returncode: int, stderr: str):
        message = stderr.strip() or f"gws exited with code {returncode}"
        super().__init__(message)
        self.returncode = returncode


# ─── Core runner ─────────────────────────────────────────────────────────────


def _gws_command(gws_args: list, json_body: dict, params: dict) -> list:
    command = [NODE_EXE, GWS_JS] + gws_args
    if params:
        command += ["--params", json.dumps(params, ensure_ascii=False)]
    if json_body:
        command += ["--json", json.dumps(json_body, ensure_ascii=False)]
    return command


def run_gws(
    gws_args: list,
    json_body: dict = None,
    params: dict = None,
    verbose: bool = True,
) -> dict:
    """
    Call gws via node.exe directly (bypasses ps1 wrapper and all shell escaping).

    Args:
        gws_args: positional args e.g. ["forms", "forms", "batchUpdate"]
        json_body: request body dict -> passed as --json
        params:    URL/query params  -> passed as --params (e.g. {"formId": "..."})
        verbose:   print a progress line

    Returns:
        parsed JSON response dict (empty dict if no output)

    Raises:
        GwsCommandError: the gws process returned a non-zero exit code.
    """
    if verbose:
        print(f"  >> gws {' '.join(gws_args)}")

    completed_process = subprocess.run(
        _gws_command(gws_args, json_body, params),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    if completed_process.returncode != 0:
        raise GwsCommandError(
            completed_process.returncode,
            completed_process.stderr,
        )

    response_text = completed_process.stdout.strip()
    return json.loads(response_text) if response_text else {}


# ─── High-level helpers ───────────────────────────────────────────────────────


def create_form(title: str, document_title: str = "") -> tuple:
    """
    Create an empty form. Returns (form_id, responder_url, revision_id).
    NOTE: Only title/documentTitle accepted at creation time.
          All items must be added via batchUpdate afterward.
    """
    body = {"info": {"title": title, "documentTitle": document_title or title}}
    created_form = run_gws(["forms", "forms", "create"], json_body=body)
    return (
        created_form["formId"],
        created_form.get("responderUri", ""),
        created_form.get("revisionId", ""),
    )


def batch_update(
    form_id: str,
    requests: list,
    include_form: bool = False,
    revision_id: str = "",
) -> dict:
    """Push a list of request dicts to an existing form."""
    body = {"requests": requests}
    if include_form:
        body["includeFormInResponse"] = True
    if revision_id:
        body["writeControl"] = {"requiredRevisionId": revision_id}
    return run_gws(
        ["forms", "forms", "batchUpdate"],
        json_body=body,
        params={"formId": form_id},
    )


def build_form(
    title: str, items: list, document_title: str = "", quiz_mode: bool = False
) -> dict:
    """
    One-shot: create form + optionally enable quiz + add all items.
    Returns {"formId", "responderUri", "editUrl"}.
    """
    form_id, responder_url, _ = create_form(title, document_title)

    all_requests = []

    if quiz_mode:
        all_requests.append(enable_quiz_request())

    all_requests.extend(items)
    if all_requests:
        batch_update(form_id, all_requests)

    edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    print("\n[OK] Form ready")
    print(f"     Responder : {responder_url}")
    print(f"     Edit      : {edit_url}")
    return {"formId": form_id, "responderUri": responder_url, "editUrl": edit_url}


def get_form(form_id: str) -> dict:
    """Fetch the full form object."""
    return run_gws(["forms", "forms", "get"], params={"formId": form_id})


def list_responses(form_id: str, page_size: int = 100, after: str = "") -> list:
    """
    Fetch all responses. after = RFC3339 timestamp filter.
    Returns flat list of FormResponse dicts.
    """
    all_responses = []
    page_token = None

    while True:
        p = {"formId": form_id, "pageSize": page_size}
        if after:
            p["filter"] = f'timestamp > "{after}"'
        if page_token:
            p["pageToken"] = page_token

        response_page = run_gws(["forms", "forms", "responses", "list"], params=p)
        all_responses.extend(response_page.get("responses", []))

        page_token = response_page.get("nextPageToken")
        if not page_token:
            break

    return all_responses


def enable_quiz(form_id: str) -> dict:
    """Enable quiz mode on an existing form."""
    return batch_update(form_id, [enable_quiz_request()])


def set_publish(form_id: str, published: bool = True, accepting: bool = True) -> dict:
    """Publish or unpublish a form (not supported on legacy forms)."""
    return run_gws(
        ["forms", "forms", "setPublishSettings"],
        json_body={
            "publishSettings": {
                "isPublished": published,
                "isAcceptingResponses": accepting,
            },
            "updateMask": "*",
        },
        params={"formId": form_id},
    )


# ─── Settings request builders ───────────────────────────────────────────────


def enable_quiz_request() -> dict:
    """batchUpdate request to enable quiz mode."""
    return {
        "updateSettings": {
            "settings": {"quizSettings": {"isQuiz": True}},
            "updateMask": "quizSettings.isQuiz",
        }
    }


def update_form_info_request(
    title: str = None, description: str = None, document_title: str = None
) -> dict:
    """batchUpdate request to update form title/description."""
    info = {}
    mask_parts = []
    if title is not None:
        info["title"] = title
        mask_parts.append("title")
    if description is not None:
        info["description"] = description
        mask_parts.append("description")
    if document_title is not None:
        info["documentTitle"] = document_title
        mask_parts.append("documentTitle")
    return {"updateFormInfo": {"info": info, "updateMask": ",".join(mask_parts) or "*"}}


# ─── Item builders ───────────────────────────────────────────────────────────


def make_page_break(title: str, index: int, description: str = "") -> dict:
    """Section header / page break."""
    item = {"title": title, "pageBreakItem": {}}
    if description:
        item["description"] = description
    return {"createItem": {"item": item, "location": {"index": index}}}


def make_text_item(title: str, index: int, description: str = "") -> dict:
    """Static (non-interactive) text block."""
    item = {"title": title, "textItem": {}}
    if description:
        item["description"] = description
    return {"createItem": {"item": item, "location": {"index": index}}}


def make_short_answer(
    question_text: str, index: int, paragraph: bool = True, required: bool = True
) -> dict:
    """
    Text question.
    paragraph=True  -> multi-line paragraph
    paragraph=False -> single-line short answer
    """
    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {
                        "required": required,
                        "textQuestion": {"paragraph": paragraph},
                    }
                },
            },
            "location": {"index": index},
        }
    }


def make_mcq(
    question_text: str,
    options: list,
    index: int,
    question_type: str = "RADIO",
    shuffle: bool = False,
    required: bool = True,
) -> dict:
    """
    Choice question.
    question_type: "RADIO" | "CHECKBOX" | "DROP_DOWN"
    options: list of strings e.g. ["A. Yes", "B. No"]
    """
    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {
                        "required": required,
                        "choiceQuestion": {
                            "type": question_type,
                            "options": [{"value": opt} for opt in options],
                            "shuffle": shuffle,
                        },
                    }
                },
            },
            "location": {"index": index},
        }
    }


def make_mcq_graded(
    question_text: str,
    options: list,
    index: int,
    correct: str,
    points: int = 1,
    feedback_right: str = "",
    feedback_wrong: str = "",
    question_type: str = "RADIO",
    required: bool = True,
) -> dict:
    """
    Choice question with automatic grading (quiz mode must be enabled).
    correct: the exact string value of the correct option.
    """
    grading = {
        "pointValue": points,
        "correctAnswers": {"answers": [{"value": correct}]},
    }
    if feedback_right:
        grading["whenRight"] = {"text": feedback_right}
    if feedback_wrong:
        grading["whenWrong"] = {"text": feedback_wrong}

    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {
                        "required": required,
                        "choiceQuestion": {
                            "type": question_type,
                            "options": [{"value": opt} for opt in options],
                            "shuffle": False,
                        },
                        "grading": grading,
                    }
                },
            },
            "location": {"index": index},
        }
    }


def make_scale(
    question_text: str,
    index: int,
    low: int = 1,
    high: int = 5,
    low_label: str = "",
    high_label: str = "",
    required: bool = False,
) -> dict:
    """Linear scale question (1–10 range)."""
    q = {"low": low, "high": high}
    if low_label:
        q["lowLabel"] = low_label
    if high_label:
        q["highLabel"] = high_label
    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {"required": required, "scaleQuestion": q}
                },
            },
            "location": {"index": index},
        }
    }


def make_date(
    question_text: str,
    index: int,
    include_time: bool = False,
    include_year: bool = True,
    required: bool = False,
) -> dict:
    """Date (and optionally time) question."""
    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {
                        "required": required,
                        "dateQuestion": {
                            "includeTime": include_time,
                            "includeYear": include_year,
                        },
                    }
                },
            },
            "location": {"index": index},
        }
    }


def make_time(
    question_text: str, index: int, duration: bool = False, required: bool = False
) -> dict:
    """
    Time question.
    duration=False -> time of day (HH:MM)
    duration=True  -> elapsed duration
    """
    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {
                        "required": required,
                        "timeQuestion": {"duration": duration},
                    }
                },
            },
            "location": {"index": index},
        }
    }


def make_rating(
    question_text: str,
    index: int,
    scale: int = 5,
    icon: str = "STAR",
    required: bool = False,
) -> dict:
    """
    Rating question.
    icon: "STAR" | "HEART" | "THUMB_UP"
    """
    return {
        "createItem": {
            "item": {
                "title": question_text,
                "questionItem": {
                    "question": {
                        "required": required,
                        "ratingQuestion": {
                            "ratingScaleLevel": scale,
                            "iconType": icon,
                        },
                    }
                },
            },
            "location": {"index": index},
        }
    }


def make_grid(
    title: str,
    rows: list,
    col_options: list,
    index: int,
    col_type: str = "RADIO",
    shuffle_rows: bool = False,
    required: bool = False,
) -> dict:
    """
    Grid question (questionGroupItem).
    rows: list of row label strings
    col_options: list of column value strings
    col_type: "RADIO" | "CHECKBOX"
    """
    return {
        "createItem": {
            "item": {
                "title": title,
                "questionGroupItem": {
                    "questions": [
                        {"rowQuestion": {"title": r}, "required": required}
                        for r in rows
                    ],
                    "grid": {
                        "columns": {
                            "type": col_type,
                            "options": [{"value": c} for c in col_options],
                        },
                        "shuffleQuestions": shuffle_rows,
                    },
                },
            },
            "location": {"index": index},
        }
    }


def make_video(
    title: str,
    youtube_uri: str,
    index: int,
    caption: str = "",
    alignment: str = "CENTER",
    width: int = 640,
) -> dict:
    """YouTube video item."""
    item = {
        "title": title,
        "videoItem": {
            "video": {
                "youtubeUri": youtube_uri,
                "properties": {"alignment": alignment, "width": width},
            }
        },
    }
    if caption:
        item["videoItem"]["caption"] = caption
    return {"createItem": {"item": item, "location": {"index": index}}}


def make_image(
    title: str,
    source_uri: str,
    index: int,
    alt_text: str = "",
    alignment: str = "CENTER",
    width: int = 640,
) -> dict:
    """Image item (sourceUri must be a public URL)."""
    item = {
        "title": title,
        "imageItem": {
            "image": {
                "sourceUri": source_uri,
                "altText": alt_text,
                "properties": {"alignment": alignment, "width": width},
            }
        },
    }
    return {"createItem": {"item": item, "location": {"index": index}}}


# ─── Example / smoke test ────────────────────────────────────────────────────

if __name__ == "__main__":
    items = [
        make_page_break("Section 1 — Text Questions", 0, "Answer fully."),
        make_short_answer("What is your name?", 1, paragraph=False),
        make_short_answer("Describe yourself.", 2, paragraph=True),
        make_page_break("Section 2 — Choice Questions", 3),
        make_mcq("Favourite colour?", ["A. Red", "B. Blue", "C. Green"], 4),
        make_scale("Rate this form:", 5, 1, 5, "Poor", "Excellent"),
        make_date("Your date of birth:", 6, include_year=True),
        make_grid(
            "Rate each subject:",
            ["Math", "Science", "Arabic"],
            ["Poor", "Good", "Excellent"],
            7,
        ),
    ]
    try:
        created_form = build_form("Test Form — All Types", items, quiz_mode=False)
    except GwsCommandError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        sys.exit(error.returncode)
    print(created_form)
