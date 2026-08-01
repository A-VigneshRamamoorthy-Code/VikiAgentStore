---
name: conventions
description: >
  Apple development skill for Conventions. Use this skill when working on conventions tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Conventions

> Part of the **[Leap Agent Guide](../../agents.md)**. The widget catalog table is in
> [architecture.md](architecture.md).

---

- **Keep source ASCII** unless a file already uses non-ASCII.
- **Gate iOS-only APIs** (`#if os(iOS)` / `#available`) where relevant.
- Add new designs by extending `LeapWidgetKind` + a private **style-aware** design
  struct in `LeapWidgetContentView.swift` (handle all **4** styles: Editorial /
  Minimal / Dot-Matrix / Neon — there is no Glass style), then wiring it into the
  dispatcher switch. Give it a `signatureStyle`. No new `Widget` struct /
  `LeapWidgetBundle` entry is needed (one configurable widget). Update the catalog
  table in [architecture.md](architecture.md).
- **Clock / watch faces have extra, non-obvious rules** (dense timelines, the gliding
  second hand, the archive budget, a do-not-retry list) - read
  [clock-faces.md](clock-faces.md) before touching anything in the `.time` category.
- Widgets: **no border/tick lines**; white content; mark hero elements for
  legibility on any wallpaper.
- **Request OS permissions only on widget-add, per category — never at launch.**
  Live-data categories request access in `AddWidgetSheet.save()` →
  `LeapViewModel.requestLiveDataAccess(for:)` and cache to the App Group (`LeapLiveStore`)
  for the extension to read; design views prefer real data and fall back to the sample.
  See "Live widget data" in [architecture.md](architecture.md).
- **Live-data usage strings:** app keys go in `project.pbxproj` as `INFOPLIST_KEY_*`
  (the app uses `GENERATE_INFOPLIST_FILE`); widget keys go in `LeapWidget/Info.plist`.
  **WeatherKit needs a paid team** — its entitlement is commented out (see
  [build-and-run.md](build-and-run.md)).
- Comment only where it clarifies; avoid noise.
