---
name: telemetry
description: >
  Guide for Firebase Analytics (GA4), custom events, user properties, session tracking, crashlytics, and privacy-preserving telemetry without PII.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Telemetry — Agent Guide

Anonymous app-usage telemetry stored in **Firebase Analytics (GA4)**. This is the guide for adding, changing, or debugging analytics in an iOS/Swift app.

## Invariants (know these before touching telemetry)

- **Single source of truth:** every event name, param key, group and user-property key should live in a centralized, shared file (e.g., `Telemetry.swift`). **Never** scatter raw analytics strings — add a case to an `Event` enum or a constant to a `Param` struct instead.
- **Anonymous, no PII, ever.** We rely only on GA4's anonymous `app_instance_id`. Do **not** call `setUserID`, request IDFA / App Tracking Transparency, or log email, name, device id, coordinates, photos, or user free-text. Only log low-cardinality enums and small counts.
- **`canImport` + compilation-flag guarded, no-op safe.** The whole surface should be wrapped in `#if canImport(FirebaseAnalytics) && APP_ANALYTICS` (or an equivalent project flag). The app must compile and run **without** the Firebase SPM package or without the flag enabled. The telemetry logger should simply do nothing if the flag is absent. Keep it that way; never make code paths depend on Firebase being linked.
- **Extensions NEVER call Firebase directly.** A second Firebase instance in an app extension (like a widget) would mint its own anonymous id and **double-count users**. The extension should only bump App-Group `UserDefaults` counters; the main app drains them to GA4 on foregrounding.
- **No blocking work in extensions.** Recording in an extension must be a synchronous counter bump only, honoring strict lifecycle timelines (e.g., a widget's `timeline(for:in:)`).
- **Platform targeting**, use `#if os(iOS)` where needed, ensuring safe both-target membership for shared files.

## Architecture / data flow

```text
Main App process                              Extension process (e.g. Widget)
----------------                              -------------------------------
Telemetry.configure()                         MetricsStore.recordEvent()
Telemetry.log(event, params) --> GA4                    |  (App Group counters)
Telemetry.setUserProperty()  --> GA4                    v
Telemetry.flushExtensionMetrics() <-------------- drain() on scenePhase == .active
   emits deferred extension events to GA4
```

## Adding a new event

1. Add a case to your centralized `Event` enum (use snake_case raw values, kept short).
2. Reuse or add a constant for any new parameter keys.
3. Log it at the call site passing only low-cardinality, non-PII values.
4. If it comes from an extension, add a counter to a shared App Group store and emit it when the main app flushes metrics — do **not** call Firebase from the extension.
5. Register the event and parameters in GA4 (custom dimensions) if they need to be queried.

## Firebase Setup and Configuration

- **Target Scoping:** Add the Firebase Analytics dependency to the **app target only** — never to extensions.
- **Initialization:** Include the `GoogleService-Info.plist` in your app target. Ensure no conflicting property lists exist.
- **Compilation Flag (Crucial):** Once `firebase-ios-sdk` is in the package graph, `canImport(FirebaseAnalytics)` evaluates true even in extensions (the module is discoverable). To prevent Firebase from compiling into extensions and failing to link, gate telemetry code behind a custom flag (e.g., `APP_ANALYTICS`) defined in `SWIFT_ACTIVE_COMPILATION_CONDITIONS` for the **main app target only**. Never add this flag to extensions. Without the flag, telemetry becomes a safe no-op.

### Verification and Debugging

**Ongoing verification** for future changes: build and run on a **physical device** (Simulators may not reliably surface analytics or simulate environment traits accurately), enable GA4 **DebugView**, and confirm events, params, and user properties appear with no PII and no IDFA.

1. **GA4 DebugView:** Launch the app with the `-FIRDebugEnabled` argument (persists across restarts until `-FIRDebugDisabled` is passed). Events will stream live in the Firebase console.
2. **On-device measurement DB:** Pull the app container from the device to inspect the local SQLite store for custom events and pending queues. Use `devicectl` or Xcode's Devices window to download the container. Inspect `Library/Application Support/Google/Measurement/google-app-measurement.sql`. Note: Successful uploads clear pending queues, so an empty queue means data successfully reached GA4.
3. Ensure no user identification tracking is implicitly configured. Anonymous by design means calling `Analytics.setAnalyticsCollectionEnabled(true)` without ever linking `AdSupport` / ATT.

## Dashboards & Funnels (Examples)

When building dashboards (GA4 / Looker Studio), structure common funnels such as:

- **Activation funnel:** `first_open` → `onboarding_start` → `onboarding_complete` → `core_action`.
- **Monetization funnel:** `paywall_impression` → `product_select` → `purchase_start` → `purchase_success`.
- **Engagement:** Segment usage by user preferences or feature configuration properties.
