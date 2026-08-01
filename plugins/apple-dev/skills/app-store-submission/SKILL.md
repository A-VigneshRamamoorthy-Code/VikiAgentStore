---
name: app-store-submission
description: >
  Apple development skill for App Store submission — privacy, IAP & review risk. Use this skill when working on app-store-submission tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# App Store submission — privacy, IAP & review risk

> Part of the **[Leap Agent Guide](../../agents.md)**. Build and upload are in
> [app-store-release.md](app-store-release.md); listing copy and screenshots
> are in [app-store-listing.md](app-store-listing.md).

---

## 0. Blockers before any submission

> **Status 2026-07-31 — most of the original blocker list is now CLEARED.**
> Re-verified against the live API; see the "now" column.

| # | Blocker | Status now |
|---|---|---|
| 1 | **No privacy policy URL** | ✅ **set** (GitHub Pages) |
| 2 | **App Privacy questionnaire not filled in** | ❓ **still unverifiable via API** — `appDataUsages` and `appDataUsagePublishState` both return `404 PATH_ERROR`, so confirm in the ASC **web UI**. Leap *does* collect (GA4 + feedback) |
| 3 | **No `ITSAppUsesNonExemptEncryption`** | ✅ **cleared** — build 7 reports `usesNonExemptEncryption: false`, no separate declaration needed |
| 4 | **No build uploaded** | ✅ **build 7 attached, `VALID`**, minOS 17.0 |
| 5 | **No categories, subtitle, keywords, description or screenshots** | ✅ **all populated + verified** — see [app-store-listing.md §0](app-store-listing.md#0-as-built-live-values) |
| 6 | **Territories not set** | ✅ **175 territories**, price schedule base `USA`, app **Free** |
| 7 | **iPad screenshots required** | ✅ **not required** — all 9 build configs are `TARGETED_DEVICE_FAMILY = "1"` (iPhone-only); the 8-shot `APP_IPHONE_67` set is sufficient |
| 8 | **Private API → Guideline 2.5.1** | ✅ **scan clean** — see below |
| 9 | Hardcoded `$12.99` strikethrough price | see §3.4 |
| 10 | An IAP product the code never reads (`…pro.lifetime.list`) | see §2.1 |
| 11 | **IAPs not attached to the first submission** | ⚠️ **open** — both are `READY_TO_SUBMIT` but must be **explicitly attached** to the v1.0 review submission, or purchases ship unreviewed and every sale fails |
| 12 | **Release binary not scanned for the debug panel** | ⚠️ **open** — no exported `Leap.app`/`.ipa` present locally, so the "no debug panel, no `NammaLeap@2026`" check has not been run against build 7's exact bits |
| 13 | **Copyright not set** | ✅ **`2026 Vignesh Ramamoorthy`** on the version |
| 14 | **Content Rights Information not set** | ✅ **`DOES_NOT_USE_THIRD_PARTY_CONTENT`** on the app |
| 15 | **No price tier chosen** | ✅ **Free** — `POST /v1/appPriceSchedules` (create-only; you cannot PATCH an empty schedule) |
| 16 | **New age-rating social-media question unanswered** | ✅ `socialMediaAgeRestricted: false` (was `null` = unanswered) |

> **Blockers 13–16 were the entire "Unable to Add for Review" banner** and none of
> them live on the version localization, so a fully populated listing still showed
> all four. All four are scriptable — the exact endpoints are in
> [app-store-listing.md §8](app-store-listing.md#8-app-level-fields--what-the-api-can-and-cannot-set).

### Guideline 2.5.1 private-API scan (2026-07-31)

`build/Release-iphoneos/LeapWidgetExtension.appex/LeapWidgetExtension` — **clean**:

```
IOPSCopyPowerSourcesInfo      0     _UIWallpaper   0
IOPSCopyPowerSourcesList      0     CHSWidget      0
IOPSGetPowerSourceDescription 0     PBWidget       0
```

The 11 `wallpaper` hits are all Leap's own symbols (`LeapWallpaperStore`,
`leap.wallpaper.kind.v1`, UI strings). `LEAP_HOST_TRANSPARENCY` confirmed off.
**Re-run this on the app binary too, not just the extension.**

### Other verified-ready items

Age rating **complete** (`FOUR_PLUS`, every category `NONE`/false) · review
details complete (contact + notes, `demoAccountRequired: false`) · support URL
set. `whatsNew` is `null`, which is **fine for a 1.0** — release notes are only
required for updates. `marketingUrl` is `null` and optional.

**IAP review screenshots are current (2026-07-31).** All three records — lifetime
`6796248820`, list-price `6796395835` and monthly subscription `6796249550` — carry
a freshly captured paywall showing the **live $9.99 / $12.99 / $0.99** prices, the
auto-renew disclosure and the Terms + Privacy links, `assetDeliveryState.state`
`COMPLETE` with no errors. The previous set showed a stale **$8.99**. Re-capture
recipe and the upload script (`scripts/asc_iap_screenshot.sh`) are in
[in-app-purchases.md §12.3b](in-app-purchases.md).

**A featuring nomination is separate from review** and is already `SUBMITTED` — see
[app-store-listing.md §9](app-store-listing.md#9-featuring-nomination--the-undocumented-v1nominations-api).
It does not gate release and does not need an approved binary.

---

## 1. App Privacy

**This cannot be scripted.** `/v1/appDataUsages` returns `404 PATH_ERROR`; the
endpoint is not exposed to third-party API keys. Submitting without it fails
with:

```
HTTP 409 STATE_ERROR.ENTITY_STATE_INVALID
  associatedErrors: /v1/appDataUsages/ → APP_DATA_USAGES_REQUIRED
```

Fill it in at
`https://appstoreconnect.apple.com/apps/6796248408/distribution/privacy`, then
**Save _and_ Publish**. Save and Publish are separate buttons, and a
saved-but-unpublished questionnaire looks complete in the UI while still
returning `APP_DATA_USAGES_REQUIRED`. If you hit that error and you are sure
you filled it in, you did not press Publish.

### What Leap actually collects — answer truthfully

Unlike a zero-collection app, **Leap collects data and must say so.** Sources:

| Source | Data | Linked to identity? | Tracking? |
|---|---|---|---|
| Firebase Analytics / GA4 ([telemetry.md](telemetry.md)) | Product Interaction, anonymous `app_instance_id` (Device ID / User ID category) | No | **No** |
| Feedback ([feedback.md](feedback.md)) | User Content (message text, up to 3 screenshots), **optional email address**, diagnostics | Only if the user supplies an email | No |
| Purchases (StoreKit) | Purchase history stays with Apple; Leap stores only a boolean in the App Group | No | No |
| WeatherKit ([weatherkit.md](weatherkit.md)) | Coarse location used **on device** to fetch weather; cached in the App Group, never uploaded by Leap | No | No |

Points to get right:

- **"Used for Tracking" must be `No`.** [telemetry.md](telemetry.md) states the
  invariant plainly: no `setUserID`, no IDFA, no App Tracking Transparency.
  Answering `Yes` would require an ATT prompt Leap does not have.
- **Email is optional user content**, not an account identifier — declare it
  under Contact Info and mark it optional.
- **Location**: the app requests When-In-Use for weather. It is used on device
  and cached to the App Group; nothing leaves the phone except the query to
  Apple's WeatherKit service. Declare it as **not linked** and **not tracked**.
- **Do not forget the widget extension.** It never calls Firebase (that would
  double-count users), so it adds no new declaration — but a reviewer may ask,
  and the answer is in [telemetry.md](telemetry.md).

### Exact answers to enter

Verified against source on 2026-07-31. Every row below is a **collected** data
type; everything not listed is **not** collected.

| Category → type | Purpose | Linked to identity | Used for tracking |
|---|---|---|---|
| Identifiers → **Device ID** (Firebase `app_instance_id`) | Analytics | **No** | **No** |
| Usage Data → **Product Interaction** | Analytics | **No** | **No** |
| User Content → **Other User Content** (feedback message + screenshots) | App Functionality, Customer Support | **No** | **No** |
| Contact Info → **Email Address** (optional, feedback only) | Customer Support | **Yes** | **No** |

Notes that decide the tricky answers:

- **Email is the only "Yes" for linked.** It is optional and user-typed, but
  `FeedbackView` attaches `LeapTelemetry.appInstanceID()` to the same document,
  so when an email *is* given the analytics id sits beside it. Declaring it
  linked is the honest answer and costs nothing.
- **Location is NOT declared.** WeatherKit is queried from the device and Apple
  is the recipient; Leap never receives or stores coordinates on a server of its
  own. Apple's own guidance is to declare data *your app* collects.
- **Purchases is NOT declared.** StoreKit keeps the transaction; Leap persists
  only a boolean.
- **Everything is `No` for tracking.** No IDFA, no ATT prompt, no `setUserID`.

### The privacy policy URL — DONE

Hosted on the owner's existing GitHub Pages site (the NotchPaw repo serves
Leap's pages) and already set on `appInfoLocalizations`:

- Privacy: `https://a-vigneshramamoorthy-code.github.io/NotchPaw/leap/privacy.html`
- Terms: `https://a-vigneshramamoorthy-code.github.io/NotchPaw/leap/terms.html`
- Support: `https://a-vigneshramamoorthy-code.github.io/NotchPaw/leap/support.html`

All three return HTTP 200 and the privacy page describes the Firebase collection
and the feedback pipeline. Regenerate from `docs/legal/*.html` if the in-app
legal text changes — the two must not drift.

---

## 2. In-app purchases

Full design lives in [in-app-purchases.md](in-app-purchases.md). What matters
at submission time:

### 2.1 What exists in App Store Connect right now

| Product ID | Type | State | In code? |
|---|---|---|---|
| `com.sololeap.leap.app.pro.lifetime` | non-consumable | `READY_TO_SUBMIT` | yes — `LeapProduct.lifetime` |
| `com.sololeap.leap.app.pro.monthly` | auto-renewable (group `22274535`) | `READY_TO_SUBMIT` | yes — `LeapProduct.monthly` |
| `com.sololeap.leap.app.pro.lifetime.list` | non-consumable | `READY_TO_SUBMIT` | **no — nothing reads it** |

`…pro.lifetime.list` ("Leap Premium (Lifetime) List Price") looks like an
attempt to source the struck-through compare-at price from a real product. It
is **not wired up**: `Shared/LeapEntitlements.swift:39` hardcodes
`lifetimeOriginalPrice = "$12.99"` and nothing in `Leap/` or `Shared/`
references the `.list` product id. Decide before submitting — either wire it up
or remove it. Submitting a purchasable product that the app never offers is a
review question at best, and it will appear on the store page's in-app
purchase list.

### 2.2 IAP must be attached to the review submission

**A first version does not carry its IAPs automatically.** Products sitting at
`READY_TO_SUBMIT` stay there unless they are added as items on the same
`reviewSubmission` as the version. Ship the app without them and the paywall
finds no products in production — `Product.products(for:)` returns `[]` and the
Unlock button shows the "Something went wrong" alert described in
[in-app-purchases.md §10.1](in-app-purchases.md).

Each product also needs, before it can be submitted: a localized display name
and description, a price, and a **review screenshot** of the paywall.

### 2.3 Paid Apps Agreement

Products will not load in Sandbox or production until the **Paid Apps
Agreement** is active in Business. `Product.products(for:)` returning `[]` in
Sandbox is almost always this and nothing else.

---

## 3. Review risks specific to Leap

### 3.1 Private API — Guideline 2.5.1 (the big one)

`LeapWidget/LeapWidgetTransparency.mm` swizzles a private WidgetKit XPC method
and writes a private ivar on `CHSBaseDescriptor` to force transparent widget
platters. [transparency.md](transparency.md) records that the 2.5.1 rejection
risk was **explicitly accepted by the user** — so this is a known, deliberate
bet, not an oversight.

What reduces the blast radius:

- The hook **fails safe**. If the private class or ivar is absent, the
  installer writes nothing, clears `leap.hostTransparent.v1`, and the Swift
  layer bakes the wallpaper instead. The app still works.
- Therefore, **do not describe the mechanism in store metadata** and do not
  promise transparency survives a wallpaper change — see
  [app-store-listing.md §4](app-store-listing.md#4-copy--proposals-to-be-confirmed-with-the-human).
- If it is rejected, the fallback path (§6b of
  [transparency.md](transparency.md)) is already a shippable product. Have a
  build ready with the hook compiled out rather than arguing in Resolution
  Center.

### 3.2 Restore Purchases is mandatory

Non-consumables require a visible **Restore Purchases** control. Its absence is
one of the most common IAP rejections. Confirm it is on the paywall before
submitting.

### 3.3 Subscription disclosure

Because Leap ships an auto-renewable monthly product, the paywall must show
price, billing period and auto-renew terms, and link to **Terms of Use (EULA)**
and the **Privacy Policy**. Apple's `SubscriptionStoreView` handles most of it;
Leap's custom `PaywallView` must carry it explicitly. The `appStoreVersions`
record also needs an EULA link.

### 3.4 The hardcoded compare-at price

`Shared/LeapEntitlements.swift:39`:

```swift
static let lifetimeOriginalPrice = "$12.99"
```

It is rendered struck-through next to a StoreKit-localized price
(`PaywallView.swift:409`). Two problems:

- **Currency mismatch outside the US.** A euro-zone user sees `$12.99` struck
  through above `€9.99`. That is visibly broken and reads as a fake discount.
- **A pricing claim Apple can test.** A "was" price that does not correspond to
  a price the product was ever sold at is a Guideline 2.3.x / 3.1.1 accuracy
  problem.

Fix before submitting: load the compare-at price from the real
`…pro.lifetime.list` product (which is presumably why it exists), or drop the
strikethrough and keep the honest single price.

### 3.5 WeatherKit attribution

Apple **requires** visible Apple Weather attribution wherever WeatherKit data
is shown, with specific placement rules. [weatherkit.md](weatherkit.md) covers
how Leap ships it — confirm it is present on every weather face and in any
screenshot that shows real weather.

### 3.6 The reviewer must be able to reach the paywall

Provide review notes describing: how to add a widget, that the Home-Screen
widget must be placed from the iOS gallery, and how to reach the paywall.
Reviewers routinely miss widget-only value if it needs Home-Screen setup.

Review notes are scriptable and stay editable even while a version is
`WAITING_FOR_REVIEW`:

```bash
V=b4f69e04-f101-4ad4-bd1d-e869c24f6fee
RD=$(.build/tools/asc_api GET "/v1/appStoreVersions/$V/appStoreReviewDetail" | jq -r '.data.id')
.build/tools/asc_api PATCH "/v1/appStoreReviewDetails/$RD" \
  '{"data":{"type":"appStoreReviewDetails","id":"'"$RD"'","attributes":{"notes":"…"}}}'
```

**Keep the notes true.** On NotchPaw the notes told the reviewer to reset a
`UserDefaults` key that had been renamed; a reviewer following a wrong
instruction concludes the app is broken. If you rename an App-Group key or
change a gesture, re-read these notes.

---

## 4. Age rating

Leap has no objectionable content — every declaration is `NONE`/`false`, giving
4+. Sent as a single PATCH:

```bash
.build/tools/asc_api PATCH "/v1/ageRatingDeclarations/6a1f8953-efb5-4bf2-b6c3-2bccac185555" \
  '{"data":{"type":"ageRatingDeclarations","id":"6a1f8953-efb5-4bf2-b6c3-2bccac185555",
    "attributes":{"violenceCartoonOrFantasy":"NONE","profanityOrCrudeHumor":"NONE",
      "userGeneratedContent":false,"unrestrictedWebAccess":false,"advertising":false,
      "gambling":false,"socialMedia":false,"messagingAndChat":false}}}'
```

Send every attribute the endpoint expects — a partial PATCH leaves the
declaration incomplete and blocks submission.

## 5. Territories

`/v2/appAvailabilities/6796248408` currently returns nothing. Set it before
submitting:

```bash
T=$(.build/tools/asc_api GET "/v1/territories?limit=200" | jq -c '[.data[].id]')
# POST /v2/appAvailabilities with availableInNewTerritories:true and one
# territoryAvailabilities entry per id — see NotchPaw/scripts/asc_metadata.sh
```

There are 175 territories. Worth a thought rather than a reflex: a
transparency hack that depends on private API behaviour may behave differently
across regions' iOS releases, but there is no regional gating to be had — it is
all-or-nothing per territory.

## 6. Submitting

```bash
API=.build/tools/asc_api
APP=6796248408
VER=b4f69e04-f101-4ad4-bd1d-e869c24f6fee

# 1. create the submission
$API POST /v1/reviewSubmissions \
  '{"data":{"type":"reviewSubmissions","attributes":{"platform":"IOS"},
    "relationships":{"app":{"data":{"type":"apps","id":"'"$APP"'"}}}}}'

# 2. attach the version …
$API POST /v1/reviewSubmissionItems \
  '{"data":{"type":"reviewSubmissionItems","relationships":{
      "reviewSubmission":{"data":{"type":"reviewSubmissions","id":"<subId>"}},
      "appStoreVersion":{"data":{"type":"appStoreVersions","id":"'"$VER"'"}}}}}'

# 2b. … and one item per IAP / subscription you intend to ship
#     relationships.inAppPurchaseV2 → {"type":"inAppPurchases","id":"6796248820"}
#     relationships.subscription    → {"type":"subscriptions","id":"<id>"}

# 3. submit
$API PATCH /v1/reviewSubmissions/<subId> \
  '{"data":{"type":"reviewSubmissions","id":"<subId>","attributes":{"submitted":true}}}'
```

Step 2 is where `APP_DATA_USAGES_REQUIRED` surfaces if §1 is unfinished.

### State machine

```
PREPARE_FOR_SUBMISSION → WAITING_FOR_REVIEW → IN_REVIEW
   → PENDING_DEVELOPER_RELEASE / READY_FOR_SALE
```

`reviewSubmissions` carry their own state; `submittedDate` stays `null` until
you PATCH `submitted: true`. Rejections land in Resolution Center — web UI
only.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403 apps does not allow 'CREATE'` | app records are web-UI only | already created for Leap |
| `404 PATH_ERROR` on `/v1/appDataUsages` | App Privacy is web-UI only | §1 |
| `409 … APP_DATA_USAGES_REQUIRED` | privacy saved but **not published** | press Publish |
| `500` on `filter[bundleId]` | known API flake | list all apps, match in `jq` |
| PATCH returns `200`, relationships `null` | ASC quirk | re-`GET` with `?include=` |
| Upload succeeded, no build appears | processing failed out-of-band | check `/v1/apps/<id>/buildUploads` for the error code |
| Build stuck on export compliance | `ITSAppUsesNonExemptEncryption` missing | [app-store-release.md §6](app-store-release.md#6-export-compliance--do-this-once-now) |
| Paywall empty in production | IAPs not attached to the submission, or Paid Apps Agreement unsigned | §2.2, §2.3 |
| Screenshot stuck at `UPLOAD_COMPLETE` | Apple still validating | wait, re-check for `COMPLETE` + empty `errors` |
| Debug panel found in a shipped build | Internal config archived instead of Release | [app-store-release.md §3](app-store-release.md#3-archive-and-export) |

← Back to [app-store-release.md](app-store-release.md)
