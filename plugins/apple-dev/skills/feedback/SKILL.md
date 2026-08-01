---
name: feedback
description: >
  Guide for implementing an in-app feedback and bug reporting loop without authenticated SDKs. Triggers on keywords like feedback, report an issue, contact us, Firebase REST, unauthenticated Firestore, URLSession.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Feedback & Contact Us

How to build a feedback loop using an unauthenticated REST API to submit user reports directly from your app to a backend database (e.g., Firestore) without embedding a heavy SDK.

---

## Conceptual Overview

- **No heavy SDKs:** Talk to the database over a plain REST endpoint (like Firestore's `:commit`) using `URLSession`. This avoids bloating the app binary with SDK dependencies for a simple write operation.
- **No User Authentication:** Do not require users to sign in to submit feedback. Anonymous submissions reduce friction.
- **Create-Only Security Model:** Security is enforced server-side via rules that only allow `create` operations. The client cannot `read`, `list`, `update`, or `delete` any data. This ensures users cannot read other people's feedback.
- **Separation of Concerns:** Keep your feedback infrastructure entirely separate from analytics and telemetry. Use a different project or environment to avoid accidental data leakage.
- **Idempotency:** Use a client-generated UUID as the submission ID to ensure network retries do not create duplicate entries.

## File Structure

Typical files for a generic feedback system in an iOS app:

| File | Role |
|------|------|
| `Models/FeedbackModels.swift` | Data models: Categories, Limits, Diagnostics, Attachments, Submissions |
| `Services/FeedbackService.swift` | Network transport layer (REST API calls), payload builders |
| `Persistence/FeedbackOutbox.swift` | Local queue: persists to disk before sending, handles retries |
| `Views/FeedbackComposerView.swift` | UI for writing messages, attaching images, and viewing diagnostics |
| `Views/SettingsSupportView.swift` | Entry point in the app settings to open the feedback flow |
| `Config/FeedbackConfig.plist` | Stores the API endpoint URL and generic API keys (no secrets) |

---

## Data Model — Category Collections

Organize feedback by category to simplify triage. For example:

```
feedback_bug/{submissionId}
feedback_feature/{submissionId}
feedback_other/{submissionId}
    └── attachments/{attachmentId}
```

Submission fields generally include: `category`, `message`, `attachmentCount`, `createdAt` (server timestamp), `appVersion`, `deviceModel`, `systemVersion`, and optionally a generated instance ID for joining with anonymous usage metrics.

Attachments (like screenshots) should be compressed on-device before uploading to save bandwidth and storage.

## Security Model

Backend security rules must enforce that:
- The target is one of the allowed feedback collections.
- The `status` is forced to "new".
- No arbitrary or restricted fields are injected.
- Attachment payloads are within acceptable size limits and correct MIME types (e.g., `image/jpeg`).

Client reads are explicitly denied.

## Client Flow

1. **User Action:** User taps "Send Feedback" in settings.
2. **Composition:** User selects a category, writes a message, and optionally attaches screenshots.
3. **Queueing:** The app saves the payload to local storage (e.g., an App Group container) first.
4. **Transmission:** The app attempts a network request. If offline, the submission remains queued for the next launch.
5. **Cleanup:** On success, local attachments and large payloads are deleted, leaving only a small receipt.

## Triage and Review

Viewing feedback is done via the backend console. Since the client cannot read the data, triaging must be performed by project administrators using backend tools or scripts that authenticate securely to fetch the records and decode attachments.

A helper script can be used to securely pull data (using administrator credentials) to a local directory for review:

```bash
./scripts/dump-feedback.sh bug <OUTPUT_DIR>
```
