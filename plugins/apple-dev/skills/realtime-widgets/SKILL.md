---
name: realtime-widgets
description: >
  Guide for real-time widgets, live activities, Dynamic Island, push to wake, background timeline refreshes, and high-frequency WidgetKit updates.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Realtime / live widget updates (how-to)

> Part of the **iOS Agent Guide**. Event-driven reloads tie into the data flow architecture. For clock / watch faces specifically, refer to clock face patterns.

---

A placed widget's SwiftUI body is rendered to a **static archived snapshot**, one per timeline entry — it does NOT keep running on the Home Screen. There are exactly **three** ways to make a placed widget change over time; use the cheapest one that fits.

1. **Timeline entries — for minute-or-coarser changes.**
   In the provider's `timeline(for:in:)`, pre-render a buffer of `TimelineEntry`s stamped with FUTURE dates and return `Timeline(entries:, policy:)`; WidgetKit swaps to each at its date with no code running.

   If you need a **continuously gliding indicator** (like a clock second hand), you can use a timeline with 2-second steps (e.g., 900 entries for 30 minutes). WidgetKit **interpolates animatable modifier parameters between consecutive entries** and renders that interpolation at full frame rate. Animations in widgets have a **maximum duration of two seconds**. By applying a `.linear(duration: 2)` rotation effect, the indicator bridges the entire gap between entries and sweeps smoothly.

   ### ✅ A 2s timeline gives a CONTINUOUSLY GLIDING hand
   The host presents a new entry roughly every 2 seconds. A 2s animation bridges this perfectly.

   #### ⛔️ Wrapping vs. monotonic rotations
   Because the interpolation is numeric, both wrapped and monotonic approaches have pitfalls:
   - **Monotonic**: If you use seconds since a fixed anchor, the value is proportional to absolute time. If the host skips entries, a resume animates the entire elapsed duration (e.g., 45 minutes skipped = 45 backward revolutions).
   - **Wrapped**: If you use `second % 60 * 6`, the value drops once a minute, causing an anti-clockwise sweep.
   - **Solution**: Use a **wrapped angle plus a one-entry animation gate**. Disable the animation exactly when the minute wraps (e.g., `secondOfMinute >= step`).

   #### ⛔️ The animation duration MUST equal the entry spacing
   If you try to shorten the animation (e.g. 1s duration for a 2s timeline step), the hand will glide for one second and freeze for the next. This reads as a tick stutter. Do not reintroduce a per-context duration for in-app previews; use `TimelineView` schedules for previews instead.

   #### ⚠️ Disable animation GLOBALLY, opt back in at the leaf
   Since recent iOS versions, WidgetKit gives each timeline-entry change an implicit animation, cross-dissolving the old render tree into the new one. This causes static gradients to dip in alpha and anti-aliased strokes to flicker once per entry. Use `.animation(nil, value: entry.date)` on the main content groups and `containerBackground`. Opt back into animation **only** on the moving components (like the hand) using an inner `.animation(_:value:)`.

   ### ⚠️ STEPPING is not an option
   If you want an indicator to step onto ticks discretely, a 1s timeline with snap animations will still stutter every 2 seconds because the widget host simply does not present entries faster than ~0.5 Hz. Stepping indicators read as a 2s stutter on hardware.

   ### ⛔️ HARD LIMIT — the TIMELINE ARCHIVE Budget ~1.5MB
   WidgetKit archives the **entire view tree once per entry**. A 900-entry timeline multiplies the view data. If the archive exceeds ~1.5MB-2MB on a physical device, the system will fail to load it (`CHSErrorDomain 1050 timelineReloadFailed`), leaving the widget stuck on a blank skeleton. Note: the Simulator will accept much larger archives (e.g., 10MB+), so ALWAYS test on physical hardware.

   **Rules to keep dense timelines under budget:**
   1. **Merge repeated moving primitives:** Use unified paths rather than many rotated shapes.
   2. **Never draw N repeated shapes:** Use a single stroked dashed circle for tick marks instead of an array of paths.
   3. **Never use `Text(_, format:)` on dense timelines:** A `Date.FormatStyle` serializes calendar/locale/timezone data into every entry (~5KB each). Use `Text(verbatim:)`.
   4. **Reduce Entry Count:** If still over budget, reduce the timeline density.
   5. **Do NOT rasterize with `ImageRenderer`:** It evaluates colors in a fresh environment (defaulting to light mode) causing dark mode bugs, and often fails completely on the Home Screen.

2. **Self-animating views — for per-second motion, ZERO timeline cost.**
   These are the only SwiftUI views the system repaints every second on the Home Screen without new timeline entries:
   - `Text(_, style: .timer | .relative | .offset)`
   - `Text(TimeDataSource.currentDate, format:)` (on newer iOS versions)
   - `ProgressView(timerInterval:)` (use `.linear` style for continuous motion; custom styles cannot animate automatically)

   - **⛔️ Live-view budget:** Devices limit the number of live views per widget (around 6-8). Exceeding this strands the tile on its placeholder forever.
   - **Locale / time-zone:** SwiftUI resolves locale/timezone for these views from the environment, silently overriding values set on the `FormatStyle`. Apply `.environment(\.locale, ...)` at the top level.

3. **Reload on data change — event-driven.**
   When app data changes, call `WidgetCenter.shared.reloadAllTimelines()` to rebuild with fresh values.

   > ### ⛔️ NEVER block `timeline(for:in:)` on an unbounded call
   > This is the leading cause for "widget goes blank / never loads". If `timeline()` suspends past its short budget (e.g., due to a hanging network or location request), the widget is stranded. `CLLocationManager.requestLocation()` can sometimes never call back in an extension.
   > **Rules:**
   > 1. Use cached data when possible.
   > 2. Wrap refreshes in a strict timeout mechanism. Do NOT use `withTaskGroup` as a race between work and timeout, because `withTaskGroup` implicitly awaits all children (including the hung work). Use a detached task and a single-resume actor gate.
   > 3. Always return a timeline from cached values if the refresh times out.

   **Battery faces:** `UIDevice.batteryLevel` is deliberately rounded to 5% steps by iOS. Do not use private IOKit APIs to get 1% precision, as it violates App Review guidelines and causes rejections.

---

## The reload budget, and why a timeline must out-live its own reload

1. **The budget is spent PER PLACED INSTANCE** (roughly 40–70 reloads/day).
2. **Reloads are hints.** `policy: .atEnd` or `.after(_:)` are not guaranteed. WidgetKit may drop or batch reloads. The provider must archive a **freeze buffer** past the point it asks to be reloaded to prevent a visibly stuck widget.
3. **Foreground exemptions.** Reload requests made while the containing app is in the `.active` scene phase are exempt from the budget. Always call `reloadAllTimelines()` when the app enters the foreground.

**Diagnose before fixing:**
- Stale but plausible data (opening app fixes it): Timeline exhausted / reload throttled -> **Lengthen** the horizon.
- Stuck on placeholder, never renders: Archive rejected -> **Shrink** the archive.
