---
name: leap-agent-guide
description: >
  Apple development skill for Leap — Agent Guide. Use this skill when working on leap-agent-guide tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Leap — Agent Guide

Authoritative technical guide for future agents working on **Leap**, an iOS 26
habit / "daily leap" app whose signature feature is a **Home-Screen widget that
looks transparent without the user turning on iOS "Clear" appearance**.

> **This file is a lean index.** The detail lives in topic files under
> [`docs/agents/`](docs/agents/) (linked in the Guide Map below) so an agent loads
> only the file it needs and context stays small. Keep this index **and** the topic
> file(s) up to date when architecture, build commands, or conventions change.

---

## What Leap is

- A SwiftUI iOS app (deployment target iOS 18+, tuned for iOS 26) plus a
  **WidgetKit extension** that ships **66 widget designs** (each in up to 3 sizes
  and **4 styles**) through one configurable widget. **Style — not design variants —
  is the primary differentiator**: every design is re-skinned across 4 styles
  (Editorial / Minimal / Dot-Matrix / Neon), and the catalog was grown to cover every
  distinct reference face in `docs/widget_research/mocks/tobuild/` rather than shipping
  a single face per idea.
- The widget appears see-through by **baking** the user's chosen wallpaper into the
  widget's own `containerBackground` (there is **no** public iOS API for a truly
  transparent Default-appearance widget). A private-API path that makes the host
  composite the **live** wallpaper exists but is **compiled out by default and must
  never ship** — it puts private class/selector literals in the binary and is a
  **guideline 2.5.1** rejection. It is gated on `LEAP_HOST_TRANSPARENCY` (default
  `0`); verify with the `strings`/`nm` check before every submission — see
  [Transparency](docs/agents/transparency.md).
- **⛔️ Never say "transparent" / "see-through" / "clear" in USER-VISIBLE copy** (App
  Store description, subtitle, promo text, screenshot captions, in-app strings). The
  positioning is **"widgets that blend in"**, which is what the shipping baked path
  actually delivers. Those words live **only** in the App Store *keywords* field,
  which is indexed for search but never displayed, so Leap still ranks for
  "transparent widget" without making a visible claim tied to the 2.5.1 risk.
- The app is a **3-tab** "widget studio": **My Widgets**, **Browse**, **Settings**
  (the old **Wallpaper**/**Style** tab was removed — wallpaper + style are now
  chosen inside the Add/Edit sheet). Users pick a design + style + wallpaper +
  Home-Screen row, save it to their list, then add the matching widget from the
  iOS gallery. **Browse** shows a **curated subset + order** of categories via
  `LeapWidgetCategory.browseOrder` (Clock, Date, Calendar, Weather, Streak, Progress,
  Battery, Storage, Activity, then Goal, Mantra) — Focus / Settings / Screen Time /
  Globe / Sound are hidden there but still exist in the catalog and work as widgets.

## Invariants (true across the codebase — know these before editing)

Enough to make routine edits without opening another file:

- **One configurable widget.** Leap registers a single `LeapWidget` (kind
  `leap.widget`, one `AppIntentConfiguration`, 3 families) in
  `LeapWidget/LeapWidgetBundle.swift` — **NOT** one `Widget` struct per design. Add a
  design by extending `LeapWidgetKind` + a **style-aware** struct in
  `Shared/LeapWidgetContentView.swift` and wiring the dispatcher; give it a
  `signatureStyle`. No new `Widget` struct / pbxproj surgery needed.
- **4 widget styles** — Editorial / Minimal / Dot-Matrix / Neon. There is **no Glass
  style** (`.glass` won't compile). Style is the variety axis.
- **`project.pbxproj` is hand-authored.** Prefer reusing existing files; a `Shared/`
  file must be registered in **both** target membership lists.
- **Keep source ASCII**; gate iOS-only APIs with `#if os(iOS)` / `#available`.
- **Widget content is white-on-wallpaper**, no border/tick lines.
- **App Group** `group.com.sololeap.leap.app`; bundle id `com.sololeap.leap.app`.
- **Monetization = "Leap Premium" (StoreKit 2), one internal "Pro" API — don't rename.**
  **User-facing** strings say **"Leap Premium"**; the **code** API stays **`isPro`**
  (`LeapProduct`, IDs `com.sololeap.leap.app.pro.{monthly,lifetime}` = $0.99/mo + $9.99,
  App-Group mirror `leap.pro.active.v1`) in `Shared/LeapEntitlements.swift`. A **7-day free
  trial** then gates the *studio* (never the daily check-in): `freeWidgetAllowance = 4` free
  widgets (hard cap **8**) + `freePhotoAllowance = 1` custom photo. Trial countdown/lock hits
  the **newest surplus** rows — `savedWidgets` is **newest-first**, so
  `rankOldestFirst = count-1-index` feeds `isFreeWidgetLocked(rankOldestFirst:)`. **The lock
  reaches PLACED Home-Screen widgets too**, not just the in-app list: the extension evaluates
  the shared `LeapEntitlements.isSavedWidgetLocked` (App-Group inputs only — no StoreKit in an
  extension) and renders `LeapLockedFace` (blurred face + lock + "PREMIUM", `widgetURL`
  `leap://premium` → `RootView.onOpenURL` → `.widgetLimit` paywall). **A locked timeline MUST
  collapse to ONE entry** or a 900-entry clock face blows the archive limit. `buildTimeline`
  returns `(timeline:deadline:)` because **`TimelineReloadPolicy` exposes no associated
  date** — a new `return` that reports a wrong deadline silently stops that face locking.
  The trial is latched one-way (`leap.trial.ended.v1` + a clock high-water mark) so winding
  the device clock back cannot revive it; **`debugSetTrialStart` must clear the latch**.
  **The App Group is the ONLY thing the app and the extension share** — *not* the Keychain
  (`LeapSecureStore` sets no `kSecAttrAccessGroup`, so each target gets its own access
  group), not `UserDefaults.standard`, not in-memory state. All Keychain I/O in
  `LeapEntitlements` goes through `secureString`/`secureSet`/`secureRemove`, which **no-op
  in the extension** (`isAppExtension`) — otherwise the extension caches its own stale copy
  of the trial start / expiry latch and a placed widget ignores the app forever. The debug
  plan override lives in the App Group and **`setPro` honours it**, or the next StoreKit
  refresh reverts the mirror and widgets disagree with the app. **When a placed widget
  "ignores" a change, check the App-Group mirror first.** **Premium
  users get a lime PREMIUM badge by the LEAP eyebrow and every upsell entry point is hidden.**
  On-accent icons/text use **`LeapTheme.onAccent`** (see [theming.md](docs/agents/theming.md)).
  A shake + password (`NammaLeap@2026`) **debug panel** in Settings toggles the plan
  (`Leap/LeapDebugPanel.swift`), gated on **`#if DEBUG || LEAP_INTERNAL`** — compiled
  **out** of the public **Release** binary (no panel, no password, no `isPro` override) and
  **into** the release-grade **Internal** build config used for QA/TestFlight. **Never** relax
  that gate to reach public Release. Build/distribute: [build-and-run.md](docs/agents/build-and-run.md)
  ("Build configurations"); IAP deep-dive: [in-app-purchases.md](docs/agents/in-app-purchases.md).
- **⛔️ Every StoreKit await must be bounded, and StoreKit Testing is BROKEN on this
  toolchain.** `AppStore.sync()`, `Transaction.currentEntitlements` and
  `Product.SubscriptionInfo.status(for:)` have **no internal deadline** — an unreachable
  store left Restore spinning for **857 s**. All three go through
  `LeapStoreKitManager.withTimeout`, which is a `withCheckedThrowingContinuation` +
  `NSLock` one-shot **and must not be "simplified" into a `withThrowingTaskGroup` race**:
  a task group awaits every child before returning and `AppStore.sync()` ignores
  cancellation, so that version bounds nothing (it still took 199 s). Separately, **Apple
  bug FB22237318** means the `.storekit` config is never synced to `storekitd` on iOS
  26.3–26.5 simulators, so `SKTestSession` silently vends **no products** — the 11
  `SKTestSession` tests in `LeapIAPTests` **skip**, while `LeapEntitlementChainTests`
  (10 headless tests) proves the rest of the chain. Never state a price StoreKit did not
  return, and never claim a benefit Leap does not enforce (all 67 designs and 4 styles are
  **free**; only the 4-widget and 1-photo caps are gated). Terms of Use + Privacy Policy
  are **required** on a subscription paywall — `Leap/LeapLegalView.swift` is the source of
  truth and generates `docs/legal/*.html`. See
  [in-app-purchases.md](docs/agents/in-app-purchases.md) §0.1 and §8.1.
- **Catalog counts come from `LeapCatalogStats` — never hard-code them.** Browse's header
  and the paywall's social-proof capsule (`PaywallView.catalogProof`, "3,500+ unique widgets
  in Premium") both read `LeapCatalogStats` in `Shared/LeapWidgetContentView.swift`, which
  derives design / style / background / combination counts from the enums, so the two
  screens can never drift and every claim is true by construction (**no invented "N people
  upgraded" social proof** — that is a 3.2.2(i) + UK DMCC risk and needs a server counter
  Leap deliberately does not have). The capsule's 28pt tiles, `mono(11.5)` text and glyph
  offsets are width-critical — see
  [in-app-purchases.md](docs/agents/in-app-purchases.md) §6.5b before touching it.
- **A lapsed subscriber's PLACED widgets lock past the free 4 — but only once the app is
  next opened.** The extension **does** read the entitlement, via the App-Group `isPro`
  mirror (`LeapEntitlements.isProCached`, the default argument to `isSavedWidgetLocked`);
  what it cannot do is *observe* a lapse, because only the app can call StoreKit. So the
  mirror stays stale until Leap is next launched, and until then placed widgets keep
  rendering. After that the 4 oldest stay unlocked and editable, the rest render
  `LeapLockedFace`, and adding stops at the hard cap. Trial expiry, by contrast, is exact —
  the extension can compute it from App-Group inputs alone. This soft landing is deliberate —
  see [in-app-purchases.md](docs/agents/in-app-purchases.md) §6.5c before "fixing" it.
- **Full-width segment chips need an explicit `contentShape`.** A `Button` whose label uses
  `.frame(maxWidth: .infinity)` + `.background` is hit-tested on the **text glyphs**, not the
  pill — `LeapSegment` and the Settings appearance picker both carry
  `.contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))` for this reason.
- **Live Calendar/Weather data + permission-on-add.** The Calendar (EventKit) and Weather
  (WeatherKit + CoreLocation) families render real data via `Shared/LeapLiveData.swift`;
  OS permissions are requested **only when that widget is added** (`AddWidgetSheet.save()`
  → `requestLiveDataAccess(for:)`), never at launch, and cached to the App Group for the
  extension. **WeatherKit is ENABLED and CONFIRMED SERVING live data** (paid Apple
  Developer Program, team `D2Z89UU4R7`): `com.apple.developer.weatherkit` is live in
  **both** `.entitlements` files and both signed binaries, and
  `xcodebuild -allowProvisioningUpdates` registers the **capability** on both App IDs
  automatically — no Xcode.app step. **But the capability alone is NOT enough, and this
  bit the project for hours**: WeatherKit ALSO has to be ticked under the App ID's
  **App Services** tab in the developer portal — a *separate* tab from Capabilities that
  authorises the App ID **server-side**, which `xcodebuild` never touches. Until it is,
  `WeatherService.weather(for:)` fails with
  `WeatherDaemon.WDSJWTAuthenticatorServiceListener.Errors Code=2` **even though the
  entitlement is provably in both binaries and both profiles**, and every weather face
  silently falls back to the **deterministic date-based placeholder**
  (`LeapWeatherSample`). Allow ~30 min for propagation after enabling; a **brand-new**
  membership can lag 24-48h. **The Simulator is NOT exempt and a `Code=2` there is a REAL
  signal** — it runs on the host Mac's `weatherd` and fetched live data the moment App
  Services was ticked, so debug it rather than dismissing it (an earlier note claiming the
  Simulator can never authenticate was wrong and cost hours). **Weather also never
  refreshes while Location is `notDetermined`** — `refreshLiveDataIfAuthorized()` gates on
  it, so the user must add a weather widget once (which prompts) before foreground
  refreshes do anything. **WeatherKit vends NO air quality** — AQI was removed outright
  (do not re-add or synthesise one). **Apple REQUIRES the Apple Weather mark + legal link
  wherever WeatherKit data shows, widgets included: the mark is overlaid from ONE place —
  `LeapWidgetContentView.styled(_:)`, gated on `kind.showsWeather && !weatherUnavailable`
  — so a new weather face can never ship without it; keep every weather design padded
  >= 14pt so it does not collide, and never move the overlay into a face.** The legal
  `Link` lives in Settings → About. **The tile is clipped to a rounded rect, so a corner
  mark gets EATEN BY THE CURVE** — `LeapWidgetSize.weatherMarkInset` (small `(13,8)` /
  medium `(17,9)` / large `(20,12)`) clears `(R-dx)^2 + (R-dy)^2 <= R^2` with >= 30%
  margin at radii 22/24/30, **and** both in-app clip sites use
  `LeapWidgetSize.previewCornerRadius(fitting:)` so a downscaled Browse miniature shrinks
  its corner too (a `[.large]`-only tile at scale 0.42 otherwise presents a ~71pt arc no
  inset can escape). **Keep the bottom-trailing corner of every weather design empty.**
  **Never round Fahrenheit before
  converting to Celsius**: store the unrounded reading in `LeapExactTemps` and let
  `converted(to:)` round once, or the widget lands a degree off Apple Weather.
  **⛔️ A PLACED widget NEVER shows fabricated weather.** The synthetic
  `LeapWeatherSample.make()` is indistinguishable from a live reading, so it survives only
  where it is honestly a *preview* — in-app Browse/Add tiles and the WidgetKit gallery
  (`context.isPreview`). On a placed widget the extension sets
  `LeapSnapshot.weatherUnavailable = (weather == nil)` and `content(now:)` intercepts
  before the 66-case `face(now:)` switch to draw `LeapWeatherUnavailableFace`; the three
  non-`.weather` combos (`greetingClock`, `sceneClock`, `dateTemp`) branch inline to `--`.
  Full guide (portal setup, attribution, pitfalls, diagnostics):
  **[weatherkit.md](docs/agents/weatherkit.md)**; signing commands in
  [build-and-run.md](docs/agents/build-and-run.md); see also
  [architecture.md](docs/agents/architecture.md).
- **⛔️ NEVER block `timeline(for:in:)` on an unbounded location/network call** — the #1
  "widget goes blank / never loads / could not run" bug. The extension must pass
  `allowOneShot: false` (no CoreLocation one-shot — it can hang forever in an extension),
  wrap refreshes in `leapRefreshBounded`, and always render from the cached `LeapLiveStore`.
  The Edit-Widget picker entity (`LeapSavedWidgetEntity`) shows a **real preview** via a
  **tiny size-guarded thumbnail** (`LeapThumbnailStore` JPEG ~6–8KB, embedded as
  `DisplayRepresentation.Image(data:)` only when `<= maxBytes`, else an SF-Symbol fallback) —
  keep it tiny: an oversized image (the old 960×960/~1MB) bloats the archived selection and
  blanks the widget. See the ⛔️ box in
  [realtime-widgets.md](docs/agents/realtime-widgets.md).
- **Battery % is 5%-granular and that is NOT fixable — do not try again.** Since iOS 17
  (still true on 18 and 26) UIKit deliberately rounds `UIDevice.batteryLevel` to **5% steps**,
  so battery faces sit on 85 / 80 / 75. This was investigated end-to-end and is closed:
  the only source of a 1% charge is the private `IOPS*` IOKit family, whose three symbols are
  named **verbatim** in Apple's canned **2.5.1** rejection (`dlsym` hides them from the import
  table but NOT from a `strings` scan), and the **public** IOKit surface is redacted — an
  on-device probe using only SDK-declared symbols got `IOPMPowerSource` /
  `AppleSmartBattery` back with just `{BatteryInstalled, ExternalConnected}`, no capacity keys
  at all. So Leap reads the plain public `UIDevice.batteryLevel` on **one code path for every
  build** — no private API, no Debug/Internal-vs-Release divergence. The product now **says
  so**: `LeapWidgetCategory.footnote` surfaces an asterisked caveat under the Battery header
  in Browse and under the preview in the Add/Edit sheet. Full evidence in
  [status-and-history.md](docs/agents/status-and-history.md).
- **⛔️ Second hands tick on a DENSE TIMELINE, and the hard limit is the timeline
  ARCHIVE SIZE — which is far stricter on a DEVICE than in the Simulator.** A placed
  widget is a baked archive: no extension code runs, so `.rotationEffect` is frozen
  *within* an entry and a moving hand can only advance when the **entry** changes. Clock
  faces therefore ship `leapSecondHandEntries` (**900**) entries `leapSecondHandStep`
  (**2s**) apart — a 30-minute DENSE RUN and ~48 reloads/day, the same budget as the old
  180 x 10s config — **and that is enough for CONTINUOUS motion, because WidgetKit
  INTERPOLATES animatable modifier parameters BETWEEN entries.** Apple: *"Widgets and Live
  Activities support all built-in SwiftUI transitions and animations"*, with a **2-second
  maximum animation duration**. So a `.linear(duration: 2)` on the hand's
  `.rotationEffect` bridges the whole 2s gap and the hand **glides at full frame rate** —
  device-confirmed. `leapSecondHandStep` must stay at **2** precisely because of that 2s
  cap: a wider spacing could not be bridged and the hand would glide, stall, glide.
  **⚠️ The catch: `LeapCheckInWidget.swift` DISABLES animation globally** —
  `.animation(nil, value: entry.date)` on the content `Group` and on the
  `containerBackground`, plus `.contentTransition(.identity)` in `LeapWidget.body`. That is
  **deliberate and must stay** (the default cross-dissolve dipped static gradients to ~0.75
  alpha and made antialiased tick strokes shimmer). **Opt individual moving elements back
  in at the LEAF** with an inner `.animation(_:value:)` — confirmed to override the outer
  `nil`. That is exactly what `LeapLiveSecondHand.sweep` does. Honour
  `isLuminanceReduced` (no animation in Always-On). **⛔️ The duration MUST equal the entry
  spacing and must NOT be made context-dependent** — shortening it outside the widget host
  (`isWidgetHost ? leapSecondHandStep : 1`) put every hand back to a 2s step, because a 1s
  animation over a 2s gap glides for a second then freezes for a second. It compiles, looks
  fine in-app, and regresses all three faces silently.
  **EVERY second indicator glides — including the Seconds face's lit bezel mark.** Making
  it *step* onto its 60 printed ticks was tried on device with a full **1800 x 1s**
  timeline (a real entry per position) and it **still stepped every 2s**, because the host
  will not present entries faster; that was reverted, and the mark now sweeps too.
  Sub-second motion is out of reach: the only public
  views iOS repaints faster are `Text(timerInterval:)` and `ProgressView(timerInterval:)`,
  and **neither can rotate a hand**. WidgetKit archives the **whole view tree once per
  entry**, so anything a face draws is multiplied by 900; over the limit chronod logs
  `reload: failed with too large timeline archive <bytes>` → `CHSErrorDomain 1050` and
  **strands the tile on its placeholder for an hour** — that *is* the "widget only shows
  the loading screen" bug. **The Simulator is far more permissive than a device** (sim:
  10.32MB accepted / 11.30MB rejected; device: 2.60MB rendered but ~4.0MB did not), so
  **treat ~1.5MB as the ceiling and always confirm on hardware.** Three rules are
  mandatory for any face on a dense timeline:
  1. **Merge repeated moving primitives.** Hour + minute hands are ONE path
     (`LeapClockHands`), not two rotated capsules (~128 B/entry each).
  2. **Never draw N repeated shapes.** 60 rotated `Capsule` tick marks cost ~10KB/entry;
     merging them into one `Path` still cost ~13KB. Use **`LeapTickMarks`**, which strokes
     **ONE** dashed circle (`LeapDashArc`) — cost is flat in the mark count. Same for any
     `ForEach`-built art: Dot-Matrix hands are one dash-stroked `LeapDottedRay`.
  3. **Never use `Text(_, format:)` / `Text(.currentDate, format:)` on a dense timeline.** A
     `Date.FormatStyle` serialises its calendar + locale + time zone into **every** entry
     (~5KB each). One entry per tick makes `Text(verbatim:)` exact and nearly free. For the
     same reason a second-hand face must pass **`seconds: false`**: text cannot be
     interpolated, so a `:SS` readout can only step at 2s and reads as a stopped clock
     beside a gliding hand.
  4. **Every clock needs a FREEZE BUFFER, and a requested reload is not a guaranteed
     reload.** When a reload is throttled or batched WidgetKit does not re-run the
     extension — it keeps presenting what is already archived, so a face whose entries ran
     out sits at a **stale but correct-looking time** until the user opens Leap (a
     *foreground* reload is budget-exempt, which is why that unsticks it). Ordinary clocks
     always had 180 per-minute entries = 3h of cover; second-hand faces archived only their
     30-minute dense run and froze. They now append a **graduated** buffer beyond it —
     per-minute for `leapClockTailFineMinutes` (30) then every 5 min out to
     `leapClockFreezeHorizon` (3h), ~54 entries / **+6%** — with policy `.after(denseEnd)`
     so the reload cadence is UNCHANGED and the buffer is never reached unless a reload was
     actually missed (it must not be: at those spacings the hand cannot glide). Anchor
     buffer entries on `minuteStart`, not the second-floored `start`.
  Also: **angle wrapping is a two-sided trap.** The second hand's angle
  (`LeapSecondAngle.degrees`) WRAPS to `0..<360` and the face suppresses the animation on
  the one decreasing step via `LeapSecondAngle.animates(at:step:)`; the hour/minute hands
  (`LeapHandAngle` - monotonic, whole-minute-snapped, zone-aware, allocation-free) never
  wrap. WidgetKit interpolates NUMERICALLY between entries, so an *animated* wrap is drawn
  as a real backwards spin (`second % 60` swept the hand BACKWARDS once a minute), but a
  monotonic SECOND angle is proportional to absolute time and the host skips entries, so
  unlocking after 45 min spun it 45 times. Also: buffer entries set
  `LeapEntry.secondsLive = false` and second indicators hide themselves there, because
  every buffer date is minute-aligned and the hand would park at 12.

  **⛔️ Do NOT flatten the dial into an `ImageRenderer` bitmap. Tried TWICE, reverted
  twice — do not try a third time.** It is tempting (a shared `Image` node costs a flat
  ~228 B/entry against ~1100–1600 B/entry for drawn dial art, and it took the worst face
  from 2.008MB to 1.148MB), but `ImageRenderer` rasterises in a **fresh environment** and
  the bitmap comes out blank or wrong-appearance **on the Home Screen only**, while the
  live hands drawn over it stay correct — the tile keeps its hands and **loses its dial
  ring, tick marks, numerals and date badge**. Pre-resolving every `Color` to concrete
  sRGB and keying the cache on the resolved components + `colorScheme` did **not** save
  it (that fixed only the first, dark-mode-specific symptom). It also cannot be caught in
  the Simulator or in-app, because flattening is only ever on in the widget host. **Face
  art must be drawn LIVE.** Keep the entry count down instead — it is the only reliable
  lever. Micro-optimising the tree does not pay either: pass-through `ModifiedContent`
  wrappers, `.resizable()`/`.frame()`, drop shadows, the ~24 `.environment` modifiers in
  `styled(_:)` and the 66-case `content(now:)` switch are **all measured at ~0 bytes**,
  and `LeapEntry`'s own fields are not archived per entry.
  Also: the second-hand angle **wraps to `0..<360`** (`LeapSecondAngle.degrees` =
  `secondOfMinute * 6`, ignoring the time zone) and the face refuses to ANIMATE the one
  decreasing step per minute (`LeapSecondAngle.animates(at:step:)`). WidgetKit interpolates
  `.rotationEffect` NUMERICALLY between entries, so **any animated wrap** is rendered as a
  real backwards spin: `second % 60` swept the hand anti-clockwise once a MINUTE, and
  counting from local midnight just moved it (1440 backwards revolutions at midnight, 60
  more at DST). But going fully **monotonic** trades that for a worse bug - the value then
  tracks absolute time and the host does not present every entry, so a 45-minute lock
  animated 45 revolutions on unlock. Wrapping + the gate bounds any resume to one sub-360
  deg flick. Second indicators also hide (`.opacity`) on freeze-buffer entries
  (`LeapEntry.secondsLive == false`), which are minute-aligned and would park the hand at 12.
  Result: worst clock face **24MB → ~2.0MB**. Also researched and **rejected**: SwiftUI's private
  `_clockHandRotationEffect` (how Clockology/Quike do it — App Review guideline
  **2.5.1** risk) and the public timer-text + custom-font ligature trick (~8 FPS, but
  needs 16 generated fonts — unnecessary once the hand glides). Also disproven, do not
  retry: a **custom**
  `DiscreteFormatStyle` compiles but is **never re-evaluated** in the host (0 changed
  pixels / 8 frames), and stacked live `ProgressView(timerInterval:)`s cap out at ~8 (10+
  strand the tile). For per-second motion *within* one entry (e.g. a blinking `:`) the only
  known public route is the **timer-text + custom-font mask** trick — not implemented
  here. Never return `policy: .never` for an unconfigured placement either — it can never
  recover. See [realtime-widgets.md](docs/agents/realtime-widgets.md), and
  **[clock-faces.md](docs/agents/clock-faces.md) before adding or editing any clock face**.
- **The Simulator masks two things** — live transparency (never relaunches the
  extension; renders custom wallpaper black) and oversized-timeline drops. Verify
  both on a **physical device**.
- **Telemetry = anonymous Firebase/GA4, app target only (LIVE + verified).** All analytics
  goes through `Shared/LeapTelemetry.swift` (single source of truth for event/param/group
  names) and is gated behind `#if canImport(FirebaseAnalytics) && LEAP_ANALYTICS`. The
  **`LEAP_ANALYTICS`** flag is defined **only on the Leap app target** (Debug/Release/Internal)
  — **NEVER** the widget extension, which would link Firebase in twice and double-count users.
  The extension only bumps App-Group counters (`LeapWidgetMetricsStore`), drained to GA4 by the
  app on foreground. **Anonymous only** — no `setUserID`, IDFA/ATT, or PII, ever. Project
  **`leap-widgets`** (account `sololeapinc@gmail.com`, cut over 2026-07-26 from
  `sololeap-leap`; GA4 has no property merge, so the old data stays behind as an archive);
  config at `Leap/GoogleService-Info.plist`. See
  [telemetry.md](docs/agents/telemetry.md).
- **Feedback is a SECOND, SEPARATE Firebase project — don't merge it with telemetry.**
  Settings → **Send Feedback** writes a user report into **`leap-feedback`** Firestore, one
  **collection per category** (`feedback_bug` / `feedback_feature` /
  `feedback_widget_request` / `feedback_other`) so triage is a single console click. It uses
  the **REST `:commit` endpoint over `URLSession` — no Firestore SDK** (gRPC/abseil/leveldb
  in a hand-authored pbxproj for one rare write) and **no Firebase Auth** (Identity Platform
  needs billing; `BILLING_NOT_ENABLED` on Spark). Safety comes from **create-only security
  rules**: clients can never `read`/`list`/`update`/`delete`, so the in-app history is served
  from a local App-Group **outbox** and any verification needs an **owner OAuth token**. Both
  projects register the same bundle id, so the **filenames are the only separator** —
  `Leap/GoogleService-Info.plist` is analytics and is auto-loaded by `FirebaseApp.configure()`,
  while `Leap/GoogleService-Info-Feedback.plist` is read by name only. **Never rename it.**
  Message text, email and images go **only** to Firestore, never to GA4. See
  [feedback.md](docs/agents/feedback.md).

## Guide map

Open the file that matches your task; each is self-contained.

| Topic | File | Open it when you need… |
|-------|------|------------------------|
| Architecture & data flow | [docs/agents/architecture.md](docs/agents/architecture.md) | target/file layout, the 66-design catalog + gallery registration, how in-app changes reach placed widgets |
| Build, run & install | [docs/agents/build-and-run.md](docs/agents/build-and-run.md) | exact sim + device build/install/launch commands, UDIDs, signing, device flag reads, live-data permissions + WeatherKit paid-team signing |
| Transparency mechanism | [docs/agents/transparency.md](docs/agents/transparency.md) | to touch `LeapWidgetTransparency.mm` or `LeapWidgetBackground` (deep-dive: [docs/TRANSPARENT_WIDGETS.md](docs/TRANSPARENT_WIDGETS.md)) |
| Theming (light/dark) | [docs/agents/theming.md](docs/agents/theming.md) | color-scheme handling, chrome tokens, white widget content |
| Conventions | [docs/agents/conventions.md](docs/agents/conventions.md) | how to add a design, style/comment/ASCII rules |
| Realtime / live widget updates | [docs/agents/realtime-widgets.md](docs/agents/realtime-widgets.md) | to make a placed widget change over time (timelines, self-animating views, reloads) |
| **Clock / watch faces** | [docs/agents/clock-faces.md](docs/agents/clock-faces.md) | **to add or edit ANY `.time` face** — every registration point, second-hand timelines, the animation-bridging glide + its 3 traps, the archive budget, the do-not-retry list, and the device validation checklist |
| **WeatherKit / weather faces** | [docs/agents/weatherkit.md](docs/agents/weatherkit.md) | **to add or edit ANY weather face, or to debug WeatherKit** — how `weatherd` mints the JWT, the two-tab portal setup (Capabilities **and** App Services), what the Simulator can and cannot prove, Apple's **mandatory attribution** (one overlay + the corner-arc inset rule), the **no-fabricated-data policy** for placed widgets, the AQI + Celsius-rounding traps, the symptom→cause→fix pitfall table, and the `leap.debug.weather.v1` breadcrumb |
| In-app purchases (Apple IAP) | [docs/agents/in-app-purchases.md](docs/agents/in-app-purchases.md) | to monetize with StoreKit 2 — product model, entitlement gating, paywall, App-Group mirror for the widget, testing |
| **Payment integration — as-built record** | [docs/agents/payment-integration.md](docs/agents/payment-integration.md) | **what state payments are actually in** — the 11 audit fixes, the live App Store Connect records + IDs, the live-price paywall, the per-territory reference pricing, the traps (FB22237318 skip probe, unaligned price tiers) and the 4 account-holder steps still blocking a sale |
| Usage telemetry (Firebase GA4) — **LIVE + verified collecting** | [docs/agents/telemetry.md](docs/agents/telemetry.md) | to add/change/debug anonymous analytics — event taxonomy, call sites, the widget-extension counter bridge, the `LEAP_ANALYTICS` flag, Firebase/GA4 setup (project `leap-widgets`), verification + dashboards (catalog: [docs/telemetry/telemetry.html](docs/telemetry/telemetry.html)) |
| Feedback & Contact Us | [docs/agents/feedback.md](docs/agents/feedback.md) | to change the Settings feedback flow — the `leap-feedback` project, per-category Firestore collections, create-only rules, the REST transport, the offline outbox, screenshots, and how to triage |
| Simulator UI automation | [docs/agents/simulator-automation.md](docs/agents/simulator-automation.md) | to drive the sim with CGEvent taps, per-family snapshot gotchas |
| Status & history | [docs/agents/status-and-history.md](docs/agents/status-and-history.md) | current status + the issues / refinements / follow-up changelog |
| QA & multi-agent reviews | [docs/agents/qa-and-reviews.md](docs/agents/qa-and-reviews.md) | to run/audit a 3-agent functional+code review, or read the record of bugs found & fixed (plus validated non-bugs and the deferred Weather/StoreKit item) |
| **App Store — build & upload** | [docs/agents/app-store-release.md](docs/agents/app-store-release.md) | **to ship a build to App Store Connect** — the ASC API client + its quirks, signing/provisioning for both targets, archive→export→verify (the Release-vs-Internal debug-panel check), versioning, `altool` upload and how to diagnose an upload that never becomes a build |
| **App Store — listing & ASO** | [docs/agents/app-store-listing.md](docs/agents/app-store-listing.md) | to write or change store metadata — the **as-built live strings** (§0), how App Store search actually indexes (name + subtitle + keywords only, so the three must share **zero** tokens), field limits, the evidence-based category call, keyword rules incl. Guideline 2.3.7, screenshot specs + the `screenshotDisplayType` enum, promo text, and the **undocumented `/v1/nominations` featuring-nomination API** (§9) |
| **App Store — submission** | [docs/agents/app-store-submission.md](docs/agents/app-store-submission.md) | **before submitting for review** — the blocker list, App Privacy (Leap *does* collect: GA4 + feedback), attaching IAPs to the first submission, the Guideline 2.5.1 private-API risk, age rating, territories, the `reviewSubmissions` calls and a troubleshooting table |
| **App Store — screenshots** | [docs/agents/store-screenshots.md](docs/agents/store-screenshots.md) | to regenerate or change a marketing screenshot — the one-command generator, the 3 frame treatments and which capture may wear a device body, the squircle corner knobs (the **exponent**, not the radius, controls roundness), the trap list, and the verify-then-upload loop |

**Other docs:** [`docs/STATUS.md`](docs/STATUS.md) (live checklist),
[`docs/PLAN.md`](docs/PLAN.md) (roadmap),
[`docs/TRANSPARENT_WIDGETS.md`](docs/TRANSPARENT_WIDGETS.md) (transparency deep-dive).
