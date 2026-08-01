---
name: app-store-listing
description: >
  Apple development skill for App Store listing — metadata, ASO & screenshots. Use this skill when working on app-store-listing tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# App Store listing — metadata, ASO & screenshots

> Part of the **[Leap Agent Guide](../../agents.md)**. Pipeline and signing are
> in [app-store-release.md](app-store-release.md); privacy, IAP and review risk
> are in [app-store-submission.md](app-store-submission.md).

---

> **⚠️ Sections 1–4 below are the original *research*. The listing is now LIVE
> and populated — see [§0 As-built](#0-as-built-live-values) for what is actually
> in App Store Connect. Where the two disagree, §0 wins.**

## 0. As-built (live values)

Applied and read-back-verified **2026-07-31** on version `1.0`
(`b4f69e04-f101-4ad4-bd1d-e869c24f6fee`), state `PREPARE_FOR_SUBMISSION`.

| Field | Value | Count |
|---|---|---|
| Name (`appInfoLocalizations` `20308d9c-65d0-4704-946a-09c990f49551`) | `Leap: Custom Widgets Studio` | 27/30 |
| Subtitle | `Clock, Photo, Wallpaper Blend` | 29/30 |
| Keywords (`appStoreVersionLocalizations` `694814fe-687d-47c2-86f6-3cd698382eaa`) | `transparent,clear,invisible,aesthetic,home,screen,maker,minimal,neon,calendar,weather,battery,streak` | 100/100 |
| Promotional text | `67 designs. 4 styles. 3,500+ combinations. Save up to 8 widgets for your first 7 days. No account, no sign-in and no ads.` | 121/170 |
| Description | see below | 4000/4000 |
| Categories | `GRAPHICS_AND_DESIGN` / `UTILITIES` | — |
| Screenshots | 8 × `APP_IPHONE_67`, set `7802553c-9f71-47fe-a1c1-38c4a9c76194` | all `COMPLETE` |
| Copyright (on `appStoreVersions`) | `2026 Vignesh Ramamoorthy` | — |
| Content rights (on `apps`) | `DOES_NOT_USE_THIRD_PARTY_CONTENT` | — |
| Price | **Free** — 1 manual price (USA `0.0`) + 174 auto-equalized | 175 territories |

### Why these exact strings

Chosen by reconciling two independent ASO reviews (GPT-5.6 Sol + Gemini 3.1 Pro),
then validated mechanically. The design rule is **zero token duplication across
the three indexed fields**:

- name → `leap`, `custom`, `widgets`, `studio`
- subtitle → `clock`, `photo`, `wallpaper`, `blend`
- keywords → the 13 above, none of which repeat a name/subtitle token

`transparent` / `clear` / `invisible` live **only** in keywords. That is what makes
Leap eligible for the query *"transparent widget"* — Apple combines tokens across
the three fields on its own, so `widgets` (name) + `transparent` (keywords) yields
the phrase **without any visible transparency claim**. Never move them into a
visible field.

**`Widget Studio`, `Widgets Studio` and `Widget Studio: Custom Widgets` are live
apps** — the `Leap:` prefix is what keeps this name unique, so do not shorten the
name to `Leap: Widgets Studio`.

### Two compliance fixes baked into the description

1. The old header `NOTHING ABOUT YOU LEAVES YOUR DEVICE` (and the bullet
   `everything you make stays on your device`) was **contradicted three paragraphs
   later** by the GA4-analytics and feedback disclosure — a Guideline **2.3.7 /
   5.1.1** deception flag that both reviewers caught independently. Now
   `YOUR CONTENT STAYS ON YOUR DEVICE`, with the absolute claims scoped to content.
2. Added `All 67 designs and all 4 styles are free.` — Guideline **3.1.2(c)**:
   Premium must never read as unlocking designs or styles.

### ⛔️ Premium is UNLIMITED — do not write "up to 8"

`freeWidgetHardCap = 8` is a **free-tier** cap. `LeapViewModel.swift:269` reads
`!isPro && LeapEntitlements.shouldPaywallNextWidget(...)`, so a Premium user has
**no widget limit at all**. An ASO draft asserted *"Leap Premium removes the
free-tier limits, up to Leap's maximum of 8 saved widgets"* — that is false and is
itself a 2.3.7 risk in the opposite direction. The trial cap of 8 **is** correct.

---

### Historical note

The research below was written when every field except the app name was empty, and
it proposed the name `Leap: Transparent Widgets`. **That name is now forbidden** —
see the visible-copy invariant in [`agents.md`](../../agents.md).

## 1. How App Store search actually works

Two rules drive every decision below.

1. **Apple indexes the union of `name` + `subtitle` + `keywords`.** Repeating a
   word across those three fields buys nothing — it wastes characters.
2. **The description is _not_ indexed** for App Store search. It exists to
   convert someone already on the page (and it does feed Google, which indexes
   the web listing).

So: zero duplication across the three indexed fields, and write the description
for humans.

## 2. Field limits

| Field | Limit | Endpoint |
|---|---|---|
| Name | 30 | `appInfoLocalizations.name` |
| Subtitle | 30 | `appInfoLocalizations.subtitle` |
| Privacy policy URL | — | `appInfoLocalizations.privacyPolicyUrl` |
| Keywords | 100 | `appStoreVersionLocalizations.keywords` |
| Promotional text | 170 | `appStoreVersionLocalizations.promotionalText` |
| Description | 4000 | `appStoreVersionLocalizations.description` |
| Marketing / Support URL | — | `appStoreVersionLocalizations.marketingUrl` / `.supportUrl` |

Keywords are **comma-separated with no spaces** — a space after a comma is a
wasted character. Check every length locally before sending; Apple's error for
an over-length field is unhelpful.

## 3. Category — use Graphics & Design

Measured against the live store (iTunes Search API, `entity=software`,
US, top ~25 per query):

| Query | Graphics & Design | Utilities | Productivity | Other |
|---|---|---|---|---|
| `transparent widget` | **14** | 6 | 4 | 1 |
| `widgets` | **16** | 5 | 1 | 2 |
| `widget wallpaper` | **18** | 1 | 2 | 2 |
| `aesthetic widgets` | **20** | 3 | 1 | 1 |

The widget-customisation cohort lives in **Graphics & Design** by a wide
margin — Widgetsmith (Productivity) and Color Widgets (Utilities) are the
exceptions, not the pattern. Category feeds Apple's *recommendation* engine as
well as search, so being in the wrong one costs "you might also like"
placement next to every competitor.

**Recommendation: `GRAPHICS_AND_DESIGN` primary, `UTILITIES` secondary.**

```bash
.build/tools/asc_api PATCH "/v1/appInfos/6a1f8953-efb5-4bf2-b6c3-2bccac185555" '{
  "data":{"type":"appInfos","id":"6a1f8953-efb5-4bf2-b6c3-2bccac185555",
    "relationships":{
      "primaryCategory":{"data":{"type":"appCategories","id":"GRAPHICS_AND_DESIGN"}},
      "secondaryCategory":{"data":{"type":"appCategories","id":"UTILITIES"}}}}}'
```

PATCH echoes `null` relationships even on success — verify with
`GET /v1/appInfos/<id>?include=primaryCategory,secondaryCategory`.

## 4. Copy — proposals, to be confirmed with the human

The name is currently **`Leap Widgets`** (12 of 30 characters). That spends
most of the highest-weighted field on a brand word that nobody searches. The
generic term Leap must own is **"widget"**, and the differentiator is
**transparent / clear**.

| Field | Proposal | Chars |
|---|---|---|
| Name | `Leap: Transparent Widgets` | 25 |
| Subtitle | `Clear home screen widgets` | 25 |
| Keywords | `aesthetic,invisible,custom,clock,face,wallpaper,weather,calendar,battery,streak,minimal,neon,photo` | 98 |

> **⛔️ SUPERSEDED AND FORBIDDEN.** This table predates the visible-copy
> invariant. `transparent` and `clear` must **never** appear in the name,
> subtitle, description or promo text. See [§0](#0-as-built-live-values) for the
> shipping values.

Renaming an app record is allowed while it is `PREPARE_FOR_SUBMISSION`, and the
name must be **globally unique across the App Store** — verify availability
before committing to it.

### Keyword rules, learned the hard way

- **Never name a competitor.** `widgetsmith`, `color widgets`, `widgy`,
  `iscreen`, `themify`, `koco` are all shipping apps; putting one in the
  keyword field breaches **Guideline 2.3.7** and is a straightforward
  rejection. This matters more than usual for Leap because
  [transparency.md](transparency.md) openly describes the mechanism as
  "Koco-style" — that is fine in engineering docs and **not** fine in store
  metadata.
- **Do not repeat a word already in the name or subtitle** — `leap`,
  `transparent`, `clear`, `widget`, `home`, `screen` are all spent.
- **Do not claim what the app does not do.** Leap has no icon themer and no
  lock-screen widgets; keywords like `icon`, `theme pack` or `lock screen`
  would rank for queries the app cannot satisfy — bad for conversion and a
  Guideline 2.3.7 accuracy risk.
- Singular only. Apple handles plurals; `widget` covers `widgets`.

### Description

Front-load the searched phrase in the first sentence — it is what Google
indexes and what the store truncates to:

> Leap makes your Home Screen widgets look **see-through**, without turning on
> iOS "Clear" appearance.

Then: 66 designs × 4 styles, live weather / calendar / battery / streak data,
the daily check-in, and what is free.

**Be careful with the transparency claim.** The primary path is a private-API
host composite that iOS can break in any release, with a baked-wallpaper
fallback that does *not* survive a wallpaper change
([transparency.md](transparency.md)). Copy that promises "always transparent,
even when you change your wallpaper" becomes false the moment the hook stops
installing. Describe the outcome, not a guarantee.

### Free-tier honesty

The paywall's own comparison table already spells out what is free (4 saved
widgets, 1 custom photo wallpaper, all 66 designs, all 4 styles, live weather
and calendar, the daily check-in). The store description should say the same
thing. Apple rejects listings that read as free when the useful part is gated,
and the **7-day trial then lock** behaviour — including
[locking already-placed Home-Screen widgets](in-app-purchases.md) — is exactly
the kind of surprise that generates one-star reviews if it is not disclosed up
front.

## 5. Screenshots

### Which sets are actually required

`TARGETED_DEVICE_FAMILY = "1"` on **all 9 build configurations** — **Leap ships
iPhone-only, so iPad screenshots are NOT required.** The 8-shot `APP_IPHONE_67`
set is sufficient. (An earlier revision of this doc claimed `"1,2"`; that is
stale — verify with
`grep TARGETED_DEVICE_FAMILY Leap.xcodeproj/project.pbxproj`.)

The API's own enum is authoritative (it is returned verbatim in the error when
you send an invalid value). Relevant entries:

```
APP_IPHONE_67   APP_IPHONE_65   APP_IPHONE_61   APP_IPHONE_58   …
APP_IPAD_PRO_3GEN_129   APP_IPAD_PRO_129   APP_IPAD_PRO_3GEN_11   …
APP_DESKTOP   APP_APPLE_VISION_PRO   APP_WATCH_*   IMESSAGE_APP_*
```

Note there is **no `APP_IPHONE_69` and no `APP_IPAD_13`** — despite what most
third-party guides say, the API still buckets the 6.9" iPhone under
**`APP_IPHONE_67`** and the 13" iPad under **`APP_IPAD_PRO_3GEN_129`**. Upload
the modern master sizes into those two sets and let Apple scale.

Requirements: PNG or JPEG, **no alpha channel**, no rounded corners, exact
pixel dimensions, 1–10 per set. A wrong dimension is not rejected at upload —
it surfaces later in `assetDeliveryState.errors`, so always verify.

### Capture them from the simulator, not from mockups

Leap already has the machinery: `docs/support/examples/proofs/` holds a full
walkthrough captured on the sim, and
[simulator-automation.md](simulator-automation.md) covers driving the UI with
CGEvent taps and the per-family snapshot gotchas.

Two Leap-specific traps when capturing:

- **The Simulator renders custom photo Home-Screen wallpapers as solid black
  and cannot show host transparency at all** — it never relaunches a
  third-party widget extension, so `+load` never runs
  ([transparency.md](transparency.md)). A Home-Screen shot taken on the sim
  will therefore show the *baked* fallback, not the real product. **The hero
  screenshot must be captured on a physical device**, where
  `hostTransparent=true / fired=true / applied=1` is verifiable from the App
  Group plist.
- **Weather faces show a deterministic placeholder** unless WeatherKit is
  actually returning data ([weatherkit.md](weatherkit.md)). Shipping a
  screenshot of the placeholder advertises fake data. Check
  `leap.debug.weather.v1` reads `ok …` before capturing any weather face, and
  remember Apple's **mandatory attribution** must be visible wherever real
  weather data is shown.

Suggested set (5–6 shots): the transparent widget on a real Home Screen · the
Browse catalog · the Add/Edit sheet with style switching · a clock face · the
daily check-in / streak · the free-vs-Premium comparison.

### Uploading

Apple's asset flow is three steps per file: reserve, PUT the bytes, commit with
an MD5.

```bash
# 1. reserve — returns signed uploadOperations, each covering a byte range
.build/tools/asc_api POST "/v1/appScreenshots" \
  '{"data":{"type":"appScreenshots",
    "attributes":{"fileName":"01-home.png","fileSize":123456},
    "relationships":{"appScreenshotSet":{"data":{"type":"appScreenshotSets","id":"<setId>"}}}}}'

# 2. PUT each range with the headers Apple supplied  (curl --data-binary)

# 3. commit
.build/tools/asc_api PATCH "/v1/appScreenshots/<id>" \
  '{"data":{"type":"appScreenshots","id":"<id>",
    "attributes":{"uploaded":true,"sourceFileChecksum":"<md5>"}}}'
```

`NotchPaw/scripts/asc_screenshots.sh` is a working implementation of exactly
this loop if you want to port it rather than rewrite it.

**Always verify** — every row must read `COMPLETE` with an empty `errors`
array. `UPLOAD_COMPLETE` means Apple has the bytes but has not finished
validating; wait and re-check.

```bash
.build/tools/asc_api GET "/v1/appScreenshotSets/<setId>/appScreenshots" \
  | jq -r '.data[] | "\(.attributes.fileName) \(.attributes.assetDeliveryState.state) \(.attributes.assetDeliveryState.errors)"'
```

## 6. App Preview videos

Optional, and Leap is a strong candidate — the transparency effect and the
style switcher are motion, not stills. Same reserve/PUT/commit flow via
`/v1/appPreviews`. Skip for 1.0; revisit once the listing converts.

## 7. Promotional text

170 characters, editable **at any time without a new build or a review**. Use
it for launch news and seasonal hooks instead of burning a version.

## 8. App-level fields — what the API can and cannot set

The version localization (description / keywords / promo / support URL) and the
app info localization (name / subtitle / privacy URL) are both straightforward
PATCHes. The **app-level** fields are where the time goes.

**Categories** live on `appInfos` as relationships, not attributes. The PATCH
echoes `null` for them even on success, so always verify with a follow-up
`GET /v1/appInfos/<id>?include=primaryCategory,secondaryCategory`.

**Age rating** is `PATCH /v1/ageRatingDeclarations/<appInfoId>` — note the id is
the **appInfo id**, not a separate one. **It is UPDATE-only**: a `GET` on the
instance is a `403 FORBIDDEN_ERROR` ("Allowed operation is: UPDATE"), so read the
current answers with
`GET /v1/appInfos/<id>?include=ageRatingDeclaration` instead. Three traps:

- The newer **`ageAssurance` attribute is REQUIRED**, and it is a **BOOLEAN**.
  Omitting it fails with `ENTITY_ERROR.ATTRIBUTE.REQUIRED`; sending the obvious
  `"NONE"` fails with `Expected a BOOLEAN but got STRING`. For Leap it is
  `false`.
- **`socialMediaAgeRestricted` is a NEW question** (ASC nags for it with a
  "Update Your Age Ratings Responses about Social Media" banner and a deadline).
  It defaults to `null`, which is *unanswered* — set it explicitly. Leap has no
  social features, so `socialMedia` and `socialMediaAgeRestricted` are both
  `false`.
- The content questions are a **mix of types**: enums (`"NONE"` /
  `"INFREQUENT_OR_MILD"` / `"FREQUENT_OR_INTENSE"`) for things like
  `violenceRealistic`, but plain booleans for `gambling`, `advertising`,
  `unrestrictedWebAccess`, `userGeneratedContent`, `socialMedia`, `lootBox`,
  `messagingAndChat`, `parentalControls`, `healthOrWellnessTopics`. The error
  message names the offending attribute, so fix them one at a time.

All-clear answers give Leap **`FOUR_PLUS`**. `userGeneratedContent` is `false`:
Mantra text is typed by the user but never shared with anyone, and Apple's
question is about content shared *between* users.

### The four "Unable to Add for Review" fields that are easy to miss

None of these live on the version localization, so a fully populated listing can
still be blocked by all four. All four **are** scriptable.

| Blocker text in ASC | Where it actually lives |
|---|---|
| "You must provide copyright information" | `PATCH /v1/appStoreVersions/<versionId>` → `attributes.copyright` |
| "You must set up Content Rights Information in App Information" | `PATCH /v1/apps/<appId>` → `attributes.contentRightsDeclaration` |
| "You must choose a price tier in Pricing" | `POST /v1/appPriceSchedules` — see below |
| "an Admin must provide information about the app's privacy practices" | **ASC web UI only** (`appDataUsages` is 404 to API keys) |

**`copyright` is a plain string with NO `©` symbol** — Apple renders the symbol.
The format is *year the rights were obtained* + *rights holder*. Leap ships
**`2026 Vignesh Ramamoorthy`**: the Developer Program membership is an
**individual** account (team `D2Z89UU4R7`, visible in the signing identity
`3rd Party Mac Developer Application: Vignesh Ramamoorthy (D2Z89UU4R7)`), so the
rights holder is the person, not a company.

**`contentRightsDeclaration`** is `DOES_NOT_USE_THIRD_PARTY_CONTENT` |
`USES_THIRD_PARTY_CONTENT`. Leap declares **`DOES_NOT_USE_THIRD_PARTY_CONTENT`**:
every widget face is drawn in code, the only bundled raster is `AppIcon-1024.png`,
there are **no bundled fonts** (`LeapFont` is system-only) and no licensed art.
Firebase and the Apple SDKs are code, not content, and WeatherKit data is licensed
through the entitlement and already carries its mandatory attribution.

### Pricing IS reachable through the API — create a schedule, don't PATCH one

An earlier revision of this doc listed pricing as UI-only. That was wrong: the
mistake was trying to **PATCH the existing empty schedule**. `appPriceSchedules`
is **create-only** — you `POST` a whole new schedule and it replaces the old one.

```sh
# 1. find the free price point for the BASE territory (customerPrice "0.0")
asc_api GET '/v1/apps/<appId>/appPricePoints?filter[territory]=USA&limit=200'

# 2. POST the schedule. The inline appPrice needs a LOCAL id of the form ${price1}
#    - a bare "price1" is rejected.
asc_api POST /v1/appPriceSchedules '{
  "data": {"type":"appPriceSchedules","relationships":{
    "app":          {"data":{"type":"apps","id":"<appId>"}},
    "baseTerritory":{"data":{"type":"territories","id":"USA"}},
    "manualPrices": {"data":[{"type":"appPrices","id":"${price1}"}]}}},
  "included": [{"type":"appPrices","id":"${price1}","relationships":{
    "appPricePoint":{"data":{"type":"appPricePoints","id":"<free point id>"}}}}]}'
```

Omit `startDate` / `endDate` and the price applies immediately and forever. Apple
then **auto-equalizes** the other storefronts: Leap ends up with **1 manual price**
(USA, `0.0`) and **174 automatic** ones — verify both counts, because a schedule
with a manual price and zero automatic ones means the equalization did not run.

> Unlike the **subscription** price points (see
> [payment-integration.md](payment-integration.md)), auto-equalization is the right
> answer here: the app itself is free in every territory, so there is no tier
> misalignment to get wrong.

**Not reachable through the API — do this in the ASC UI:**

| Field | Symptom |
|---|---|
| App Privacy "nutrition labels" | `/v1/apps/<id>/appDataUsages` returns `PATH_ERROR — The relationship 'appDataUsages' does not exist`. |
| Territory availability | `/v2/apps/<id>/appAvailability` 404s. (Creating the price schedule above is enough to clear the *pricing* blocker.) |

App Privacy is required before the version can be submitted, so budget a UI pass
at the end no matter how much of the rest is automated.

## 9. Featuring nomination — the undocumented `/v1/nominations` API

A **nomination** is how you pitch the app to Apple's **editorial** team for a
feature/story on the App Store. It is a **completely separate** submission from
App Review: it does not gate release, and a nomination can be submitted while
the app is still `PREPARE_FOR_SUBMISSION`.

**It is not discoverable.** `nominations` does **not** appear in the app's
relationship list, so the usual "GET the app and read its relationships" walk
never finds it. It was found by probing: `GET /v1/nominations` returns **400**,
not 404 — a 400 means the path exists and the *request* was wrong.

### As-built — Leap 1.0

| Field | Value |
|---|---|
| id | `3e75272d-a54a-45ab-a7a8-c080abc0f0b1` |
| `name` | `Leap 1.0 - widgets that blend into your wallpaper` (49/60) |
| `type` | `APP_LAUNCH` |
| `publishStartDate` | `2026-08-15T11:00:00Z` |
| `state` | **`SUBMITTED`** |
| `deviceFamilies` / `locales` | `["IPHONE"]` / `["EN-US"]` |
| `relatedApps` | `6796248408` |

The long-form pitch that the 1000-char limit would not take is kept outside the
repo, in the session folder (`nomination-description.txt` / `nomination-notes.txt`).
The shipped `description` leads with the *blend* idea, then the 67x4 catalogue as
a designed system, then the sweeping second hand as the technical story, then
privacy. The `notes` field is for the reviewer: what to look at, plus explicit
assurance that **no private API is used** and that the 5%-granular battery
readout is Apple's own `UIDevice` behaviour (see `agents.md`).

### The schema, learned entirely from rejection messages

```
GET    /v1/nominations?filter[state]=DRAFT|SUBMITTED|ARCHIVED
POST   /v1/nominations
PATCH  /v1/nominations/<id>
```

- **`filter[state]` is REQUIRED on the list call.** A bare `GET /v1/nominations`
  is a 400.
- **Required on POST:** `name`, `description`, `publishStartDate`, `submitted`,
  `type`, plus the `relatedApps` relationship.
- **Length limits — much tighter than they look:** `name` **<= 60**,
  `description` **<= 1000**, `notes` **<= 500**. Drafts of 67 / 2891 / 3607
  characters were all rejected. Write to the limit *first*; do not write a pitch
  and then try to cut it.
- `type` enum: `APP_LAUNCH` | `APP_ENHANCEMENTS` | `NEW_CONTENT`.
- `publishStartDate` must be a full **ISO 8601 date-time** (`2026-08-15T11:00:00Z`).
  A bare `2026-08-15` is rejected.
- `deviceFamilies` enum: `IPHONE` | `IPAD` | `APPLE_TV` | `APPLE_WATCH` | `MAC` |
  `VISION`. `locales` uses **UPPERCASE** codes — `EN-US`, not `en-US`.
- **Every PATCH must carry `submitted` or `archived`**, even when you are only
  changing an unrelated attribute, or it fails with
  `At least one of parameters 'submitted or archived' is required`.
- **`submitted: true` is the send button.** After it lands, the resource reports
  `state: SUBMITTED` and `submitted` reads back as `null` — that is normal, read
  **`state`**, not `submitted`.

> Apple wants nominations **well ahead** of the launch date. Submit the
> nomination as soon as the launch window is known; it does not have to wait for
> the binary to be approved.

→ Next: [Submission & review](app-store-submission.md)
