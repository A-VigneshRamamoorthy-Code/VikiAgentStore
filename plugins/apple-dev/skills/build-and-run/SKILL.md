---
name: build-and-run
description: >
  Guide for xcodebuild, CLI simulator launching, scheme configurations, UDID targeting, provisioning profiles, code signing, and CLI testing.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Build, run & install (verified)

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. Transparency verification
> requires a device — see [transparency.md](../transparency/SKILL.md).

---

Simulator: **Latest iPhone, latest iOS**, UDID `<SIM_UDID>`.
Bundle id `com.example.app`; App Group `group.com.example.app`
(the widget extension is `com.example.app.WidgetExtension`).

```bash
cd /path/to/project

# Build (app + widget extension)
xcodebuild -project com.example.app.xcodeproj -scheme com.example.app -configuration Debug \
  -destination 'platform=iOS Simulator,id=<SIM_UDID>' \
  -derivedDataPath DerivedData/App build

# Install + launch
xcrun simctl install  <SIM_UDID> \
  DerivedData/App/Build/Products/Debug-iphonesimulator/com.example.app
xcrun simctl launch   <SIM_UDID> com.example.app

# Toggle light/dark to test system theme (no rebuild needed)
xcrun simctl ui <SIM_UDID> appearance dark   # or light
```

Verification is visual in the simulator.

**Physical device (REQUIRED to verify host transparency — the sim cannot; see
[transparency.md](../transparency/SKILL.md)).** Device UDID `<DEVICE_UDID>`
(Test iPhone), team `YOUR_TEAM_ID`. One-time: open `com.example.app.xcodeproj` in Xcode
once with Automatic signing so the App Group capability is registered on the App ID
(the CLI `-allowProvisioningUpdates` won't create it). Then:

```bash
# Build (signed) + install + launch on device
xcodebuild -project com.example.app.xcodeproj -scheme com.example.app -configuration Debug \
  -destination 'platform=iOS,id=<DEVICE_UDID>' \
  -derivedDataPath DerivedData/AppDevice \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=YOUR_TEAM_ID build
xcrun devicectl device install app --device <DEVICE_UDID> \
  DerivedData/AppDevice/Build/Products/Debug-iphoneos/com.example.app
xcrun devicectl device process launch --device <DEVICE_UDID> com.example.app

# Read the host-transparency flags off the device (no debugger needed)
xcrun devicectl device copy from --device <DEVICE_UDID> \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.example.app \
  --source Library/Preferences/group.com.example.app.plist \
  --destination app_group.plist && plutil -p app_group.plist
```

## Permissions & App Capabilities

Specific features like Widgets, live data, or WeatherKit require proper capabilities and entitlements setup.

- **Usage strings** live where each target reads its Info.plist. The app often uses
  `GENERATE_INFOPLIST_FILE = YES`, meaning location and other privacy usage descriptions
  are build settings (`INFOPLIST_KEY_*`) in the project configuration. The widget extension typically uses its own Info.plist.
- **Capabilities (like EventKit + CoreLocation) often work on a free/personal team** — calendar events and location
  resolve on both sim and device with no paid membership.
- **Advanced Capabilities (like WeatherKit) may REQUIRE the PAID Apple Developer Program membership.** The
  capability entitlement must be live in both the app and the extension's `.entitlements` files.
- **WeatherKit DOES work on the Simulator** once the App ID is fully configured: the Simulator uses the **host Mac's** `weatherd`, so it does not need the app's provisioning profile. It reports the **Mac's** simulated location. A `Code=2` error means a real failure (like missing App Services configuration), not a Simulator limitation.
- **Location must be granted once before fetching weather or nearby data.**
  Ensure the app requests authorization when a relevant feature is accessed or a widget is added, before attempting to fetch real-world data.

### Entitlements and App Services Configuration

Some services, like WeatherKit or Push Notifications, live in **two separate places** on the App ID at developer.apple.com
(Certificates, Identifiers & Profiles -> Identifiers): the **App Capabilities** tab (which
`xcodebuild -allowProvisioningUpdates` sets for you, and which is what lands in the
provisioning profile) **and** the **App Services** tab, which authorises the App ID
server-side and which **nothing in the build ever touches**. Both are needed on **both**
the app **and** the widget extension.

### Verifying the build actually carries the entitlement

```bash
codesign -d --entitlements :- DerivedData/AppDevice/Build/Products/Debug-iphoneos/com.example.app
codesign -d --entitlements :- \
  DerivedData/AppDevice/Build/Products/Debug-iphoneos/com.example.app/PlugIns/WidgetExtension.appex
```

Check the output for the required capability. To confirm the *profile* carries it too:

```bash
security cms -D -i \
  DerivedData/AppDevice/Build/Products/Debug-iphoneos/com.example.app/PlugIns/WidgetExtension.appex/embedded.mobileprovision \
  | grep -A2 capability_name
```

### Debugging App Group Shared Data

To debug data shared between an app and its extension (like cached weather or settings), you can read the App Group UserDefaults directly:

```bash
xcrun devicectl device copy from --device <DEVICE_UDID> \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.example.app \
  --source Library/Preferences/group.com.example.app.plist \
  --destination app_group.plist && plutil -p app_group.plist
```

The same check works on the **Simulator**, where it is fully scriptable.

```bash
SIM=<SIM_UDID>
xcrun simctl launch $SIM com.example.app && sleep 5
xcrun simctl terminate $SIM com.example.app   # flush cfprefsd before reading
GC=$(xcrun simctl get_app_container $SIM com.example.app groups | awk '{print $2}')
plutil -p "$GC/Library/Preferences/group.com.example.app.plist"
```

Terminate the app before reading: the simulator's `cfprefsd` buffers writes, and editing
that plist from the host while the sim is booted is silently discarded.

## In-app purchases: run from the scheme, not `simctl`

Full StoreKit design/behavior lives in [in-app-purchases.md](../in-app-purchases/SKILL.md); the build/run
gotcha is that the StoreKit config (if used) is typically a **scheme run-action setting**, **not** baked into the `.app`:

- **Exercise a purchase** by running from Xcode with the corresponding scheme (Run / Cmd-R) — the local
  `.storekit` store applies and buy / cancel / restore / refund all work with **no paid team**. A
  plain `xcrun simctl launch` of the installed build (as above) does **not** apply it, so local StoreKit testing may fail.
- Real Apple purchase sheets + real products need a **paid** membership and App Store Connect records.

## Build configurations: Debug / Release / Internal

A typical iOS project defines different configurations:

- **Debug** — everyday development (`DEBUG` defined).
- **Release** — the **public App Store** build. Ships **no** debug/admin surface.
- **Internal** — **release-grade** (cloned from Release: same optimization, dSYM, signing)
  **plus** custom flags (e.g., `APP_INTERNAL`) set at the project-level so all targets inherit it.
  Use it for QA, TestFlight, and Ad-hoc builds where you want hidden admin/debug panels inside an otherwise production-like app.

Use compiler directives like `#if DEBUG || APP_INTERNAL` to gate debug panels, ensuring they are **fully compiled out of public Release**.

```bash
# Build any config (Debug | Release | Internal):
xcodebuild -project com.example.app.xcodeproj -scheme com.example.app -configuration Internal \
  -destination 'platform=iOS Simulator,id=<SIM_UDID>' \
  -derivedDataPath DerivedData/App build
```

**Internal builds can also ship live telemetry.** You might define `APP_ANALYTICS` in the app target's Internal config to include analytics SDKs, while omitting it from widget extensions to avoid double-counting users.

Build, install, and launch an Internal build on a **physical device** (useful to verify analytics/debug features):

```bash
xcodebuild -project com.example.app.xcodeproj -scheme "com.example.app (Internal)" \
  -configuration Internal -destination 'platform=iOS,id=<DEVICE_UDID>' \
  -derivedDataPath DerivedData/AppInternal -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=YOUR_TEAM_ID build
xcrun devicectl device install app --device <DEVICE_UDID> \
  DerivedData/AppInternal/Build/Products/Internal-iphoneos/com.example.app
# NOTE the `--` terminator, or devicectl misparses launch flags:
xcrun devicectl device process launch --device <DEVICE_UDID> --terminate-existing \
  com.example.app -- -FIRDebugEnabled
```

## Gotcha: the device must be UNLOCKED to launch

`xcrun devicectl device process launch …` fails on a **locked** phone with
`CoreDeviceError 10002` / `FBSOpenApplicationServiceErrorDomain … RequestDenied … Locked`.
The **install still succeeds** — just unlock the iPhone and re-run the launch (or tap the
app icon).
