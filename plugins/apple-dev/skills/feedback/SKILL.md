---
name: feedback
description: >
  Apple development skill for Feedback & Contact Us. Use this skill when working on feedback tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Feedback & Contact Us

How a user report gets from the **Settings** tab into a triageable Firestore
collection, and everything you need to change it safely.

---

## Invariants (know these before touching feedback)

- **Feedback is a SEPARATE Firebase project from telemetry.** Analytics is
  `leap-widgets`; feedback is **`leap-feedback`**. Both are owned by
  `sololeapinc@gmail.com` and both register the same bundle id, so the *only* thing
  keeping them apart is the **filename** of the bundled config:
  `Leap/GoogleService-Info.plist` (analytics, auto-loaded by
  `FirebaseApp.configure()`) vs `Leap/GoogleService-Info-Feedback.plist` (feedback,
  read by name only). **Never rename the feedback plist to `GoogleService-Info.plist`** —
  Firebase would configure the wrong project and telemetry would silently die.
- **No Firebase SDK is used for feedback.** It talks to Firestore over the plain
  **REST `:commit` endpoint** with `URLSession`. Adding `FirebaseFirestore` would drag
  gRPC/abseil/leveldb into a **hand-authored `project.pbxproj`** for one rare write,
  and would additionally need a *secondary* `FirebaseApp` (a different project from
  Analytics, which only ever works on the default app). Do not "upgrade" this to the SDK.
- **There is no Firebase Auth, deliberately.** Enabling it needs Identity Platform,
  which returns `BILLING_NOT_ENABLED` on Spark — and minting anonymous user records
  would contradict Leap's zero-user-record stance anyway. Security comes from
  **create-only security rules** instead (see below).
- **The client can only ever CREATE.** `read`, `list`, `update` and `delete` are
  `false` for every path. That means **the app can never read its own submissions
  back** — the "Your messages" history is served entirely from the local outbox, and
  any verification you do must use an **owner OAuth token** (which bypasses rules).
- **The three feedback files live in `Leap/`, not `Shared/`.** The repo invariant is
  that anything in `Shared/` must be registered in **both** target membership lists;
  feedback is app-only, so it stays out of `Shared/`.
- **Nothing a user typed reaches GA4.** Message text, email and images go only to
  Firestore. See the note in [telemetry.md](telemetry.md).
- **The submission id is a client UUID and retries are idempotent.** The write is
  guarded by `currentDocument.exists == false`, so a replay returns **409**, which the
  outbox treats as *success* — a flaky network can never duplicate a report.

---

## Files

| File | Role |
|------|------|
| `Leap/LeapFeedback.swift` | Single source of truth: `LeapFeedbackCategory` (+ its Firestore collection name), `LeapFeedbackLimits`, `LeapFeedbackDiagnostics`, `LeapFeedbackAttachment`, `LeapFeedbackSubmission` (+ `validationError`) |
| `Leap/LeapFeedbackService.swift` | Firestore REST `:commit` transport, `SubmitError` taxonomy, `Configuration.bundled()`, payload builders, JPEG `prepareAttachment` |
| `Leap/LeapFeedbackOutbox.swift` | Durable App-Group queue **and** the in-app history: persist → send → retry → prune |
| `Leap/FeedbackView.swift` | `FeedbackFlowView`, `FeedbackCategoryPicker`, `FeedbackComposerView`, `FeedbackHistoryView` |
| `Leap/HomeView.swift` | The **SUPPORT** section in `SettingsTab` that presents the two sheets |
| `Leap/GoogleService-Info-Feedback.plist` | `leap-feedback` project id + API key (app target Resources only) |

`LeapFeedbackCategory.collection` **must stay in sync with the deployed rules'
`isFeedbackCollection`/`categoryFor` helpers** — a mismatch is denied server-side.

---

## Firebase project `leap-feedback`

| Item | Value |
|------|-------|
| Project id / number | `leap-feedback` / `315085549800` |
| Owner account | `sololeapinc@gmail.com` |
| Billing | **Spark (free)** |
| iOS app id | `1:315085549800:ios:a1bc87f355081e60d9195d` (bundle `com.sololeap.leap.app`) |
| API key | `AIzaSyB49WjjbZr6JXiNAWckf9eecQ7-6UiVWDA` (public by design; rules are the control) |
| Firestore | Native mode, `(default)`, location `nam5` |
| Rules ruleset | `765b2213-9b4d-42bb-a712-bcc7a10af69b`, released to `cloud.firestore` |
| App Check | App Attest provider configured (TTL 1h); enforcement **OFF** |

Console triage: <https://console.firebase.google.com/project/leap-feedback/firestore>

## Data model — one collection per category

```
feedback_bug/{submissionId}              <- Report an issue
feedback_feature/{submissionId}          <- Feature request
feedback_widget_request/{submissionId}   <- Widget / design request
feedback_other/{submissionId}            <- Something else
    └── attachments/{attachmentId}       <- one doc per screenshot
```

The split is the whole point: triaging bugs is one click in the console with no
query or composite index. Sorting by `createdAt` needs only the automatic
single-field index, so **there is no index to deploy**.

Submission fields: `schema`(1), `category`, `message` (3–4000), `email` (`""` when
omitted), `attachmentCount` (0–3), `createdAt` (**server** timestamp),
`clientCreatedAt`, `status` (always `new` on create), `app` map
(`version`/`build`/`bundleId`), `device` map
(`model`/`systemVersion`/`locale`/`appearance`), `state` map
(`plan`/`savedWidgets`/`onboardingCompleted`), and an optional `appInstanceId` —
the GA4 `app_instance_id`, which is what lets you join a report to that user's
anonymous usage funnel.

Attachment fields: `schema`, `index` (0–2), `mime` (`image/jpeg`), `bytes`
(Firestore **Blob**), `width`, `height`, `createdAt`.

**`bytes` is a Blob, not a base64 string.** It is base64 *on the wire* but stored raw,
so it is not inflated 33% against the 1 MiB per-document limit (verified: 40 004
bytes in, 40 004 bytes stored).

## Security model

Rules enforce, server-side, that: the target is one of the four `feedback_*`
collections; `category` matches the collection it was written to; `status == 'new'`;
`createdAt == request.time`; `keys().hasOnly(...)` (no smuggled fields); the doc id is
20–64 chars; message 3–4000; attachment `index` 0–2, `bytes` ≤ 750 000, `mime ==
'image/jpeg'`.

Probed against the **live** database with only the public API key — valid write
accepted; mismatched category, arbitrary collection, extra field, forged `status`,
document read and collection list **all `PERMISSION_DENIED`**.

The deployed source is version-controlled at **`firebase/feedback.firestore.rules`**.
`firebase-tools` is not installed; rules are shipped by creating a ruleset and
releasing it over REST with an owner token:

```bash
TOK=$(gcloud auth print-access-token --account=sololeapinc@gmail.com)
# 1. create a ruleset from firebase/feedback.firestore.rules  ->  returns {name: .../rulesets/<ID>}
#    POST https://firebaserules.googleapis.com/v1/projects/leap-feedback/rulesets
# 2. point the live release at it
#    PATCH https://firebaserules.googleapis.com/v1/projects/leap-feedback/releases/cloud.firestore
```

Firebase Management/Rules/AppCheck REST calls **require an
`x-goog-user-project: leap-feedback` header**, otherwise they 403 with "requires a
quota project".

**App Check is intentionally unenforced.** App Attest needs the DeviceCheck
capability, which a **free Apple team cannot sign** — the same constraint that keeps
WeatherKit disabled in this repo. The provider is already configured, so once Leap is
on a paid team this is one API call plus attaching an `X-Firebase-AppCheck` header in
`LeapFeedbackService`.

## Client flow

`SettingsTab` → **Send Feedback** → `FeedbackCategoryPicker` → `FeedbackComposerView`
(message + up to 3 screenshots + optional email + a "What we'll include" diagnostics
disclosure) → `LeapFeedbackOutbox.enqueue`.

The outbox **persists to the App Group before the network call**, so a crash or a kill
mid-send can never lose a report. `.offline`/`.server`/`.transport` are retryable and
leave the item `pending` for the next foreground flush (`LeapApp.swift`,
`scenePhase == .active`); `.invalid`/`.rejected` are terminal so a poisoned payload
cannot retry forever. Retries are capped at 6. On success the screenshots are deleted
immediately and only a lightweight text receipt is kept, pruned after 90 days.

Screenshots are downscaled and JPEG-recompressed **on device** before upload, which
also strips EXIF/GPS.

## Viewing / triaging reports

**Firebase console** (sign in as **sololeapinc@gmail.com**) — one link per
category, so each is already a triage queue:

| Category | Console |
|----------|---------|
| Report an issue | <https://console.firebase.google.com/project/leap-feedback/firestore/databases/-default-/data/~2Ffeedback_bug> |
| Feature request | `.../data/~2Ffeedback_feature` |
| Widget request | `.../data/~2Ffeedback_widget_request` |
| Something else | `.../data/~2Ffeedback_other` |

The console **cannot preview screenshots** — they are Firestore Blobs, which it
renders as base64. Use the committed helper instead, which writes a readable
`report.txt` plus decoded `screenshot_N.jpg` per submission:

```bash
firebase/dump-feedback.sh bug                 # -> ~/Desktop/leap-feedback/bug/<id>/
firebase/dump-feedback.sh feature /tmp/out    # or pick your own output directory
```

It authenticates with `gcloud auth print-access-token --account=sololeapinc@gmail.com`;
an **owner token bypasses the rules**, which is the only way to read this data at all.

## Verifying (client reads are denied — use an owner token)

```bash
TOK=$(gcloud auth print-access-token --account=sololeapinc@gmail.com)
BASE="https://firestore.googleapis.com/v1/projects/leap-feedback/databases/(default)/documents"
curl -s -H "Authorization: Bearer $TOK" "$BASE/feedback_bug?pageSize=20"
```

Deleting a parent document does **not** delete its `attachments` subcollection —
delete the attachment docs first or they are orphaned and keep consuming quota.

## Quotas & limits

Spark allows 20 000 writes/day and 1 GiB stored. One report with 3 images is 4 writes,
so the ceiling is thousands of reports/day. Worst case ~2.2 MB per report, so ~450
fully-illustrated reports fill the free tier — prune triaged reports, or move
attachments to Cloud Storage on Blaze if that ever becomes real.
