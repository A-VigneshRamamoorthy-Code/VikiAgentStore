---
name: weatherkit
description: >
  Apple development skill for WeatherKit — building Leap's weather widgets, and every way it breaks. Use this skill when working on weatherkit tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# WeatherKit — building Leap's weather widgets, and every way it breaks

Everything needed to work on a Leap **weather face**: how WeatherKit actually
authenticates, the portal setup that is *not* optional, what the Simulator can and cannot tell you,
Apple's **mandatory attribution** rule, and a symptom-first pitfall table.

Read this **before** touching `Shared/LeapLiveData.swift`, `Shared/LeapWidgetWeather.swift`,
or anything that calls `WeatherService`. Signing / build commands live in
[build-and-run.md](build-and-run.md); the widget-timeline rules live in
[realtime-widgets.md](realtime-widgets.md).

---

## 1. How WeatherKit authentication actually works

This one mechanism explains almost every failure below, so it is worth internalising.

**Your app never mints its own credential.** When you call
`WeatherService.shared.weather(for:)`, the framework hands off over XPC to a system
daemon — **`weatherd` (WeatherDaemon)**. `weatherd` mints an Apple-signed **JWT** for
`com.apple.weatherkit.authservice`, asserting that *this App ID, on this team, is
entitled to WeatherKit*. Only then does a network request to Apple Weather happen.

Three things must line up for that JWT to be issued:

1. The **signed binary** carries `com.apple.developer.weatherkit` (from the entitlements
   file, validated against the embedded provisioning profile).
2. The **App ID is authorised for WeatherKit server-side** at developer.apple.com.
3. The team holds a **paid** Apple Developer Program membership.

**The consequence that trips everyone up:** items 1 and 3 are locally verifiable, item 2
is not. So you can have a perfectly signed binary, a valid 1-year profile that visibly
contains `weatherkit`, and *still* fail — because the failure is server-side. A
`Code=2` error is thrown **before any weather lookup**, which is why it is instant and
100% reproducible rather than flaky.

> Corollary: **no amount of local rebuilding, profile deletion, or clean-building fixes a
> server-side authorisation gap.** If the entitlement is provably in the binary, stop
> rebuilding and go look at the portal.

---

## 2. Portal setup — WeatherKit lives in TWO places, and Xcode only writes one

This is the single most common cause of a WeatherKit that "should work" but doesn't.

At **developer.apple.com -> Certificates, Identifiers & Profiles -> Identifiers**, open an
App ID. The editor presents **two separate surfaces**, and WeatherKit appears in **both**:

| Surface | What it does | Who sets it |
|---|---|---|
| **App Capabilities** (a.k.a. Capabilities) | Puts `com.apple.developer.weatherkit` into the **provisioning profile**, so the entitlement can be signed into the binary. | **`xcodebuild -allowProvisioningUpdates` sets this automatically.** |
| **App Services** | Authorises the App ID **server-side** so `weatherd` will actually mint the JWT. | **Manual, one-time, per App ID. Nothing in the build ever touches it.** |

Because `xcodebuild` silently handles the Capabilities half, the build succeeds, the
profile genuinely contains `weatherkit`, `codesign` confirms the entitlement — and the
service still refuses to authenticate. **Ticking Capabilities alone is not enough.**

> **This is not theoretical — it is exactly what happened to Leap.** WeatherKit was
> enabled under Capabilities (by `xcodebuild`) but **not** under App Services, and every
> weather face failed with `Code=2` for hours while the entitlement was provably present
> in both signed binaries and both provisioning profiles. Ticking **App Services** on both
> App IDs fixed it within ~30 minutes. If you see `Code=2`, check this **first** — do not
> waste time rebuilding, regenerating profiles, or blaming the code.

Both of Leap's App IDs need **both** ticks — the extension does **not** inherit WeatherKit
from its host app:

- `com.sololeap.leap.app`
- `com.sololeap.leap.app.LeapWidget`

Then **Save**, and allow **~30 minutes** to propagate.

Other portal facts worth knowing:

- **Explicit (non-wildcard) App IDs are required.** WeatherKit cannot be attached to a
  `com.example.*` wildcard. Leap's IDs are explicit, so this is satisfied.
- **A paid membership is required.** Free/personal teams cannot enable the service at all.
  Quick check: paid teams get **1-year** provisioning profiles, personal teams get **7-day**
  ones (`security cms -D -i embedded.mobileprovision | grep -A1 ExpirationDate`).
- **No App Store Connect app record is required** for the on-device framework. Access is
  tied to the membership + App ID entitlement, not to a published app.
- **No `.p8` key is required either.** The Keys section / hand-signed JWT flow is **only**
  for the WeatherKit **REST API**. On-device, `weatherd` mints the token for you. Do not
  go down the Keys path trying to fix the framework — it is a dead end.
- **Brand-new memberships can lag.** When a membership was purchased very recently, the
  WeatherKit token backend can trail the portal by **hours, occasionally 24-48h**, even
  when every setting is provably correct. Symptom is identical to a missing App Services
  tick, which makes the two hard to tell apart — confirm the tick first, then wait.

---

## 3. The Simulator DOES work - but only once the portal is right

An earlier version of this guide claimed the Simulator can *never* authenticate
WeatherKit because a Simulator build is ad-hoc signed. **That is wrong, and it cost hours
of debugging.** Once the **App Services** tick (section 2) was enabled, the exact same
Simulator that had been failing all day fetched real data on the next launch:

    leap.debug.weather.v1 => "ok 68F MOSTLY CLEAR"

The Simulator runs on the **host Mac's** `weatherd`, which authenticates against the App
ID server-side; it does not need the app's own provisioning profile. So a Simulator
`Code=2` is a **real signal**, not noise - treat it exactly like a device `Code=2` and go
check the portal.

What the Simulator still cannot tell you:

- It uses the **Mac's** location (Xcode's simulated location), not the device's, so the
  numbers will not match a phone standing next to you.
- Entitlement / profile problems that are specific to device signing are invisible there.

**A physical device remains the only surface that proves the shipped build is correct**,
but the Simulator is a perfectly good first check and is far faster to iterate on.

---

## 4. Attribution is MANDATORY - how Leap ships it

Apple **requires** every surface displaying WeatherKit data to show the **Apple Weather
trademark** and a link to Apple's **legal attribution page**. This is a condition of use,
and omitting it is a documented **App Review rejection** cause. It applies to
**Home-Screen widgets** too, not just in-app screens.

The API:

```swift
let attribution = try await WeatherService.shared.attribution
attribution.combinedMarkLightURL   // logo for light backgrounds
attribution.combinedMarkDarkURL    // logo for dark backgrounds
attribution.squareMarkURL          // compact mark
attribution.legalPageURL           // must be reachable by the user
```

### What Leap does

**The mark: one insertion point, not eighteen.** `LeapWidgetContentView.styled(_:)`
carries a single `.overlay(alignment: .bottomTrailing)` that renders
`LeapWeatherAttribution()` whenever `kind.showsWeather` is true. Every weather-bearing
face inherits it, so **a new weather design can never ship without the mark** - which is
exactly why it lives there and not in the individual designs. Do not move it into a face.

`LeapWeatherAttribution` (in `Shared/LeapWidgetWeather.swift`) draws the `apple.logo`
**SF Symbol** plus the word `Weather` at **7pt / 0.42 opacity**, inheriting `leapInk` so
it stays white-on-wallpaper like the rest of the content. It sets
`.allowsHitTesting(false)`: a widget has exactly **one** tap target and Leap spends it on
check-in / open-app, so the mark must not steal it.

The overlay is gated on `kind.showsWeather && !snapshot.weatherUnavailable` - with no
reading, nothing on screen is WeatherKit data, so the mark is suppressed too (see 4c).

> **⛔️ The tile is CLIPPED TO A ROUNDED RECT, so a mark tucked tight into the corner is
> EATEN BY THE CURVE.** This is a real shipped bug, not a theoretical one: the original
> `(trailing 5, bottom 3)` inset sliced the end of "Weather" clean off. A point `(dx, dy)`
> in from a corner of radius `R` survives iff **`(R-dx)^2 + (R-dy)^2 <= R^2`** - but a
> `.continuous` squircle eats more than that circular model predicts, so treat it as a
> floor and keep **>= 30% margin**. `LeapWidgetSize.weatherMarkInset` (in
> `LeapWidgetContentView.swift`) returns **small `(13, 8)` / medium `(17, 9)` / large
> `(20, 12)`** against radii 22 / 24 / 30. Device-confirmed unclipped.
>
> **The other half of the fix is in the PREVIEW.** `previewCornerRadius` is keyed by
> *family*, but a `[.large]`-only design (`weatherGraph`, `weatherMetrics`, `monthAgenda`)
> lands in a ~147x150 Browse tile at scale **~0.42** - a fixed 30pt corner is then 21% of
> the tile width instead of the ~9% a real widget has, i.e. an effective **~71pt** arc in
> the design's own coordinates that **no inset can escape**. Both clip sites
> (`LeapWidgetPreview` and `BrowseTile`) now call
> **`LeapWidgetSize.previewCornerRadius(fitting:)`**, which scales the radius with the
> miniature and is a no-op above scale 0.9 (small/medium tiles, the Add-sheet hero).
>
> **Layout budget.** Those insets are as small as the arc allows, because every weather
> design pads its content by **at least 18pt** and the mark has to live under that gutter.
> **Do not put face content in the bottom-trailing corner of a weather design** -
> `WeatherGraphDesign` used to draw a `BrandMark()` there and it collided with the
> mandatory mark, so it was removed. If you raise a corner radius, re-run the inequality.

**The mark image is NOT downloaded.** `combinedMark*URL` / `squareMarkURL` are *remote*
images; fetching them on a widget timeline is exactly the unbounded-network mistake the
architecture exists to avoid, and caching a bitmap per entry would inflate the timeline
archive (see [clock-faces.md](clock-faces.md)). The SF-Symbol + text construction renders
offline, costs nothing per entry, and keeps the sources ASCII (the `\u{F8FF}` Apple glyph
is a private-use codepoint and would not).

**The legal link lives in the app**, not the widget - Settings -> About renders a tappable
`Link` to the legal page (`HomeView.aboutCard`). The URL is whatever
`WeatherService.attribution.legalPageURL` returned on the last successful fetch, cached to
the App Group under `leap.live.weather.legal.v1` and read back by `LeapWeatherLegal.url`,
which falls back to `https://weatherkit.apple.com/legal-attribution.html` if nothing has
been cached yet.

### Quota

**500,000 calls/month** are included with the membership; unused calls do not roll over.
Leap's cache-first architecture (app fetches, App Group stores, extension reads) keeps
usage far below this; per-face uncached fetching would not.

---

## 4b. Two data traps Leap already hit

**1. WeatherKit vends NO air quality.** There is no AQI in the framework at any tier. An
earlier build carried an `aqi` field that was permanently `-1` and rendered as `--`, plus
a `CHECK AIR` verdict that could never fire. Both were **removed** (`AirBodyDesign` now
shows UV / HUMID / WIND / GUST). Do not add AQI back, and above all do not synthesise a
number for it.

**2. Never round Fahrenheit before converting to Celsius.** Leap stores temperatures as
integer Fahrenheit, and converting *that* to Celsius double-rounds: a true `15.4 C`
becomes `60 F` becomes `15.6 C` becomes **"16"** while Apple Weather shows **"15"**. That
is the whole of the "our widget disagrees with Apple by a degree" bug. The fix is
`LeapExactTemps` (in `LeapLiveData.swift`), which keeps the **unrounded** Fahrenheit for
temp / feels / high / low / hourly / dayHighs / dayLows alongside the rounded ints;
`LeapWeatherSample.converted(to:)` prefers it and rounds **once**, via
`LeapTempUnit.convert(fromFahrenheitExact:)`. `exact` is **optional** so older cached
payloads still decode - the Int path is kept purely as that fallback.

Related: `LeapWeatherData.Day` originally had **no low at all**, so
`WeatherWeekDesign.rangeText` *invented* one (`high - spread + index % 3`). It now stores
WeatherKit's real `lowTemperature`. `Day.low` is optional for the same
backward-compatibility reason.

---

## 4c. ⛔️ A PLACED widget NEVER shows fabricated weather

Every weather design has a permission-free `LeapWeatherSample.make()` so the catalog can
be browsed before Location is granted. That sample is **indistinguishable from a live
reading**, so on a *placed* Home-Screen widget it is a lie: if Location is denied the tile
sits there forever showing a plausible forecast the user will act on.

The rule: **the synthetic sample survives only where it is honestly a PREVIEW.**

| Surface | Weather shown | Why |
|---|---|---|
| Browse / Add tiles in-app | real cached reading, else the sample | it is a catalog; blanking 15 tiles makes the app look broken |
| WidgetKit gallery (`context.isPreview`) | the sample | Apple's own convention for gallery art |
| **PLACED widget** | **real reading, else an explicit "no data" face** | anything else is fabricated data |

How it is wired:

- `LeapSnapshot.weatherUnavailable` (`LeapWidgetContentView.swift`) - defaults `false`.
- `LeapCheckInWidget.entry(for:)` sets it to `snapshot.weather == nil` whenever
  `design.showsWeather`. `placeholder(in:)` and `snapshot(for:in:)` **clear it again when
  `context.isPreview`**, which is the gallery exemption.
- `LeapWidgetContentView.content(now:)` intercepts *before* the 66-case switch (now
  `face(now:)`): `weatherUnavailable && kind.category == .weather` -> `LeapWeatherUnavailableFace`
  ("NO WEATHER / Open Leap and allow Location", style-aware).
- The three **combo** faces are not in `.weather`, so they handle it inline instead:
  `greetingClock.weatherRow` and `sceneClock.weatherLine` (`LeapWidgetTime.swift`) swap to
  `cloud.slash` + `--` + an explanation, and `dateTemp.temperatureColumn`
  (`LeapWidgetCalendar.swift`) renders `--` with no unit letter. `LeapTemp` gained an
  `unavailable` flag for this.
- In-app previews get real data because `LeapViewModel.snapshot` now loads
  `LeapLiveStore.shared.loadWeather()`.

**If you add a weather-bearing face, it must handle the unavailable state** - either by
being in `LeapWidgetCategory.weather` (free, via the intercept) or by branching on
`snapshot.weatherUnavailable` like the three combos do.

---

## 5. Leap's architecture (and why it is the right one)

```
Leap app  ──(CoreLocation + WeatherService)──>  App Group cache  ──>  Widget extension
           requests permission on widget add     leap.live.weather.v1    reads cache,
                                                                        bounded 2.5s refresh
```

- The **app** does the real fetching and writes `leap.live.weather.v1` into the App Group.
- The **extension** renders from that cache, and only attempts a **bounded** refresh.
- The extension passes **`allowOneShot: false`** — a CoreLocation one-shot can hang
  forever inside an extension.

This "fetch in the host app, share via App Group, cache-first in the widget" pattern is
the Apple-recommended shape, and it is load-bearing for Leap: blocking
`timeline(for:in:)` on an unbounded network call is the **#1 cause of a widget that goes
blank, never loads, or reports "could not run"**. Never regress it. Details and the
⛔️ box in [realtime-widgets.md](realtime-widgets.md).

**Location gating.** `LeapViewModel.refreshLiveDataIfAuthorized()` only fetches weather
when `LeapWeatherService.shared.isAuthorized`. Leap requests Location **only when the user
adds a weather widget** (`AddWidgetSheet.save()` -> `requestLiveDataAccess(for:)`), never
at launch. So on a device where Location was never granted, weather **never refreshes and
that is by design** — it is not a WeatherKit failure. The `else` branch leaves a
`recordSkippedRefresh()` breadcrumb precisely so the two can be told apart.

Prefer the narrowest query. `weather(for:including:.current)` pulls far less than the full
`weather(for:)` — cheaper, faster, and easier to keep inside the extension's time budget.

---

## 6. Pitfalls — symptom -> cause -> fix

| Symptom | Cause | Fix |
|---|---|---|
| `WDSJWTAuthenticatorServiceListener.Errors Code=2` on a **device**, entitlement provably in the binary | WeatherKit ticked under **Capabilities** but **not App Services** — `xcodebuild` only writes the former | Tick WeatherKit under **App Services** for **both** App IDs, Save, wait ~30 min |
| `Code=2` with **both** tabs ticked, membership just purchased | Apple backend propagation lag for a **new** membership | Wait — hours up to 24-48h; retry periodically before concluding it is broken |
| `Code=2` on the **Simulator** | Same server-side causes as on device - the Simulator is NOT exempt | Debug it for real (start with the App Services tick); do not dismiss it |
| `Code=2` after fixing the portal | Stale profile, or `weatherd` cached the negative auth | Regenerate profiles, clean build, reinstall, then **reboot the device** |
| Entitlement missing from the built binary | Entitlements file edited but target/profile out of sync | `codesign -d --entitlements :-` on **both** `.app` and `.appex`; both must print it |
| Weather never refreshes, **no** error logged | Location `notDetermined` — the foreground refresh is gated off by design | Add a weather widget in-app once and tap Allow |
| Weather resolves to a point off the African coast | A zero/invalid `CLLocation` (0,0) was passed | Always pass a validated cached coordinate; never a default-constructed `CLLocation` |
| Widget blank / "could not load" / stuck on placeholder | Timeline blocked on an unbounded network or CoreLocation call | Cache-first render; bounded refresh; `allowOneShot: false` |
| App Review rejection | Missing Apple Weather mark + legal link | Shipped - see §4. The mark comes from ONE overlay in `styled(_:)`; do not remove it |
| Widget temp is 1 degree off Apple Weather in Celsius | Rounded Fahrenheit converted to Celsius (double rounding) | Use `LeapExactTemps` / `convert(fromFahrenheitExact:)` - §4b |
| Forecast LOWS look invented | They were - `rangeText` derived them from the high | Fixed: `Day.low` now carries WeatherKit's `lowTemperature` - §4b |
| AQI always `--` | WeatherKit vends no air quality, ever | Removed. Do not re-add or synthesise one - §4b |
| Quota exhaustion | Per-face uncached fetching | Keep the single app-side fetch + App Group cache |
| Free/personal team | WeatherKit cannot be enabled at all | Paid membership required (1-year profiles = paid) |
| Wildcard App ID | WeatherKit needs an explicit App ID | Use explicit IDs (Leap already does) |

**On `Code=1` / `Code=4`:** Apple publishes no mapping of these codes. Community reports
treat them as variants of the same "JWT could not be generated/validated" auth failure —
**run the same checklist**; do not read meaning into the specific number.

---

## 7. Diagnosing: what Leap records for you

WeatherKit errors are **deliberately swallowed** in `LeapWeatherService.refresh` so a face
always renders *something*. That makes a mis-provisioned WeatherKit look exactly like a
boring forecast — so Leap writes a breadcrumb. Two App-Group keys tell the whole story:

- **`leap.debug.weather.v1`** — why the last refresh succeeded or failed.
  **Debug / Internal builds only**; public Release writes nothing (verified via `strings`).
  - `ok 61F CLOUDY @ <date>` — real data, everything works.
  - `fetch failed: ...Code=2` — auth/provisioning; go to §2.
  - `skipped - location not authorized (status 0)` — Location gate, not a WeatherKit bug.
  - `no-coordinate (location auth N)` — no cached or live coordinate to query.
- **`leap.live.weather.v1`** — the cached reading. **Absent = no fetch has ever succeeded.**

Read both off a device without a debugger:

```bash
xcrun devicectl device copy from --device 00008150-0014746214F2401C \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.sololeap.leap.app \
  --source Library/Preferences/group.com.sololeap.leap.app.plist \
  --destination /tmp/leap_group.plist && plutil -p /tmp/leap_group.plist | grep -i weather
```

Confirm the signed artefacts really carry the entitlement:

```bash
codesign -d --entitlements :- .../Leap.app
codesign -d --entitlements :- .../Leap.app/PlugIns/LeapWidgetExtension.appex
security cms -D -i .../embedded.mobileprovision | grep -A2 weatherkit
```

Deeper system logs (`weatherd`) need **root**, which is often unavailable:
`log collect --device-udid <udid>` fails with "Must be root", and
`xcrun devicectl device sysdiagnose --device <udid> --destination <dir>` (note:
`--destination`, **not** `--output`) has proven unreliable. In practice the App-Group
breadcrumb above is the most reliable signal.

**Escalation:** if it still fails **>48h** after both the App Services tick and membership
activation, with the entitlement provably in both binaries, open an **Apple Developer
Technical Support** ticket quoting the Team ID, both bundle IDs, and the exact `Code=2`
string.

---

## 8. Adding or changing a weather face

- All 18 weather-rendering faces (15 in the Weather category plus the `greetingClock`,
  `sceneClock` and `dateTemp` combos) consume live data. 17 resolve through
  `LeapWeatherSample.resolve`; `WeatherDesign` reads `snapshot.weather` via `weatherMood`.
  **None is hard-wired to the placeholder** — so once auth works, they all light up
  together.
- The extension wires it up in `LeapCheckInWidget.swift`
  (`snapshot.weather = LeapLiveStore.shared.loadWeather()`).
- `DateTempDesign` lives in `Shared/LeapWidgetCalendar.swift`, not the weather file.
- A face must **always** render acceptably from a `nil` reading — a cold widget
  legitimately has no cached weather yet. On a **placed** widget `nil` must resolve to the
  explicit no-data treatment, never the synthetic sample — see §4c.
- Weather text obeys the same archive-size rules as clocks: prefer `Text(verbatim:)` over
  `Text(_, format:)` on any dense timeline. See [clock-faces.md](clock-faces.md).
- **Keep the bottom-trailing corner EMPTY** (pad content by at least 18pt): the mandatory
  Apple Weather mark is overlaid there by `styled(_:)` - see §4.
- **Add any new temperature to `LeapExactTemps` too**, not just as a rounded Int, or that
  reading will drift a degree from Apple Weather in Celsius - see §4b.
- **Handle `snapshot.weatherUnavailable`** unless the face is in
  `LeapWidgetCategory.weather` (which gets it for free) - see §4c.

### Verified working reference reading

A known-good live payload (Dublin, real WeatherKit) for comparison when debugging:

```
leap.debug.weather.v1 = "ok 64F DRIZZLE @ ..."
tempF 64 / feels 60 / high 74 / low 60   condition DRIZZLE   symbol cloud.drizzle
hourly [67,66,65,64,63,63,61,62]         days 7 entries with symbol/high/label
sunrise 05:36  sunset 21:25  daylight "15H 49M"  humidity 79  uv 0
windMph 9  gustMph 17  windDir W  windDeg 282   rainProb 0  rainPhrase "NO RAIN SOON"
```

Every field a Leap face reads is populated. A payload written by a current build also
carries `exact` (unrounded Fahrenheit) and a per-day `low`; one written before that work
has neither, and decodes fine via the Int fallbacks - if `exact` is missing, the app has
simply not refreshed since the update.

---

## Sources

- Apple — WeatherKit: <https://developer.apple.com/weatherkit/>
- Apple — Enabling WeatherKit (Help / Account): <https://developer.apple.com/help/account/services/weatherkit>
- Apple — `WeatherAttribution`: <https://developer.apple.com/documentation/weatherkit/weatherattribution>
- Apple — Fetching weather forecasts with WeatherKit: <https://developer.apple.com/documentation/weatherkit/fetching_weather_forecasts_with_weatherkit>
- WWDC22 session 10003, "Meet WeatherKit"
- Apple Developer Forums threads 834697, 835229, 807586, 829457, 789900, 789157
- anupdsouza — Fixing WeatherKit JWT authentication errors: <https://www.anupdsouza.com/blog/weatherkit-jwt-auth-error>
- alexpaul.dev — Adding WeatherKit to an iOS app: <https://alexpaul.dev/2023/11/29/adding-weatherkit-to-an-ios-app/>
- nickkaczmarek.com — WeatherKit App ID troubleshooting (2024-04-12)
