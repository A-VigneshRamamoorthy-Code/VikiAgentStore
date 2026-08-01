---
name: status-and-history
description: >
  Apple development skill for Status & history. Use this skill when working on status-and-history tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Status & history

Current status plus the changelog of issue/refinement passes. This is the
"what's been done" record — open it when you need historical context, not for
day-to-day editing.

> Part of the **[Leap Agent Guide](../../agents.md)**. Live checklist:
> [`docs/STATUS.md`](../STATUS.md) · roadmap: [`docs/PLAN.md`](../PLAN.md).

---

## Current status

See [`docs/STATUS.md`](../STATUS.md) for the live checklist and
[`docs/PLAN.md`](../PLAN.md) for the roadmap.
Short version: **3-tab app** (My Widgets / Browse / Settings) + a **66-design** pack
(16 categories, **4 styles** each: Editorial / Minimal / Dot-Matrix / Neon) +
upload-wallpaper + system theme are built, installed, and running. **Browse** now
features a **curated subset/order** of categories (`LeapWidgetCategory.browseOrder`:
Clock, Date, Calendar, Weather, Streak, Progress, Battery, Storage, Activity, then
Goal, Mantra — 59 designs shown; Focus/Settings/Screen Time/Globe/Sound hidden but
still shipped). The full
**[`issues/issues.md`](../../issues/issues.md)** set (Visual 1-16, Functionality 1-7,
Performance 1-2) has been addressed and reviewed by the **GPT-5.6 Sol** design judge —
see "Issues addressed" below.

The **live-transparent widget** (Koco-style, private API — see
[transparency.md](transparency.md)) is implemented and **device-verified** on iOS
26.5.2 (flags `hostTransparent/fired/count/applied` all confirm the hook installed,
ran, and marked the placed widget transparent). Settings shows a **"LIVE WALLPAPER"**
status row. The only unverified item is the pure visual (needs the user's eyes:
confirm the widget shows the live wallpaper and survives a wallpaper change on the
device). Falls back to baking if the private API is absent.

On top of the `issues/issues.md` set, **three later refinement passes** (bug fixes +
follow-up 1/2/3) are done, built, and installed — most notably a **user-selectable app
accent color** (replacing hard-coded lime), a **swipeable infinite hero carousel**, and
an **onboarding theme picker**. See "Later refinement passes" below.

**Calendar + Weather widgets now render real data** (EventKit / Apple WeatherKit +
CoreLocation), with OS permissions requested **only when that widget is added** — see
"Live widget data — real Calendar + Weather" below and in
[architecture.md](architecture.md). **Caveat:** WeatherKit is **disabled on the current
free signing team** (its entitlement is commented out), so weather faces render a
**deterministic date-based placeholder** — this is **expected** and looks "wrong / not
refreshing" vs Apple Weather. Re-enable once a paid membership is active via the runbook
in [build-and-run.md](build-and-run.md) ("Re-enabling WeatherKit").

## Multi-agent QA pass — functional test + code review (stale-widget & premium audit)

A two-stage, three-agent QA sweep (**Opus** orchestrated + fixed; **Gemini** +
**GPT** reviewed) fixed **10 functional bugs** — the debug-panel-in-Release leak,
system-stat / weather-clock staleness, missing weather/calendar permission prompts,
the photo-gate upgrade + paywall-resume races, and the frozen Record Player — and
confirmed the trial reinstall-defense is correct. Both reviewers ended clean; Weather
+ StoreKit real-data validation is deferred to a paid Apple membership. **Full record
(reusable playbook, the 10-bug found->fixed table, reviewer verdicts, validated
non-bugs, deferred TODO): [qa-and-reviews.md](qa-and-reviews.md).**

## In-app purchases — Leap Pro paywall (purchase experience)

The **StoreKit 2 purchase experience** for "Leap Pro" is built and simulator-verified
(spec: [in-app-purchases.md](in-app-purchases.md) + its "User requirement" section).
**Scope note:** this is the purchase *experience* only — the paywall UI + a real
StoreKit purchase that flips an `isPro` flag + its App-Group mirror. **Applying** the
unlock across the app (unlocking every design/style/wallpaper, downgrade/removal logic)
is **deliberately separate** and still open (so `docs/PLAN.md:72` "real premium
restrictions" stays **un-flipped**).

- **Two products:** `com.sololeap.leap.app.pro.monthly` ($0.99/mo auto-renewable) and
  `com.sololeap.leap.app.pro.lifetime` ($9.99 non-consumable, shown with a struck-through
  **$12.99** reference + a computed "23% OFF"). The reference is a THIRD, never-sold
  product (`...pro.lifetime.list`), so BOTH figures come from StoreKit and neither is
  hard-coded - see [in-app-purchases.md](in-app-purchases.md) SS12.4b. Product IDs live
  once in `Shared/LeapEntitlements.swift`.
- **Paywall** (`Leap/PaywallView.swift`): header, a 5-row free-vs-Pro comparison
  (free = **4** saved widgets, Pro = Unlimited/All 66/All 4/photo/live data),
  Lifetime+Monthly plan picker, **"No commitment, cancel anytime"**, purchase CTA,
  **Restore Purchases**, legal footnote. A `.widgetLimit(savedCount:)` context adds the
  orange **"You'll lose access to [savedCount − 4] widgets"** banner.
- **Three triggers:** the Home top-right **Upgrade** button (`ScreenHeader`, hidden when
  `isPro`), the **9th-widget** save gate (`AddWidgetSheet.save()` → paywall when
  `savedCount >= 8`, then `performSave()` completes the add on upgrade), and a Settings
  **PREMIUM** section (Unlock / Pro badge + Restore).
- **Engine:** `Leap/LeapStoreKitManager.swift` (@MainActor, owned by `LeapViewModel`) —
  `Transaction.updates` listener, verified-only `currentEntitlements` → `isPro` →
  `LeapEntitlements.setPro` (App-Group mirror) → `WidgetCenter.reloadAllTimelines()`.
  The widget extension only **reads** `LeapEntitlements.isProCached` (never calls StoreKit).
- **Testing:** `Leap.storekit` (scheme-referenced) drives the Xcode-run Simulator.
  **`simctl launch` does NOT apply `.storekit`** (Xcode-debugger only) — products load
  empty and the paywall falls back to `LeapProduct.Fallback` prices; run from Xcode (or
  StoreKit testing) to exercise a real purchase. Both paywall variants were rendered on
  the sim via a temporary launch-arg hook (since CGEvent taps don't drive modal sheets).

### Premium refinements (round 2) — trial + gating polish

The paywall + gating were refined; the block above is the original build, **superseded**
on these points:

- **User-facing branding is "Leap Premium"** (internal API stays `isPro` / `LeapProduct`
  / `com.sololeap.leap.app.pro.*` / App-Group `leap.pro.active.v1` — do **not** rename).
- **Comparison rows** now read **Styles 1 / All** and **Widget designs Basics / All**
  (no "All 66 / All 4" figures) and **Wallpapers + photo 1 / checkmark**.
- **7-day free trial** (`LeapEntitlements`: `trialStartKey`, `trialLengthDays=7`,
  `startTrialIfNeeded()` in `LeapViewModel.init`). Free users may add up to
  `freeWidgetHardCap=8` widgets during the trial; the newest surplus (oldest-first
  rank >= `freeWidgetAllowance=4`) are the ones at risk.
- **Per-widget countdown replaces the top banner.** The old Home trial banner was
  removed; each surplus saved-widget row instead shows a **red** (`LeapTheme.danger`)
  `hourglass` "N days left in trial" line under its style meta
  (`LeapViewModel.surplusTrialDaysLeft(for:)` -> `SavedWidgetRow.trialDaysLeft`). After
  the trial expires those rows become `locked` (dim + lime "Tap to keep this widget with
  Premium", tap -> paywall). The first 4 widgets and Premium users never show either.
- **Loss banner shows from any entry.** `PaywallView.atRiskCount` derives the at-risk
  count from the live `LeapLibraryStore` for the `.upgrade` context (not only
  `.widgetLimit`), so **"Don't lose access to your [savedCount - 4] trial widgets"**
  appears from the Upgrade button too (fixes the "banner missing past 8 widgets" bug).
- **Photo gate:** a free user gets **1** custom photo; adding a 2nd
  (`LeapViewModel.canAddCustomPhoto(excluding:)` in `AddWidgetSheet.onChange(photoItem)`)
  presents the paywall.
- **Premium experience:** when `isPro`, a lime **crown + "PREMIUM"** badge sits next to
  the LEAP eyebrow, and **every** upsell entry point is hidden (Upgrade button, per-row
  countdowns/locks, photo gate, save gate) — a Premium user is never blocked.
- **Paywall hero icon** is now `crown.fill` (was `sparkles`); the Home **Upgrade** button
  uses white text + a star-burst icon.

### Premium refinements (round 3) — rank fix, premium mark, debug panel

Round-2 corrections + additions, all simulator-verified:

- **Trial-countdown rank fix (the key bug).** The "N days left in trial" line was showing
  on the **wrong** (oldest) widgets. `savedWidgets` is **newest-first** (`LeapLibraryStore.add()`
  inserts at index 0, `Shared/LeapWallpaperStore.swift:536`) but
  `LeapEntitlements.isFreeWidgetLocked(rankOldestFirst:)` expects **oldest-first** ranks.
  Fixed in `LeapViewModel.isWidgetLocked` + `surplusTrialDaysLeft` with
  `rankOldestFirst = savedWidgets.count - 1 - index`. Display stays **newest-first**
  (`MyWidgetsTab.filteredWidgets` renders `savedWidgets` unreversed) so the most recently
  added widgets sit at the top; the countdown/lock still lands on the **newest surplus**
  rows (rank >= `freeWidgetAllowance` = 4) because the rank is derived from each item's
  index in `savedWidgets`, not the row order. Rank is **global** across sizes, so in a
  size-filtered view the free/surplus split may not be at row 4.
- **Loss banner is upgrade-context-scoped (round-2 revert).** The banner
  **"Don't lose access to your [savedCount - 4] trial widgets"** must appear **only** when
  the paywall is triggered by a **restricted action** (`.widgetLimit` — add-past-limit save
  gate, locked-widget tap), **not** from the proactive **Upgrade** button. `atRiskCount`
  now returns `0` for `.upgrade`.
- **Custom premium mark** (`Leap/LeapPremiumMark.swift`, NEW) — a tintable `Canvas`
  award-emblem (5-point star + arcs + ribbon) replaces `crown.fill`/`sparkle` in **4 places**:
  the Home Upgrade button, the `isPro` PREMIUM badge, the paywall hero, the paywall purchase
  CTA, and the Settings "Unlock Leap Premium" row.
- **Photo gate fixes.** (a) The upload tile now has `.contentShape(...)` so the **whole card**
  taps (not just the icon). (b) `canAddCustomPhoto(excluding: nil)` (was `excluding: editingID`)
  so **changing/duplicating** an already-saved custom photo also upsells (the sole saved custom
  counts against the `freePhotoAllowance = 1`).
- **Shake-triggered debug panel** (`Leap/LeapDebugPanel.swift`, NEW). Shaking the device sets
  `LeapViewModel.debugPanelRevealed` + switches to Settings, revealing a hidden **DEBUG**
  "Debug Panel" row. The panel is **password-gated** (`"NammaLeap@2026"`), then shows a
  **Premium** toggle. `debugIsPremium` flips `isPro` + `LeapEntitlements.setPro` (App-Group
  mirror) + `reloadAllTimelines`, and persists `debugPlanOverride` in
  `UserDefaults.standard` (`leap.debug.plan.override.v1`). The `storeKit.$isPro` pipeline is a
  `.sink` that **skips** assignment while an override is set, so the toggle sticks; `init`
  applies the persisted override to the initial `isPro`.
- **Upgrade button is Liquid Glass.** The Home **Upgrade** CTA now uses an iOS 26
  Liquid Glass capsule (`leapGlass(Capsule(), tint: LeapTheme.lime, interactive: true)`
  in `Shared/LeapTheme.swift` - the shared helper gained an `interactive` flag mapping to
  `Glass.regular.tint(...).interactive()`), replacing the flat lime gradient fill. Keeps
  the white premium mark + text and the soft lime glow shadow; falls back to a tinted
  material on < iOS 26.
- **Accent-aware foreground (`LeapTheme.onAccent`).** New token — near-black (`ink`) on
  the bright **lime** accent, **white** on the darker jewel accents
  (`LeapAppAccent.onAccentColor = self == .lime ? ink : .white`). Applied to every
  text/icon that sits ON an accent fill: the Home **Upgrade** button + `isPro` **PREMIUM**
  badge, the locked-widget **PREMIUM** pill, the **Save to Home** CTA, and the paywall
  **hero emblem**, **SAVE 30%** badge, and **Unlock** CTA. Fixes the low-contrast dark
  emblem/text that appeared on non-lime accents (e.g. the indigo upsell hero). The Settings
  "Unlock Leap Premium" row keeps `accentText` (accent-COLOURED icon on a neutral card, not
  on-accent).
- **System wallpaper swatch label follows the appearance.** The `SYSTEM` chip's vertical
  label now uses `LeapWallpaperKind.systemInk(for: scheme)` (white in dark mode, near-black
  in light mode) via a new `@Environment(\.colorScheme)` on `WallpaperStrip`, so it stays
  legible on the System panel which itself flips with the device appearance. `WHITE` stays
  dark-on-light; the other solid panels stay white.

## Issues addressed (`issues/issues.md`) — reviewed by GPT-5.6 Sol


The three issue sets were implemented and passed a **GPT-5.6 Sol** (`gpt-5.6-sol`)
design-judge review (styleDifferentiation **9.5**, iOS26Nativeness **9**,
sleekness **9**, legibility **8**, consistency **9**). Highlights:

- **Style is the variety axis (V5/V7).** Catalog consolidated **21 → 13** (no
  near-duplicate designs). Every design + shared chrome (`BrandMark`, `TapPill`,
  `CheckInDesign` prompt) is style-aware so the 4 styles read as clearly distinct
  (Editorial serif+filled pill · Minimal thin-uppercase+underline · Dot-Matrix
  monospaced `[ ]` · Neon glowing lime).
- **Neon style added (V14).** 4th (newest) style, deep-lime glow. There is no Glass style.
- **3-tab app (V8).** Dropped the standalone Style/Wallpaper tab; style + wallpaper
  are chosen in the Add/Edit sheet. Dock is a translucent iOS-26 glass bar (V1).
- **Add/Edit sheet:** prefilled with the widget's current preset on edit (V3);
  horizontal, uncluttered style picker (V6); full-width gradient **Save** (not a
  button-in-a-button) with no overflow scroll (V12); **Design** row opens a drawer
  filtered to designs supporting the current size (V10).
- **Showcase preselect (V13).** Each kind has a `signatureStyle` used in Browse and
  preselected on add (Clock → Dot-Matrix, Big Date → Minimal, …).
- **My Widgets / Browse polish (V4/V9/V11).** Compact `SavedWidgetCard` shows the
  whole widget cleanly; single-line meta chips (no wrap); premium Browse tiles.
- **Adaptive previews (V2).** In light mode widget content is dark-on-white and
  vice-versa (in-app previews); Home-Screen content stays white-on-wallpaper.
- **Rabbit app icon (V15);** iOS-gallery guidance to tap **Edit Widget** (V16).
- **Functionality:** realtime clocks tick via `TimelineView(.periodic(by:1))` when
  `clockLive` in-app (Add/Edit sheet only - Browse tiles stay cached/static); on the
  Home Screen every time face runs a **per-minute** timeline (minute-accurate
  hands/digits). Faces with a **second hand** (`showsSecondHand`: Analog, Segment,
  Seconds) instead ship `leapSecondHandEntries` (**900**) entries at **2s**, so the hand
  **ticks every two seconds** - the same 30-minute horizon and ~48 reloads/day as a
  180-entry 10s timeline, because entry *count* is free as long as the archive fits. 2s
  rather than 1s is deliberate and measured: iOS coalesces third-party widget repaints,
  so a 1s timeline still rendered at ~2s on device while doubling the archive and the
  extension's peak memory - and at 1s the heavier Analog/Segment faces never left their
  placeholder. There is no public API for a true 1Hz Home-Screen repaint. The
  real ceiling is the **timeline ARCHIVE SIZE**, and the **device is far stricter than
  the Simulator** (sim: 10.32MB accepted, 11.30MB rejected; device: ~2.2MB rendered but
  ~4.0MB did not - budget ~1.5MB): WidgetKit archives the whole view tree once per entry, and an oversized
  archive is rejected outright (`too large timeline archive`, `CHSErrorDomain 1050`),
  retried an hour later, and the tile sits on its placeholder - the "widget only shows
  the loading screen" report. Four fixes brought the worst face from **24MB to 1.3MB**:
  `LeapTickMarks` draws the 60 bezel marks as **one dashed circle** instead of 60 shapes
  (a single merged `Path` was not enough - 18MB); the readouts use `Text(verbatim:)`
  instead of `Text(.currentDate, format:)`, because a `Date.FormatStyle` serialises its
  calendar + locale + time zone into every entry (~5KB each); and the step moved to
  2s/900 entries, bringing the worst face to 2.2MB. Rasterising each static dial via
  `ImageRenderer` (`LeapStaticDial`) also worked size-wise (-34%) but was **reverted**: it
  renders in a fresh, light-appearance environment and a cache key interpolated from a
  `Color` cannot tell light from dark, so every dial, tick ring and numeral vanished on a
  dark Home Screen. Separately, the second-hand angle **wraps to `0..<360`**
  (`LeapSecondAngle.degrees`) and the face suppresses the animation on the single
  decreasing step per minute (`animates(at:step:)`): WidgetKit animates between entries, so
  an *animated* `second % 60` wrap swept the hand backwards once a minute - but a fully
  monotonic angle tracks ABSOLUTE time and spun it once per skipped minute on unlock. The
  hour/minute hands (`LeapHandAngle`) stay monotonic; at 6 deg/min they never accumulate a
  turn. See the second-hand section at the end of this file.
  Measured NON-causes, do not chase: the ~24 `.environment` modifiers in
  `LeapWidgetView.styled(_:)`, the 66-case `content(now:)` switch, and the 521 no-op
  `legible()` / `legibleContent()` / `neonGlow()` / `neonIf()` wrappers (16 bytes). A per-second *rotating*
  hand built on a custom `DiscreteFormatStyle` remains **measured not to work** - the
  host never repaints a custom style (0 changed pixels over 8 frames on a placed
  widget), and stacked live views cap at about **8** (10/12/60 strand the tile) (F1);
  every design is functional after
  the consolidation (F2); Today
  card **daily-resets +
  increments streak on tap, with a 7-day free-widget-credit stub** in `LeapStore`
  (`leap.state.v1`, `freeWidgetCredits`) (F3); per-widget **opensApp** toggle (F4)
  makes the tap either launch Leap or stay **interactive** (F5); dot-matrix time
  widgets **blink the `:`** (F6); **Mantra** accepts custom text with a default (F7).
- **Performance:** `clockLive` is opt-in and time content is only wrapped in a
  `TimelineView` when needed; lazy stacks in Browse/pickers keep scrolling smooth
  (P1/P2).

## Refinements addressed (`docs/refinement_ask.md`)

A follow-up refinement pass ([`docs/refinement_ask.md`](../refinement_ask.md), refs
in [`docs/refinement_ref/`](../refinement_ref/)):

1. **More gradient wallpapers + a `system` wallpaper.** `LeapWallpaperKind` gained
   `system, ocean, grape, sunset, rose, forest` (plus existing gradients). The
   `.system` wallpaper is **scheme-adaptive**: on the Home Screen (and in in-app
   previews) its panel + content flip light/dark with the OS theme via
   `LeapWallpaperKind.systemThemed` / `systemInk(for:)` / `systemColors(for:)`
   (`Shared/LeapWallpaper.swift`). Other wallpapers keep their fixed gradient.
2. **Transparent is now per-placement in Edit Widget, not the app.** The in-app
   Add/Edit sheet has **no** transparent toggle; `LeapWidgetConfigIntent` gained a
   `@Parameter var transparent: Bool` (**default `false`** — follow-up-1 #10 "don't
   make the widget transparent by default") chosen in the long-press → Edit Widget
   menu. Provider maps it to `LeapBackgroundStyle.transparent` ("Invisible") /
   `.solid` ("Solid") (`LeapWidget/LeapCheckInWidget.swift`). `LeapSavedWidget
   .transparent` is retained for back-compat but no longer drives the background.
3. **Widget-gallery guide.** In the iOS widget gallery the preview swatch renders a
   concise `LeapGalleryGuide` (touch-cue + 4 numbered steps) instead of live content:
   `LeapEntry.isPreview = context.isPreview` (set in `placeholder`/`snapshot`),
   branched in `LeapWidgetEntryView.body` with a neutral dark `containerBackground`.
   Placed widgets (isPreview == false) render normally. **Can't be verified in the
   Simulator** (no gallery access) — build-verified only.
4. **Edit-Widget picker (real preview, payload-safe).** `LeapSavedWidgetQuery` is an
   `EntityStringQuery` (searchable -> sheet drawer). `LeapSavedWidgetEntity`'s
   `displayRepresentation` shows a **real miniature** of each saved widget: the app
   renders a **tiny** preview (`LeapViewModel.renderThumbnail` -> `LeapWidgetPreview`
   via `ImageRenderer`, JPEG ~6-8KB) into `LeapThumbnailStore` (App Group) whenever the
   library changes; the entity embeds it as `DisplayRepresentation.Image(data:)` — but
   ONLY through `LeapThumbnailStore.data(for:)`, which refuses anything over
   `maxBytes` (~12KB), and falls back to the category **SF Symbol** otherwise. This is
   the key: iOS archives the *selected* entity's display representation into the
   widget-intent payload, so an **oversized** image (the old 960×960/~1MB, which had no
   guard) bloated it, `configuration.widget` arrived **nil**, and the placed widget
   showed the how-to guide ("selecting a widget in Edit doesn't load it", issue3 #6). A
   guaranteed-tiny image makes that impossible by construction (Apple's own Photos
   widget shows thumbnails in this same picker), so previews are safe again. **Keep the
   thumbnail tiny** — do not remove the size guard. Belt-and-suspenders: `LeapSavedWidget`
   decodes `wallpaper`/`slot` tolerantly and `LeapLibraryStore.load()` decodes
   element-by-element (`LeapFailable`), so one bad record can't return an empty
   library in the extension (another path to the guide).
5. **My Widgets list is concise.** `SavedWidgetRow` = left text meta (size badge +
   title + style·wallpaper), right compact `LeapWidgetPreview`; **swipe-left to
   delete** (`.swipeActions`). A `sizeFilterBar` (SMALL/MEDIUM/LARGE counts) filters
   the list (`Leap/HomeView.swift`).
6. **Hero = auto-scrolling carousel.** `WidgetShowcaseCarousel` auto-advances curated
   medium (kind, style, wallpaper) picks; tap opens the Add sheet prefilled with that
   design+style. The daily check-in (F3) is preserved as a slim `checkInStrip`.
7. **Browse text.** Tile title (`BrowseTile`, `LeapFont.display(20,.bold)`) is bigger
   than the category header (mono) and left-aligned to the tile's edge
   (`Leap/Browse/BrowseComponents.swift`).
8. **Custom-photo slot preview.** `LeapWidgetPreview` gained `slot` + `screen` and a
   `customSlice` that bakes the exact wallpaper slice at the slot (mirrors
   `LeapWidgetBackground.bakedWallpaper`), so changing Top/Middle/Bottom updates the
   uploaded-photo preview (`Leap/WidgetShowcase.swift`).
9. **Image-led onboarding.** `Leap/OnboardingView.swift` rewritten to 3 visual,
   few-words pages (hero widget cluster · "melts into your wallpaper" · 4-step add
   guide) using `LeapFont` (no `design:.rounded`).

## Later refinement passes (bug fixes + follow-up 1/2/3)

Three more passes after the refinements above (sources: the commented block +
`follow up 1/2/3` in [`docs/refinement_bug.md`](../refinement_bug.md)). Durable
architecture facts (not a full changelog):

- **User-selectable app accent color (biggest change — follow-up-2 #2/#3).** The
  hard-coded lime is now one of **7 accents** — `LeapAppAccent` (`lime, coral, teal,
  indigo, amber, azure, rose`) in `Shared/LeapTheme.swift`. `LeapAccentStore` (a
  `final class`, `.shared.current`, persists `leap.accent.v1` in the App Group) is the
  source of truth. `LeapTheme.lime` / `limeDeep` / `accentText` are **static computed
  reads** of that store. `LeapViewModel.appAccent` is `@Published`; `setAppAccent(_:)`
  updates the store, calls `WidgetCenter.reloadAllTimelines()`.
  Widget content/previews read the accent via the `\.leapAccent` / `\.leapAccentDeep`
  environment (injected in `LeapWidgetPreview` / dispatcher). Changeable anytime in
  **Settings**, and on **onboarding page 2**. Default lime.
- **Theme propagation gotcha (follow-up-3 h3).** Because `LeapTheme.lime` etc. are
  **static** (not `@Published`/observable), SwiftUI won't re-read them in a subtree
  that didn't otherwise change — the color looked stale until you navigated away. Fix:
  each tab in `HomeView`'s `TabView` has **`.id(model.appAccent)`** so its subtree
  rebuilds on accent change. `OnboardingView` already re-renders (it's
  `@EnvironmentObject model`). Placed widgets + Edit-picker thumbnails update via the
  `setAppAccent` reload/render calls above. **If you add a new top-level surface that
  uses `LeapTheme.lime`, give it an accent-keyed `.id` or observe `model` or it'll go
  stale.**
- **Theme propagation gotcha #2 — BAKED BITMAP CACHES ignore `.id(...)` (fixed).** The
  `.id(model.appAccent)` rebuild above only re-runs *view* code; it cannot repaint a
  bitmap that was already rendered. **Browse tiles are exactly that** —
  `BrowsePreviewCache` (`Leap/Browse/BrowsePreviewCache.swift`) is a `static let shared`
  singleton of `ImageRenderer` output that outlives the `.id` rebuild, and its `Key`
  originally covered only design/size/style/colour-scheme. So every Browse preview kept
  its OLD accent (lime tiles under an amber app) until the cache happened to be dropped.
  Fix: the accent is now part of **both** `BrowsePreviewCache.Key` (`accent:
  LeapAccentStore.shared.current`, passed explicitly from `BrowseTile.cacheKey`) **and**
  `BrowsePreviewCache.signature(for:)`, so an accent change clears the whole cache (rather
  than accumulating one bitmap set per accent) and re-fires each tile's `.task(id:)`.
  `setAppAccent` also calls `refreshThumbnails(force: true)` so the iOS Edit-Widget picker
  miniatures — likewise baked bitmaps — are re-rendered. **Rule: any new cached/rendered
  bitmap of widget content must include the accent in its cache key.** Verified in the sim
  (Settings -> Amber -> Browse): the Browse screenshot went from 18,802 lime pixels to
  **0**, with 18,183 amber.
- **Swipeable infinite hero carousel (follow-up-2 #1, follow-up-3 h2).**
  `WidgetShowcaseCarousel` (`Leap/HomeView.swift`) auto-advances curated
  `(kind, style, wallpaper)` picks with a slow cross-fade and wraps infinitely; the
  daily check-in is slide 0. Each slide is a `Button` that opens the Add sheet.
  Tap-vs-swipe is disambiguated with **`.simultaneousGesture(DragGesture(minimumDistance:
  10))`** that flips a `dragActive` flag in `onChanged`; the slide button guards
  `if !dragActive`. `simultaneousGesture` (not `.gesture`/`.highPriorityGesture`) keeps
  the vertical `List` scroll working while stopping a slow swipe from registering as a
  tap that wrongly opens the sheet.
- **Transparency restored & re-verified (follow-up-3 h1).** The host-transparency
  swizzle had been temporarily disabled (grey/flicker) and now baked only; it was
  **re-enabled** per the user ("a previous build had this working") and **device-verified**
  (see [transparency.md](transparency.md) / [`docs/TRANSPARENT_WIDGETS.md`](../TRANSPARENT_WIDGETS.md)).
  The Swift render path is the **3-case** `transparentBackground` (system Clear/Tinted →
  live host → bake); the `Color.clear` gate on `isLiveWidget && hostTransparencyAvailable`
  is what prevents the old grey.
- **Onboarding theme picker (follow-up-3 h4).** `BlendPage` (page index 1,
  `Leap/OnboardingView.swift`) hosts a live 7-swatch accent picker + a **Neon** Clock
  preview passing `accent: model.appAccent.color`; tapping a swatch immediately
  recolors the widget preview, the selection ring, **and** the Continue CTA.
- **Wallpapers & smaller items.** `LeapWallpaperKind` grew scheme-adaptive `system`
  plus `frosty` / `white` / black (with vertical swatch labels for system/frosty/white)
  and more gradients (`ocean, grape, sunset, rose, forest`) — see the widget-styling
  memories. Home tab renamed from "My Widgets"; **All** size filter added; swipe-left
  delete CTA is red; splash shows just "Leap by Solo Leap Inc"; the Settings tab was
  slimmed (removed the transparency/wallpaper/position rows and the "how it works"
  block). Perf: hero timer ticks once per slide (not ~25 Hz) and off-screen slides
  don't run live clock timelines.

## Live widget data — real Calendar + Weather (add-time permissions)

The **Calendar** family (`monthGrid` / `agenda` / `daySpine`) renders real **EventKit**
events and the **Weather** family (8 designs) renders real **Apple WeatherKit** data for
the user's **CoreLocation** location. Durable facts:

- **New layer `Shared/LeapLiveData.swift`** — models (`LeapWeatherData`,
  `LeapCalendarEvent`), App Group cache (`LeapLiveStore`), and services
  (`LeapLocationProvider`, `LeapWeatherService`, `LeapCalendarService`). Threaded into the
  widget via two new optional `LeapSnapshot` fields (`weather`, `events`), injected by
  category in `LeapProvider.entry(...)`. See "Live widget data" in
  [architecture.md](architecture.md).
- **Permissions fire only on widget-add, never at launch** — `AddWidgetSheet.save()`
  (`Leap/HomeView.swift`) → `LeapViewModel.requestLiveDataAccess(for: kind.category)`
  (weather → Location + WeatherKit, calendar → EventKit). Verified end-to-end on the sim:
  the iOS Calendar and Location alerts appear with the exact usage strings **only** on
  *Save to Home*; the coordinate + events then cache to the App Group.
- **Graceful fallback** — nil real data → the existing representative sample
  (`LeapWeatherSample.resolve` / `LeapAgendaSample.resolved`); `agenda` shows a
  "Nothing scheduled" empty state (`[]` = real data, nothing scheduled). WeatherKit has
  no AQI (`aqi = -1` → designs render `--`). Calendar fetch is **timed events only**
  (all-day holidays filtered out).
- **WeatherKit is a PAID-team capability** — its entitlement is **commented out** in both
  `.entitlements` files so the free/personal team (`D2Z89UU4R7`) can sign device builds;
  EventKit + Location work regardless. WeatherKit returns nothing on the sim. Re-enable
  steps + the "device must be unlocked to launch" gotcha: [build-and-run.md](build-and-run.md).

## This-session refinements (widget-config, in-widget shadows, Live Clock bar, Browse curation)

Four fixes on top of the passes above. Durable facts (not a full changelog):

- **Edit-widget selection round-trip fix.** Selecting a saved widget in the iOS
  Edit-Widget menu showed the how-to guide instead of the chosen design. Two causes,
  both fixed: (1) `LeapSavedWidgetEntity.displayRepresentation` embedded a
  960×960 thumbnail image that bloated the archived selection so `configuration.widget`
  arrived **nil** at the provider — that unbounded thumbnail was removed (later re-added
  **size-guarded**: a tiny `Image(data:)` behind `LeapThumbnailStore.maxBytes`, see item 4); (2)
  `LeapSavedWidget` now decodes `wallpaper`/`slot` **tolerantly** (unknown rawValue →
  `.system`/`.top`) and `LeapLibraryStore.load()` decodes **element-wise** via a
  `LeapFailable` wrapper, so one bad record can't wipe the whole library.
- **No shadows on in-widget text/elements (card shadow kept).** `LeapLegibleShadow`,
  `LeapLegibleContentShadow`, and `NeonGlow`/`NeonIf` are **no-ops**; `WeekStripView`'s
  `.shadow` was removed. Only the outer **card** shadow (`WidgetShowcase` /
  `BrowseComponents`) remains. The `leapContentShadows` env/param is now dead plumbing
  left in place to avoid churn.
- **Live Clock / Day Timer progress bar matches the style (`LeapDayProgressBar`).**
  `ProgressView(timerInterval:)` only renders correctly inside a WidgetKit host; in the
  in-app Browse/preview render (ImageRenderer) it fell back to a stray **yellow** linear
  bar with a position **knob**, ignoring `.tint(accent)`. Replaced the day-progress bar
  in `CurrentTimeDesign` ("Live Clock", `.timeNow`) and `DayTimerDesign` with a custom
  **`LeapDayProgressBar`** (Capsule track + accent Capsule filled to the day fraction).
  A day bar advances ~0.001 %/sec, so a static fill from the entry date is visually
  identical to the self-animating version on the Home Screen while matching the widget
  style everywhere. `clockLive` can't distinguish preview-vs-widget (Browse tiles render
  `live:false`, same as the host). `Shared/LeapWidgetTime.swift`.
- **Browse category curation (`LeapWidgetCategory.browseOrder`).** Browse now iterates a
  curated list instead of `allCases`: **Clock, Date, Calendar, Weather, Streak, Progress,
  Battery, Storage, Activity**, then Goal, Mantra. Focus / Settings / Screen Time / Globe
  / Sound are hidden from Browse (still shipped + addable). The header design count is
  computed from `browseOrder` (59, was 66). Decoupled from the enum declaration order so
  timeline/categorization logic is unaffected. `Shared/LeapWidgetContentView.swift`,
  `Leap/Browse/BrowseTab.swift`. Verified end-to-end on the iPhone 17 Pro sim.

## This-session refinements (widget spacing + real battery %)

Layout polish + one architecture fact. Durable facts:

- **Battery widgets show the REAL device battery (new App-Group live-data channel).**
  `LeapBatteryRepresentative` (the hardcoded `percent = 80` sample in
  `Shared/LeapWidgetBattery.swift`, used by Gradient/Speedo/BatteryStorage/BatteryGauge
  designs) now reads `LeapLiveStore.shared.loadBattery()`, falling back to 80 only when
  no reading is cached. The **app** reads the battery (an app-only capability — WidgetKit
  extensions can't) in `LeapViewModel.refreshBattery()`: enables
  `UIDevice.isBatteryMonitoringEnabled`, reads `batteryLevel`/`batteryState`, caches to
  the App Group via `LeapLiveStore.saveBattery(level:charging:)`
  (`leap.live.battery.level.v1` / `leap.live.battery.charge.v1`), and calls
  `reloadAllTimelines()` when it changes. Called from `refresh()` (launch/foreground).
  Mirrors the weather/calendar live-data pattern. **The Simulator reports `batteryLevel
  = -1` (unknown), so battery widgets fall back to 80 on the sim** — real % only shows on
  a physical device. `BatteryDesign`/`.battery` kind (Low-Power/thermal, not %) is
  untouched. Files: `Shared/LeapLiveData.swift`, `Leap/LeapViewModel.swift`,
  `Shared/LeapWidgetBattery.swift`.
- **Large designs fill their card by distributing rows/sections, not trailing Spacers.**
  Month+Agenda (`MonthAgendaDesign.monthPanel`) lays the month out as `weekRows: [[Int?]]`
  in a `VStack` where each week `HStack` cell is `.frame(maxWidth/maxHeight: .infinity)`,
  so the calendar occupies the whole panel instead of leaving a blank lower half. Same
  idea applied to Goal Dashboard (`DashboardDesign` interleaves `Spacer(minLength: 8)`)
  and Weather Metrics (UVI bar + tile grid stretched to `maxHeight: .infinity`).

## This-session refinements (modern tab icons + widget declutter)

- **Tab bar uses a modern filled trio.** `Leap/HomeView.swift` `TabView`: Home
  `house.fill`, Browse `square.grid.2x2.fill`, Settings `gearshape.fill` (were the older
  `square.grid.2x2` / `square.grid.3x3` / `gearshape` outlines).
- **Declutter direction = shrink icons/elements, keep ALL data, add spacing** (user:
  "reduce the icons size and keep all the data as is ... fit all the data with enough
  spacing"). Applied in `Shared/LeapWidgetWeather.swift` + `Shared/LeapWidgetBattery.swift`:
  Weather Metrics (Neon L) metric-ring circles 48->40 / icon 17->14, hero glyph 60->50,
  temp 30->26, UVI bar width 38->30, grid spacing 18->20; Hourly (Editorial M) hour-cell
  glyph 21->17 / v-padding 8->7 / inner spacing 8->6 / bottom-row spacing 6->8;
  Battery+Storage (Minimal) panel icon 22/18->20/16.
- **GOTCHA - Horizon (`WeatherHorizonDesign`) medium overflows the 165pt frame.** The
  design is force-framed to `size.previewReferenceSize` (medium 338x165) by
  `LeapWidgetPreview`, but hero (glyph+temp+condition+L/H) + 3-day forecast + 4 gauge
  circles intrinsically need ~210pt, so the content **center-clips**: the 3-day forecast
  **day labels (FRI/SAT/SUN) are always clipped above the frame**. With the original 54pt
  gauge circles they're hidden entirely (looks clean/balanced); shrinking them shifts the
  whole top row up and exposes the clipped label stubs. So Horizon was historically left
  at its original sizing. **UPDATE (this session): RESOLVED** - rather than leave the medium
  clipped, `WeatherHorizonDesign` was split into `mediumBody` / `largeBody` (compact
  horizontal hero + smaller 44pt gauges + bigger 16pt labels) that fits 165pt with no
  clipping, so the old "do NOT shrink its gauges" caution no longer applies. See
  "This-session refinements" below.
- Verified each of the 4 at native reference size via a temporary in-app Debug gallery
  (4th tab rendering `LeapWidgetPreview(adaptive:true, live:false)` at
  `previewReferenceSize`), then fully reverted the gallery before committing. Committed +
  installed to Viki's iPhone (CoreDevice `81D76C67-...`).

## This-session refinements (blank-widget hang FIX + battery/storage/Horizon)

Five issues; the first is a CORE functionality break the user has hit repeatedly.

- **CORE FIX - "widget goes blank on edit / never loads / could not run".** ROOT CAUSE:
  `timeline(for:in:)` `await`ed `LeapWeatherService.refresh()` which, when location was
  authorized, ran `CLLocationManager.requestLocation()` — a one-shot GPS fix whose delegate
  **can silently never call back inside a widget extension**, suspending the provider
  forever. The placed widget then stays on its blank placeholder and iOS can surface **"The
  action 'Leap Widget' could not run because an unknown error occurred."** Weather faces
  (e.g. Rain Window) were the victims; it was intermittent because it depended on
  location/OS timing. FIX (`Shared/LeapLiveData.swift`, `LeapWidget/LeapCheckInWidget.swift`):
  (a) `LeapLocationProvider.currentCoordinate(allowOneShot:)` + `LeapWeatherService.refresh(allowOneShot:)`
  — the extension passes **`allowOneShot: false`** so it uses the app-cached coordinate and
  never runs the hanging one-shot; (b) new **`leapRefreshBounded(_:_:)`** wraps each refresh
  in a 6s cap so a slow WeatherKit/EventKit call can't blow the budget; (c) the timeline is
  always built from the cached `LeapLiveStore` values regardless. **Permanent rule added to
  [realtime-widgets.md](realtime-widgets.md) (⛔️ box) so this never recurs.**
- **Battery shows wrong/stale %.** `LeapBatteryRepresentative` (`Shared/LeapWidgetBattery.swift`)
  now reads the charge **live in-process** (`UIDevice.isBatteryMonitoringEnabled = true` ->
  `batteryLevel`), which works in the extension too on a real device, falling back to the
  app cache then 80. Added `showsBattery` capability + a `+30 min` reload policy so battery
  faces refresh regularly instead of once a day. Sim still shows 80 (`batteryLevel == -1`).
- **Storage wrong (hardcoded 168/88 GB).** `BatteryStorageDesign` now reads real volume
  capacity via the existing `LeapSystemInfo.storage()` helper
  (`.volumeTotalCapacityKey` / `.volumeAvailableCapacityForImportantUsageKey`).
- **WeatherIsle wind showed a hardcoded `"N/A"`.** The wind row in `WeatherIsleDesign`
  (`Shared/LeapWidgetWeather.swift`) rendered a literal `isleMeta("N/A")` next to the
  `location.north.fill` glyph; it now shows the real sample wind
  (`isleMeta("\(wx.windMph) \(wx.windDir)")`, e.g. `6 SW`). (The nearby medium `WindCompass`
  `"SW - MPH"` caption is intentional - the big `LeapNum` above it is the value.)
- **Horizon layout (issue A) - GOTCHA above is RESOLVED.** `WeatherHorizonDesign` split into
  `mediumBody` / `largeBody`. Medium is now a **compact horizontal hero** (glyph + temp +
  one `Cloudy L.. H..` caption line) with the 3-day forecast on the right, then a row of
  **smaller gauges (circle 44) with bigger value labels (16)** below, a flexible `Spacer`
  keeping it top-anchored. Fits 165pt with **padding on all four sides and NO clipping** (the
  FRI/SAT/SUN labels are now fully visible). `WeatherRoundMetric` gained `diameter` /
  `valueSize` / `iconSize` params. Verified 1:1 in the sim Debug gallery.
- **Picker previews (issue E) - added, size-guarded.** The user asked (twice) for rendered
  thumbnails in the Edit-Widget picker. Now delivered safely: the app renders a **tiny**
  (~120px, JPEG ~6-8KB) preview per saved widget into `LeapThumbnailStore` and the entity
  embeds it via `DisplayRepresentation.Image(data:)` behind a hard `maxBytes` guard (with an
  SF-Symbol fallback). The earlier "intentionally NOT added" stance was an over-correction: the
  blank-widget bug was the **~1MB image size**, not images per se. Keep the thumbnail tiny; the
  guard (`LeapThumbnailStore.data(for:)`) means the archived selection can never bloat. See item
  4 above and the comments in `Shared/LeapIntents.swift` / `Shared/LeapWallpaperStore.swift`.

Sim + device builds SUCCEEDED; committed as `e244b67` and installed to Viki's iPhone
(CoreDevice `81D76C67-...`). The blank-widget-hang rule is also mirrored as a repository
memory ("widget blank hang") so it survives outside these docs.

## Leap Premium IAP refinements (paywall + 7-day trial + photo gate)

Refined the Pro purchase experience into **"Leap Premium"** and added a trial + gating layer.
User-facing strings only were rebranded Pro -> Premium; the internal API (`isPro`,
`LeapProduct`, product IDs `com.sololeap.leap.app.pro.*`) is unchanged so `.storekit`
matching stays intact. `Leap.storekit` display/reference names were rebranded to Premium.

- **Paywall (`Leap/PaywallView.swift`).** `LEAP PREMIUM` eyebrow, `PREMIUM` column,
  `Unlock Leap Premium` CTA. Comparison rows simplified: Widget designs `Basics / All`,
  Styles `1 / All`, Wallpapers+photo `1 / check`, plus Saved widgets `4 / Unlimited` and
  Live weather & calendar. Loss banner (widget-limit context) now reads
  **"Don't lose access to your \(savedCount-4) trial widget(s)"**.
- **Upgrade button (`ScreenHeader`).** Icon `sparkles` -> **`sparkle`** (star-burst),
  label tint -> **white**.
- **7-day trial (`Shared/LeapEntitlements.swift`).** `trialStartKey = leap.trial.start.v1`
  (App-Group, `timeIntervalSince1970`), `startTrialIfNeeded()` called once from
  `LeapViewModel.init`. Home shows a **`trialBanner`** ("N days left") while
  `!isPro && isTrialActive`. After expiry, `isFreeWidgetLocked(rankOldestFirst:isPro:now:)`
  locks the **newest surplus widgets** (oldest-first rank >= `freeWidgetAllowance` = 4); those
  `SavedWidgetRow`s dim, show a lime `PREMIUM` lock pill + "Tap to keep this widget with
  Premium", and tap -> paywall. `freeWidgetHardCap` = 8 still paywalls the 9th add.
- **Photo gate (`AddWidgetSheet`).** `freePhotoAllowance = 1`. Picking a 2nd custom photo
  (`model.canAddCustomPhoto(excluding: editingID)` counts saved `.custom` widgets) is blocked
  and surfaces the upsell instead of importing. A purchase mid-add completes the interrupted
  save via `onChange(of: model.isPro)`.

Verified: `xcodebuild` BUILD SUCCEEDED; sim screenshots of both paywall variants, the white
star-burst Upgrade button, and the "7 days left" trial banner; an App-Group plist injection of
an expired `leap.trial.start.v1` showed the newest widget locked (lock overlay) with the banner
hidden. A standalone 19-assertion logic harness confirmed the trial-day math, lock ranks
(0-3 unlocked / 4-7 locked, Pro exempt), and photo gating (1 free, 2nd blocked).

## Battery %: investigated, NOT fixable, no code shipped (issue6 #4)

Reported: "battery app still shows at 5% intervals not the real time battery percentage".

**Root cause is iOS, not Leap.** Since iOS 17 UIKit deliberately quantises
`UIDevice.batteryLevel` to 5% steps, and it still does on iOS 18 and 26. Apple engineers
describe it as "expected and intended behavior" (an anti-fingerprinting measure). No Leap
code ever rounded anything - the faces were faithfully rendering an already-rounded value.
`batteryLevelDidChangeNotification` is quantised the same way.

**Outcome: no product change. The 5% granularity stands.** Both ways of getting a finer
reading were built and tested on a physical iPhone 17 Pro (iOS 26), and both are dead ends:

1. **Private `IOPS*` IOKit power source** - `IOPSCopyPowerSourcesInfo` /
   `IOPSCopyPowerSourcesList` / `IOPSGetPowerSourceDescription`, resolved via
   `dlopen` + `dlsym`. This *works*: device-verified returning `Current Capacity` in both the
   app process **and** the widget extension. But those three symbols are enumerated
   **verbatim** in Apple's canned Guideline 2.5.1 rejection ("uses or references the
   following non-public APIs: _IOPSCopyPowerSourcesInfo, ..."), the rejection that blocked
   every Adobe AIR app for months. `dlsym` keeps them out of the import table (`nm -u` is
   clean) but a byte scan of the built binary found all three sitting in it as **plaintext**,
   which is exactly what a `strings` scan reads. Not shippable.
   - Note for anyone weighing this against the transparency hook: they are **not** the same
     risk class. `LeapWidgetTransparency.mm` resolves an **Obj-C class name** via
     `objc_lookUpClass`, not a C symbol on Apple's published list.
2. **Public IOKit** - every symbol needed is genuinely public on iOS (`IOServiceMatching`,
   `IOServiceGetMatchingService`, `IORegistryEntryCreateCFProperties`, `IOObjectRelease`,
   `kIOMainPortDefault`, all DECLARED in the iOS SDK headers; the `IOPS*` family is the
   opposite - exported by the dylib, declared in **zero** iOS headers, 36 of them). An
   on-device probe using only the public symbols showed the sandbox does **not** block the
   lookup, but iOS **redacts the property dictionary**:

   ```
   IOPMPowerSource   = OK[n=2]{BatteryInstalled,ExternalConnected}
   AppleSmartBattery = OK[n=2]{BatteryInstalled,ExternalConnected}
   AppleARMPMUCharger= NOT_FOUND
   IOPMrootDomain    = OK[n=0]{}
   ```

   No `CurrentCapacity`, no `MaxCapacity`, no `AppleRawCurrentCapacity`, no `IsCharging`. A
   third-party app may learn a battery exists and that the device is plugged in - never the
   charge.

An intermediate version shipped the private path gated behind `#if DEBUG || LEAP_INTERNAL`
(exact % for dev/TestFlight, coarse % for the App Store). **That was reverted**: a widget
must not behave differently for the developer than for the user, and a divergence that only
ever manifests in the build the customer *doesn't* get is a debugging trap, not a feature.
Leap now reads the plain public `UIDevice.batteryLevel` on **one code path for every build**.

**Do not reopen this.** Getting a 1% charge on iOS requires private API; there is no public
alternative. `Shared/LeapLiveData.swift`, `Leap/LeapViewModel.swift` and
`Shared/LeapWidgetBattery.swift` are back at their pre-investigation state, and the working
tree carries no private-API code.

**Useful gotchas banked from the investigation** (they apply to any future private-symbol
question):

- Scan a **device (`-sdk iphoneos`)** build, never a simulator one - simulator-excluded code
  gets dead-stripped by whole-module optimisation, so a clean sim scan proves nothing.
- `nm -u` alone is not evidence of absence; `strings -a <binary> | grep <symbol>` is the check
  that matters.
- Swift small-string optimisation hides literals of <= 15 UTF-8 bytes from `strings`
  entirely (e.g. the 14-byte debug-panel password), so a missing short string proves nothing
  either.

---

## LKG-Fix: 4-agent audit + the on-device clock freeze (functional + perf pass)

A multi-agent review (GPT / Opus / Gemini, plus an independent GPT-5.6 Sol code review)
audited the app for functional and performance defects. Every finding was **verified
independently before being actioned** - 4 of the 15 reported issues were disproved and
rejected, which is why the list below is shorter than the reports were.

### The headline bug: clocks froze after ~30 minutes

**Symptom (user-reported, on device):** second-hand clock faces ran correctly for a while,
then sat at a stale time and never recovered "until I open the Leap app and close it".

**Cause:** second-hand faces were the *only* clock family with **no freeze buffer**. Every
other clock ships 180 per-minute entries = **3 h** of archived cover precisely so a
throttled `.atEnd` reload cannot strand it; second-hand faces archived exactly their
900 x 2s = **30-minute** dense run and stopped there. A reload that is dropped or batched
does not re-run the extension - WidgetKit simply keeps presenting what is already archived
- so once those 30 minutes were spent the face was frozen. Opening the app fixed it because
a **foreground** reload is budget-exempt.

**Fix:** the dense run is unchanged (900 x 2s), the reload is now requested via
`.after(denseEnd)` - the exact moment `.atEnd` used to ask - so the **reload budget is
unchanged (~48/day)**, and a **graduated freeze buffer** is archived beyond it: per-minute
for 30 min, then every 5 min out to 3 h. **+54 entries (+6 %)** buys a **5.8x** longer
freeze window (30 min -> ~175 min). It is graduated rather than flat per-minute because a
flat buffer costs +17 % archive, and archive size is the constraint that gets a reload
rejected outright (the *opposite* bug). The buffer is never reached in the happy path,
which matters because at those spacings the hand cannot glide.

Verified by sweeping all 60 build-seconds: 0 duplicates, 0 backwards, 0 past-dated, 0
misaligned buffer entries. Buffer entries anchor on `minuteStart`, **not** the
second-floored `start` - anchoring on `start` lands every entry at an offset like `:37`.

### Also fixed

| Area | Issue | Fix |
|---|---|---|
| Live data | `leapRefreshBounded` enforced **no** timeout: `withTaskGroup` implicitly awaits *all* children, and `EKEventStore.events` ignores cancellation. Measured 6.01 s under a 2.5 s budget | Detached task + single-resume actor gate -> **2.65 s**. Gate proven safe against double-resume, never-resume, lost wakeup |
| Clock | Hour/minute angles wrapped (`minute / 60 * 360`) - dormant today, but re-arms the backwards-spin bug the moment those hands are animated | `LeapHandAngle`: monotonic, whole-minute-snapped, zone-aware, allocation-free. Verified **pixel-identical** to the old maths (max deviation 3e-14 deg over 5 zones x 400k samples); backwards steps fell from *every minute* to 2/year (real DST fall-backs). Also drops a `Calendar` + `DateComponents` allocation per entry |
| Clock | Dot-Matrix analog hands were a `ForEach` of `Circle`s - N shapes x ~950 entries | One dash-stroked `LeapDottedRay` per hand; flat in the dot count |
| Clock | `:SS` digits on dense-timeline faces stepped 13, 15, 17 - text cannot be interpolated, so it read as a *stopped* clock next to a gliding hand | `seconds: false` on both dense-timeline readouts. `CurrentTimeDesign` keeps its seconds - it is not on the dense timeline and uses the self-updating `Text(.currentDate, format:)` |
| IAP | User cancellation reported as an error; a cancelled **restore** additionally fell through to "No previous purchases found" | Four distinct outcomes kept separate; `userCancelled` no longer logged as a telemetry failure reason |
| IAP | Stale `errorMessage` re-fired on the next attempt | Cleared before every purchase/restore |
| Premium | `freePhotoAllowance` was enforced at *import* only, so the imported photo stayed selectable on every later widget - one import unlocked unlimited use | Gate also applied on **save** (`isPro` short-circuits first) |
| Memory | `BrowsePreviewCache` unbounded across 66 designs x 4 styles | LRU cap + purge on memory warning |
| Storage | Day-counter records leaked forever after a widget was deleted | `LeapCounterStore.remove/prune`; **`prune` must run after `savedWidgets` is reassigned** or it deletes live counters |

### Rejected after verification (do not re-report)

- **"NaN reaches a `frame(...)`"** - reported CRITICAL. Disproved by running the actual
  Swift: `min`/`max` **sanitize** NaN (`min(1, NaN)` returns `1`), so the guard was already
  effective.
- **Gating the foreground `reloadAllTimelines()`** - shipped, then fully reverted. The
  budget exemption is **state-based, not initiator-based**: foreground reloads were always
  free, so the gate saved nothing and removed the user's only escape hatch from a frozen
  tile. See [realtime-widgets.md](realtime-widgets.md).
- **"Midnight angle rewind"** - the reviewer missed that the tile suppresses entry
  animation globally, so the wrap was not rendered as a spin.
## Second-hand resume spin + park-at-12 (post-LKG-Fix, on-device report)

Two symptoms reported off one build, both on the second hand only (the minute hand kept
moving correctly in each):

1. **"Locked for a while, unlocked, the hand spins many times before it starts gliding."**
2. **"Sometimes the hand stops at 12 and never moves."**

They have **different** causes and needed different fixes.

| # | Cause | Fix |
|---|---|---|
| 1 | `LeapSecondAngle.degrees` was strictly increasing from a fixed anchor, so its value tracked **absolute** time. The host does **not** present every archived entry - while the screen is locked they are skipped - so the next transition animated a delta of `elapsed x 6` deg over 2 s. 45 minutes locked = **45 revolutions**. This was the previous fix for the *opposite* bug (a wrapped angle sweeping backwards once a minute) | Angle **wrapped back to `0..<360`** (`secondOfMinute * 6`), and the wrap step is no longer animated: new **`LeapSecondAngle.animates(at:step:)`** returns `false` when `secondOfMinute < leapSecondHandStep`, i.e. on the **first entry of each minute** - the only transition where the wrapped value drops. That step is snapped (12 deg) instead of swept |
| 2 | The freeze-buffer tail added in LKG-Fix is deliberately **minute-aligned** (anchoring on the second-floored `start` would show a stale minute). So every buffer entry has `secondOfMinute == 0`: the hand rendered **at 12** on all of them, spun one revolution into the first, then sat still for a minute at a time while the minute hand advanced | Buffer entries carry **`LeapEntry.secondsLive = false`** -> `\.leapSecondsLive`; `LeapLiveSecondHand` and `SecondsClockDesign`'s bezel mark apply `.opacity(secondsLive ? 1 : 0)`. A hidden indicator honestly says "seconds unavailable"; a parked one asserts "0 seconds", which is wrong information. Only ever visible in the already-degraded throttled state |

Verified by running the arithmetic standalone: the wrapped angle is **exactly** the old
angle mod 360 (max deviation **0.0** over 200k seconds, so the picture is unchanged);
`animates(at:step:)` suppresses **exactly one** entry per minute for **both** parities of the
dense run (it lands on 58->0 or 59->1, and catches both); **zero** animated backwards
transitions over a 30-minute dense run; `LeapHandAngle` untouched (3e-14 deg vs legacy).

**Known residual, do not re-report:** a resumed entry can land *earlier* in its minute than
the last one drawn, giving one backwards flick of up to 354 deg. A view cannot see which
entry was previously on screen, and a skipped entry is indistinguishable from a presented
one, so this is **bounded, not eliminated**. Considered and rejected: nested
unanimated-coarse + animated-fine rotations (at the wrap the outer jumps +360 deg while the
inner animates 358->2, i.e. a **visible** backwards 356 deg spin) and `@State` to remember
the previous angle (SwiftUI state persistence in the widget host is undocumented).

**Review follow-up (GPT-5.6-sol and Gemini 3.1 Pro, independently, same finding):** the
first version gated on a hard-coded 2 s threshold, which is right for the widget's 2 s
timeline but wrong for the in-app `TimelineView` preview's **1 s** tick - there it snapped
BOTH the wrap and the following tick, i.e. two visible stutters a minute. `animates` now
takes the caller's real entry spacing (`step:`), read from `\.leapIsWidgetHost`. The
threshold is load-bearing in both directions, measured over 30 min: 2 s threshold in a 1 s
preview = 60 snaps instead of 30; 1 s threshold on an **odd-parity** 2 s host run = **30
animated backwards steps**, i.e. the original once-a-minute spin returns. Note this is the
opposite of the animation DURATION, which must stay context-INdependent.

## Paywall social proof: the catalog pill (shipped)

Added `PaywallView.catalogProof` - a full-width capsule with four overlapped 28pt mini
widget tiles and one line, **"3,500+ unique widgets in Premium"** - plus
**`LeapCatalogStats`** (`Shared/LeapWidgetContentView.swift`), now the single source for
the design / style / background / combination counts. `BrowseTab` was rewired to it and
its four private count helpers deleted, so the Browse header and the paywall can never
disagree.

**What was rejected and why** (do not revisit without new information):

| Considered | Verdict |
|---|---|
| Avatar stack + "210 people upgraded in the last 7 days" (the user's first pick) | **Rejected.** Invented customers on a purchase screen are a guideline **3.2.2(i)** risk and a **UK DMCC Act 2024 / EU Omnibus** fake-claim exposure. A *real* recency counter is also impossible here: `firebase/feedback.firestore.rules` is write-only-create with **no client reads**, so it would need Cloud Functions and therefore **Blaze billing**, which the project deliberately avoids |
| App Store rating / award badges | **Deferred.** Nothing to show pre-launch; revisit once there are real ratings |
| Cumulative "12,400+ widgets made with Leap" from the GA4 export | **Viable later.** Can only grow and is substantiable by the export, but needs a human to refresh a constant each release. Swap the copy in when the number is worth showing |
| Catalog arithmetic (**shipped**) | True by construction, derived at runtime, nothing to substantiate, no backend |

**Layout facts that cost several build/measure cycles** (all verified on the simulator in
both schemes): the string is **221.6pt** at `mono(11.5)` against **226pt** available on a
390pt phone, which is why the tiles are **28pt/-9pt** rather than 30/-10 and why
`mono(12.5)` (240.8pt) clips; **9pt of every tile but the last is covered by its
neighbour**, so "9:41" must occupy the **last** slot and overlapped slots carry <= 2
characters offset `-4` (otherwise it renders "9:4", then "9:41" clipped on the left once
offset); the wallpaper gradients need a `black.opacity(0.18)` scrim under white glyphs;
the number must use `LeapTheme.accentText`, not `LeapTheme.lime`, or it fails contrast on
the light canvas.

## Add/Edit sheet polish: hit areas, Word Clock, battery caveat

Three small, independent fixes.

1. **Segment chips were only tappable on the text.** `LeapSegment` (`Leap/HomeView.swift`)
   and the Settings appearance picker fill their row with
   `.frame(maxWidth: .infinity)` and draw the pill via `.background`. SwiftUI still
   hit-tested the **label glyphs**, so taps on the empty half of a SIZE / CLOCK FORMAT /
   TEMPERATURE chip did nothing. Both now carry
   `.contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))`.
   **Rule: any Button whose label uses `maxWidth: .infinity` + `.background` needs an
   explicit `contentShape`** - the background alone does not extend the tap target here.
2. **CLOCK FORMAT is now offered exactly where an hour is printed.** The rule is no
   longer "digital faces minus a hard-coded list" - it is *does this face render an hour?*
   - **Removed** from **Word Clock**: it spells the time on a fixed `ONE..TWELVE` word
     grid, so 24h has no rendering at all. Its `lit` set comes from
     `leapZonedCalendar(tz)` hour arithmetic, not a formatter, so dropping the forced
     locale changes nothing on screen.
   - **Added** to **World Clock**: it was deliberately configuration-free and followed
     `LeapClockFormat.deviceUses24Hour` (old issue6 #6). `WorldClocksDesign` now reads
     `@Environment(\.leapClockFormat)` like every other clock. Rows stay compact and
     never print AM/PM (three cities of "9:23 PM" would not fit), so the control's only
     effect is `1:23` vs `13:23` - applied to all rows at once. `deviceUses24Hour` is now
     **unused**; it is kept as the correct way to read the phone's setting.
   - **Added** to **Analog Clock at `.medium` only**, via the new
     `usesClockFormat(size:)`. The small family is a bare dial, but the medium layout
     pairs the dial with a digital `liveTimeReadout` that already honoured
     `leapClockFormat` - the control simply was not surfaced. The Add/Edit sheet calls
     `kind.usesClockFormat(size: size)`; the plain property is still what
     `LeapWidgetView.styled(_:)` uses to decide the forced locale.
   Still excluded: `.analogClock` (small), `.segmentClock` (also a hands face despite the
   name) and `.dayTimer` (a duration countdown only).
   **Behaviour change to know:** an existing World Clock widget on a 24h phone will flip
   to 12h, because saved widgets default to `LeapClockFormat.leapDefault` (12h). The user
   can now set it explicitly, which is the point.
3. **Battery's 5% granularity is now stated in the UI.** `LeapWidgetCategory.footnote`
   (`Shared/LeapWidgetContentView.swift`) returns an optional asterisked caveat; only
   `.battery` has one today - *"Due to iOS restrictions, battery percentage updates in 5%
   steps."* It renders under the category header in Browse (with a `*` beside the count)
   and under the preview in the Add/Edit sheet. This is the same closed, unfixable
   platform behaviour documented above - saying it once in the product stops it being
   filed as a bug. Add a caveat for another category by returning a string from `footnote`;
   both surfaces pick it up with no further wiring.

## Placed widgets now lock after trial expiry / churn

**Gap closed.** Until now the paywall only reached the *in-app* My Widgets list: a user
could stock up during the 7-day trial, let it lapse, and keep every widget rendering on
the Home Screen forever (documented as deliberate in `in-app-purchases.md` 6.5c). Now a
**placed** widget bound to a saved widget past the free 4 renders **blurred with a lock**.

Full mechanism and the exact tuned values are in
**[in-app-purchases.md 6.5d](in-app-purchases.md)** - only the decisions worth knowing
up front are repeated here.

1. **One shared decision, two targets.** The rank arithmetic used to live inline in
   `LeapViewModel`. It moved to `Shared/LeapEntitlements.swift`
   (`rankOldestFirst`, `isSavedWidgetLocked`, `willLockAtTrialEnd`) so the app list and the
   extension can never disagree. `LeapViewModel.isWidgetLocked` is now a one-liner.
   **Do not re-derive `count - 1 - index` anywhere else.**
2. **The extension decides for itself.** StoreKit is unavailable in an extension, but every
   input (library, `isProCached` mirror, trial start) is already in the App Group, so this
   needed **no new IPC**. *Trial expiry is exact*; a subscription *lapse* only lands after
   Leap is next opened, because nothing but the app can observe it.
3. **A locked timeline collapses to ONE entry** (`policy: .after(now + 1h)`,
   `history = []`). Non-negotiable: clock faces otherwise archive 900 entries and blow the
   WidgetKit archive limit, which strands the tile on its placeholder.
4. **`clampToTrialEnd`** trims entries at/after `trialEndDate()` so the tile flips into the
   locked state exactly when the trial ends - but **only when the expiry falls inside the
   timeline's own horizon**, or it would push a natural reload days out.
5. **The face stays recognisable.** blur 3.5/4.5 + saturation 0.85 + opacity 0.85 + a light
   scrim. **The first attempt (blur 6/8, saturation 0.4, opacity 0.55) was unreadable - do
   not go back to it.** A blank Home Screen is the worst possible churn experience; the
   point is to advertise what was lost, not to erase it.
6. **The lock is applied in `LeapWidgetEntryView` only**, never the shared `LeapWidgetView`,
   so in-app previews / Browse / the Edit sheet keep showing the clean design.
7. **Tapping a locked tile sells.** `.widgetURL("leap://premium")` ->
   `RootView.onOpenURL` -> `PaywallView(context: .widgetLimit(savedCount:), source:
   "widget_lock")`. **No URL-scheme registration was needed** (and none is possible without
   pbxproj surgery - the Info.plist is generated) because `widgetURL` is delivered straight
   to the owning app.

**Verified on the simulator, full round trip:** forced the trial to day 8 via the debug
panel -> both a small and a medium placement blurred and showed PREMIUM / "Tap to unlock"
-> tapping opened Leap on the `.widgetLimit` paywall -> toggling Premium on restored both
faces immediately. Debug, Internal and Release all build.

**Simulator gotchas hit while verifying** (worth knowing before re-testing this):
- `xcrun simctl spawn <udid> defaults write group.<id> ...` does **not** write the
  app-group container plist; it writes the sim's global prefs. Seed state through the UI.
- `LeapEntitlements.trialStartDate` reads the **Keychain first**, so editing the App-Group
  plist cannot fake an expired trial. Use the debug panel.
- A configured placement can report `configuration.widget?.id == nil` in the provider even
  though the Edit Widget picker shows the selection, and it survives a sim reboot. This is
  a **pre-existing sim quirk**, unrelated to this change - it blocks normal verification.

## License state-transition audit (GPT-5.6 Sol + Gemini 3.1 Pro) - gaps found & fixed

Two independent reviewers audited every free <-> Premium transition against the new
placed-widget lock. **Both independently found the SAME high-severity hole**, which is
the strongest signal in this file - it is fixed, along with three follow-ons.

### FIXED 1 (high, consensus): `clampToTrialEnd` silently skipped every sparse timeline

`clampToTrialEnd` decided whether the trial expiry fell inside the timeline's horizon by
comparing it to the **last entry's date**. That is only valid for `.atEnd`. The **sparse**
faces - default, weather, battery, system-stats - emit a **single entry dated `now`** and
then request `.after(now + 20min ... nextMidnight)`, so `end <= last` was **always false**,
the clamp bailed out, and the tile kept rendering live until its natural reload:
**up to a full day of free Premium after the trial ended.**

The root cause is a WidgetKit API limitation worth remembering: **`TimelineReloadPolicy`
exposes no associated date**, so a timeline's reload deadline *cannot be recovered from the
`Timeline` value*. `buildTimeline` therefore now returns `(timeline:deadline:)` - every
return site reports its own deadline (`denseEnd`, `next`, `nextMidnight`, or the last entry
for `.atEnd`) - and `clampToTrialEnd(_:reloadDeadline:willLock:)` compares against that.
**If you add a `return` to `buildTimeline`, you MUST supply its real deadline** or that
face silently stops locking.

### FIXED 2 (high): the trial was pure device-clock arithmetic - winding the date back revived it

Only the trial *start* was persisted; everything else trusted `Date()`. Setting the phone's
clock back a week resurrected an expired trial, in the app **and** in every placed widget.
`LeapEntitlements` now has a **one-way latch** (`leap.trial.ended.v1`, App Group + Keychain)
plus a **clock high-water mark** (`leap.clock.highwater.v1`) consumed via `observedNow(_:)`:

- Rolling the clock **back** is ignored (time only moves forward).
- Rolling it **forward** is self-defeating - it trips the latch, which never clears.
- Keychain-backed, so wipe-and-reinstall cannot mint a second trial.

Two things to know before touching this: `debugSetTrialStart` / `debugResetTrialAndSpin`
**must** call `clearTrialEndedLatch()` (the stepper moves in both directions, and without it
every step after the first reads as expired), and `observedNow` persists **at 60s
granularity on purpose** - it runs inside `isWidgetLocked`, which SwiftUI evaluates per row
per frame, so writing every call meant a UserDefaults write per row per frame.

### FIXED 3 (medium): opening the app did not repair stale placed widgets

A placed widget only re-evaluates its lock when its own timeline reloads. The trial can
expire - or a widget can be added/removed, which shifts everyone's oldest-first rank -
while Leap is closed. `LeapViewModel.syncPlacedWidgetLocks()` now runs on every `refresh()`
and calls `reloadAllTimelines()` **only when the set of locked widget IDs actually changed**
(signature in `leap.locks.signature.v1`), so it is a no-op on a normal foreground.

### FIXED 4 (low): a comment claimed the extension could self-heal out-of-process purchases

The hourly locked-timeline policy was documented as letting "an upgrade made outside the app
unlock the tile on its own". **It cannot** - the extension has no StoreKit and only re-reads
the mirror. Comment corrected: purchases made on another device land when Leap is next
opened.

### Accepted, NOT fixed (deliberate - do not re-litigate without a server)

- **Refund / revocation / Ask-to-Buy approval while Leap is terminated** cannot be observed.
  Correcting it needs a server-side entitlement mirror (App Store Server Notifications +
  `appAccountToken`). Today the state corrects on next app open.
- **The trial is per-device**, not per-Apple-ID: it is a local Keychain record and the
  products carry no StoreKit introductory offer, so a second device gets a fresh 7 days.
  The real fix is an introductory offer, which is a StoreKit/App Store Connect change.
- **Family Sharing** is not a transition here - both products are `familyShareable: false`.

### Verified correct by both reviewers (no action needed)

Fresh install -> trial; trial expired -> purchase (monthly + lifetime); lapsed -> repurchase
/ restore; cancellation before period end; billing-retry / grace (delegated to
`Transaction.currentEntitlements`); pending transactions granting nothing; refund while
running (`revocationDate == nil` check); offline launch; reinstall (Keychain survives, App
Group re-seeds); editing a widget preserving its rank; deleting an old widget correctly
unlocking a newer one; and the locked path still collapsing to one entry so the archive
limit is respected.

**Re-verified on the simulator after the fixes:** Premium ON -> all unlocked; Premium OFF +
day 8 -> the 2 surplus rows lock; stepper back to day 2 -> latch clears and the rows show
"5 days left in trial"; stepper forward to day 8 -> they lock again. Debug, Internal and
Release all build; Internal installed on device.

## Follow-up bug: the extension's Keychain latch pinned placed widgets locked forever

**Reported on device:** *"changing the number of trial days in the debug menu still shows
the premium widget being locked."* The in-app My Widgets rows unlocked correctly; only the
**placed Home-Screen widget** stayed on the locked face.

**Cause - a trap specific to this two-target layout.** The new one-way expiry latch was
written to BOTH the App Group and the Keychain (the Keychain copy exists so a
wipe-and-reinstall cannot mint a second trial). But **`LeapSecureStore` sets no
`kSecAttrAccessGroup`**, so each target lands in its own default access group:

| Process | Keychain access group |
|---|---|
| Leap app | `<prefix>.com.sololeap.leap.app` |
| Widget extension | `<prefix>.com.sololeap.leap.app.LeapWidget` |

So when the **extension** first observed the trial expire, it latched into a Keychain the
**app cannot see**. `clearTrialEndedLatch()` (called by the debug stepper) removed the App
Group key and the *app's* Keychain key, but the extension kept reading its own private copy
and returned "expired" forever - unclearable by the stepper, by a reinstall, or by anything
short of deleting the extension's keychain items.

**Fix:** `LeapEntitlements.isAppExtension` (`Bundle.main.bundleURL.pathExtension == "appex"`)
now gates the latch's Keychain I/O to the **app process only**. The extension reads and
writes the **App Group mirror exclusively**. Stale extension-Keychain entries left by the
previous build are simply never read again, so devices self-heal on update.

**Rule to remember: `LeapSecureStore` is NOT shared between the app and the widget
extension - only the App Group is.** Any state the extension must read has to live in (or
be mirrored to) `LeapConstants.appGroup`. This is also why `trialStartDate` reads the
Keychain first and falls back to the App-Group mirror: in the extension the Keychain lookup
always misses and the mirror is what actually answers.

**Verified on the simulator by inspecting the App Group plist directly**
(`.../Containers/Shared/AppGroup/<uuid>/Library/Preferences/group.com.sololeap.leap.app.plist`,
read with `plutil -p`): at day 8 it holds `leap.trial.ended.v1 => "1"`; after stepping the
trial back to day 2 both `leap.trial.ended.v1` and the stale `leap.clock.highwater.v1` are
gone and the panel reports "Days remaining: 5". Debug, Internal and Release all build.

## Two more debug-panel/widget desync bugs (same root theme: the App Group is the ONLY bridge)

**Reported on device:** *"in the debug menu if I change the trial to 5 days, locked widgets
on the Home Screen are not updated - still shows as locked. Same for turning on Premium:
the toggle still shows locked widgets but the app is updated to the premium experience."*
Two independent causes, both instances of the same trap.

### A. The Premium toggle was reverted in the mirror on the very next StoreKit refresh

`LeapViewModel.debugIsPremium` wrote the App-Group mirror (`LeapEntitlements.setPro`), but
`debugPlanOverride` only pinned the **app's own** `isPro`. `LeapStoreKitManager.applyPro`
runs at launch, on every foreground (`LeapViewModel.refresh()`) and from the transaction
listener, and unconditionally called `setPro(realStoreKitAnswer)` - overwriting the mirror
with `false` seconds later. So the app stayed on the forced plan while the extension, whose
ONLY input is that mirror, still saw a free user. Exactly the reported asymmetry.

**Fix:** the override now lives in `LeapEntitlements.debugProOverride` (**App Group**, not
`UserDefaults.standard`) and **`setPro` honours it**, so a forced plan pins the mirror too.
`LeapViewModel.debugPlanOverride` just delegates. Still wrapped in
`#if DEBUG || LEAP_INTERNAL`, so public Release has no bypass - verified by a clean Release
build.

### B. The extension cached the trial start in its OWN Keychain, forever

`trialStartDate` **promotes** the App-Group value into the Keychain on first read:

```swift
guard let date = defaultsTrialStartDate() else { return nil }
LeapSecureStore.set(trialStartString(for: date), for: trialStartKey)   // <- in the extension too
mirrorTrialStart(date)
```

In the widget extension that wrote the value into its own (different, unreachable) access
group. Every later call then HIT that stale copy, returned the **first trial start it ever
saw**, and even re-mirrored the stale value back over the App-Group key. Changing the trial
in the app could therefore never reach a placed widget - and the extension could clobber the
app's value.

**Fix:** all Keychain I/O in `LeapEntitlements` now goes through `secureString` /
`secureSet` / `secureRemove`, which **no-op inside the extension** (`isAppExtension`). The
Keychain is an app-only concern - it exists to survive reinstall - and the extension uses
the App Group alone. This also subsumes the earlier per-latch guard.

### The rule these three bugs share

**The App Group is the ONLY thing the app and the widget extension share.** Not the
Keychain, not `UserDefaults.standard`, not in-memory `@Published` state. Any debug or
entitlement state that must change what a PLACED widget renders has to be written to
`LeapConstants.appGroup` *and* not be overwritten by a later refresh. When a widget
"ignores" a change, check the mirror first.

**Verified on the simulator by reading the App Group plist:** toggle Premium ON ->
`leap.debug.pro.override.v1 = true` and `leap.pro.active.v1 = true`, and **both survive a
background/foreground cycle and a relaunch** (previously `pro.active` flipped back to
false); toggle OFF -> both false, also surviving relaunch. Debug, Internal and Release all
build.

**Gotcha while testing:** the App Group **plist on disk lags** - `cfprefsd` buffers writes,
so a read taken while the app is still foregrounded can show a half-updated pair. Background
the app (or relaunch) before trusting `plutil -p`. The extension reads through `UserDefaults`
rather than the file, so it never sees that skew.
