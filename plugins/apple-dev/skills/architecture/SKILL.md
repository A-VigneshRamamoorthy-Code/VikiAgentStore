---
name: architecture
description: >
  Guide for iOS app architecture, Target layout, WidgetKit extensions, App Groups, Xcode project structure, shared code, and data flow.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Architecture & data flow

Repo/target layout, widget design catalog, and how in-app changes reach placed widgets.

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. See also:
> [build-and-run.md](../build-and-run/SKILL.md), [transparency.md](../transparency/SKILL.md),
> [conventions.md](../conventions/SKILL.md).

---

## Targets & layout

```
App.xcodeproj
├─ App/            App target (SwiftUI UI layer)
├─ WidgetExt/      WidgetKit extension (Widget structs, provider, intent)
└─ Shared/         Code compiled into BOTH targets (models, catalog, utilities)
```

- **`Shared/` files are added to both targets.** In `project.pbxproj` each shared
  file appears in both target memberships. When adding a shared file you must register it in **both**
  target membership lists or one target won't see it.
- **Transparency Hooks:** If using a private-API host-transparency hook, it belongs in the **widget target only**, often compiled `-fno-objc-arc` (MRC). Avoid touching the `project.pbxproj` configuration for these heavily customized build files unnecessarily.
- **Shared Data Layer:** Files like `Shared/LiveData.swift` act as the **live widget-data layer** (managing content like Calendar and Weather models, App Group cache, and services like CoreLocation, WeatherKit, or EventKit). They must be compiled into **both** targets.
- **`project.pbxproj` Management:** Prefer reusing existing files over adding new ones to avoid pbxproj surgery if you are not using Xcode's synchronized folders. 
  - New shared types → existing `Shared/Models.swift` or similar.
  - New widget **designs** → `Shared/WidgetContentView.swift` (style-aware struct + dispatcher, no new `Widget` struct).
  - New app UI → appropriate view files in the `App/` directory.

## The design catalog (consolidated single source of truth)

Single source of truth for widget rendering: **`Shared/WidgetContentView.swift`** (or equivalent).

- **Widget Catalog (`WidgetKind`):** An enum serving as the catalog for widget designs. Each case exposes properties like `title`, `category`, `supportedSizes`, `isInteractive`, **`signatureStyle`**, and capability flags (e.g., `showsLiveTime`, `showsWeather`, `showsCalendar`). 
- **Dispatcher:** A centralized view dispatcher (e.g., `WidgetView(kind:snapshot:size:interactive:style:)`) renders the correct private design struct based on the enum.
- **Style Awareness:** Designs should be **style-aware** (e.g., Editorial, Minimal, Bold, etc.), composed from a shared style kit (custom progress rings, dot-matrix text, branded pills). Avoid hardcoding fonts. Shared UI components should vary per style so the styles are visibly distinct.
- **Signature Style:** Each widget kind can define a showcase style used as its default in the Browse/Add screen. Selecting a showcased design pre-selects that style.
- **Categories:** Organize widgets by categories (e.g., time, calendar, weather, progress). Use a curated array (e.g., `WidgetCategory.browseOrder`) to drive the browse display order, decoupling UI presentation from the enum's declaration order so logic that iterates `allCases` is unaffected.

### Gallery registration
The app should ideally register **ONE configurable widget** (a single `AppIntentConfiguration` with multiple families) rather than one struct per design.
The design, style, background, and slot are chosen via an `AppIntent` (the iOS **Edit Widget** sheet). Adding a design then simply means extending the `WidgetKind` enum and creating a design struct—no pbxproj surgery and no new `Widget` struct needed.

## Data flow & "changes reflect on the widget"

- **App Group** (e.g. `group.com.example.app`).
  UserDefaults keys are used for shared state:
  - `app.wallpaper.kind` — global wallpaper choice
  - `app.widget.slot` — global Home-Screen row context
  - `app.library` — the user's saved-widget list
  - `app.background.style` — global default widget style
- **Per-saved-widget fields** should live inside the JSON of the user's saved-widget list, rather than as separate top-level defaults. This includes interactive toggles, custom text overrides, and display options (e.g., 12H/24H format, C/F units).
- **Per-widget display options** surface as configurable options in the **Add/Edit sheet**. These values thread from the saved model through the `AppIntent` entry into the widget view (e.g., via `@Environment`), allowing designs to read the options seamlessly.
- **Intent Parameters:** Parameters in the widget config intent (like background, wallpaper, slot) should be **OPTIONAL**. The widget provider uses `param ?? global_store_value`.
  → A freshly added widget (nil params) **follows the app's global store** and updates on `WidgetCenter.shared.reloadAllTimelines()`. Editing a widget sets a per-widget override. This is why in-app changes reflect immediately on placed widgets.
- **Resource Management:**
  - **Custom images/wallpapers:** Save images in the App Group container so both app and widget render identical pixels.
  - **Deletion:** Deleting a saved widget must also clean up its associated side data (e.g., daily tracking records, cached images) to prevent unbounded growth in the App Group. Run a prune pass **after** the saved-widget list is updated to sweep orphans.
  - **Cache Caps:** Browse screens that render many widget previews must use bounded LRU caches and respond to memory warnings (`UIApplication.didReceiveMemoryWarningNotification`). Unbounded dictionaries will crash the app when scrolling the catalog.

## Live widget data (Calendar, Weather, etc.)

For widgets that render **real** data (e.g., Calendar events, Weather), the pipeline lives in a shared layer (e.g., `Shared/LiveData.swift`):

- **Models** — Define strict models representing the required data (e.g., `WeatherData`, `CalendarEvent`). Do not rely directly on framework models inside the UI.
- **Services** — Service layers encapsulate fetching data (CoreLocation, WeatherKit, EventKit). Expose methods for `requestAccessAndRefresh()` and `refresh()`.
- **App Group cache** — Cache fetched data and coordinates in the App Group. Add daystamp guards to prevent rendering stale data on a new day. **Both app and extension read this cache.**
- **Into the widget** — The widget snapshot and entry models should include optional properties for live data (`weather: WeatherData?`, `events: [CalendarEvent]?`). The widget provider injects them **by category**. Widget views should prefer real data and **fall back to deterministic placeholder samples when data is nil**. `[]` means real data with empty states (e.g. "Nothing scheduled"), whereas `nil` means no access or data pending.
- **Permission-on-add (critical UX rule)** — OS permission prompts (Location, Calendar) should fire **only when the user adds a widget of that category**, never at initial app launch. Since a widget extension can't present prompts, the **app** makes the request in the configuration UI, and both targets subsequently read the shared cache. App-side refresh logic handles updates on scene-active.
