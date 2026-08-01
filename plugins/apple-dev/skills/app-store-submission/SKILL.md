---
name: app-store-submission
description: >
  Guide for App Store submission checklist, export compliance, privacy questionnaires, age ratings, App Review rejections, and binary upload.
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

← Back to [app-store-release.md](../app-store-release/SKILL.md)
