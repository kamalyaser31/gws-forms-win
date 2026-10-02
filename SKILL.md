---
name: gws-forms-win
description: >
  Build, update, and read Google Forms on Windows via gws CLI.
  Automates Google Forms and Quizzes using concise JSON specifications
  and pre-built Python runners. Use when creating forms, adding questions,
  enabling quiz mode with auto-grading, updating existing forms, or reading
  responses, including Arabic requests such as نموذج جوجل، اختبار، استبيان،
  or قراءة الردود.
---

# gws-forms-win

> **Prerequisites:** `gws` installed via npm (`npm i -g @googleworkspace/cli`) · Auth valid (`cmd /c "gws auth login"`)
> **Full Schema Reference:** [references/REFERENCE.md](references/REFERENCE.md)
> **Scripts Directory:** [scripts/](scripts/)

---

## 1. Creating Forms (JSON-First Workflow)

The agent writes a compact JSON specification file, then invokes `json_runner.py`.

### Step 1 — Write `form.json`

```json
{
  "title": "My Form Title",
  "desc": "Optional description of the form or exam.",
  "doc_title": "Drive File Title (optional)",
  "quiz": true,
  "items": [
    {"type": "section", "title": "Part 1 — Short Answers", "desc": "Answer briefly."},
    {"type": "short",   "q": "Explain X in your own words.", "required": true},
    {"type": "section", "title": "Part 2 — Multiple Choice"},
    {
      "type": "mcq",
      "q": "Which option is correct?",
      "options": ["A) One", "B) Two", "C) Three"],
      "correct": "B) Two",
      "points": 5,
      "wrong": "The correct answer is B."
    }
  ]
}
```

### Step 2 — Run `json_runner.py`

```powershell
python scripts/json_runner.py form.json
# Optional: record to local history log
python scripts/json_runner.py form.json --history
```

- Outputs Edit URL and Responder URL to `stdout`.
- Optional `--history [PATH]` records form metadata to `forms_history.json` in current directory; a `"history_path"` key in the spec does the same.
- The spec is validated before anything is created: an unknown type, a missing required key, a `correct` answer that is not one of the `options`, or `correct` without `"quiz": true` stops the run with a clear `[ERROR]` and creates no form.
- If the form is created but adding its items fails, the error includes the empty form's Edit URL. Delete that form or finish it with `form_updater.py`; do not rerun blindly, or a second form is created.
- Large forms are sent in several requests automatically, because Windows caps one command line at 32,767 characters.

---

## 2. JSON Item Type Reference

| `type` | Required keys | Optional keys |
|---|---|---|
| `section` | `title` | `desc` |
| `text` | `title` | `desc` |
| `short` | `q` | `paragraph` (bool, def true), `required` |
| `mcq` | `q`, `options` | `correct`, `points`, `right`, `wrong`, `qtype` (RADIO/CHECKBOX/DROP_DOWN), `shuffle`, `required` |
| `scale` | `q` | `low`, `high`, `low_label`, `high_label`, `required` |
| `date` | `q` | `time` (bool), `year` (bool), `required` |
| `time` | `q` | `duration` (bool), `required` |
| `rating` | `q` | `scale` (1-5), `icon` (STAR/HEART/THUMB_UP), `required` |
| `grid` | `title`, `rows`, `cols` | `col_type` (RADIO/CHECKBOX), `shuffle_rows`, `required` |
| `video` | `title`, `uri` | `caption`, `align`, `width` |
| `image` | `title`, `uri` | `alt`, `align`, `width` |

> **Quiz grading:** Adding `"correct"` to any `mcq` item attaches grading; the spec must set `"quiz": true`, and `correct` must match an option exactly. A `CHECKBOX` question may take a list: `"correct": ["A", "C"]`. `shuffle` is honored on graded questions too.

---

## 3. Updating an Existing Form

Updating follows a 3-step workflow: fetch snapshot -> prepare update spec -> apply updates.

### Step 1 — Fetch current snapshot (Mandatory)

```powershell
python scripts/form_fetcher.py --id <FORM_ID>
# or via edit URL:
python scripts/form_fetcher.py --url "https://docs.google.com/forms/d/<FORM_ID>/edit"
```
Saves: `<form_id>_snapshot.json` in current working directory (or custom path via `-o`).

### Step 2 — Write `update.json`

```json
{
  "form_id": "<FORM_ID>",
  "ops": [
    { "op": "update_info", "title": "Updated Title", "description": "Updated Description" },
    { "op": "add_item",    "item": {"type": "short", "q": "New question?"}, "at_index": 2 },
    { "op": "delete_item", "item_id": "<ITEM_ID_FROM_SNAPSHOT>" },
    { "op": "move_item",   "item_id": "<ITEM_ID_FROM_SNAPSHOT>", "to_index": 4 },
    { "op": "enable_quiz" },
    { "op": "set_publish", "published": true, "accepting": true }
  ]
}
```

### Step 3 — Run `form_updater.py`

```powershell
python scripts/form_updater.py update.json
# or with custom snapshot path:
python scripts/form_updater.py update.json -s path/to/snapshot.json
```

- A `"snapshot_path"` key in `update.json` works like `-s`.
- Every successful op refreshes the snapshot. If only the refresh fails, the op is still counted as done and a `[WARN]` asks you to re-run `form_fetcher.py`; do not repeat that op.

---

## 4. Reading Form Responses

Fetches all submitted responses independently without requiring a snapshot. Automatically paginates through all records.

```powershell
python scripts/form_reader.py --id <FORM_ID>
python scripts/form_reader.py --id <FORM_ID> --after "2026-01-01T00:00:00Z"
python scripts/form_reader.py --id <FORM_ID> -o custom_responses.json
```

- Output: `<form_id>_responses.json` in current working directory (or specified `-o` / `--output` path).
- Preserves respondent emails, individual answer values, file upload metadata, total scores, and grades.
- Each answer carries its question `title` (grid rows as `Grid — Row`), so the file reads without a snapshot.

> **Locating gws:** the scripts find `run.js` next to the `gws` command on PATH (covers nvm and custom npm prefixes). Override with the `GWS_FORMS_GWS_JS` and `GWS_FORMS_NODE_EXE` environment variables.

---

## 5. Script Summary

- [scripts/json_runner.py](scripts/json_runner.py) — Main CLI runner for form creation from JSON.
- [scripts/form_fetcher.py](scripts/form_fetcher.py) — Fetches existing form and saves local snapshot.
- [scripts/form_updater.py](scripts/form_updater.py) — Applies sequential update operations to a form.
- [scripts/form_reader.py](scripts/form_reader.py) — Extracts and normalizes form submissions.
- [scripts/form_builder.py](scripts/form_builder.py) — Low-level API client and request serialization library.
- [tests/run_tests.py](tests/run_tests.py) — Offline unit test suite.
- [tests/simulate_lifecycle.py](tests/simulate_lifecycle.py) — End-to-end lifecycle simulation runner.
