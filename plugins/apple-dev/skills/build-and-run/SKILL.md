---
name: build-and-run
description: >
  Apple development skill for Build, run & install (verified). Use this skill when working on build-and-run tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Build, run & install (verified)

> Part of the **[Leap Agent Guide](../../agents.md)**. Transparency verification
> requires a device — see [transparency.md](transparency.md).

---

Simulator: **iPhone 17 Pro, iOS 26.5**, UDID `D95D5EEF-A4E4-41B1-976B-52635F7305C7`.
Bundle id `com.sololeap.leap.app`; App Group `group.com.sololeap.leap.app`
(the widget extension is `com.sololeap.leap.app.LeapWidget`).

```bash
cd /Users/vignesh/Code/Leap

# Build (app + widget extension)
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Debug \
  -destination 'platform=iOS Simulator,id=D95D5EEF-A4E4-41B1-976B-52635F7305C7' \
  -derivedDataPath /tmp/LeapDerivedData build

# Install + launch
xcrun simctl install  D95D5EEF-A4E4-41B1-976B-52635F7305C7 \
  /tmp/LeapDerivedData/Build/Products/Debug-iphonesimulator/Leap.app
xcrun simctl launch   D95D5EEF-A4E4-41B1-976B-52635F7305C7 com.sololeap.leap.app

# Toggle light/dark to test system theme (no rebuild needed)
xcrun simctl ui D95D5EEF-A4E4-41B1-976B-52635F7305C7 appearance dark   # or light
```

There is no separate unit-test suite; verification is visual in the simulator
(screenshots in `examples/proofs/`).

**Physical device (REQUIRED to verify host transparency — the sim cannot; see
[transparency.md](transparency.md)).** Device UDID `00008150-0014746214F2401C`
(Viki's iPhone), team `D2Z89UU4R7`. One-time: open `Leap.xcodeproj` in Xcode.app
once with Automatic signing so the App Group capability is registered on the App ID
(the CLI `-allowProvisioningUpdates` won't create it). Then:

```bash
# Build (signed) + install + launch on device
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Debug \
  -destination 'platform=iOS,id=00008150-0014746214F2401C' \
  -derivedDataPath /tmp/LeapDeviceBuild \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=D2Z89UU4R7 build
xcrun devicectl device install app --device 00008150-0014746214F2401C \
  /tmp/LeapDeviceBuild/Build/Products/Debug-iphoneos/Leap.app
xcrun devicectl device process launch --device 00008150-0014746214F2401C com.sololeap.leap.app

# Read the host-transparency flags off the device (no debugger needed)
xcrun devicectl device copy from --device 00008150-0014746214F2401C \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.sololeap.leap.app \
  --source Library/Preferences/group.com.sololeap.leap.app.plist \
  --destination /tmp/leap_group.plist && plutil -p /tmp/leap_group.plist
```

## Live-data permissions & WeatherKit signing

The Calendar + Weather widgets use real data (see "Live widget data" in
[architecture.md](architecture.md)). Signing/plist facts:

- **Usage strings** live where each target reads its Info.plist. The **app** uses
  `GENERATE_INFOPLIST_FILE = YES`, so `NSLocationWhenInUseUsageDescription` /
  `NSCalendarsFullAccessUsageDescription` / `NSCalendarsUsageDescription` are
  `INFOPLIST_KEY_*` build settings in `project.pbxproj` (**both** Debug + Release app
  blocks); the **widget** has a real `LeapWidget/Info.plist` with the two calendar keys.
- **EventKit + CoreLocation work on a free/personal team** — calendar events and location
  resolve on both sim and device with no paid membership.
- **WeatherKit is ENABLED and requires the PAID Apple Developer Program membership.** The
  `com.apple.developer.weatherkit` entitlement is live in both `Leap/Leap.entitlements`
  and `LeapWidget/LeapWidget.entitlements`. On the paid team (`D2Z89UU4R7`) a device build
  signs cleanly and `-allowProvisioningUpdates` registers the **capability** on both App
  IDs by itself — the old free-team failure (*"Personal development teams ... do not
  support the WeatherKit capability"*) is gone, and no Xcode.app step is needed.
- **WeatherKit DOES work on the Simulator** once the App ID is fully configured (see
  below): the Simulator uses the **host Mac's** `weatherd`, so it does not need the app's
  provisioning profile. It reports the **Mac's** simulated location, so the numbers will
  not match a phone next to you, but a `Code=2` there is a **real** failure worth
  debugging - not an expected Simulator limitation.
- **Weather never refreshes until Location has been granted once.**
  `LeapViewModel.refreshLiveDataIfAuthorized()` gates on
  `LeapWeatherService.shared.isAuthorized`, so while CoreLocation is `notDetermined` a
  plain launch fetches nothing. The prompt only appears when the user **adds a weather
  widget** (`AddWidgetSheet.save()` -> `requestLiveDataAccess(for:)`). Do that once on the
  test device before expecting live values.

### The entitlement alone does NOT make WeatherKit return data

WeatherKit lives in **two separate places** on the App ID at developer.apple.com
(Certificates, Identifiers & Profiles -> Identifiers): the **App Capabilities** tab (which
`xcodebuild -allowProvisioningUpdates` sets for you, and which is what lands in the
provisioning profile) **and** the **App Services** tab, which authorises the App ID
server-side and which **nothing in the build ever touches**. Both are needed, on **both**
`com.sololeap.leap.app` **and** `com.sololeap.leap.app.LeapWidget`. Until App Services is
ticked — and for up to ~30 min afterwards while it propagates — the fetch throws:

```
Error Domain=WeatherDaemon.WDSJWTAuthenticatorServiceListener.Errors Code=2
```

and every weather face silently falls back to the placeholder. **See
[weatherkit.md](weatherkit.md) for the full picture** — how `weatherd` mints the JWT, what
the Simulator can and cannot prove, the mandatory Apple Weather attribution (and how Leap
ships it), the AQI / Celsius-rounding data traps, and the complete pitfall table.

### Verifying the build actually carries the entitlement

```bash
codesign -d --entitlements :- /tmp/LeapDeviceBuild/Build/Products/Debug-iphoneos/Leap.app
codesign -d --entitlements :- \
  /tmp/LeapDeviceBuild/Build/Products/Debug-iphoneos/Leap.app/PlugIns/LeapWidgetExtension.appex
```

Both must print `com.apple.developer.weatherkit`. To confirm the *profile* carries it too:

```bash
security cms -D -i \
  /tmp/LeapDeviceBuild/Build/Products/Debug-iphoneos/Leap.app/PlugIns/LeapWidgetExtension.appex/embedded.mobileprovision \
  | grep -A2 weatherkit
```

### Debugging a weather face that shows the placeholder

The WeatherKit error is deliberately swallowed (the `catch` in
`LeapWeatherService.refresh`) so a face always renders something, which makes a
mis-provisioned WeatherKit look identical to a boring forecast. Two App-Group keys tell
you what actually happened:

- **`leap.debug.weather.v1`** — the reason the LAST refresh succeeded or failed, written
  by `LeapWeatherService.recordDiagnostic`. **Debug / Internal builds only** (public
  Release writes nothing). Values you will see:
  - `ok 61F CLOUDY @ <date>` — real WeatherKit data; everything is working.
  - `fetch failed: ...WDSJWTAuthenticatorServiceListener.Errors Code=2` — WeatherKit is
    not ticked under the App ID's **App Services** tab (see above).
  - `skipped - location not authorized (status 0); add a weather widget to prompt` — the
    foreground refresh is gated off; grant Location by adding a weather widget.
  - `no-coordinate (location auth N)` — no cached or live coordinate to query.
- **`leap.live.weather.v1`** — the cached reading itself, written **only** after a
  successful fetch. Absent = no fetch has ever succeeded.

Read both off a device with:

```bash
xcrun devicectl device copy from --device 00008150-0014746214F2401C \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.sololeap.leap.app \
  --source Library/Preferences/group.com.sololeap.leap.app.plist \
  --destination /tmp/leap_group.plist && plutil -p /tmp/leap_group.plist | grep -i weather
```

`leap.live.coord.lat.v1` / `leap.live.coord.lon.v1` show whether a coordinate was ever
cached — the fetch still proceeds off that cached coordinate even when Location is
currently `notDetermined`, so a JWT error (not a missing coordinate) is the usual cause.

The same check works on the **Simulator**, where it is fully scriptable — useful because
WeatherKit fails there identically when the service is not registered:

```bash
SIM=D95D5EEF-A4E4-41B1-976B-52635F7305C7
xcrun simctl privacy $SIM grant location-always com.sololeap.leap.app
xcrun simctl location $SIM set 53.2669,-6.2028
xcrun simctl launch $SIM com.sololeap.leap.app && sleep 20
xcrun simctl terminate $SIM com.sololeap.leap.app   # flush cfprefsd before reading
GC=$(xcrun simctl get_app_container $SIM com.sololeap.leap.app groups | awk '{print $2}')
plutil -p "$GC/Library/Preferences/group.com.sololeap.leap.app.plist" | grep -i weather
```

Terminate the app before reading: the simulator's `cfprefsd` buffers writes, and editing
that plist from the host while the sim is booted is silently discarded.

### What the placeholder looks like (so you can recognise it)

- A **deterministic** forecast generated from the calendar date
  (`LeapWeatherSample.make()` in `Shared/LeapWidgetWeather.swift`) — e.g. `CLEAR / sun /
  H:25 / L:16`. It **changes once per calendar day**, never from real conditions, so it
  will not match Apple's Weather app and looks "stuck / wrong / not refreshing". A current
  temperature that happens to match Apple is a coincidence.
- Fallback chain: `WeatherService.weather(for:)` throws -> `LeapWeatherService.refresh()`
  caches nothing -> `LeapLiveStore.loadWeather()` returns `nil` ->
  `LeapWeatherSample.resolve()` (or `WeatherDesign.weatherMood`) renders the placeholder.
  Location still resolves; only the weather **fetch** fails.

## In-app purchases: run from the scheme, not `simctl`

Full StoreKit design/behavior lives in [in-app-purchases.md](in-app-purchases.md); the build/run
gotcha is that the `Leap.storekit` config is a **scheme run-action setting**
(`Leap.xcodeproj/xcshareddata/xcschemes/Leap.xcscheme`), **not** baked into the `.app`:

- **Exercise a purchase** by running from Xcode with the **Leap scheme** (Run / Cmd-R) — the local
  `.storekit` store applies and buy / cancel / restore / refund all work with **no paid team**. A
  plain `xcrun simctl launch` of the installed build (as above) does **not** apply it, so the
  paywall finds no products and the **Unlock** button pops an alert titled **"Something went
  wrong"** — expected, not a bug (see §10.1 in the IAP doc).
- **Purchased premium restores automatically** on reinstall (Apple-ID entitlement, mirrored to the
  App Group); the **7-day trial** persists separately in the Keychain. The real Apple purchase
  sheet + real products need a **paid** membership and App Store Connect records — the same
  paid-team constraint as WeatherKit above.

## Build configurations: Debug / Release / Internal

Three configs live in the hand-authored `Leap.xcodeproj/project.pbxproj`:

- **Debug** — everyday development (`DEBUG` defined; app code links dynamically via
  `Leap.debug.dylib`, so the main `.app/Leap` binary is a small stub).
- **Release** — the **public App Store** build. Ships **no** debug/admin surface.
- **Internal** — **release-grade** (cloned from Release: same optimization, dSYM, signing)
  **plus** the `LEAP_INTERNAL` Swift flag, set once at the **project-level** Internal config
  (`SWIFT_ACTIVE_COMPILATION_CONDITIONS = "LEAP_INTERNAL $(inherited)"`) so both the app and
  the widget-extension targets inherit it. Use it for QA, TestFlight, and Ad-hoc builds where
  you want the hidden admin/debug panel inside an otherwise production-like app.

The admin/debug panel (shake → password → toggle plan / simulate trial / replay onboarding)
is gated on **`#if DEBUG || LEAP_INTERNAL`**, so it is present in **Debug** and **Internal**
and **fully compiled out of public Release** — verified by string-scanning the *fully linked*
binaries: `LeapDebugPanelView` + `leap.debug.plan.override.v1` are present in the Internal
binary and **absent** from Release. (Don't scan the Debug main binary — its app code is in
`Leap.debug.dylib`.) Public Release derives `isPro` **solely** from StoreKit; there is no
shippable master-key bypass. **Never** relax the gate to include public Release.

```bash
# Build any config (Debug | Release | Internal):
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Internal \
  -destination 'platform=iOS Simulator,id=<SIM_UDID>' \
  -derivedDataPath /tmp/LeapDerivedData build
```

Run / Profile / Archive the Internal build from Xcode with the shared **"Leap (Internal)"**
scheme (`Leap.xcodeproj/xcshareddata/xcschemes/Leap (Internal).xcscheme`) — all of its
actions use the Internal configuration.

**Internal builds also ship live telemetry.** In addition to `LEAP_INTERNAL`, the app
target's Internal config defines **`LEAP_ANALYTICS`** (`SWIFT_ACTIVE_COMPILATION_CONDITIONS =
"$(inherited) LEAP_ANALYTICS"`), so an Internal build carries **both** the debug panel and
**working Firebase/GA4 collection**. The widget extension's Internal config gets only
`LEAP_INTERNAL` — **never** `LEAP_ANALYTICS` (that would link Firebase into the extension and
fail to link / double-count users). See [telemetry.md](telemetry.md).

Build, install, and launch an Internal build on a **physical device** (used to verify
telemetry — `-FIRDebugEnabled` turns on GA4 DebugView and persists across restarts):

```bash
GIT_CONFIG_VALUE_0=all xcodebuild -project Leap.xcodeproj -scheme "Leap (Internal)" \
  -configuration Internal -destination 'platform=iOS,id=<DEVICE_UDID>' \
  -derivedDataPath /tmp/LeapInternalBuild -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=D2Z89UU4R7 build
xcrun devicectl device install app --device <DEVICE_UDID> \
  /tmp/LeapInternalBuild/Build/Products/Internal-iphoneos/Leap.app
# NOTE the `--` terminator, or devicectl misparses the launch flag:
xcrun devicectl device process launch --device <DEVICE_UDID> --terminate-existing \
  com.sololeap.leap.app -- -FIRDebugEnabled
```

To grant Premium to real testers **without** a bypass, prefer App Store **promo / offer
codes**, **TestFlight + StoreKit sandbox** (sandbox buys are free), or a server-side
entitlement — see [in-app-purchases.md](in-app-purchases.md).

## Gotcha: the device must be UNLOCKED to launch

`xcrun devicectl device process launch …` fails on a **locked** phone with
`CoreDeviceError 10002` / `FBSOpenApplicationServiceErrorDomain … RequestDenied … Locked`.
The **install still succeeds** — just unlock the iPhone and re-run the launch (or tap the
app icon).
