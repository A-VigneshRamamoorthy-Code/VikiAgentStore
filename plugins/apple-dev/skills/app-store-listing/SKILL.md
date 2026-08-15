---
name: app-store-listing
description: >
  Guide for App Store Connect metadata and ASO: what Apple actually indexes (name, subtitle, the 100-char keyword field) versus what it does not (description, promotional text), keyword budgeting and accuracy, categories, promo text, pricing and featuring nominations. Covers the request to rank for a competitor's name — why trademarked terms in metadata breach Guideline 2.3.7 and why Apple Search Ads is the only compliant route — plus Custom Product Pages and the paid-app conversion trap.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# App Store listing — metadata, ASO & screenshots

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. Pipeline and signing are
> in [app-store-release.md](../app-store-release/SKILL.md); privacy, IAP and review risk
> are in [app-store-submission.md](../app-store-submission/SKILL.md).

---

## 1. How App Store search actually works

Two rules drive every decision below.

1. **Apple indexes the union of `name` + `subtitle` + `keywords`.** Repeating a
   word across those three fields buys nothing — it wastes characters. Apple
   recombines the union into phrases on its own, so `cloud` in the name plus
   `player` in the subtitle already matches "cloud player".
2. **The description is _not_ indexed** for App Store search. It exists to
   convert someone already on the page (and it does feed Google, which indexes
   the web listing).

So: zero duplication across the three indexed fields, and write the description
for humans.

### What is and is not indexed

| Indexed | Weight | Not indexed |
|---|---|---|
| App name | highest | **Description** |
| Subtitle | second | **Promotional text** |
| Keyword field (100) | third | What's New |
| IAP / subscription display names | exact-match | Review notes |
| In-app event titles, seller name | low | Screenshot *images* |

Two consequences people get wrong:

- **Promotional text is not indexed either.** It is a conversion and
  announcement tool, not an ASO one. Stuffing keywords there is pure waste.
- **The subtitle is the second-heaviest field**, so it is usually worth more as
  keyword real estate than as a slogan. Moving two high-volume terms into the
  subtitle frees ~10 characters in the keyword field *and* upgrades their
  weight. Write the emotional pitch in the promo text, which humans actually
  read.

> Screenshot **OCR** is widely believed by ASO agencies to contribute a little.
> Apple has never confirmed it. Do not spend design decisions on it.

### Budgeting the three fields

Compute this, do not eyeball it — the failure mode is silent wasted characters:

```python
import re
covered = set(re.findall(r"[a-z0-9]+", (name + " " + subtitle).lower()))
assert not (covered & set(keywords.split(","))), "keyword already in name/subtitle"
assert len(keywords) <= 100 and " " not in keywords
```

Then sanity-check the phrases the union can actually form ("cloud music player",
"offline mp3 player", …) rather than admiring the word list.

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

## 3. Category Strategy

Select primary and secondary categories based on the live store competition. Category feeds Apple's *recommendation* engine as
well as search, so being in the wrong one costs "you might also like"
placement next to every competitor.

```bash
.build/tools/asc_api PATCH "/v1/appInfos/<appInfoId>" '{
  "data":{"type":"appInfos","id":"<appInfoId>",
    "relationships":{
      "primaryCategory":{"data":{"type":"appCategories","id":"GRAPHICS_AND_DESIGN"}},
      "secondaryCategory":{"data":{"type":"appCategories","id":"UTILITIES"}}}}}'
```

PATCH echoes `null` relationships even on success — verify with
`GET /v1/appInfos/<id>?include=primaryCategory,secondaryCategory`.

## 4. Copy and Keyword Rules

- **Zero duplication:** Do not repeat a word already in the name or subtitle within your keywords.
- **Never name a competitor.** See §4a — it is the most-requested and most
  dangerous ASO change there is.
- **Do not claim what the app does not do.** Irrelevant keywords rank for queries the app cannot satisfy — bad for conversion and a
  Guideline 2.3.7 accuracy risk.
- **Singular only.** Apple handles plurals; `widget` covers `widgets`.
- **Absolute claims:** Be careful with absolute claims in your description (e.g., "Nothing leaves your device"). If you use analytics or crash reporting, you contradict yourself and risk a 5.1.1 or 2.3.7 rejection. Scope claims accurately.
- **Free-tier honesty:** Apple rejects listings that read as free when the useful part is gated. Disclose subscription caps or trial behaviors upfront (Guideline 3.1.2(c)). Do not make premium sound like unlocking baseline usability unless accurately described.

### Audit every keyword against the code, not against the pitch

An inaccurate keyword is *itself* a 2.3.7 violation, and the words that get
added by reflex are usually the ones the app does not have. Before shipping a
keyword list, grep for each term and delete the ones with no implementation:

```bash
rg -i "equalizer|crossfade|gapless|playlist" Sources/   # no hits ⇒ no keyword
```

Typical casualties: `equalizer`, `playlist`, `gapless`, `crossfade`, `widget`,
`carplay`, `airplay`. Also drop terms that are *technically* true but mislead —
a player that parses `.m4b` but never resumes position is not an `audiobook`
app.

**A trademark you genuinely integrate with is fine**, and this is the one
exception worth stating plainly: `dropbox`, `onedrive`, `google` and `drive` may
appear when the app really does connect to them. That is nominative use — it
describes the integration rather than trading on the brand. Put a line in the
review notes saying so, naming the keyword field explicitly, so a reviewer never
has to guess:

> *"We are an independent third-party client built on <vendor>'s public API, not
> affiliated with or endorsed by them. The vendor name appears in the keyword
> field solely to describe an integration the app actually ships."*

## 4a. ⛔️ Ranking for a competitor's name

**The request:** "when someone searches Spotify / Notion / Uber, we should show
up." It arrives on nearly every app. The metadata answer is always no.

**Guideline 2.3.7:** *"Choose a unique app name, assign keywords that accurately
describe your app, and don't try to pack any of your metadata with trademarked
terms, popular app names, pricing information, or other irrelevant phrases just
to game the system."* **Guideline 5.2.1** covers the IP side.

- It applies to the **hidden 100-character keyword field** as well. Users cannot
  see it; Apple scans it.
- Consequences escalate: metadata rejection at review, then — post-launch — an
  IP complaint through Apple's dispute portal that can hide or pull the listing,
  and repeat offences put the developer account at risk.

**The permitted route is Apple Search Ads.** You may bid on a rival's brand as
an ad keyword; you may not print it anywhere.

| Allowed | Not allowed |
|---|---|
| Bidding on `spotify` as a Search Ads keyword | `spotify` in name, subtitle or keyword field |
| Naming your own real integrations | "Better than Spotify" in the creative or copy |
| Generic category terms with real volume | A competitor's logo in a screenshot |

Two economics warnings before anyone budgets for it:

1. **Expect a poor Relevance Score** against the brand owner's own defensive
   bids, which means a materially higher cost per tap.
2. **Conversion rate is a heavy organic ranking factor.** Shoppers who searched
   a free rival, land on a paid app and bounce actively teach Apple to demote
   the listing. Cheap irrelevant traffic is worse than none.

Mitigate with **Custom Product Pages** (up to 35, each with its own screenshots
and its own ASA ad group), so a shopper who searched a rival lands on the frame
that answers *that* query instead of the generic first screenshot.

### Optional: a second localisation doubles the indexed keywords

A storefront indexes more than one locale's keyword field. The long-standing
example is that **English (US)** shoppers also match the **Spanish (Mexico)**
field, so a second localisation is worth roughly another 100 indexed characters
for the same storefront.

Caveats to state before doing it:

- It is **ASO-agency consensus, not documented Apple behaviour**. Measure it.
- Screenshots are **per-localisation**. Adding a locale with no screenshot set
  is a real listing regression, so budget the upload too.
- The visible text should still be genuinely localised. Only the invisible
  keyword field carries the extra English terms.

## 5. Screenshots

### Which sets are actually required

Check your app's `TARGETED_DEVICE_FAMILY` in `project.pbxproj` (e.g., `"1"` for iPhone only, `"1,2"` for iPhone and iPad). 

The API's own enum is authoritative (it is returned verbatim in the error when you send an invalid value):

```
APP_IPHONE_67   APP_IPHONE_65   APP_IPHONE_61   APP_IPHONE_58   …
APP_IPAD_PRO_3GEN_129   APP_IPAD_PRO_129   APP_IPAD_PRO_3GEN_11   …
APP_DESKTOP   APP_APPLE_VISION_PRO   APP_WATCH_*   IMESSAGE_APP_*
```

Note there is **no `APP_IPHONE_69` and no `APP_IPAD_13`** — the API still buckets the newest 6.9" iPhone under **`APP_IPHONE_67`** and the 13" iPad under **`APP_IPAD_PRO_3GEN_129`**. Upload the modern master sizes into those largest sets and let Apple scale.

Requirements: PNG or JPEG, **no alpha channel**, no rounded corners, exact pixel dimensions, 1–10 per set. A wrong dimension is not rejected at upload — it surfaces later in `assetDeliveryState.errors`, so always verify.

### Capture automation traps

When capturing via Simulator automation or UI tests:
- **Simulator limitations:** Some system frameworks (e.g., certain Camera setups or complex widget transparency hooks) fail to render accurately on Simulator. Capture these hero shots on a physical device to ensure the real product is shown.
- **Placeholder data:** Ensure dynamic data views (weather, calendars, empty states) show realistic data instead of deterministic placeholders. Shipping a screenshot of a "Placeholder" view is unprofessional and advertises fake data. Ensure mandatory attributions (e.g., WeatherKit) are visible.

### Uploading via API

Apple's asset flow is three steps per file: reserve, PUT the bytes, commit with an MD5.

```bash
# 1. reserve — returns signed uploadOperations, each covering a byte range
.build/tools/asc_api POST "/v1/appScreenshots"   '{"data":{"type":"appScreenshots",
    "attributes":{"fileName":"01-home.png","fileSize":123456},
    "relationships":{"appScreenshotSet":{"data":{"type":"appScreenshotSets","id":"<setId>"}}}}}'

# 2. PUT each range with the headers Apple supplied  (curl --data-binary)

# 3. commit
.build/tools/asc_api PATCH "/v1/appScreenshots/<id>"   '{"data":{"type":"appScreenshots","id":"<id>",
    "attributes":{"uploaded":true,"sourceFileChecksum":"<md5>"}}}'
```

**Always verify** — every row must read `COMPLETE` with an empty `errors` array. `UPLOAD_COMPLETE` means Apple has the bytes but has not finished validating; wait and re-check.

## 6. App Preview videos

App Preview videos follow the same reserve/PUT/commit flow via `/v1/appPreviews`. Keep them concise and focused on UI interaction rather than marketing fluff.

## 7. Promotional text

170 characters, editable **at any time without a new build or a review**. Use it for launch news, updates, and seasonal hooks instead of burning a version description update.

## 8. App-level fields — what the API can and cannot set

**Age rating** is `PATCH /v1/ageRatingDeclarations/<appInfoId>` — note the id is the **appInfo id**, not a separate one. **It is UPDATE-only**: a `GET` on the instance is a `403 FORBIDDEN_ERROR`. Three API traps:
- **`ageAssurance` attribute is REQUIRED**, and it is a **BOOLEAN**.
- **`socialMediaAgeRestricted` is a NEW question**. It defaults to `null` (unanswered) — set it explicitly to `true` or `false`.
- Content questions are a **mix of types**: enums (`"NONE"` / `"INFREQUENT_OR_MILD"`) for things like `violenceRealistic`, but plain booleans for `gambling`, `advertising`, `userGeneratedContent`, etc. Fix them one at a time based on the API error message.

### The four "Unable to Add for Review" blockers

None of these live on the version localization, so a fully populated listing can still be blocked by all four.

| Blocker text in ASC | Where it actually lives |
|---|---|
| "You must provide copyright information" | `PATCH /v1/appStoreVersions/<versionId>` → `attributes.copyright` |
| "You must set up Content Rights Information in App Information" | `PATCH /v1/apps/<appId>` → `attributes.contentRightsDeclaration` |
| "You must choose a price tier in Pricing" | `POST /v1/appPriceSchedules` — see below |
| "an Admin must provide information about the app's privacy practices" | **ASC web UI only** (`appDataUsages` is 404 to API keys) |

**`copyright` is a plain string with NO `©` symbol** — Apple renders the symbol.
Format: *year the rights were obtained* + *rights holder*. For individual Developer Program accounts, the rights holder is the person's name, not a company name.

**`contentRightsDeclaration`** is `DOES_NOT_USE_THIRD_PARTY_CONTENT` | `USES_THIRD_PARTY_CONTENT`. Ensure declarations reflect bundled fonts, code, or third-party licensed art.

### Pricing API — create a schedule, don't PATCH one

`appPriceSchedules` is **create-only** — you `POST` a whole new schedule and it replaces the old one. Do not try to PATCH the existing empty schedule.

```bash
# 1. find the base price point for the BASE territory (e.g., customerPrice "0.0")
asc_api GET '/v1/apps/<appId>/appPricePoints?filter[territory]=USA&limit=200'

# 2. POST the schedule. The inline appPrice needs a LOCAL id of the form ${price1}
asc_api POST /v1/appPriceSchedules '{
  "data": {"type":"appPriceSchedules","relationships":{
    "app":          {"data":{"type":"apps","id":"<appId>"}},
    "baseTerritory":{"data":{"type":"territories","id":"USA"}},
    "manualPrices": {"data":[{"type":"appPrices","id":"${price1}"}]}}},
  "included": [{"type":"appPrices","id":"${price1}","relationships":{
    "appPricePoint":{"data":{"type":"appPricePoints","id":"<free point id>"}}}}]}'
```

Omit `startDate` / `endDate` and the price applies immediately and forever. Apple then **auto-equalizes** the other storefronts. Verify both counts: a schedule with a manual price and zero automatic ones means the equalization did not run.

> Unlike subscription price points, auto-equalization is usually the right answer for the base app price (especially if the app is free), so there is no tier misalignment to get wrong.

**UI Only:** Territory availability and App Privacy declarations must be handled in the ASC web UI.

## 9. Featuring nomination — the undocumented `/v1/nominations` API

A **nomination** pitches the app to Apple's **editorial** team for a feature on the App Store. It is a separate submission, does not gate release, and can be submitted while `PREPARE_FOR_SUBMISSION`.

**It is not discoverable.** `nominations` does **not** appear in the app's relationship list. `GET /v1/nominations` returns a **400** (not 404) because it requires filters.

### The schema, learned entirely from rejection messages

```
GET    /v1/nominations?filter[state]=DRAFT|SUBMITTED|ARCHIVED
POST   /v1/nominations
PATCH  /v1/nominations/<id>
```

- **`filter[state]` is REQUIRED on the list call.** A bare `GET` is a 400.
- **Required on POST:** `name`, `description`, `publishStartDate`, `submitted`, `type`, plus the `relatedApps` relationship.
- **Length limits are strict:** `name` **<= 60**, `description` **<= 1000**, `notes` **<= 500**. Write to the limit first.
- `type` enum: `APP_LAUNCH` | `APP_ENHANCEMENTS` | `NEW_CONTENT`.
- `publishStartDate` must be a full **ISO 8601 date-time** (e.g., `2024-01-01T11:00:00Z`).
- `deviceFamilies` enum: `IPHONE` | `IPAD` | `APPLE_TV` | `APPLE_WATCH` | `MAC` | `VISION`. 
- `locales` uses **UPPERCASE** codes — `EN-US`, not `en-US`.
- **Every PATCH must carry `submitted` or `archived`**.
- **`submitted: true` is the send button.** After it lands, the resource reports `state: SUBMITTED` and `submitted` reads back as `null`. Read the `state`, not `submitted`.

> Apple wants nominations **well ahead** of the launch date. Submit the nomination as soon as the launch window is known; it does not have to wait for the binary to be approved.

→ Next: [Submission & review](../app-store-submission/SKILL.md)
