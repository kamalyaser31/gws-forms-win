# -*- coding: utf-8 -*-
"""
form_builder.py — Reusable Google Forms builder for Windows via gws (npm).

Key design: calls node.exe + run-gws.js directly to avoid PowerShell/cmd
escaping issues with JSON containing special chars (&, ", ', —).

Full API reference: see REFERENCE.md in this skill folder.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# ─── Paths ───────────────────────────────────────────────────────────────────

SKILL_SCRIPTS = Path(__file__).resolve().parent
SKILL_ROOT = SKILL_SCRIPTS.parent


def resolve_node_exe() -> str:
    """Resolve node executable dynamically from env or system PATH."""
    env_node = os.environ.get("GWS_FORMS_NODE_EXE")
    if env_node:
        return env_node
    which_node = shutil.which("node")
    if which_node:
        return which_node
    return "node"


def resolve_gws_js() -> str:
    """Resolve run.js or run-gws.js entrypoint from env or standard npm prefix."""
    env_gws = os.environ.get("GWS_FORMS_GWS_JS")
    if env_gws:
        return env_gws
    cli_dir = (
        Path.home()
        / "AppData"
        / "Roaming"
        / "npm"
        / "node_modules"
        / "@googleworkspace"
        / "cli"
    )
    for candidate in ("run.js", "run-gws.js"):
        target = cli_dir / candidate
        if target.exists():
            return str(target)
    return str(cli_dir / "run.js")


NODE_EXE = resolve_node_exe()
GWS_JS = resolve_gws_js()


class GwsCommandError(RuntimeError):
    """A gws process completed with a non-zero exit code."""

    def __init__(self, returncode: int, stderr: str):
        message = stderr.strip() or f"gws exited with code {returncode}"
        super().__init__(message)
        self.returncode = returncode


# ─── URL parsing & storage helpers ──────────────────────────────────────────

FORM_PATH = re.compile(r"^/forms/d/([^/]+)/(?:edit|viewform)/?$")
ENCODED_FORM_PATH = re.compile(r"^/forms/d/e/[^/]+/viewform/?$")


def extract_form_id(url: str) -> str:
    """Return a form ID from an authenticated Google Forms URL."""
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "docs.google.com":
        raise ValueError(
            "Could not extract form_id from URL: must start with https://docs.google.com/forms/d/<ID>/edit"
        )

    if ENCODED_FORM_PATH.fullmatch(parsed_url.path):
        raise ValueError(
            "Encoded viewform URL (/e/...) does not expose the form_id. Use the Edit URL or --id directly."
        )

    form_match = FORM_PATH.fullmatch(parsed_url.path)
    if form_match:
        return form_match.group(1)
    raise ValueError(
        "Could not extract form_id from URL path. Use: https://docs.google.com/forms/d/<ID>/edit"
    )


def write_json_atomic(path: Path, content: object) -> None:
    """Replace a JSON file only after its complete replacement is durable."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as json_file:
            json.dump(content, json_file, ensure_ascii=False, indent=2)
            json_file.flush()
            os.fsync(json_file.fileno())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


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


def build_requests_from_spec(spec: dict) -> list:
    all_requests = []
    description = spec.get("desc") or spec.get("description")
    if description:
        all_requests.append(update_form_info_request(description=description))
    if spec.get("quiz", False):
        all_requests.append(enable_quiz_request())
    for idx, item in enumerate(spec.get("items", [])):
        all_requests.append(build_item_request(item, idx))
    return all_requests


_build_requests_from_spec = build_requests_from_spec


def build_form(
    spec_or_title,
    items: list = None,
    document_title: str = "",
    quiz_mode: bool = False,
) -> dict:
    """One-shot: create form and apply all item/quiz requests atomically."""
    if isinstance(spec_or_title, dict):
        spec = spec_or_title
        title = spec["title"]
        document_title = spec.get("doc_title") or spec.get("document_title", title)
        all_requests = _build_requests_from_spec(spec)
    else:
        title = spec_or_title
        all_requests = [enable_quiz_request()] if quiz_mode else []
        if items:
            all_requests.extend(items)

    form_id, responder_url, _ = create_form(title, document_title)
    if all_requests:
        batch_update(form_id, all_requests)

    edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
    print(
        f"\n[OK] Form ready\n     Responder : {responder_url}\n     Edit      : {edit_url}"
    )
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


def _build_section_request(spec: dict, index: int) -> dict:
    item = {"title": spec["title"], "pageBreakItem": {}}
    description = spec.get("desc") or spec.get("description", "")
    if description:
        item["description"] = description
    return {"createItem": {"item": item, "location": {"index": index}}}


def _build_text_request(spec: dict, index: int) -> dict:
    item = {"title": spec["title"], "textItem": {}}
    description = spec.get("desc") or spec.get("description", "")
    if description:
        item["description"] = description
    return {"createItem": {"item": item, "location": {"index": index}}}


def _build_short_request(spec: dict, index: int) -> dict:
    return {
        "createItem": {
            "item": {
                "title": spec["q"],
                "questionItem": {
                    "question": {
                        "required": spec.get("required", True),
                        "textQuestion": {"paragraph": spec.get("paragraph", True)},
                    }
                },
            },
            "location": {"index": index},
        }
    }


def _build_choice_grading(spec: dict) -> dict:
    grading = {
        "pointValue": spec.get("points", 1),
        "correctAnswers": {"answers": [{"value": spec["correct"]}]},
    }
    if spec.get("right") or "right" not in spec:
        grading["whenRight"] = {"text": spec.get("right", "Correct!")}
    if spec.get("wrong"):
        grading["whenWrong"] = {"text": spec["wrong"]}
    return grading


def _build_mcq_request(spec: dict, index: int) -> dict:
    is_graded = "correct" in spec
    choice = {
        "type": spec.get("qtype", "RADIO"),
        "options": [{"value": opt} for opt in spec["options"]],
        "shuffle": False if is_graded else spec.get("shuffle", False),
    }
    question = {"required": spec.get("required", True), "choiceQuestion": choice}
    if is_graded:
        question["grading"] = _build_choice_grading(spec)
    return {
        "createItem": {
            "item": {"title": spec["q"], "questionItem": {"question": question}},
            "location": {"index": index},
        }
    }


def _build_scale_request(spec: dict, index: int) -> dict:
    scale_payload = {"low": spec.get("low", 1), "high": spec.get("high", 5)}
    if spec.get("low_label"):
        scale_payload["lowLabel"] = spec["low_label"]
    if spec.get("high_label"):
        scale_payload["highLabel"] = spec["high_label"]
    return {
        "createItem": {
            "item": {
                "title": spec["q"],
                "questionItem": {
                    "question": {
                        "required": spec.get("required", False),
                        "scaleQuestion": scale_payload,
                    }
                },
            },
            "location": {"index": index},
        }
    }


def _build_date_request(spec: dict, index: int) -> dict:
    return {
        "createItem": {
            "item": {
                "title": spec["q"],
                "questionItem": {
                    "question": {
                        "required": spec.get("required", False),
                        "dateQuestion": {
                            "includeTime": spec.get("time", False),
                            "includeYear": spec.get("year", True),
                        },
                    }
                },
            },
            "location": {"index": index},
        }
    }


def _build_time_request(spec: dict, index: int) -> dict:
    return {
        "createItem": {
            "item": {
                "title": spec["q"],
                "questionItem": {
                    "question": {
                        "required": spec.get("required", False),
                        "timeQuestion": {"duration": spec.get("duration", False)},
                    }
                },
            },
            "location": {"index": index},
        }
    }


def _build_rating_request(spec: dict, index: int) -> dict:
    return {
        "createItem": {
            "item": {
                "title": spec["q"],
                "questionItem": {
                    "question": {
                        "required": spec.get("required", False),
                        "ratingQuestion": {
                            "ratingScaleLevel": spec.get("scale", 5),
                            "iconType": spec.get("icon", "STAR"),
                        },
                    }
                },
            },
            "location": {"index": index},
        }
    }


def _build_grid_request(spec: dict, index: int) -> dict:
    rows = [
        {"rowQuestion": {"title": r}, "required": spec.get("required", False)}
        for r in spec["rows"]
    ]
    grid = {
        "columns": {
            "type": spec.get("col_type", "RADIO"),
            "options": [{"value": c} for c in spec["cols"]],
        },
        "shuffleQuestions": spec.get("shuffle_rows", False),
    }
    return {
        "createItem": {
            "item": {
                "title": spec["title"],
                "questionGroupItem": {"questions": rows, "grid": grid},
            },
            "location": {"index": index},
        }
    }


def _build_video_request(spec: dict, index: int) -> dict:
    video_payload = {
        "video": {
            "youtubeUri": spec["uri"],
            "properties": {
                "alignment": spec.get("align", "CENTER"),
                "width": spec.get("width", 640),
            },
        }
    }
    if spec.get("caption"):
        video_payload["caption"] = spec["caption"]
    return {
        "createItem": {
            "item": {"title": spec["title"], "videoItem": video_payload},
            "location": {"index": index},
        }
    }


def _build_image_request(spec: dict, index: int) -> dict:
    image_payload = {
        "sourceUri": spec["uri"],
        "altText": spec.get("alt", ""),
        "properties": {
            "alignment": spec.get("align", "CENTER"),
            "width": spec.get("width", 640),
        },
    }
    return {
        "createItem": {
            "item": {
                "title": spec["title"],
                "imageItem": {"image": image_payload},
            },
            "location": {"index": index},
        }
    }


ITEM_BUILDERS = {
    "section": _build_section_request,
    "text": _build_text_request,
    "short": _build_short_request,
    "mcq": _build_mcq_request,
    "scale": _build_scale_request,
    "date": _build_date_request,
    "time": _build_time_request,
    "rating": _build_rating_request,
    "grid": _build_grid_request,
    "video": _build_video_request,
    "image": _build_image_request,
}


def build_item_request(spec: dict, index: int) -> dict:
    """Convert one JSON item specification into a createItem request."""
    item_type = spec.get("type", "").lower()
    builder = ITEM_BUILDERS.get(item_type)
    if builder is None:
        raise ValueError(f"Unknown item type: '{item_type}'")
    return builder(spec, index)
