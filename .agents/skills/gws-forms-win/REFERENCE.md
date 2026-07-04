# Google Forms API v1 — المرجع الشامل

> مصدر: `developers.google.com/forms/api/reference/rest/v1/`

---

## Base URL & Auth

| البند | القيمة |
|---|---|
| **Base URL** | `https://forms.googleapis.com/v1` |
| **Discovery** | `https://forms.googleapis.com/$discovery/rest?version=v1` |

### OAuth Scopes

| النطاق | الاستخدام |
|---|---|
| `forms.body` | قراءة وكتابة هيكل النموذج |
| `forms.body.readonly` | قراءة هيكل النموذج فقط |
| `forms.responses.readonly` | قراءة الإجابات فقط |
| `drive` | وصول كامل لـ Drive |
| `drive.file` | وصول للملفات التي أنشأها التطبيق فقط |
| `drive.readonly` | قراءة Drive فقط |

---

## Form Resource — المخطط الكامل

```json
{
  "formId":          "string — Output only",
  "info":            "Info",
  "settings":        "FormSettings",
  "items":           "Item[]",
  "revisionId":      "string — Output only (صالح 24 ساعة)",
  "responderUri":    "string — Output only (رابط المستجيبين)",
  "linkedSheetId":   "string — Output only",
  "publishSettings": "PublishSettings — Output only"
}
```

### Info

```json
{
  "title":         "string — العنوان المرئي للمستجيب",
  "documentTitle": "string — اسم ملف Drive",
  "description":   "string — وصف النموذج"
}
```

---

## نقاط النهاية (Endpoints)

### 1. forms.create

| | |
|---|---|
| **Method** | `POST /forms` |
| **Scopes** | `forms.body`, `drive`, `drive.file` |
| **Body** | `Info` فقط — `title` و `documentTitle` |
| **ملاحظة حرجة** | لا يمكن إضافة items أثناء الإنشاء — استخدم `batchUpdate` لاحقاً |

```bash
gws forms create --json '{"info": {"title": "...", "documentTitle": "..."}}'
```

---

### 2. forms.get

| | |
|---|---|
| **Method** | `GET /forms/{formId}` |
| **Scopes** | `forms.body`, `forms.body.readonly`, `drive`, `drive.readonly` |

```bash
gws forms get --params '{"formId": "FORM_ID"}'
```

---

### 3. forms.batchUpdate

| | |
|---|---|
| **Method** | `POST /forms/{formId}:batchUpdate` |
| **Scopes** | `forms.body`, `drive`, `drive.file` |
| **Atomicity** | نعم — إما نجاح الجميع أو فشل الجميع |

**Request Body:**

```json
{
  "includeFormInResponse": "boolean — إعادة النموذج المحدَّث في الردّ",
  "requests": [
    {
      "// Union — اختر واحداً": "",
      "updateFormInfo":  "UpdateFormInfoRequest",
      "updateSettings":  "UpdateSettingsRequest",
      "createItem":      "CreateItemRequest",
      "moveItem":        "MoveItemRequest",
      "deleteItem":      "DeleteItemRequest",
      "updateItem":      "UpdateItemRequest"
    }
  ],
  "writeControl": {
    "requiredRevisionId": "string — يجب أن يطابق الـ revisionId الحالي",
    "targetRevisionId":   "string — يحاول الدمج مع التغييرات اللاحقة"
  }
}
```

**Response:**

```json
{
  "form":    "Form — إذا كان includeFormInResponse=true",
  "replies": [
    {
      "createItem": {"itemId": "string", "questionId": ["string"]},
      "updateItem": {},
      "deleteItem": {},
      "moveItem":   {},
      "updateFormInfo":  {},
      "updateSettings":  {}
    }
  ],
  "writeControl": {"requiredRevisionId": "string"}
}
```

```bash
gws forms batchUpdate \
  --params '{"formId": "FORM_ID"}' \
  --json '{"includeFormInResponse": true, "requests": [...]}'
```

---

### 4. forms.setPublishSettings

| | |
|---|---|
| **Method** | `POST /forms/{formId}:setPublishSettings` |
| **ملاحظة** | غير مدعوم للنماذج القديمة (Legacy Forms) |

```bash
gws forms setPublishSettings \
  --params '{"formId": "FORM_ID"}' \
  --json '{"publishSettings": {"isPublished": true, "isAcceptingResponses": true}, "updateMask": "*"}'
```

---

### 5. forms.responses.get

```bash
gws forms responses get --params '{"formId": "FID", "responseId": "RID"}'
```

---

### 6. forms.responses.list

| Query Param | النوع | الوصف |
|---|---|---|
| `filter` | string | `timestamp > "2024-01-01T00:00:00Z"` أو `timestamp >= "..."` |
| `pageSize` | integer | الحد الأقصى (الافتراضي 5000) |
| `pageToken` | string | رمز الصفحة التالية |

```bash
gws forms responses list --params '{"formId": "FID", "pageSize": 100}'
gws forms responses list --params '{"formId":"FID","filter":"timestamp > \"2024-01-01T00:00:00Z\""}'
```

---

### 7. forms.watches.create / list / renew / delete

```bash
# إنشاء
gws forms watches create \
  --params '{"formId": "FID"}' \
  --json '{"watch": {"target": {"topic": {"topicName": "projects/P/topics/T"}}, "eventType": "RESPONSES"}}'

# قائمة
gws forms watches list --params '{"formId": "FID"}'

# تجديد
gws forms watches renew --params '{"formId": "FID", "watchId": "WID"}' --json '{}'

# حذف
gws forms watches delete --params '{"formId": "FID", "watchId": "WID"}'
```

---

## أنواع طلبات batchUpdate

### createItem

```json
{
  "item": {
    "itemId":      "string — اختياري، يُولَّد تلقائياً",
    "title":       "string",
    "description": "string",
    "// kind — Union": "",
    "questionItem":      "QuestionItem",
    "questionGroupItem": "QuestionGroupItem",
    "pageBreakItem":     "{}",
    "imageItem":         "ImageItem",
    "videoItem":         "VideoItem",
    "textItem":          "{} — نص ثابت غير تفاعلي"
  },
  "location": {"index": "integer — 0-indexed (Required)"}
}
```

### updateItem

```json
{
  "item":       "Item كامل",
  "location":   {"index": "integer — الموضع الحالي (Required)"},
  "updateMask": "string — مسارات الحقول (Required)"
}
```

### deleteItem

```json
{"location": {"index": "integer"}}
```

### moveItem

```json
{
  "originalLocation": {"index": "integer"},
  "newLocation":      {"index": "integer"}
}
```

### updateFormInfo

```json
{
  "info": {"title": "...", "documentTitle": "...", "description": "..."},
  "updateMask": "title,description  أو  *"
}
```

**updateMask paths:** `title` | `documentTitle` | `description` | `*`

### updateSettings

```json
{
  "settings": {
    "quizSettings": {"isQuiz": "boolean"},
    "emailCollectionType": "EmailCollectionType"
  },
  "updateMask": "quizSettings.isQuiz  أو  *"
}
```

**updateMask paths:** `quizSettings` | `quizSettings.isQuiz` | `emailCollectionType` | `*`

---

## أنواع الأسئلة — Schemas

### TextQuestion

```json
{"paragraph": "boolean — false=قصير، true=فقرة"}
```

### ChoiceQuestion (RADIO | CHECKBOX | DROP_DOWN)

```json
{
  "type": "RADIO | CHECKBOX | DROP_DOWN",
  "options": [
    {
      "value":        "string",
      "image":        "Image — اختياري",
      "isOther":      "boolean — خيار 'أخرى' (RADIO/CHECKBOX فقط)",
      "goToAction":   "NEXT_SECTION | RESTART_FORM | SUBMIT_FORM",
      "goToSectionId":"string — عند GO_TO_SECTION"
    }
  ],
  "shuffle": "boolean"
}
```

### ScaleQuestion

```json
{
  "low":       "integer — 0 أو 1",
  "high":      "integer — 2 حتى 10",
  "lowLabel":  "string",
  "highLabel": "string"
}
```

### DateQuestion

```json
{"includeTime": "boolean", "includeYear": "boolean"}
```

### TimeQuestion

```json
{"duration": "boolean — false=وقت اليوم، true=مدة منقضية"}
```

### FileUploadQuestion

```json
{
  "folderId":    "string — Output only",
  "types":       "FileType[] — ANY|DOCUMENT|PRESENTATION|SPREADSHEET|DRAWING|PDF|IMAGE|VIDEO|AUDIO",
  "maxFiles":    "integer",
  "maxFileSize": "string (بالبايت)"
}
```

> **تنبيه:** الإنشاء برمجياً غير مدعوم — قراءة فقط.

### RatingQuestion

```json
{
  "ratingScaleLevel": "integer — الحد الأقصى (مثل 5)",
  "iconType": "STAR | HEART | THUMB_UP"
}
```

### RowQuestion (داخل questionGroupItem فقط)

```json
{"title": "string — عنوان الصفّ"}
```

---

## QuestionGroupItem (الشبكة)

```json
{
  "questions": [{"rowQuestion": {"title": "string"}}],
  "grid": {
    "columns": {
      "type":    "RADIO | CHECKBOX",
      "options": "Option[]"
    },
    "shuffleQuestions": "boolean"
  },
  "image": "Image — اختياري"
}
```

---

## ImageItem & VideoItem

```json
// ImageItem
{
  "image": {
    "sourceUri":  "string — Input only",
    "contentUri": "string — Output only",
    "altText":    "string",
    "properties": {"alignment": "LEFT|CENTER|RIGHT", "width": "integer px"}
  }
}

// VideoItem
{
  "video": {
    "youtubeUri":  "string",
    "properties":  {"alignment": "LEFT|CENTER|RIGHT", "width": "integer px"}
  },
  "caption": "string"
}
```

---

## updateMask Paths — updateItem

| المسار | ما يعدّله |
|---|---|
| `title` | عنوان العنصر |
| `description` | وصف العنصر |
| `questionItem.question.required` | إلزامية |
| `questionItem.question.choiceQuestion` | كامل السؤال الاختياري |
| `questionItem.question.choiceQuestion.options` | الخيارات فقط |
| `questionItem.question.choiceQuestion.shuffle` | الخلط |
| `questionItem.question.textQuestion.paragraph` | نوع النص |
| `questionItem.question.scaleQuestion` | كامل المقياس |
| `questionItem.question.dateQuestion.includeTime` | تضمين الوقت |
| `questionItem.question.dateQuestion.includeYear` | تضمين السنة |
| `questionItem.question.timeQuestion.duration` | نوع الوقت |
| `questionItem.question.grading.pointValue` | قيمة النقاط |
| `questionItem.question.grading.correctAnswers` | الإجابات الصحيحة |
| `questionItem.question.grading.whenRight` | تغذية راجعة عند الصحة |
| `questionItem.question.grading.whenWrong` | تغذية راجعة عند الخطأ |
| `questionItem.question.grading.generalFeedback` | تغذية راجعة عامة |
| `questionItem.image` | الصورة المصاحبة |
| `videoItem.video.youtubeUri` | رابط الفيديو |
| `videoItem.caption` | التعليق |
| `imageItem.image.sourceUri` | مصدر الصورة |
| `imageItem.image.altText` | النص الوصفي |

---

## Grading (نظام الكويز)

```json
{
  "pointValue": "integer — ≥ 0",
  "correctAnswers": {
    "answers": [{"value": "string — الإجابة الصحيحة الحرفية"}]
  },
  "whenRight":       "Feedback",
  "whenWrong":       "Feedback",
  "generalFeedback": "Feedback"
}
```

```json
// Feedback
{
  "text": "string",
  "material": [
    {"link":  {"uri": "string", "displayText": "string"}},
    {"video": {"youtubeUri": "string", "displayText": "string"}}
  ]
}
```

**التصحيح التلقائي:**

| نوع السؤال | مدعوم |
|---|---|
| choiceQuestion (RADIO/CHECKBOX/DROP_DOWN) | ✅ |
| textQuestion (paragraph=false) | ✅ |
| scaleQuestion / dateQuestion / timeQuestion | ❌ |

---

## FormSettings

```json
{
  "quizSettings": {"isQuiz": "boolean"},
  "emailCollectionType": "DO_NOT_COLLECT | VERIFIED | RESPONDER_INPUT"
}
```

---

## Watch Resource

```json
{
  "id":         "string",
  "target":     {"topic": {"topicName": "projects/P/topics/T"}},
  "eventType":  "SCHEMA | RESPONSES",
  "createTime": "RFC3339",
  "expireTime": "RFC3339 — 7 أيام",
  "state":      "ACTIVE | SUSPENDED",
  "errorType":  "string"
}
```

> **Pub/Sub:** يجب منح `forms-notifications@system.gserviceaccount.com` صلاحية Publish على الـ Topic.

---

## FormResponse Resource

```json
{
  "formId":            "string",
  "responseId":        "string",
  "createTime":        "RFC3339",
  "lastSubmittedTime": "RFC3339",
  "respondentEmail":   "string",
  "answers": {
    "QUESTION_ID": {
      "questionId": "string",
      "grade":      {"score": "number", "correct": "boolean", "feedback": "Feedback"},
      "textAnswers":       {"answers": [{"value": "string"}]},
      "fileUploadAnswers": {"answers": [{"fileId": "string", "fileName": "string", "mimeType": "string"}]}
    }
  },
  "totalScore": "number"
}
```

---

## أخطاء شائعة

| الخطأ | السبب | الحل |
|---|---|---|
| `400 Unknown property addItem` | الحقل الصحيح هو `createItem` | استخدم `createItem` |
| `400 location is required` | `createItem` بدون `location` | أضف `"location": {"index": N}` |
| `400 Invalid writeControl` | `requiredRevisionId` لا يطابق | اجلب `revisionId` جديداً |
| `403 FileUploadQuestion` | إنشاء برمجي غير مدعوم | أنشئه يدوياً من الواجهة |
| `429 Too Many Requests` | تجاوز حد الطلبات | Exponential Backoff |
| Watch `SUSPENDED` | فشل Pub/Sub | تحقق الصلاحيات ثم `renew` |

---

## أمثلة JSON كاملة

### تفعيل الكويز وتحديث العنوان

```json
{
  "requests": [
    {
      "updateFormInfo": {
        "info": {"title": "اختبار نهائي", "description": "الفصل الأول"},
        "updateMask": "title,description"
      }
    },
    {
      "updateSettings": {
        "settings": {"quizSettings": {"isQuiz": true}},
        "updateMask": "quizSettings.isQuiz"
      }
    }
  ]
}
```

### سؤال اختياري مع تصحيح تلقائي

```json
{
  "createItem": {
    "item": {
      "title": "ما عاصمة مصر؟",
      "questionItem": {
        "question": {
          "required": true,
          "choiceQuestion": {
            "type": "RADIO",
            "options": [{"value": "القاهرة"}, {"value": "الإسكندرية"}],
            "shuffle": false
          },
          "grading": {
            "pointValue": 10,
            "correctAnswers": {"answers": [{"value": "القاهرة"}]},
            "whenRight": {"text": "أحسنت!"},
            "whenWrong": {"text": "الإجابة: القاهرة"}
          }
        }
      }
    },
    "location": {"index": 0}
  }
}
```

### شبكة (questionGroupItem)

```json
{
  "createItem": {
    "item": {
      "title": "قيّم المواد",
      "questionGroupItem": {
        "questions": [
          {"rowQuestion": {"title": "الرياضيات"}},
          {"rowQuestion": {"title": "العلوم"}},
          {"rowQuestion": {"title": "اللغة العربية"}}
        ],
        "grid": {
          "columns": {
            "type": "RADIO",
            "options": [{"value": "ضعيف"}, {"value": "جيد"}, {"value": "ممتاز"}]
          },
          "shuffleQuestions": false
        }
      }
    },
    "location": {"index": 1}
  }
}
```

### فيديو YouTube

```json
{
  "createItem": {
    "item": {
      "title": "شاهد أولاً",
      "videoItem": {
        "video": {
          "youtubeUri": "https://www.youtube.com/watch?v=VIDEO_ID",
          "properties": {"alignment": "CENTER", "width": 720}
        },
        "caption": "مقدمة الدرس"
      }
    },
    "location": {"index": 2}
  }
}
```

### سؤال مقياس

```json
{
  "createItem": {
    "item": {
      "title": "كيف تقيّم هذا البرنامج؟",
      "questionItem": {
        "question": {
          "required": false,
          "scaleQuestion": {
            "low": 1, "high": 5,
            "lowLabel": "ضعيف جداً",
            "highLabel": "ممتاز"
          }
        }
      }
    },
    "location": {"index": 3}
  }
}
```
