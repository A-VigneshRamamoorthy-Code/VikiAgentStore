---
name: architecture
description: >
  Apple development skill for Architecture & data flow. Use this skill when working on architecture tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Architecture & data flow

Repo/target layout, the 66-design catalog + gallery registration, and how in-app
changes reach placed widgets.

> Part of the **[Leap Agent Guide](../../agents.md)**. See also:
> [build-and-run.md](build-and-run.md), [transparency.md](transparency.md),
> [conventions.md](conventions.md).

---

## Targets & layout

```
Leap.xcodeproj
├─ Leap/            App target (SwiftUI UI layer)
├─ LeapWidget/      WidgetKit extension (Widget structs, provider, intent)
└─ Shared/          Code compiled into BOTH targets (models, catalog, wallpaper)
```

- **`Shared/` files are added to both targets.** In `project.pbxproj` each shared
  file appears twice in `PBXBuildFile` (app build files are `DA…`, widget build
  files are `DD…`). When adding a shared file you must register it in **both**
  target membership lists or one target won't see it.
- **`LeapWidget/LeapWidgetTransparency.mm`** is the private-API host-transparency hook
  (see [transparency.md](transparency.md); full write-up in
  `docs/TRANSPARENT_WIDGETS.md`) — **widget target only**, compiled `-fno-objc-arc`
  (MRC). In `project.pbxproj` it is fileRef `FC0000000000000000000006`, buildFile
  `DD30000000000000000000AA` (with the `-fno-objc-arc` `COMPILER_FLAGS`), in the
  widget Sources phase `PW01000000000000000000AA` and group
  `G000000000000000000WIDGT`. Already wired; no further pbxproj surgery needed.
- **`Shared/LeapLiveData.swift`** is the **live widget-data layer** (real Calendar +
  Weather content: models, App Group cache, and the CoreLocation / WeatherKit / EventKit
  services) — a `Shared/` file compiled into **both** targets. See "Live widget data
  (Calendar + Weather)" under Data flow below.
- `project.pbxproj` is **hand-authored** (not the Xcode 15 "synchronized folders"
  feature). Prefer reusing existing files over adding new ones to avoid pbxproj
  surgery. New shared types → existing `Shared/*.swift`; new widget **designs** →
  `Shared/LeapWidgetContentView.swift` (style-aware struct + dispatcher, no new
  `Widget` struct); new app UI → `Leap/HomeView.swift`. The **Browse** tab is split
  per category under `Leap/Browse/` — `BrowseTab.swift` (container), shared
  `BrowseComponents.swift` (`BrowseTile` + `BrowseCategoryRow`), and one
  `Browse<Category>Section.swift` per `LeapWidgetCategory` (Focus/Streaks/Time/
  Calendar/Progress/Signal), so each category is edited in isolation. `BrowseTab`
  iterates **`LeapWidgetCategory.browseOrder`** (a curated list — not `allCases`) so
  editing that one array reorders or hides Browse categories; the header design count
  follows it. Empty categories are still skipped.

## The 66-design catalog (consolidated — style is the variety axis)

Single source of truth: **`Shared/LeapWidgetContentView.swift`**.

- `LeapWidgetKind` — **66-case** `String` enum (the catalog, consolidated down from
  21 near-duplicate designs, then grown by 3 permission-free faces — `dayTimer`,
  `progressBar`, `storage` — per `docs/widget_ask.md`, then by **25 reference faces**
  from `docs/widget_research/mocks/tobuild/` (6 clocks, 6 weather, 4 date/calendar,
  6 system/battery/progress, 2 fitness, 1 music), plus `timeNow` (a Day-Timer-styled
  live current-time clock); **style**, not design variants,
  still carries the variety). Each case exposes `widgetKind`, `title`, `blurb`,
  `category`, `supportedSizes`, `previewSize`, `isInteractive`, **`signatureStyle`**,
  and the realtime/edit **capability flags** `showsLiveTime` / `showsWeather` /
  `showsCalendar` / `usesClockFormat` / `usesTempUnit` (see the live-data section).
- `LeapWidgetView(kind:snapshot:size:interactive:style:)` — the dispatcher that
  renders the correct private design struct, injecting `\.leapStyle`. **Widget
  content is white-on-wallpaper with NO corner ticks / border lines.**
- Every design is **style-aware** (**4 styles**: Editorial / Minimal / Dot-Matrix /
  **Neon**), composed from the style kit (`LeapNum`, `LeapProgressArc`,
  `LeapProgressRing`, `LeapDotMatrixText`, `TapPill`, `BrandMark`, …) — don't
  hardcode fonts. **Neon** (deep-lime glow) was added per issue V14; even shared
  chrome like `BrandMark`, `TapPill`, and the `CheckInDesign` prompt vary per style
  so the 4 styles are visibly distinct (issues V5/V7). There is **no Glass style** —
  `LeapWidgetStyle` has exactly these 4 cases (`.glass` will not compile).
- **`signatureStyle`** — each kind names a showcase style used as its default in
  Browse/Add (e.g. Clock → Dot-Matrix, Big Date → Minimal, Streak/Progress Ring/Leap
  Counter → Neon, Goal Dashboard → Minimal). Selecting a showcased design
  pre-selects that style (issue V13).
- `LeapWidgetCategory` (**16**): `focus, streaks, time, date, calendar, progress, goal,
  storage, settings, globe, battery, screenTime, signal, weather, fitness, music`.
  `LeapWidgetKind` + its `.category` in `LeapWidgetContentView.swift` is the
  authoritative catalog — it has grown past the table below, which highlights the
  original categories plus the live-data (Calendar / Weather) families.
  **Browse display** is driven by a separate **`LeapWidgetCategory.browseOrder`** list
  (Clock, Date, Calendar, Weather, Streak, Progress, Battery, Storage, Activity, then
  Goal, Mantra); `focus/settings/screenTime/globe/music` are intentionally omitted from
  Browse. This is decoupled from the enum's declaration order so widget logic that
  iterates `allCases` (timelines, categorization) is unaffected.
- `LeapWidgetSize` (`small, medium, large`).

| Category | Kind (`rawValue`) — title — sizes — signature style |
|----------|------------------------------------------------------|
| focus | `checkIn` — Daily Check-in — S·M (interactive) — Editorial |
| streaks | `streakFlame` — Streak — S·M — Neon · `weekDots` — Week Dots — S·M — Minimal · `activityGrid` — Activity Grid — M·L — Dot-Matrix |
| time | `clock` — Clock — S·M — Dot-Matrix · `analogClock` — Analog Clock — S·M (tick face + baton hands + on-face accent second hand + date chip; medium adds a live digital readout) — Editorial · `bigDate` — Big Date — S·M — Minimal · `dayTimer` — Day Timer — S·M (live `Text(timerInterval:)` countdown to midnight) — Neon · `flipClock` — Flip Clock — S·M (stacked HH/MM flip card; honors the per-widget **12h/24h** option) — Editorial |
| calendar | `monthGrid` — Month — M·L — Editorial · `agenda` — Agenda — M·L (**real EventKit events**, "Nothing scheduled" empty state) — Minimal · `daySpine` — Day Spine — M·L (**real EventKit events**) — Editorial |
| progress | `goalDashboard` — Goal Dashboard — L — Minimal · `progressRing` — Progress Ring — S·M (elapsed Monday-Sunday week) — Neon · `yearProgress` — Year Progress — S·M — Minimal · `progressBar` — Progress Bar — S·M (curve-free elapsed-week bar) — Minimal |
| signal | `mantra` — Mantra — M·L (custom text) — Editorial · `leapCounter` — Leap Counter — S·M — Neon · `storage` — Storage — S·M (real device capacity via `LeapSystemInfo`, no permission) — Neon |
| weather | `weather` · `weatherNow` · `rainWindow` · `weatherGraph` · `forecastRow` · `sunArc` · `airBody` · `windCompass` · `skyCondition` (Sky — weekday · condition · temp, centered) — 9 designs, **real Apple WeatherKit** for the user's location (falls back to a **deterministic date-based placeholder** when WeatherKit is disabled/unavailable; **needs a paid team** — re-enable runbook in [build-and-run.md](build-and-run.md)); all honor the per-widget **°C/°F** option |

**The leap curve (`LeapProgressArc`, the swooping lime quad-curve) is retained ONLY
where it already existed:** Year Progress (all styles), Progress Ring (Editorial),
and the medium Clock. **Do NOT add it to other designs** (e.g. Goal Dashboard has
none) — a user correction: "retain the curve for the ones which already existed,
don't add it to all."

### Gallery registration
Leap registers **ONE configurable widget** (`LeapWidget`, kind `"leap.widget"`)
in **`LeapWidget/LeapCheckInWidget.swift`** (a single `AppIntentConfiguration`,
3 families) — **not** one struct per design. **`LeapWidget/LeapWidgetBundle.swift`**
(`@main`) returns just `LeapWidget()`. The design + style + wallpaper + slot +
transparent are chosen via `LeapWidgetConfigIntent` (the iOS **Edit Widget**
sheet). Adding a design = extend `LeapWidgetKind` + a design struct; no pbxproj
surgery and no new `Widget` struct needed.

## Data flow & "changes reflect on the widget"

- **App Group** `group.com.sololeap.leap.app` (`Shared/LeapModel.swift`).
  UserDefaults keys:
  - `leap.wallpaper.kind.v1` — global wallpaper choice
  - `leap.widget.slot.v1` — global Home-Screen row (top/middle/bottom)
  - `leap.wallpaper.custom.stamp.v1` — bump to invalidate the cached custom image
  - `leap.library.v1` — the user's saved-widget list (`LeapSavedWidget[]`)
  - `leap.state.v1` — streak state (`doneToday`, `streak`, `bestStreak`,
    `freeWidgetCredits`; daily reset + 7-day free-widget stub, see F3 in
    [status-and-history.md](status-and-history.md))
  - `leap.background.style.v1` — global default widget style
  - `leap.appearance.v1` — System/Light/Dark (app-only, `UserDefaults.standard`)
  - `leap.onboarding.done.v1` — onboarding completion (app-only)
- **Per-saved-widget fields** live inside the `leap.library.v1` JSON, not as
  separate defaults: `opensApp` (tap launches Leap vs. stays interactive — F4/F5),
  `mantra` (custom Mantra text with a default — F7), and the **display options**
  `clockFormat` (`LeapClockFormat`: system/12h/24h) + `tempUnit` (`LeapTempUnit`:
  system/C/F), decoded with `decodeIfPresent` for back-compat
  (`Shared/LeapWallpaperStore.swift`).
- **Per-widget display options** (`clockFormat`, `tempUnit`) surface as segmented
  controls in the **Add/Edit sheet** (`AddWidgetSheet`, `Leap/HomeView.swift`):
  a **CLOCK FORMAT** (12H/24H) picker shown when `kind.usesClockFormat(size:)` - i.e.
  any `.time` face that actually prints an hour, including World Clock, and Analog Clock
  only at `.medium` where a digital readout sits beside the dial; hidden for the bare
  dials (`analogClock` small, `segmentClock`), `dayTimer` and `wordClock` where it is a
  no-op - and a **TEMPERATURE** (AUTO/C/F) picker shown when
  `kind.usesTempUnit` (= `showsWeather`: every `.weather` face **plus** the weather
  combos `greetingClock` / `sceneClock` / `dateTemp`). Both enums
  live in `Shared/LeapBackgroundStyle.swift`; the value threads
  `LeapSavedWidget` → `LeapEntry` (`LeapWidget/LeapCheckInWidget.swift`) →
  `LeapWidgetView` → `.environment(\.leapClockFormat / \.leapTempUnit)`, and each
  design reads it via `@Environment`. `.system` follows the device locale
  (24h / °C on a metric device). Weather temps are canonical Fahrenheit;
  `LeapWeatherSample.resolve(unit:)` applies `.converted(to:)` for display.
- **`LeapWidgetConfigIntent`** (`Shared/LeapIntents.swift`) params `background`,
  `wallpaper`, `slot` are **OPTIONAL**. The provider uses `param ?? store value`.
  → A freshly added widget (nil params) **follows the app's global store** and
  updates on `WidgetCenter.shared.reloadAllTimelines()`; editing a widget sets a
  per-widget override. This is why in-app changes reflect on placed widgets.
- Custom wallpaper: `LeapWallpaperKind.custom` loads a PNG persisted in the App
  Group container; app + widget render identical pixels so the bake still lines up.
- **Deleting a saved widget must also delete its side data.** `LeapCounterStore` keeps a
  per-widget day-counter record keyed by widget id; those records used to survive the
  widget forever and grow the App Group defaults without bound.
  `LeapViewModel.removeWidget` now calls `LeapCounterStore.remove(_:)`, and `prune(keeping:)`
  sweeps orphans left by older builds. **`prune` must run AFTER `savedWidgets` has been
  reassigned** — running it against the pre-delete list deletes counters that are still live.
  Any future per-widget store needs the same delete + prune pair.
- **`BrowsePreviewCache` is bounded.** Browse renders 66 designs x 4 styles; the preview
  cache had no cap and no eviction, so scrolling the catalog grew it without limit. It is now
  an LRU with a fixed cap that also purges on `UIApplication.didReceiveMemoryWarningNotification`.
  Don't reintroduce an unbounded `[Key: Image]` dictionary here.

## Live widget data (Calendar + Weather)

The **Calendar** and **Weather** families render **real** data; every other design uses
permission-free device/sample data. The pipeline lives in
**`Shared/LeapLiveData.swift`** (unless noted):

- **Models** — `LeapWeatherData` (temp, condition, symbol, hi/lo, feels-like, hourly,
  7-day, sun, UV, humidity, wind; **no AQI** — WeatherKit has none, so `aqi = -1` and
  designs render `--`) and `LeapCalendarEvent` (start / title / hex color).
- **Services** — `LeapWeatherService` (CoreLocation via `LeapLocationProvider` →
  WeatherKit, guarded `#if canImport(WeatherKit)` / `@available(iOS 16)`) and
  `LeapCalendarService` (EventKit `requestFullAccessToEvents`, **today's non-all-day
  events**, sorted by start). Each exposes `requestAccessAndRefresh()` (ask permission
  then fetch) and `refresh()` (fetch only if already authorized).
- **App Group cache** (`LeapLiveStore`) — `leap.live.weather.v1`, `leap.live.events.v1`
  (+ `leap.live.events.day.v1` daystamp guard so a stale day reads empty),
  `leap.live.coord.lat/lon.v1`. **Both app and extension read it.**
- **Into the widget** — `LeapSnapshot` gained `weather: LeapWeatherData?` and
  `events: [LeapCalendarEvent]?`. `LeapProvider.entry(...)` injects them **by category**
  (`.weather` → `loadWeather()`, `.calendar` → `loadEvents(for:)`); the design views
  prefer real data and **fall back to the representative sample when nil**
  (`LeapWeatherSample.resolve` / `LeapAgendaSample.resolved`; `agenda` shows a
  "Nothing scheduled" empty state when the list is empty but non-nil). Nil ⇒ no access ⇒
  sample; `[]` ⇒ real data, nothing scheduled ⇒ empty state.
- **Permission-on-add (critical UX rule)** — OS prompts fire **only when the user adds a
  widget of that category**, never at launch: `AddWidgetSheet.save()`
  (`Leap/HomeView.swift`) → `LeapViewModel.requestLiveDataAccess(for: kind.category)`
  (weather → Location + WeatherKit, calendar → EventKit). A widget extension can't
  prompt, so the **app** requests; both then read the shared cache. App-side refresh also
  runs on scene-active (`LeapViewModel.refreshLiveDataIfAuthorized()`). See
  [build-and-run.md](build-and-run.md) for the WeatherKit paid-team signing caveat.
