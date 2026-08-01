---
name: app-store-release
description: >
  Apple development skill for App Store release — pipeline & provisioning. Use this skill when working on app-store-release tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# App Store release — pipeline & provisioning

> Part of the **[Leap Agent Guide](../../agents.md)**. Listing copy, ASO and
> screenshots are in [app-store-listing.md](app-store-listing.md); privacy,
> IAP submission and review risks are in
> [app-store-submission.md](app-store-submission.md).
>
> Build/run for **development** is [build-and-run.md](build-and-run.md). This
> file is only about shipping to the **App Store**.

---

## Where Leap actually stands (verified against the live API)

| | |
|---|---|
| App record | **exists** — "Leap Widgets", Apple ID `6796248408`, SKU `LEAPWIDGETS2026` |
| Bundle id | `com.sololeap.leap.app` (extension `…​.LeapWidget`) |
| Team | `D2Z89UU4R7` — **paid membership is active** |
| Version | `1.0`, platform `IOS`, state `PREPARE_FOR_SUBMISSION` |
| Builds | **none uploaded** — `/v1/builds` and `/v1/buildUploads` are both empty |
| IAP | 2 non-consumables + 1 subscription, all `READY_TO_SUBMIT` |
| Price schedule | set |
| Territories | **not set** |
| Listing | name only — **no** subtitle, categories, keywords, description, screenshots, privacy URL |

So the account side is done and the **content** side is almost entirely
untouched. The gating list is in
[app-store-submission.md](app-store-submission.md#0-blockers-before-any-submission).

> **Stale doc note:** §2 of [in-app-purchases.md](in-app-purchases.md) says the
> team "appears to be a free/personal team". That is out of date —
> [build-and-run.md](build-and-run.md) records WeatherKit live on the paid team,
> and real IAP records exist in App Store Connect.

---

## 1. The App Store Connect API client

`scripts/asc_api.swift` is a ~100-line, dependency-free client: it mints an
ES256 JWT with CryptoKit and performs one request. It is the fastest way to
inspect or change anything in App Store Connect, and it is how every fact in
the table above was verified.

```bash
swiftc -O scripts/asc_api.swift -o .build/tools/asc_api   # .build/ is gitignored

export ASC_KEY_ID=XXXXXXXXXX                              # the key row in ASC
export ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx # above the key table

.build/tools/asc_api GET    "/v1/apps?limit=200"
.build/tools/asc_api POST   "/v1/appScreenshots" '{"data":{…}}'
.build/tools/asc_api PATCH  "/v1/appStoreVersionLocalizations/<id>" '{"data":{…}}'
.build/tools/asc_api DELETE "/v1/appScreenshots/<id>"
```

The key itself: **Users and Access → Integrations → App Store Connect API**,
role **Admin** (App Manager cannot issue certificates). Apple lets you download
`AuthKey_<KEY_ID>.p8` **exactly once**; save it to
`~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`. It is a private key —
never commit it, and note that `.gitignore` does **not** currently cover `*.p8`.

### Two API quirks that will waste your time

- **`filter[bundleId]` on `/v1/apps` intermittently returns HTTP 500.** List
  everything and match client-side:
  ```bash
  .build/tools/asc_api GET "/v1/apps?limit=200" \
    | jq -r '.data[] | select(.attributes.bundleId=="com.sololeap.leap.app") | .id'
  ```
- **A `PATCH` can return `200` with `null` relationships even on success.**
  Never trust the response body; verify with a fresh `GET …?include=…`.

### Two things the API flatly refuses

| | |
|---|---|
| Creating the app record | `POST /v1/apps` → **403** `The resource 'apps' does not allow 'CREATE'` |
| App Privacy / data usages | `/v1/appDataUsages` → **404** `PATH_ERROR` |

Both are web-UI only. Leap's app record already exists; App Privacy does not —
see [app-store-submission.md](app-store-submission.md#1-app-privacy).

---

## 2. Signing

Unlike a hand-assembled bundle, Leap has a real Xcode project, so signing is
`xcodebuild`'s job. What matters:

- **Team `D2Z89UU4R7`**, paid. `-allowProvisioningUpdates` will create and
  refresh the App Store profiles for **both** App IDs
  (`com.sololeap.leap.app` and `com.sololeap.leap.app.LeapWidget`).
- **App Group** `group.com.sololeap.leap.app` must be on both App IDs. It was
  registered by opening the project in Xcode.app once with Automatic signing —
  the CLI cannot create a *new* capability
  ([build-and-run.md](build-and-run.md)).
- **WeatherKit must be ticked in two separate places** on both App IDs: the
  **App Capabilities** tab (what `-allowProvisioningUpdates` sets, and what
  lands in the profile) **and** the **App Services** tab (server-side
  authorisation, which nothing in the build ever touches). Miss the second and
  every weather face silently renders the placeholder — see
  [weatherkit.md](weatherkit.md).
- **In-App Purchase needs no entitlement key.** It comes from the App ID
  capability. Do not add a StoreKit key to `Leap.entitlements`.

---

## 3. Archive and export

Ship the **Release** configuration. `Internal` carries `LEAP_INTERNAL` (the
shake-to-open admin panel) **and** `LEAP_ANALYTICS`; `Debug` links app code
through `Leap.debug.dylib`. Neither is shippable — see
"Build configurations" in [build-and-run.md](build-and-run.md).

```bash
cd /Users/vignesh/Code/Leap

xcodebuild -project Leap.xcodeproj -scheme Leap \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath /tmp/Leap.xcarchive \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=D2Z89UU4R7 \
  archive

xcodebuild -exportArchive -archivePath /tmp/Leap.xcarchive \
  -exportOptionsPlist packaging/ExportOptions.plist \
  -exportPath /tmp/LeapExport -allowProvisioningUpdates
```

`ExportOptions.plist` (create it; there is no `packaging/` directory yet):

```xml
<dict>
  <key>method</key>              <string>app-store-connect</string>
  <key>teamID</key>              <string>D2Z89UU4R7</string>
  <key>uploadSymbols</key>       <true/>
  <key>signingStyle</key>        <string>automatic</string>
</dict>
```

`uploadSymbols` matters: Firebase Crashlytics and Apple's own crash reports are
useless without dSYMs, and the widget extension is a separate binary.

### Verify the archive before uploading

```bash
APP=/tmp/Leap.xcarchive/Products/Applications/Leap.app

# 1. The admin panel must NOT be in a public Release build.
#    (Scan the fully linked binary — Debug hides app code in Leap.debug.dylib.)
strings "$APP/Leap" | grep -c "LeapDebugPanelView"        # must be 0

# 2. Both binaries must carry the WeatherKit entitlement.
codesign -d --entitlements :- "$APP"
codesign -d --entitlements :- "$APP/PlugIns/LeapWidgetExtension.appex"

# 3. The extension must actually be embedded.
ls "$APP/PlugIns"
```

Check 1 is the important one. `LEAP_INTERNAL` is set at the **project level**
on the Internal config, so a mis-selected configuration silently ships a
debug panel that can toggle the user's plan — an obvious rejection and a
revenue hole.

---

## 4. Versioning

`MARKETING_VERSION = 1.0`, `CURRENT_PROJECT_VERSION = 2` today.

- `CURRENT_PROJECT_VERSION` (build number) must **strictly increase on every
  upload**, including uploads that later fail processing. Apple burns the
  number regardless.
- `MARKETING_VERSION` only changes when you ship a new store version.
- Both live in the hand-authored `project.pbxproj`, so bump them there (or pass
  them on the `xcodebuild` command line) — there is no `agvtool`-friendly
  Info.plist.

---

## 5. Upload

```bash
xcrun altool --validate-app -f /tmp/LeapExport/Leap.ipa -t ios \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"

xcrun altool --upload-app  -f /tmp/LeapExport/Leap.ipa -t ios \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
```

Always validate first — it catches missing icons, bad entitlements and
profile mismatches in seconds rather than after a 30-minute processing wait.

### Watching it process

```bash
A=6796248408
.build/tools/asc_api GET "/v1/builds?filter[app]=$A&limit=5" \
  | jq -r '.data[] | "\(.attributes.version) \(.attributes.processingState)"'
```

Wait for `processingState: VALID`. Processing takes 5–30 minutes.

**A package can upload cleanly and still fail processing minutes later, in
which case it never becomes a build at all** — `/v1/builds` stays empty and
nothing explains why. Those failures appear only here:

```bash
.build/tools/asc_api GET "/v1/apps/$A/buildUploads?limit=10" \
  | jq -r '.data[] | "\(.attributes.cfBundleShortVersionString) (\(.attributes.cfBundleVersion)) \(.attributes.state.state)",
           (.attributes.state.errors[]? | "  ✗ \(.code): \(.description)")'
```

Check this **first** whenever "the upload worked but there is no build".

---

## 6. Export compliance — do this once, now

There is **no `ITSAppUsesNonExemptEncryption` key anywhere in the project**
(verified: 0 hits in `project.pbxproj` and both `GoogleService-Info*.plist`).
Without it, every single upload parks the build behind a manual "Export
Compliance" question in App Store Connect and blocks submission until someone
clicks through it.

Leap uses only standard HTTPS (Firebase, WeatherKit) and the iOS Keychain,
which is exempt. The app uses `GENERATE_INFOPLIST_FILE`, so add it as a build
setting in `project.pbxproj` for **both** the app and the widget extension:

```
INFOPLIST_KEY_ITSAppUsesNonExemptEncryption = NO
```

---

## 7. One-shot runbook

```bash
export ASC_KEY_ID=... ASC_ISSUER_ID=...
swiftc -O scripts/asc_api.swift -o .build/tools/asc_api

# build
xcodebuild … archive && xcodebuild -exportArchive …
xcrun altool --validate-app -f /tmp/LeapExport/Leap.ipa -t ios --apiKey … --apiIssuer …
xcrun altool --upload-app  -f /tmp/LeapExport/Leap.ipa -t ios --apiKey … --apiIssuer …

# then, in order
#  1. listing copy + categories + screenshots  → app-store-listing.md
#  2. App Privacy (web UI, Save AND Publish)   → app-store-submission.md
#  3. attach the build + the 3 IAPs, submit    → app-store-submission.md
```

→ Next: [Listing & ASO](app-store-listing.md) ·
[Submission & review](app-store-submission.md)
