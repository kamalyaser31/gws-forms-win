---
name: gws-forms-win
description: >
  Build and populate Google Forms on Windows via gws CLI (Node.js npm package).
  Handles Windows-specific invocation (node.exe directly to avoid PowerShell escaping),
  correct Google Forms API v1 field names (createItem, location required), and the
  two-step create -> batchUpdate workflow. Use when user wants to create a Google Form,
  add questions to an existing form, read responses, manage watches, enable quiz mode,
  add grading/feedback, or automate Google Forms on a Windows machine running gws from npm.
  Includes a ready-made Python builder script.
---

# gws-forms-win

> **Prerequisites:** `gws` installed via npm · Auth valid (`cmd /c "gws auth login"`)
> **Full API Reference:** [REFERENCE.md](REFERENCE.md)
> **Builder Script:** [scripts/form_builder.py](scripts/form_builder.py)
> **JSON Runner:** [scripts/json_runner.py](scripts/json_runner.py)

---

## ⚡ MANDATORY: Token-Efficient Workflow (JSON-First)

**ALWAYS use this pattern** — write a JSON spec file, then run `json_runner.py`.
Never write a full Python script per form. Python scripts waste tokens.

### Step 1 — Agent writes a compact JSON file

```json
{
  "title": "My Exam Title",
  "doc_title": "Exam — Subtitle",
  "quiz": true,
  "items": [
    {"type": "section", "title": "Part 1 — Review", "desc": "Answer in 1–3 sentences."},
    {"type": "short",   "q": "Explain X in your own words."},
    {"type": "section", "title": "Part 2 — MCQ"},
    {
      "type": "mcq",
      "q": "Which is correct?",
      "options": ["A) One", "B) Two", "C) Three"],
      "correct": "B) Two",
      "wrong": "Correct answer is B."
    }
  ]
}
```

### Step 2 — Agent runs one command

```powershell
python "<SKILL_ROOT>\scripts\json_runner.py" form.json
```

-> Prints Edit URL and Responder URL. Done.

---

## JSON Item Type Reference

| `type` | Required keys | Optional keys |
|---|---|---|
| `section` | `title` | `desc` |
| `text` | `title` | `desc` |
| `short` | `q` | `paragraph` (bool, def true), `required` |
| `mcq` | `q`, `options` | `correct`, `points`, `right`, `wrong`, `qtype`, `shuffle`, `required` |
| `scale` | `q` | `low`, `high`, `low_label`, `high_label`, `required` |
| `date` | `q` | `time` (bool), `year` (bool), `required` |
| `time` | `q` | `duration` (bool), `required` |
| `rating` | `q` | `scale` (1-5), `icon` (STAR/HEART/THUMB_UP), `required` |
| `grid` | `title`, `rows`, `cols` | `col_type` (RADIO/CHECKBOX), `shuffle_rows`, `required` |
| `video` | `title`, `uri` | `caption`, `align`, `width` |
| `image` | `title`, `uri` | `alt`, `align`, `width` |

> **Quiz grading:** Add `"correct"` key to any `mcq` item -> auto-graded (quiz mode must be `true`).

---

## Fallback: Direct Python (advanced / non-standard cases only)

Only use this if you need logic not expressible in JSON:

```python
from scripts.form_builder import build_form, make_page_break, make_short_answer, make_mcq

items = [
    make_page_break("Part 1 - Short Answer", 0, "Answer in 1-3 sentences."),
    make_short_answer("Explain X in your own words.", 1),
    make_page_break("Part 2 - MCQ", 2),
    make_mcq("Which is correct?", ["A. One", "B. Two", "C. Three"], 3),
]
result = build_form("My Exam Title", items)
# -> prints Edit URL and Responder URL
```

---

## Windows Invocation Rule

**Never** use `cmd /c gws --json ...` or PowerShell for JSON payloads - `&`, `"`, `'` break parsing.

**Always** call Node.js directly via `subprocess`. The scripts detect their
own skill root from `__file__`; they do not depend on `.codex` or `.gemini`
being the parent folder.

```python
NODE_EXE = os.environ.get("GWS_FORMS_NODE_EXE", r"C:\Program Files\nodejs\node.exe")
GWS_JS = os.environ.get("GWS_FORMS_GWS_JS", str(Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@googleworkspace" / "cli" / "run-gws.js"))
subprocess.run([NODE_EXE, GWS_JS, "forms", "forms", "batchUpdate", "--json", json_str], ...)
```

`form_builder.py` handles this automatically.

---

## Auth

```bash
cmd /c "gws auth login"   # opens browser OAuth - MUST use cmd /c
```

---

## All Item Builder Functions (form_builder.py)

| الدالة | الغرض |
|---|---|
| `make_page_break(title, index, desc="")` | فاصل قسم |
| `make_short_answer(q, index, paragraph=True)` | إجابة قصيرة/فقرة |
| `make_mcq(q, options, index, type="RADIO")` | اختيار من متعدد |
| `make_scale(q, index, low=1, high=5, ...)` | مقياس تقييم |
| `make_date(q, index, include_time=False, include_year=True)` | تاريخ |
| `make_time(q, index, duration=False)` | وقت |
| `make_text_item(title, index, desc="")` | نص ثابت |
| `make_video(title, youtube_uri, index, ...)` | فيديو YouTube |
| `make_grid(title, rows, col_options, index, ...)` | شبكة (questionGroupItem) |

---

## API Gotchas (Hard-learned)

| خطأ | الصحيح |
|---|---|
| `addItem` | `createItem` |
| `createItem` بدون `location` | `"location": {"index": N}` **مطلوب دائماً** |
| إنشاء items أثناء `forms.create` | `create` فارغة، ثم `batchUpdate` |
| تمرير JSON عبر cmd/PowerShell | استدعاء `node.exe` مباشرةً من Python |

---

## batchUpdate Request Types

| النوع | الغرض |
|---|---|
| `createItem` | إضافة عنصر جديد |
| `updateItem` | تعديل عنصر قائم (يتطلب `updateMask`) |
| `deleteItem` | حذف عنصر بموضعه |
| `moveItem` | نقل عنصر من موضع لآخر |
| `updateFormInfo` | تعديل عنوان/وصف النموذج |
| `updateSettings` | تفعيل quiz، إعداد جمع البريد |

---

## Item Types

| النوع | الكائن |
|---|---|
| سؤال واحد | `questionItem` |
| شبكة صفوف/أعمدة | `questionGroupItem` |
| فاصل قسم | `pageBreakItem: {}` |
| صورة | `imageItem` |
| فيديو YouTube | `videoItem` |
| نص ثابت | `textItem: {}` |

---

## Question Types

| النوع | الكائن |
|---|---|
| نص قصير / فقرة | `textQuestion` |
| اختيار متعدد RADIO/CHECKBOX/DROP_DOWN | `choiceQuestion` |
| مقياس خطي | `scaleQuestion` |
| تاريخ | `dateQuestion` |
| وقت | `timeQuestion` |
| تقييم بنجوم | `ratingQuestion` |
| رفع ملفات (قراءة فقط) | `fileUploadQuestion` |
| صفّ شبكة | `rowQuestion` |

---

## Quiz Mode (الكويز والتصحيح التلقائي)

```python
# تفعيل وضع الكويز
run_gws(["forms", "forms", "batchUpdate"],
        json_body={"requests": [{"updateSettings": {
            "settings": {"quizSettings": {"isQuiz": True}},
            "updateMask": "quizSettings.isQuiz"
        }}]},
        params={"formId": form_id})

# سؤال مع تصحيح تلقائي (choiceQuestion و textQuestion فقط)
make_mcq_graded("السؤال", ["A. صح", "B. خطأ"], index=0,
                correct="A. صح", points=10,
                feedback_right="أحسنت!", feedback_wrong="الصواب: A")
```

---

## Reading Responses

```python
# جلب كل الإجابات
responses = run_gws(["forms", "forms", "responses", "list"], params={"formId": form_id})
for r in responses.get("responses", []):
    for qid, ans in r["answers"].items():
        print(qid, ans.get("textAnswers", {}).get("answers", []))
```

---

## Watches (Push Notifications)

```python
# مراقبة الإجابات الجديدة عبر Pub/Sub
run_gws(["forms", "forms", "watches", "create"],
        json_body={"watch": {
            "target": {"topic": {"topicName": "projects/P/topics/T"}},
            "eventType": "RESPONSES"   # أو SCHEMA
        }},
        params={"formId": form_id})
```

**EventType:** `RESPONSES` (إجابات جديدة) | `SCHEMA` (تغييرات بنية النموذج)

---

## Updating an Existing Form (JSON-First)

> [!IMPORTANT]
> **ALWAYS run `form_fetcher.py` first** before any update. No snapshot = no update.
> The updater finds the current `index` from the snapshot using the `item_id`.

### Step 1 - Fetch the form (MANDATORY)

```powershell
python "C:\...\scripts\form_fetcher.py" --id FORM_ID
# or (Edit URL only - NOT the encoded /e/ viewform URL)
python "C:\...\scripts\form_fetcher.py" --url "https://docs.google.com/forms/d/.../edit"
```

Saves: `SKILL_ROOT/snapshots/<form_id>_snapshot.json`

### Step 2 - Agent reads snapshot, writes update spec

```json
{
  "form_id": "1abc...XYZ",
  "ops": [
    { "op": "update_info",  "title": "New Title", "description": "New desc" },
    { "op": "add_item",     "item": {"type": "short", "q": "New Q?"}, "at_index": 3 },
    { "op": "delete_item",  "item_id": "3f2a" },
    { "op": "move_item",    "item_id": "7c1b", "to_index": 5 }
  ]
}
```

### Step 3 - Run the updater

```powershell
python "C:\...\scripts\form_updater.py" update.json
```

### Supported ops

| `op` | Required keys | Optional keys | Notes |
|---|---|---|---|
| `update_info` | — | `title`, `description` | At least one required |
| `add_item` | `item` | `at_index` | Default: append to end |
| `delete_item` | `item_id` | — | Resolves `item_id` to `index` via snapshot |
| `move_item` | `item_id`, `to_index` | — | Resolves `item_id` to `index` via snapshot |
| `enable_quiz` | — | — | — |
| `set_publish` | `published` | `accepting` (def: true) | Warns if unsupported, continues |

> [!WARNING]
> Each op runs in its **own** `batchUpdate` call (not batched together).
> Because `delete_item` and `move_item` resolve indexes from the saved snapshot,
> do not combine several delete/move operations that depend on shifted indexes
> without re-running `form_fetcher.py` between passes.

---

## Reading Responses (JSON-First)

No snapshot needed. Fully independent.

```powershell
python "C:\...\scripts\form_reader.py" --id FORM_ID
python "C:\...\scripts\form_reader.py" --id FORM_ID --after "2026-01-01T00:00:00Z"
python "C:\...\scripts\form_reader.py" --id FORM_ID --output responses.json
```

- Automatically paginates through **all pages** — no response limit.
- Rejects encoded `/e/` viewform URLs (use `--id` or Edit URL).
- Output: `<form_id>_responses.json` (or `--output` path).

---

## See Also

- [REFERENCE.md](REFERENCE.md) — التوثيق الكامل لكل حقل وكل Enum
- [scripts/json_runner.py](scripts/json_runner.py) — **المشغّل العام للإنشاء (الأسلوب الموصى به)**
- [scripts/form_fetcher.py](scripts/form_fetcher.py) — جلب النموذج القائم + snapshot
- [scripts/form_updater.py](scripts/form_updater.py) — تعديل النموذج القائم
- [scripts/form_reader.py](scripts/form_reader.py) — قراءة الإجابات
- [scripts/form_builder.py](scripts/form_builder.py) — مكتبة البناء الأساسية
