---
name: app-store-submission
description: >
  Guide for App Store submission checklist, export compliance, privacy questionnaires, age ratings, App Review rejections, and binary upload. Covers Guideline 2.1 "Information Needed" replies, App Review notes (4000-char cap), and uploading a demo screen recording as a review attachment.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---

# App Store submission — privacy, IAP & review risk

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. Build and upload are in
> [app-store-release.md](../app-store-release/SKILL.md); listing copy and screenshots
> are in [app-store-listing.md](../app-store-listing/SKILL.md).

---

## 0. Blockers before any submission

Before submitting an app for review, clear this checklist to ensure all metadata, binaries, and configurations are ready:

| # | Blocker | Status Requirement |
|---|---|---|
| 1 | **Privacy policy URL** | Must be hosted and accessible (e.g., GitHub Pages, company site) |
| 2 | **App Privacy questionnaire** | Must be filled in via the ASC **web UI** (`appDataUsages` API often returns `404 PATH_ERROR`) |
| 3 | **Export Compliance (`ITSAppUsesNonExemptEncryption`)** | Must be declared in `Info.plist` or ASC |
| 4 | **Build uploaded** | A valid release binary attached with the correct minimum OS |
| 5 | **App Store Metadata** | Categories, subtitle, keywords, description, and screenshots populated |
| 6 | **Territories & Pricing** | Territories set (e.g., all regions), price schedule base established |
| 7 | **Screenshots** | Device families targeted correctly (e.g., iPhone-only vs Universal needs iPad screenshots) |
| 8 | **Private API → Guideline 2.5.1** | Binary scanned and clean of prohibited private framework usage |
| 9 | **Accurate Pricing Display** | In-app paywalls must not hardcode incorrect or mismatched currency symbols |
| 10 | **Unused IAPs** | Remove any IAP products from ASC that the code never reads or offers |
| 11 | **IAPs attached to first submission** | IAPs must be **explicitly attached** to the v1.0 review submission, or purchases ship unreviewed |
| 12 | **Debug features disabled** | Verify internal debug panels, developer cheat codes, and staging APIs are stripped |
| 13 | **Copyright & Content Rights** | Copyright set (e.g., `YYYY Developer Name`); Third-party content rights declared |
| 14 | **Age-rating questions** | Age rating declarations and social-media questions answered |

### Guideline 2.5.1 private-API scan

Ensure your release binary and any extensions are free of private API usage. You can run `nm` or `strings` against the archived binary:

```bash
nm -u path/to/Release.app/Executable | grep -i private
```

If your app intentionally swizzles system UI or uses private classes, verify that it **fails safe** in production if the system changes underneath it, and be prepared for potential review rejections.

### Other verified-ready items

- **Age rating:** Complete all questions (e.g., `FOUR_PLUS`, `NONE` for violence/profanity).
- **Review details:** Contact info and notes complete (`demoAccountRequired` handled properly).
- **IAP review screenshots:** Upload current screenshots of the paywall showing accurate prices, auto-renew disclosures, and Terms + Privacy links.
- **Featuring nominations:** Submitted separately via ASC if desired; does not gate release.

---

## 1. App Privacy

**This process is typically manual.** The ASC API `/v1/appDataUsages` endpoint is often not exposed to third-party API keys and returns `404 PATH_ERROR`. Submitting without filling this out fails with:

```
HTTP 409 STATE_ERROR.ENTITY_STATE_INVALID
  associatedErrors: /v1/appDataUsages/ → APP_DATA_USAGES_REQUIRED
```

Fill it in at `https://appstoreconnect.apple.com/apps/<APP_ID>/distribution/privacy`, then **Save _and_ Publish**. Save and Publish are separate actions; an unpublished questionnaire blocks submission.

### What the App collects — answer truthfully

Declare data accurately. Common examples:

| Source | Data | Linked to identity? | Tracking? |
|---|---|---|---|
| Analytics (e.g., GA4, Telemetry) | Product Interaction, anonymous device IDs | Usually No | **No** (unless cross-app tracking) |
| Feedback | User Content (message text, screenshots), optional email | Yes (if email provided) | No |
| Purchases (StoreKit) | Purchase history (kept by Apple, standard validation) | No | No |
| Location Services | Coarse/precise location | Depends on app logic | No |

Points to get right:

- **"Used for Tracking":** If `Yes`, you must implement App Tracking Transparency (ATT). Avoid tracking if not strictly necessary.
- **Email:** If users can enter contact info, declare it and mark whether it links to identity.
- **Extensions:** Widget or Share extensions count towards privacy data if they make network requests or collect user inputs.

### The privacy policy URL

Ensure you have working links in `appInfoLocalizations`:
- Privacy Policy URL
- Terms of Service URL
- Support URL

These must return HTTP 200 and accurately describe data collection.

---

## 2. In-app purchases

### 2.1 What exists in App Store Connect

Products typically fall into types like `non-consumable` or `auto-renewable`. Before submission, ensure all intended products are `READY_TO_SUBMIT`. Do not submit products that are never displayed or purchasable in the app.

### 2.2 IAP must be attached to the review submission

**A first version does not carry its IAPs automatically.** Products sitting at `READY_TO_SUBMIT` stay there unless added as items on the same `reviewSubmission` as the version. Shipping a v1.0 app without attaching IAPs results in a broken paywall in production.

Each product also needs:
- Localized display name and description
- A price tier
- A **review screenshot** of the paywall in action.

### 2.3 Paid Apps Agreement

Products will not load in Sandbox or production until the **Paid Apps Agreement** is active in App Store Connect Business. If `Product.products(for:)` returns `[]` in Sandbox, this is almost always the cause.

---

## 3. Review risks specific to iOS Apps

### 3.1 Restore Purchases is mandatory

Non-consumables and subscriptions require a visible **Restore Purchases** control. Its absence is one of the most common IAP rejections. Confirm it is on the paywall before submitting.

### 3.2 Subscription disclosure

If the app ships an auto-renewable subscription, the paywall must show the price, billing period, auto-renew terms, and link to **Terms of Use (EULA)** and the **Privacy Policy**. The `appStoreVersions` record also needs an EULA link.

### 3.3 Dynamic Pricing and Strikethroughs

Avoid hardcoding prices in UI components. This causes:
- **Currency mismatches:** A user outside the base currency region sees a mismatched currency symbol stuck next to their localized price, which looks broken.
- **Accuracy violations (Guideline 2.3.x / 3.1.1):** Claiming a "was" price that is fake or localized improperly will trigger rejections.
Always fetch localized prices directly from StoreKit (`Product.displayPrice`).

### 3.4 Service Attribution

If you use third-party services (e.g., Apple WeatherKit, Google Maps), you **must** display their required attribution logos and links according to their specific placement rules.

### 3.5 The reviewer must be able to reach features

Provide review notes detailing how to access locked features, navigate to the paywall, or configure extensions (like widgets requiring Home-Screen setup). Reviewers routinely miss value if setup is complex. Keep notes accurate and update them if app logic changes.

Review notes are scriptable and stay editable even while `WAITING_FOR_REVIEW`:

```bash
RD=$(asc_api GET "/v1/appStoreVersions/<VERSION_ID>/appStoreReviewDetail" | jq -r '.data.id')
asc_api PATCH "/v1/appStoreReviewDetails/$RD" \
  '{"data":{"type":"appStoreReviewDetails","id":"'"$RD"'","attributes":{"notes":"<YOUR_NOTES>"}}}'
```

---

## 4. Age rating

Age rating declarations must be fully answered. This can be scripted via the ASC API:

```bash
asc_api PATCH "/v1/ageRatingDeclarations/<DECLARATION_ID>" \
  '{"data":{"type":"ageRatingDeclarations","id":"<DECLARATION_ID>",
    "attributes":{"violenceCartoonOrFantasy":"NONE","profanityOrCrudeHumor":"NONE",
      "userGeneratedContent":false,"unrestrictedWebAccess":false,"advertising":false,
      "gambling":false,"socialMedia":false,"messagingAndChat":false}}}'
```

Send every attribute; partial patches leave the declaration incomplete.

## 5. Territories

Set your app's availability across desired territories.

```bash
# Fetch all territories
T=$(asc_api GET "/v1/territories?limit=200" | jq -c '[.data[].id]')
# POST /v2/appAvailabilities with availableInNewTerritories:true
```

## 6. Submitting via API

```bash
API=asc_api
APP=<APP_ID>
VER=<VERSION_ID>

# 1. create the submission
$API POST /v1/reviewSubmissions \
  '{"data":{"type":"reviewSubmissions","attributes":{"platform":"IOS"},
    "relationships":{"app":{"data":{"type":"apps","id":"'"$APP"'"}}}}}'

# 2. attach the version …
$API POST /v1/reviewSubmissionItems \
  '{"data":{"type":"reviewSubmissionItems","relationships":{
      "reviewSubmission":{"data":{"type":"reviewSubmissions","id":"<SUB_ID>"}},
      "appStoreVersion":{"data":{"type":"appStoreVersions","id":"'"$VER"'"}}}}}'

# 2b. … attach IAPs or subscriptions
#     relationships.inAppPurchaseV2 → {"type":"inAppPurchases","id":"<IAP_ID>"}

# 3. submit
$API PATCH /v1/reviewSubmissions/<SUB_ID> \
  '{"data":{"type":"reviewSubmissions","id":"<SUB_ID>","attributes":{"submitted":true}}}'
```

Step 2 is where `APP_DATA_USAGES_REQUIRED` surfaces if the App Privacy section is unfinished.

### State machine

```
PREPARE_FOR_SUBMISSION → WAITING_FOR_REVIEW → IN_REVIEW
   → PENDING_DEVELOPER_RELEASE / READY_FOR_SALE
```

`reviewSubmissions` carry their own state; `submittedDate` stays `null` until you PATCH `submitted: true`. Rejections land in Resolution Center (web UI only).

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 apps does not allow 'CREATE'` | app records are web-UI only | Create app in ASC web interface |
| `404 PATH_ERROR` on `/v1/appDataUsages` | App Privacy is web-UI only | Use web UI |
| `409 … APP_DATA_USAGES_REQUIRED` | privacy saved but **not published** | Press Publish in ASC |
| `500` on `filter[bundleId]` | known API flake | list all apps, match locally |
| PATCH returns `200`, relationships `null` | ASC quirk | re-`GET` with `?include=` |
| Upload succeeded, no build appears | processing failed out-of-band | check `/v1/apps/<id>/buildUploads` for the error |
| Build stuck on export compliance | `ITSAppUsesNonExemptEncryption` missing | Set in Info.plist |
| Paywall empty in production | IAPs not attached to submission, or agreement unsigned | Check submission attachments and Paid Apps Agreement |
| Screenshot stuck at `UPLOAD_COMPLETE` | Apple still validating | Wait, check for `COMPLETE` + empty `errors` |
| Debug panel found in a shipped build | Internal config archived instead of Release | Use Release config for archiving |
| `409 … ATTRIBUTE.INVALID.TOO_LONG` on notes | Review notes exceed **4000 chars** | Rewrite to fit; the cap is hard (§8) |
| Rejected "Information Needed", nothing broken | Guideline **2.1** — review notes too thin | Answer all 7 asks + attach a demo video (§8) |
| Updated notes but reviewer never responds | Resolution Center has **no API** | A human must reply in the web UI (§8) |

---

## 8. Guideline 2.1 "Information Needed"

A very common first-submission rejection that is **not** a bug, a crash or a
policy breach: App Review cannot tell what the app does, so they ask. The version
goes to `REJECTED` and the `reviewSubmission` to `UNRESOLVED_ISSUES`. Nothing in
the binary needs to change — this is answered entirely in metadata.

Apple asks for seven things. Answer **all** of them, numbered, in
`appStoreReviewDetails.notes`, except the recording which is an attachment:

| # | Ask | Where |
|---|---|---|
| 1 | Screen recording on a **physical device**, **latest OS**, **starting at app launch** | attachment |
| 2 | Device models + OS versions tested | notes |
| 3 | Functions, target audience, problem solved | notes |
| 4 | Setup/access instructions + demo credentials | notes |
| 5 | External services (data, auth, payment, AI) | notes |
| 6 | Regional differences, or confirmation there are none | notes |
| 7 | Regulated industry / third-party material authorisation | notes |

### ⛔️ Say "does not apply" out loud

Apple's list includes login flows, account deletion, UGC reporting/blocking and
ATT prompts. If the app has none of those, **state that explicitly** — silence is
what triggered the request in the first place, and a reviewer cannot tell "absent
because it does not exist" from "absent because it was hidden". A recording
cannot show a flow that does not exist, so the notes must say so.

### ⛔️ Review notes are capped at 4000 characters

```
409 ENTITY_ERROR.ATTRIBUTE.INVALID.TOO_LONG
  detail: Review Notes cannot be longer than 4000 characters.
  source.pointer: /data/attributes/notes
```

Seven answers rarely fit alongside verbose pre-existing notes — expect to
**rewrite rather than append**. Keep the source text in the repo and check
`len()` before every PATCH instead of re-deriving the budget by hand. Write it in
plain human prose and sign it; a reviewer reads this, not a parser.

```bash
RD=$($API GET "/v1/appStoreVersions/$VER/appStoreReviewDetail" | jq -r '.data.id')
$API PATCH "/v1/appStoreReviewDetails/$RD" \
  '{"data":{"type":"appStoreReviewDetails","id":"'"$RD"'","attributes":{"notes":"…"}}}'
```

### Attaching the demo recording

`appStoreReviewAttachments` uses the same **reserve → upload → commit** pattern as
screenshots. A **~40 MB** video uploads fine; Apple splits it into 5 MB parts
itself. (The widely quoted "500 MB" limit is for *marketing app previews* — a
different asset. Apple's own help page for review attachments 404s, so verify by
attempting the reservation rather than trusting a number.)

```bash
# 1. reserve — returns uploadOperations[] (url, offset, length, requestHeaders)
$API POST /v1/appStoreReviewAttachments \
  '{"data":{"type":"appStoreReviewAttachments",
     "attributes":{"fileName":"Demo.mp4","fileSize":<BYTES>},
     "relationships":{"appStoreReviewDetail":{"data":
       {"type":"appStoreReviewDetails","id":"'"$RD"'"}}}}}'
# 2. PUT each part with curl --data-binary, honouring offset/length
# 3. commit
$API PATCH /v1/appStoreReviewAttachments/<ID> \
  '{"data":{"type":"appStoreReviewAttachments","id":"<ID>",
     "attributes":{"uploaded":true,"sourceFileChecksum":"<md5>"}}}'
```

Poll until `assetDeliveryState.state` is `COMPLETE` with `errors: []`.
**`UPLOAD_COMPLETE` only means the bytes landed**, not that Apple accepted them.

### Compressing a screen recording

A 4-5 minute iPhone capture is typically 300 MB+. Two-pass x264 at ~1150 kbps
**keeps the original resolution** and stays legible — do **not** downscale, that
destroys the small type and price labels a reviewer needs to read:

```bash
ffmpeg -i src.mp4 -c:v libx264 -preset slow -b:v 1150k -pass 1 -an -f mp4 /dev/null
ffmpeg -i src.mp4 -c:v libx264 -preset slow -b:v 1150k -pass 2 \
  -c:a aac -b:a 64k -ac 1 -movflags +faststart Demo.mp4
```

### Audit the recording before attaching it

Re-shooting after a second rejection is expensive. Extract a contact sheet and
confirm with your own eyes that it starts at launch and covers the paid flow and
every permission prompt:

```bash
ffmpeg -i Demo.mp4 -vf "fps=1/6,scale=300:-1,tile=4x4" -q:v 4 sheet_%02d.jpg
```

### ⛔️ The Resolution Center reply is web-UI only

There is **no ASC API endpoint for Resolution Center messages**, and a
`reviewSubmission` at `UNRESOLVED_ISSUES` is not re-driven by the API. Updating
notes and attachments does **not** notify the reviewer — a human must open
Resolution Center and reply. Prepare the reply text and a copy of the video for
that step, and attach the video there **as well as** on the version. Keep a
smaller spare encode to hand in case that upload box rejects the full-size file.

### While you are in there: verify the IAP items

A rejection is the moment to check blocker #11, because it is otherwise invisible
until launch day:

```bash
$API GET "/v1/reviewSubmissions/<SUB_ID>/items?include=appStoreVersion"
```

If that returns a single item (the version) with no `inAppPurchaseV2` /
`subscription` items while products sit at `READY_TO_SUBMIT`, purchases ship
unreviewed and `Product.products(for:)` returns `[]` in production.

---

← Back to [app-store-release.md](../app-store-release/SKILL.md)
