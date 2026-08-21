---
name: app-store-release
description: >
  Guide for App Store release management, phased releases, App Review guidelines, version bumps, fastlane, and TestFlight distribution.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# App Store release — pipeline & provisioning

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. Listing copy, ASO and
> screenshots are in [app-store-listing.md](../app-store-listing/SKILL.md); privacy,
> IAP submission and review risks are in
> [app-store-submission.md](../app-store-submission/SKILL.md).
>
> Build/run for **development** is [build-and-run.md](../build-and-run/SKILL.md). This
> file is only about shipping to the **App Store**.

---

## 1. Verifying App State via App Store Connect API

You can inspect the state of your app record, bundle ID, team membership, builds, and in-app purchases directly against the App Store Connect API.

Ensure the following are prepared before submission:
- **App record**: Exists in App Store Connect with an Apple ID and SKU.
- **Bundle ID**: Registered and matches your Xcode project.
- **Team**: Paid Apple Developer membership is active.
- **Builds**: Ready to be uploaded, or check `/v1/builds` for processing status.
- **IAP**: Configured and `READY_TO_SUBMIT`.
- **Listing**: Subtitle, categories, keywords, description, screenshots, and privacy URL are populated.

---

## 2. The App Store Connect API client

`scripts/asc_api.swift` (if available in your project) is a dependency-free client: it mints an
ES256 JWT with CryptoKit and performs requests. It is the fastest way to
inspect or change anything in App Store Connect.

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
`AuthKey_<KEY_ID>.p8` **exactly once**; save it securely (e.g., `~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8`). It is a private key —
never commit it, and note that `.gitignore` does **not** typically cover `*.p8`.

### Two API quirks that will waste your time

- **`filter[bundleId]` on `/v1/apps` intermittently returns HTTP 500.** List
  everything and match client-side:
  ```bash
  .build/tools/asc_api GET "/v1/apps?limit=200" \
    | jq -r '.data[] | select(.attributes.bundleId=="com.example.app") | .id'
  ```
- **A `PATCH` can return `200` with `null` relationships even on success.**
  Never trust the response body; verify with a fresh `GET …?include=…`.

### Two things the API flatly refuses

| | |
|---|---|
| Creating the app record | `POST /v1/apps` → **403** `The resource 'apps' does not allow 'CREATE'` |
| App Privacy / data usages | `/v1/appDataUsages` → **404** `PATH_ERROR` |

Both are web-UI only. You must create the initial app record and fill out App Privacy via the App Store Connect web interface.

---

## 3. Signing

Unlike a hand-assembled bundle, signing is typically `xcodebuild`'s job. What matters:

- **Team**, must be a paid account. `-allowProvisioningUpdates` will create and
  refresh the App Store profiles for your App IDs (including extensions/widgets).
- **App Groups** must be registered on all relevant App IDs. The CLI cannot create a *new* capability automatically, so register them in Xcode first.
- **Capabilities/Services** (e.g., WeatherKit, Push Notifications) must be enabled in both the **App Capabilities** tab (in the portal/profile) **and** the **App Services** tab (server-side authorization).
- **In-App Purchase** needs no specific entitlement key in your `.entitlements` file; it comes automatically from the App ID capability in the portal.

---

## 4. Archive and export

Ship the **Release** configuration. Ensure debug menus, development analytics, or internal testing tools are excluded from the Release build.

```bash
cd /path/to/project

xcodebuild -project YourApp.xcodeproj -scheme YourApp \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath build/YourApp.xcarchive \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=YOUR_TEAM_ID \
  archive

xcodebuild -exportArchive -archivePath build/YourApp.xcarchive \
  -exportOptionsPlist packaging/ExportOptions.plist \
  -exportPath build/AppExport -allowProvisioningUpdates
```

*Note: Use local directories like `build/` instead of temporary system paths to preserve artifacts and avoid system cleanup issues.*

`ExportOptions.plist` (create it if missing):

```xml
<dict>
  <key>method</key>              <string>app-store-connect</string>
  <key>teamID</key>              <string>YOUR_TEAM_ID</string>
  <key>uploadSymbols</key>       <true/>
  <key>signingStyle</key>        <string>automatic</string>
</dict>
```

`uploadSymbols` matters: Crashlytics and Apple's own crash reports are
useless without dSYMs, especially for extension binaries.

### Verify the archive before uploading

```bash
APP="build/YourApp.xcarchive/Products/Applications/YourApp.app"

# 1. Ensure internal admin panels or debug code are NOT in the public Release build.
strings "$APP/YourApp" | grep -i "DebugPanel"        # must be 0

# 2. Check entitlements are correctly applied to the app (and any extensions).
codesign -d --entitlements :- "$APP"
# codesign -d --entitlements :- "$APP/PlugIns/YourAppExtension.appex"

# 3. Ensure extensions (like widgets) are actually embedded.
ls "$APP/PlugIns"
```

Verify that debug configurations are not accidentally shipped, as this could expose internal features or logic to users, leading to rejection.

---

## 5. Versioning

- `CURRENT_PROJECT_VERSION` (build number) must **strictly increase on every
  upload**, including uploads that later fail processing. Apple burns the
  number regardless.
- `MARKETING_VERSION` only changes when you ship a new store version.
- Both typically live in the hand-authored `project.pbxproj`, so bump them there (or pass
  them on the `xcodebuild` command line).

---

## 6. Upload

```bash
xcrun altool --validate-app -f build/AppExport/YourApp.ipa -t ios \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"

xcrun altool --upload-app  -f build/AppExport/YourApp.ipa -t ios \
  --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
```

Always validate first — it catches missing icons, bad entitlements and
profile mismatches in seconds rather than after a 30-minute processing wait.

### Watching it process

```bash
APP_APPLE_ID=1234567890
.build/tools/asc_api GET "/v1/builds?filter[app]=$APP_APPLE_ID&limit=5" \
  | jq -r '.data[] | "\(.attributes.version) \(.attributes.processingState)"'
```

Wait for `processingState: VALID`. Processing takes 5–30 minutes.

**A package can upload cleanly and still fail processing minutes later, in
which case it never becomes a build at all** — `/v1/builds` stays empty and
nothing explains why. Those failures appear only here:

```bash
.build/tools/asc_api GET "/v1/apps/$APP_APPLE_ID/buildUploads?limit=10" \
  | jq -r '.data[] | "\(.attributes.cfBundleShortVersionString) (\(.attributes.cfBundleVersion)) \(.attributes.state.state)",
           (.attributes.state.errors[]? | "  ✗ \(.code): \(.description)")'
```

Check this **first** whenever "the upload worked but there is no build".

---

## 7. Export compliance — do this once, now

If there is no `ITSAppUsesNonExemptEncryption` key in your project, every single upload parks the build behind a manual "Export Compliance" question in App Store Connect and blocks submission until acknowledged.

If the app uses only standard HTTPS and the iOS Keychain, it is exempt. If the app uses `GENERATE_INFOPLIST_FILE`, add it as a build setting in `project.pbxproj` for **both** the app and extensions:

```
INFOPLIST_KEY_ITSAppUsesNonExemptEncryption = NO
```

Alternatively, add the boolean key `ITSAppUsesNonExemptEncryption` set to `NO` in your `Info.plist`.

---

## 8. One-shot runbook

```bash
export ASC_KEY_ID=... ASC_ISSUER_ID=...
swiftc -O scripts/asc_api.swift -o .build/tools/asc_api

# build
xcodebuild … archive && xcodebuild -exportArchive …
xcrun altool --validate-app -f build/AppExport/YourApp.ipa -t ios --apiKey … --apiIssuer …
xcrun altool --upload-app  -f build/AppExport/YourApp.ipa -t ios --apiKey … --apiIssuer …

# then, in order
#  1. listing copy + categories + screenshots  → app-store-listing.md
#  2. App Privacy (web UI, Save AND Publish)   → app-store-submission.md
#  3. attach the build + IAPs, submit          → app-store-submission.md
```

**Shipping a Mac build from the same record?** Run the Guideline 4 window sweep first —
a closed main window must be reopenable from the Window menu — and remember the two
platforms have **independent** versions and submissions, so never push a one-platform
metadata change with a script that walks both. → [macos-app.md](../macos-app/SKILL.md)

→ Next: [Listing & ASO](../app-store-listing/SKILL.md) ·
[Submission & review](../app-store-submission/SKILL.md)
