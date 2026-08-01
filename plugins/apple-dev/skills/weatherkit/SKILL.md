---
name: weatherkit
description: >
  Guide for Apple WeatherKit integration, App Services provisioning, WeatherService APIs, CoreLocation, attribution requirements, and data caching.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# WeatherKit — building weather widgets and avoiding pitfalls

Everything needed to work on iOS **weather widgets and apps**: how WeatherKit actually
authenticates, the portal setup that is *not* optional, what the Simulator can and cannot tell you,
Apple's **mandatory attribution** rule, and a symptom-first pitfall table.

Read this **before** integrating `WeatherService` into any app or widget extension.

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

> **This is exactly what happens to most apps.** WeatherKit gets enabled under Capabilities (by `xcodebuild`) but **not** under App Services, and weather features fail with `Code=2` for hours while the entitlement is provably present in both signed binaries and both provisioning profiles. Ticking **App Services** on both App IDs fixes it within ~30 minutes. If you see `Code=2`, check this **first** — do not waste time rebuilding, regenerating profiles, or blaming the code.

All relevant App IDs need **both** ticks — a widget extension does **not** inherit WeatherKit
from its host app:

- `com.example.app`
- `com.example.app.WidgetExtension`

Then **Save**, and allow **~30 minutes** to propagate.

Other portal facts worth knowing:

- **Explicit (non-wildcard) App IDs are required.** WeatherKit cannot be attached to a
  `com.example.*` wildcard. 
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

It is a common misconception that the Simulator can *never* authenticate WeatherKit because a Simulator build is ad-hoc signed. **That is wrong.** Once the **App Services** tick (section 2) is enabled, the Simulator can fetch real data on the next launch.

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

## 4. Attribution is MANDATORY

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

### Best Practices for Attribution

**The mark insertion:** You should carry a single `.overlay(alignment: .bottomTrailing)` that renders the attribution whenever weather data is shown. Every weather-bearing view should inherit it, so **a new weather design can never ship without the mark**.

Instead of downloading remote images (`combinedMark*URL` / `squareMarkURL`), which can be problematic in a widget timeline context without a network connection, you can draw the `apple.logo` **SF Symbol** plus the word `Weather`. Make sure to set `.allowsHitTesting(false)` if the widget has tap targets that the mark must not steal. 

**Avoid squircle clipping:** Widgets are clipped to a continuous rounded rectangle (squircle), so a mark tucked tight into the corner can be **eaten by the curve**. A point `(dx, dy)` in from a corner of radius `R` survives iff `(R-dx)^2 + (R-dy)^2 <= R^2` - but a `.continuous` squircle eats more than that circular model predicts, so treat it as a floor and keep a safe margin.

**The legal link:** The link should live in the host app (e.g., Settings -> About rendering a tappable `Link` to the legal page). The URL is whatever `WeatherService.attribution.legalPageURL` returned on the last successful fetch, falling back to `https://weatherkit.apple.com/legal-attribution.html` if nothing has been cached yet.

### Quota

**500,000 calls/month** are included with the membership; unused calls do not roll over.
A cache-first architecture (app fetches, App Group stores, extension reads) keeps
usage far below this; per-widget uncached fetching will quickly exhaust it.

---

## 5. Two data traps to avoid

**1. WeatherKit vends NO air quality.** There is no AQI in the framework at any tier. Do not attempt to add AQI back from WeatherKit, and above all do not synthesise a number for it.

**2. Never round Fahrenheit before converting to Celsius.** If you store temperatures as integer Fahrenheit, converting *that* to Celsius will double-round. A true `15.4 C` becomes `60 F` becomes `15.6 C` becomes **"16"** while Apple Weather shows **"15"**. The fix is to keep the **unrounded** exact value for conversions and only round once before displaying to the user.

---

## 6. A PLACED widget NEVER shows fabricated weather

Every weather design needs a permission-free sample so the catalog can be browsed before Location is granted. But on a *placed* Home-Screen widget, a sample is a lie: if Location is denied, the tile sits there forever showing a plausible forecast the user will act on.

The rule: **the synthetic sample survives only where it is honestly a PREVIEW.**

| Surface | Weather shown | Why |
|---|---|---|
| Browse / Add tiles in-app | real cached reading, else the sample | it is a catalog; blanking tiles makes the app look broken |
| WidgetKit gallery (`context.isPreview`) | the sample | Apple's own convention for gallery art |
| **PLACED widget** | **real reading, else an explicit "no data" face** | anything else is fabricated data |

**If you add a weather-bearing widget, it must handle the unavailable state** (e.g. "NO WEATHER / Open App and allow Location") instead of showing dummy data.

---

## 7. The recommended architecture

```
Host App ──(CoreLocation + WeatherService)──>  App Group cache  ──>  Widget extension
            requests permission on widget add    weather.cache.v1      reads cache,
                                                                       bounded refresh
```

- The **app** does the real fetching and writes the data into the App Group.
- The **extension** renders from that cache, and only attempts a **bounded** refresh.
- The extension passes **`allowOneShot: false`** — a CoreLocation one-shot can hang
  forever inside an extension.

This "fetch in the host app, share via App Group, cache-first in the widget" pattern is
the Apple-recommended shape. Blocking `timeline(for:in:)` on an unbounded network call is the **#1 cause of a widget that goes blank, never loads, or reports "could not run"**. 

Prefer the narrowest query. `weather(for:including:.current)` pulls far less than the full `weather(for:)` — cheaper, faster, and easier to keep inside the extension's time budget.

---

## 8. Pitfalls — symptom -> cause -> fix

| Symptom | Cause | Fix |
|---|---|---|
| `WDSJWTAuthenticatorServiceListener.Errors Code=2` on a **device**, entitlement provably in the binary | WeatherKit ticked under **Capabilities** but **not App Services** — `xcodebuild` only writes the former | Tick WeatherKit under **App Services** for **both** App IDs, Save, wait ~30 min |
| `Code=2` with **both** tabs ticked, membership just purchased | Apple backend propagation lag for a **new** membership | Wait — hours up to 24-48h; retry periodically before concluding it is broken |
| `Code=2` on the **Simulator** | Same server-side causes as on device - the Simulator is NOT exempt | Debug it for real (start with the App Services tick); do not dismiss it |
| `Code=2` after fixing the portal | Stale profile, or `weatherd` cached the negative auth | Regenerate profiles, clean build, reinstall, then **reboot the device** |
| Entitlement missing from the built binary | Entitlements file edited but target/profile out of sync | `codesign -d --entitlements :-` on **both** `.app` and `.appex`; both must print it |
| Weather never refreshes, **no** error logged | Location `notDetermined` — the foreground refresh is gated off by design | Request location permission in the app appropriately |
| Weather resolves to a point off the African coast | A zero/invalid `CLLocation` (0,0) was passed | Always pass a validated cached coordinate; never a default-constructed `CLLocation` |
| Widget blank / "could not load" / stuck on placeholder | Timeline blocked on an unbounded network or CoreLocation call | Cache-first render; bounded refresh; `allowOneShot: false` |
| App Review rejection | Missing Apple Weather mark + legal link | Add the required attribution mark and link - see §4. |
| Widget temp is 1 degree off Apple Weather in Celsius | Rounded Fahrenheit converted to Celsius (double rounding) | Use exact unrounded values for conversions - see §5 |
| Free/personal team | WeatherKit cannot be enabled at all | Paid membership required (1-year profiles = paid) |
| Wildcard App ID | WeatherKit needs an explicit App ID | Use explicit IDs |

**On `Code=1` / `Code=4`:** Apple publishes no mapping of these codes. Community reports
treat them as variants of the same "JWT could not be generated/validated" auth failure —
**run the same checklist**; do not read meaning into the specific number.

---

## 9. Diagnosing & Verifying

WeatherKit errors are often swallowed or difficult to expose in extensions. It's recommended to write debugging information to the App Group to help tell the whole story.

Read App Group data off a device without a debugger:

```bash
xcrun devicectl device copy from --device <UDID> \
  --domain-type appGroupDataContainer \
  --domain-identifier group.com.example.app \
  --source Library/Preferences/group.com.example.app.plist \
  --destination ./app_group.plist && plutil -p ./app_group.plist | grep -i weather
```

Confirm the signed artefacts really carry the entitlement:

```bash
codesign -d --entitlements :- .../App.app
codesign -d --entitlements :- .../App.app/PlugIns/WidgetExtension.appex
security cms -D -i .../embedded.mobileprovision | grep -A2 weatherkit
```

Deeper system logs (`weatherd`) need root, which is often unavailable. In practice, writing a breadcrumb string into your App Group data is the most reliable signal.

**Escalation:** if it still fails **>48h** after both the App Services tick and membership
activation, with the entitlement provably in both binaries, open an **Apple Developer
Technical Support** ticket quoting the Team ID, both bundle IDs, and the exact `Code=2`
string.

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
