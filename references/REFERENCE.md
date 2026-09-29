# Google Forms API v1 — Technical Reference

Technical reference for Google Forms API v1 resource and payload schemas used by `gws-forms-win`.

---

## 1. Form Resource

```json
{
  "formId": "string (output only)",
  "info": {
    "title": "string (required)",
    "documentTitle": "string",
    "description": "string"
  },
  "settings": {
    "quizSettings": {"isQuiz": true},
    "emailCollectionType": "DO_NOT_COLLECT | VERIFIED | RESPONDER_INPUT"
  },
  "items": [ /* Item[] */ ],
  "revisionId": "string (output only)",
  "responderUri": "string (output only)"
}
```

---

## 2. batchUpdate Requests

### createItem
```json
{
  "createItem": {
    "item": {
      "title": "string",
      "description": "string",
      "questionItem": {},
      "questionGroupItem": {},
      "pageBreakItem": {},
      "textItem": {},
      "imageItem": {},
      "videoItem": {}
    },
    "location": {"index": 0}
  }
}
```

### updateItem, moveItem, deleteItem
```json
{"updateItem": {"item": {}, "location": {"index": 0}, "updateMask": "path1,path2"}}
{"moveItem": {"originalLocation": {"index": 0}, "newLocation": {"index": 1}}}
{"deleteItem": {"location": {"index": 0}}}
```

### updateFormInfo & updateSettings
```json
{"updateFormInfo": {"info": {"title": "Title", "description": "Desc"}, "updateMask": "title,description"}}
{"updateSettings": {"settings": {"quizSettings": {"isQuiz": true}}, "updateMask": "quizSettings.isQuiz"}}
```

---

## 3. Item Schemas

### Question Items (`questionItem.question`)

| Type | Payload under `questionItem.question` |
|---|---|
| **Text** | `{"textQuestion": {"paragraph": false}}` |
| **Choice** | `{"choiceQuestion": {"type": "RADIO\|CHECKBOX\|DROP_DOWN", "options": [{"value": "Opt", "isOther": false}], "shuffle": false}}` |
| **Scale** | `{"scaleQuestion": {"low": 1, "high": 5, "lowLabel": "Min", "highLabel": "Max"}}` |
| **Date** | `{"dateQuestion": {"includeTime": false, "includeYear": true}}` |
| **Time** | `{"timeQuestion": {"duration": false}}` |
| **Rating** | `{"ratingQuestion": {"ratingScaleLevel": 5, "iconType": "STAR\|HEART\|THUMB_UP"}}` |

### Non-Question & Complex Items
- **Section**: `{"pageBreakItem": {}}`
- **Text**: `{"textItem": {}}`
- **Grid**: `{"questionGroupItem": {"questions": [{"rowQuestion": {"title": "R1"}}], "grid": {"columns": {"type": "RADIO", "options": [{"value": "C1"}]}}}}`
- **Image**: `{"imageItem": {"image": {"sourceUri": "https://...", "altText": "...", "properties": {"alignment": "CENTER", "width": 640}}}}`
- **Video**: `{"videoItem": {"video": {"youtubeUri": "https://youtube.com/...", "properties": {"alignment": "CENTER", "width": 640}}, "caption": "..."}}`

---

## 4. Grading Schema (`question.grading`)

```json
{
  "pointValue": 1,
  "correctAnswers": {"answers": [{"value": "exact match"}]},
  "whenRight": {"text": "Feedback when correct"},
  "whenWrong": {"text": "Feedback when incorrect"}
}
```

---

## 5. updateMask Paths

| Target Field | `updateMask` Path |
|---|---|
| Title / Description | `title`, `description` |
| Required toggle | `questionItem.question.required` |
| Choices / Shuffle | `questionItem.question.choiceQuestion.options`, `questionItem.question.choiceQuestion.shuffle` |
| Paragraph mode | `questionItem.question.textQuestion.paragraph` |
| Points / Correct / Feedback | `questionItem.question.grading.pointValue`, `questionItem.question.grading.correctAnswers`, `questionItem.question.grading.whenRight,questionItem.question.grading.whenWrong` |
| Media URI | `videoItem.video.youtubeUri`, `imageItem.image.sourceUri` |

---

## 6. FormResponse Schema (`scripts/form_reader.py`)

```json
{
  "responseId": "string",
  "createTime": "RFC3339",
  "lastSubmittedTime": "RFC3339",
  "respondentEmail": "string",
  "totalScore": 10.0,
  "answers": {
    "QUESTION_ID": {
      "questionId": "string",
      "textAnswers": ["string"],
      "fileUploadAnswers": [{"fileId": "...", "fileName": "...", "mimeType": "..."}],
      "grade": {"score": 10.0, "correct": true, "feedback": {"text": "..."}}
    }
  }
}
```

---

## 7. Common API Errors & Remedies

| Error Code | Root Cause | Remedy |
|---|---|---|
| `400 Unknown property addItem` | `addItem` typo for `createItem` | Use `createItem` in requests array. |
| `400 location is required` | Missing `location` in `createItem` | Specify `"location": {"index": N}`. |
| `400 Invalid writeControl` | Revision ID mismatch | Re-fetch snapshot and update `requiredRevisionId`. |
| `403 FileUploadQuestion` | Attempting programmatic file-upload question | Web UI only; unsupported via API. |
| `429 Too Many Requests` | Rate limit exceeded (>300 req/min) | Implement exponential backoff. |
