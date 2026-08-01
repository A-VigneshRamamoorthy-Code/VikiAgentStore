---
name: telemetry
description: >
  Apple development skill for Telemetry — Agent Guide. Use this skill when working on telemetry tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Telemetry — Agent Guide

Anonymous app-usage telemetry for Leap, stored in **Firebase Analytics (GA4)**. This is
the guide for adding, changing, or debugging analytics. Human-facing data catalog:
[`docs/telemetry/telemetry.html`](../telemetry/telemetry.html).

## Invariants (know these before touching telemetry)

- **Single source of truth:** every event name, param key, group and user-property key
  lives in `Shared/LeapTelemetry.swift`. **Never** scatter raw analytics strings — add a
  case to `LeapTelemetry.Event` / a constant to `LeapTelemetry.Param` instead.
- **Anonymous, no PII, ever.** We rely only on GA4's anonymous `app_instance_id`. Do
  **not** call `setUserID`, request IDFA / App Tracking Transparency, or log email, name,
  device id, coordinates, photos, or user free-text (mantra / goal / counter names). Only
  low-cardinality enums and small counts.
- **`canImport` + `LEAP_ANALYTICS`-guarded, no-op safe.** The whole surface is wrapped in
  `#if canImport(FirebaseAnalytics) && LEAP_ANALYTICS`. The app compiles and runs **without**
  the Firebase SPM package or without the flag (CI / free-team builds / the widget extension)
  — `LeapTelemetry.log` simply does nothing. Keep it that way; never make code paths depend on
  Firebase being linked. See the `LEAP_ANALYTICS` note under "Firebase setup" for why the flag
  (not `canImport` alone) is required.
- **The widget extension NEVER calls Firebase.** A second Firebase instance would mint its
  own anonymous id and **double-count users**. The extension only bumps App-Group counters
  via `LeapWidgetMetricsStore`; the app drains them to GA4 on foreground
  (`LeapTelemetry.flushWidgetMetrics()` from `LeapApp.onChange(scenePhase)`).
- **No blocking work in the widget.** Recording is a synchronous `UserDefaults` counter
  bump only — honours the widget's "never block `timeline(for:in:)`" invariant.
- **ASCII source**, `#if os(iOS)` where needed, both-target membership for `Shared/` files.

## Architecture / data flow

```
App process                                   Widget extension process
-----------                                   ------------------------
LeapTelemetry.configure()  (LeapApp.init)
LeapTelemetry.log(event, params) --> GA4      LeapWidgetMetricsStore.recordRender/…()
LeapTelemetry.setUserProperty()  --> GA4                 |  (App Group counters)
LeapTelemetry.flushWidgetMetrics() <--------------- drain()  on scenePhase == .active
   emits widget_render / widget_checkin_tap / widget_open_app_tap
```

## Event groups (the `event_group` param stamped on every event)

`lifecycle`, `onboarding`, `widget`, `widget_usage`, `monetization`, `pref`, `livedata`,
`engagement`, `support`. Full event + param tables live in the HTML catalog and in the
`Event`/`Param` enums. `Event.group` maps each event to its group automatically.

## Call sites (where events are logged)

| Area | File | Events |
|------|------|--------|
| App lifecycle / trial | `Leap/LeapApp.swift`, `Leap/LeapViewModel.swift` | `app_foreground`, `trial_start`, `trial_expire`, user properties |
| Onboarding | `Leap/OnboardingView.swift`, `Leap/OnboardingSpinWheelPage.swift` (via `OnboardingView`) | `onboarding_start/page_view/skip/complete`, `welcome_spin` |
| Widget studio | `Leap/LeapViewModel.swift` (`addWidget/updateWidget/removeWidget`), `Leap/HomeView.swift` (`AddWidgetSheet.save`) | `widget_add/edit/remove/save_blocked` |
| Widget usage | `LeapWidget/LeapCheckInWidget.swift` (render), `Shared/LeapIntents.swift` (`ToggleLeapIntent`) | `widget_render`, `widget_checkin_tap` |
| Preferences | `Leap/LeapViewModel.swift` (`setAppearance/setAppAccent/setBackgroundStyle`) | `pref_*` + user properties |
| Live data | `Leap/LeapViewModel.swift` (`requestLiveDataAccess`) | `livedata_permission_request/result` |
| Monetization | `Leap/HomeView.swift`, `Leap/Browse/BrowseTab.swift` (CTA + paywall sheets, pass `source:`), `Leap/PaywallView.swift` (impression/select/dismiss), `Leap/LeapStoreKitManager.swift` (purchase/restore) | `upgrade_cta_tap`, `paywall_*`, `purchase_*`, `restore_*` |
| Engagement | `Leap/LeapViewModel.swift` (`toggleToday`) | `checkin_toggle` |
| Support / feedback | `Leap/FeedbackView.swift` (open, category, send outcome), `Leap/HomeView.swift` (`SettingsTab` rows) | `feedback_open`, `feedback_category_select`, `feedback_submit`, `feedback_fail`, `feedback_history_open` |

**Feedback events carry no content.** `feedback_submit` reports only `category`,
`has_email` (a bool), `attachment_count` and a **bucketed** `message_length` — never
the message text, the email address or any image bytes. Those live solely in the
separate `leap-feedback` Firestore project ([feedback.md](feedback.md)), which keeps
the "anonymous only" contract above intact.

`LeapViewModel.syncTelemetryUserProperties()` publishes user-scoped properties
(`plan_status`, `current_appearance/accent/bg_style`, `saved_widget_bucket`,
`most_used_style`, `has_custom_photo`, `transparent_widget_user`) on launch and after
relevant changes.

## Adding a new event

1. Add a case to `LeapTelemetry.Event` (snake_case raw value, <= 40 chars) and map it in
   `Event.group`.
2. Reuse or add a `LeapTelemetry.Param` constant for any new parameter.
3. Log it at the call site: `LeapTelemetry.log(.myEvent, [LeapTelemetry.Param.x: value])`.
   Pass only low-cardinality, non-PII values.
4. If it comes from the widget, add a counter to `LeapWidgetMetricsStore` and emit it in
   `LeapTelemetry.flushWidgetMetrics()` — do **not** call Firebase from the extension.
5. Register it in GA4 (custom dimensions) and add it to the HTML catalog.

## Firebase setup (LIVE — wired, linked, and verified collecting)

The Firebase project and SDK are **created, wired, GA4-linked, and confirmed collecting real
events from a device build** (verified 2026-07-25). No setup work remains — this section is
now a reference for maintenance and account switching.

**Active project (`leap-widgets`, account `sololeapinc@gmail.com`) — since the 2026-07-26 cutover:**
- Project id: `leap-widgets`  ·  project number: `522404004428`
- iOS app id: `1:522404004428:ios:426f4616f8c9b6d77caae9`  ·  bundle `com.sololeap.leap.app`
- Config committed at `Leap/GoogleService-Info.plist`, added to the **app target only**.
- `firebase-ios-sdk` SPM package (product **FirebaseAnalytics**, min 11.0.0) added to the
  **app target only** — never to the widget extension.
- **GA4 linked ✅** — GA4 property `547176151` (account `402379473`) with iOS data stream
  `15329436711` mapped to the app (`projects/leap-widgets/analyticsDetails`). Collection is
  enabled at runtime via `Analytics.setAnalyticsCollectionEnabled(true)`. **Note:** an iOS
  `GoogleService-Info.plist` does **not** contain `MEASUREMENT_ID` (that is a *web* data-stream
  field) and its `IS_ANALYTICS_ENABLED` key is a legacy no-op — their absence/false value is
  normal and does **not** mean analytics is off. GA linking itself cannot be done via CLI
  (the `analytics.edit` scope is blocked for gcloud's default client) — it was enabled once in
  the Firebase console.

**⚠️ Funnel discontinuity on 2026-07-26.** Telemetry ran on `sololeap-leap`
(project number `717896615373`, GA4 property `547087762`, account
`vigneshme2011@gmail.com`) from 2026-07-25 until the cutover, then moved to
`leap-widgets` so every Leap service lives under the company account
`sololeapinc@gmail.com`. **GA4 has no property-merge**, so the historical data did
**not** come across: `sololeap-leap` is left intact as a read-only archive and any
report spanning that date will show a hard break with users re-counted as new.
The move was a **bundled-config swap only** — no Swift changed, because the app
reads whatever `GoogleService-Info.plist` is bundled. The same cutover also
deleted the stale, unreferenced duplicate `Leap/GoogleService_sololeapinc-Info.plist`.

**Don't confuse the two plists in the app target.** `Leap/GoogleService-Info.plist`
is analytics (`leap-widgets`) and is what `FirebaseApp.configure()` auto-loads;
`Leap/GoogleService-Info-Feedback.plist` is the **feedback** project
(`leap-feedback`) and is read by filename only, never by Firebase — see
[feedback.md](feedback.md). The deliberately different filename is what stops
Firebase from configuring the wrong project.

Firebase Management write calls need **ADC with the `firebase` scope**:
`gcloud auth application-default login --scopes=openid,email,cloud-platform,https://www.googleapis.com/auth/firebase`
then `gcloud auth application-default set-quota-project leap-widgets`.

> **Switching the Firebase account/project.** To move to a different Google account, just
> **replace `Leap/GoogleService-Info.plist`** with the new project's config — no code changes
> (the app reads whatever plist is bundled). Fastest reliable path: create the project in the
> **Firebase console** (https://console.firebase.google.com/) with **Google Analytics enabled**
> (this also links GA4 in one step), Add app → iOS → bundle `com.sololeap.leap.app` → download
> the plist → drop it in `Leap/` → rebuild. **CLI caveats learned the hard way:** a brand-new
> account must **accept the Google Cloud Terms of Service** once in the browser before
> `gcloud projects create` works, and GA4 linking **cannot** be done via the CLI — the
> `analytics.edit` scope is blocked for gcloud's default client ("This app is blocked"), so the
> GA4 enable is always a console action.

**`LEAP_ANALYTICS` compilation flag (important).** Once `firebase-ios-sdk` is in the package
graph, `canImport(FirebaseAnalytics)` evaluates **true even in the widget extension** (the
module is discoverable), which made Firebase code compile into the extension and fail to link
(missing nanopb/GoogleAppMeasurement symbols — extensions must not link Firebase). To fix this,
**all** Firebase code in `Shared/LeapTelemetry.swift` is gated behind
`#if canImport(FirebaseCore/FirebaseAnalytics) && LEAP_ANALYTICS`, and `LEAP_ANALYTICS` is
defined in `SWIFT_ACTIVE_COMPILATION_CONDITIONS` for the **Leap app target only** (both Debug
and Release). **Never add `LEAP_ANALYTICS` to the widget extension target.** Without the flag
the whole telemetry surface is a safe no-op (this is how free-team / CI builds stay green).

**Build note (SwiftPM + session git config).** The session env injects
`GIT_CONFIG_VALUE_0=safe.bareRepository=explicit`, which breaks SwiftPM's use of bare cached
repos. Build with it overridden:
```
GIT_CONFIG_VALUE_0=all xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Debug \
  -destination 'platform=iOS Simulator,id=<UDID>' -clonedSourcePackagesDirPath /tmp/leap_spm build
```

**Internal builds ship working telemetry.** The **Internal** build configuration defines
`LEAP_ANALYTICS` on the **app target** (`SWIFT_ACTIVE_COMPILATION_CONDITIONS = "$(inherited)
LEAP_ANALYTICS"`, where project-level Internal supplies `LEAP_INTERNAL`), so an Internal
build gets **both** the shake-to-reveal debug panel **and** live GA4 collection. The widget
extension's Internal config gets only `LEAP_INTERNAL` (never `LEAP_ANALYTICS`). See
[build-and-run.md](build-and-run.md) for the Internal scheme + device install/launch commands.

### Verified collecting (2026-07-25)

An Internal build was installed on a physical device and confirmed sending anonymous GA4
events three ways:

1. **GA4 DebugView** (launch with `-FIRDebugEnabled` — persists across restarts until
   `-FIRDebugDisabled`) showed events streaming live.
2. **On-device measurement DB** pulled from the app container confirmed our custom events
   with real counts (`widget_render`, `paywall_impression`, `app_foreground`,
   `paywall_dismiss`, `upgrade_cta_tap`, `pref_appearance_change`, `pref_accent_change`,
   `widget_remove`, `widget_edit`) plus Firebase internals (`first_open`, engagement). The
   upload `queue` was drained to 0 (all events successfully uploaded), and the config plist
   showed only the anonymous `app_instance_id` + correct `gmp_app_id`
   (`1:717896615373:ios:01567a15088c3948dbb084`) — **no user id / IDFA / PII**.
3. Config verification (used only if you need to re-check the SDK on a device build; the GA4
   Data API and DebugView are the normal channels — the on-device DB is a fallback because
   the `analytics.readonly` scope is blocked for gcloud's default client):
   ```bash
   xcrun devicectl device copy from --device <UDID> \
     --domain-type appDataContainer --domain-identifier com.sololeap.leap.app \
     --source "Library/Application Support/Google" --destination /tmp/leap_ga
   sqlite3 /tmp/leap_ga/Measurement/google-app-measurement.sql \
     "SELECT name, lifetime_count FROM events ORDER BY last_fire_timestamp DESC;"
   plutil -p /tmp/leap_ga/Measurement/com.google.gmp.measurement.plist   # app_instance_id, gmp_app_id
   ```
   Note: successful uploads clear pending `raw_events`/`queue`, so an empty queue means data
   already reached GA4 — it is **not** a failure.

**Ongoing verification** for future changes: build + run on a **device** (the Simulator masks
transparency and does not reliably surface analytics), enable GA4 **DebugView**
(`-FIRDebugEnabled`), and confirm events, params and user properties appear with no PII and no
IDFA.

Anonymous by design: we call `Analytics.setAnalyticsCollectionEnabled(true)` and never link
`AdSupport` / ATT, so GA4 collects an anonymous instance id only.

## Dashboards (GA4 / Looker Studio)

- **Activation funnel:** `first_open → onboarding_start → onboarding_complete → widget_add`.
- **Monetization funnel:** `upgrade_cta_tap` / `paywall_impression → paywall_product_select
  → purchase_start → purchase_success`; skips = `paywall_dismiss (purchased=false)`.
- **Widget leaderboard:** `widget_add` + `widget_render` grouped by `design` / `category`.
- **Style & theme mix:** `widget_add.style`, `most_used_style`, `current_appearance`,
  `current_accent`.
- **Transparency adoption:** `widget_add.transparent` + `current_bg_style`.
- **Sub vs lifetime:** `paywall_product_select.product_type` + `purchase_success.product_type`.

> Note: true "added to Home Screen" is only observable from the widget. `widget_render`
> (distinct users with >= 1 render) is the documented **proxy** for placement.
