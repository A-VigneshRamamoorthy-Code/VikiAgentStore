---
name: clock-faces
description: >
  Apple development skill for Building a clock / watch face. Use this skill when working on clock-faces tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Building a clock / watch face

> Part of the **[Leap Agent Guide](../../agents.md)**. General design rules are in
> [conventions.md](conventions.md); the timeline machinery behind moving widgets is in
> [realtime-widgets.md](realtime-widgets.md); the catalog table is in
> [architecture.md](architecture.md).

**Read this before adding or editing any face in the `.time` category.** Clock faces are
the only designs in Leap that carry a *moving* element on the Home Screen, which puts
them under a set of hard constraints no other design has to satisfy. Every one of the
rules below was paid for with a shipped bug.

---

## The five rules

1. **A face is a style-aware struct, not a `Widget`.** Leap ships **one** configurable
   widget. You never touch `LeapWidgetBundle` or `project.pbxproj`.
2. **Handle all 4 styles** — Editorial / Minimal / Dot-Matrix / Neon. There is no Glass
   style (`.glass` will not compile).
3. **A moving second hand costs ~950 timeline entries.** Everything the face draws is
   archived **~950 times**, so the archive budget is the design constraint.
4. **Motion comes from animation bridging, not from a faster timeline.** The Home Screen
   presents entries at ~0.5Hz and that cannot be changed.
5. **Nothing here can be validated in the Simulator or in-app.** A face is only "working"
   once it has been seen on a physical Home Screen.

---

## Adding a face: every place you must touch

All of these live in **`Shared/LeapWidgetContentView.swift`** unless noted. Missing one
is the usual cause of "my face compiles but never appears".

| # | Where | What |
|---|---|---|
| 1 | `enum LeapWidgetKind` (~L160) | Add the `case`, under the `// Time` grouping. The raw value is persisted, so **never rename an existing case**. |
| 2 | `var title` (~L202) | Gallery / Browse name. |
| 3 | `var blurb` (~L281) | One-line description shown in Browse. |
| 4 | `var category` (~L360) | Return `.time`. |
| 5 | `var supportedSizes` (~L489) | Usually `[.small, .medium]`. |
| 6 | `var signatureStyle` (~L574) | The style the face is previewed in. |
| 7 | `var usesClockFormat` (~L450) | Membership is by exclusion — a face that never prints an hour (a bare dial, a duration countdown, Word Clock's word grid) **must be excluded**, or the 12/24h toggle is offered pointlessly. If the control only applies to *some* families of your face, add a case to `usesClockFormat(size:)` instead (as Analog Clock does: dial-only at `.small`, dial + digital readout at `.medium`). |
| 8 | `var showsSecondHand` (~L415) | **Only if the face draws a moving second indicator.** This one flag switches the face onto the dense timeline — see below. |
| 9 | `content(now:)` dispatcher (~L808) | `case .myClock: MyClockDesign(size: size, date: now)` |
| 10 | The design struct | Time faces live in **`Shared/LeapWidgetTime.swift`**, not in `LeapWidgetContentView.swift`. |
| 11 | [architecture.md](architecture.md) | Add the row to the catalog table. |
| 12 | `LeapWidgetCategory.browseOrder` | Only if you are adding a *category*; `.time` is already curated into Browse. |

### The design struct

```swift
struct MyClockDesign: View {
    @Environment(\.leapInk) private var ink            // content colour, follows appearance
    @Environment(\.leapStyle) private var style        // the 4-style switch
    @Environment(\.leapAccent) private var accent      // user's accent colour
    @Environment(\.leapTimeZone) private var tz        // user-selected zone
    @Environment(\.leapClockFormat) private var clock  // 12/24h
    var size: LeapWidgetSize
    var date: Date                                     // the ENTRY's date - never Date()
}
```

- **Read the time from `date`,** the timeline entry's date. `Date()` returns the moment
  the archive was *built*, so the face would freeze.
- **Zone-aware helpers:** `leapZonedCalendar(tz)`, `leapZoned(date, .dateTime…, in: tz)`,
  `clock.timeString(from:timeZone:seconds:)`.
- **Colours:** `ink` for content, `accent` for the highlight. Hands are conventionally
  `style == .neon ? accent : ink`. No border/tick lines around the tile.
- **Legibility:** `.legible()` on hero elements, `.legibleContent()` on the root, and
  `.neonIf(on: style == .neon, color: accent)` for the Neon style.

---

## Faces with a second hand

Setting `showsSecondHand = true` changes the face's timeline in
`LeapWidget/LeapCheckInWidget.swift` (~L140-182):

| | Ordinary clock face | Second-hand face |
|---|---|---|
| entry spacing | 60 s | `leapSecondHandStep` = **2 s** |
| dense entry count | 180 | `leapSecondHandEntries` = **900** |
| dense run covers | 3 h | 30 min |
| **+ freeze buffer** | — | **~54 coarse entries out to 3 h** |
| total entries | 180 | **~954** |
| reload requested at | `.atEnd` (3 h) | `.after(denseEnd)` (**30 min**) |
| reloads/day | ~48 | ~48 (**identical**) |

The 30-minute reload cadence is deliberate. Shrinking it to 15 minutes doubles reloads to
~96/day, past Apple's 40–70 budget, and the face freezes.

### ⛔️ The freeze buffer — why the run does not stop at the reload

**A requested reload is not a guaranteed reload.** The budget is spent **per placed
instance**, and the system also batches and defers. When a reload does not land, WidgetKit
does *not* re-run the extension — it simply keeps presenting whatever is **already
archived**. A face whose archive ended at the reload point therefore sits at a **stale but
correct-looking time** until something forces a refresh.

That was a real shipped bug: second-hand faces archived exactly 30 minutes, so the clock
was fine for a while and then froze until the user opened the Leap app — opening it issues
a **foreground** reload, which is budget-*exempt*, which is why that was the only thing
that unstuck it. Every other clock already had a 3 h buffer for exactly this reason; the
second-hand branch was the only one that did not.

The fix is purely "archive further ahead". Two constraints shape it, and both matter:

- **The buffer must never be reached in the happy path.** Policy is
  `.after(denseEnd)` — a reload asked for at precisely the moment `.atEnd` used to ask,
  so the reload budget is **unchanged**. This matters because at buffer spacings the
  second hand **cannot glide** (Apple's 2 s animation cap), so it would visibly stall. The
  buffer is insurance, not the normal path.
- **The buffer must stay cheap.** Everything in it is multiplied by the archive cost (see
  below), and an oversized archive is rejected outright — the *opposite* bug. So it is
  **graduated**: per-minute for `leapClockTailFineMinutes` (30) minutes, then every 5
  minutes out to `leapClockFreezeHorizon` (3 h). That is ~54 entries (**+6 %**) instead of
  the 150 (+17 %) a flat per-minute buffer would cost, and it buys a **5.8× longer**
  freeze window (30 min → ~175 min).

Buffer entries are anchored on **`minuteStart`, not `start`**: second-hand faces floor
`start` to the *second*, so anchoring there lands every buffer entry at an arbitrary offset
like `:37` and shows a stale minute.

### How the hand actually moves

A placed widget is a **baked archive** — no extension code runs, so a `.rotationEffect`
is frozen *within* an entry. But WidgetKit **interpolates animatable modifier parameters
between consecutive entries**: *"Widgets and Live Activities support all built-in SwiftUI
transitions and animations"*, with a **maximum duration of two seconds** (Apple,
*Animating data updates in widgets and Live Activities*).

So a linear animation **exactly as long as the entry spacing** bridges the gap and the
hand glides continuously, even though the host only presents an entry every ~2 s. That is
what `LeapLiveSecondHand` does — reuse it rather than rolling your own:

```swift
LeapLiveSecondHand(date: date, length: r * 1.06, width: 1.5, color: accent)
// bezel-mark variant: pass centerOffset to park the bar out on the ring
```

### ⛔️ Three traps that will silently undo it

1. **The tile globally suppresses entry animations.** `LeapCheckInWidget.swift` applies
   `.animation(nil, value: entry.date)` at two sites plus `.contentTransition(.identity)`
   — they fix a real cross-dissolve flicker and **must stay**. A moving element opts back
   in with an **inner, leaf-level** `.animation(_:value:)`, which overrides the outer nil.
2. **The duration must equal the entry spacing, and must not be context-dependent.** An
   earlier version used `isWidgetHost ? leapSecondHandStep : 1` to match the in-app
   preview. A 1 s animation across a 2 s gap glides for one second then **freezes** for
   the next — visually identical to the old 2 s tick. It compiles, looks right in-app, and
   fails only on the Home Screen.
3. **An animated angle must never wrap *while it is being animated*.** Interpolation is
   *numeric*, so a wrap is drawn as a real backwards spin, not folded into the equivalent
   position. There are two valid ways out, and Leap uses a different one per hand:
   - **`LeapHandAngle`** (hour/minute) — **never wraps**: counts from a fixed 2025 anchor
     and is never reset. Safe because these climb only 6°/min and 0.5°/min.
   - **`LeapSecondAngle.degrees(of:)`** (second) — **wraps to `0..<360`**, and pairs with
     **`LeapSecondAngle.animates(at:step:)`**, which returns `false` on the first entry of each
     minute so the one decreasing step is *snapped* (12° at the shipping 2 s spacing)
     rather than swept. Any face driving a second indicator **must** gate its `Animation?`
     on `animates(at:step:)`.

   A monotonic *second* angle is a trap of its own: because it is proportional to absolute
   time, and the host does **not** present every archived entry, a resume after skipped
   entries animates a delta of `elapsed × 6°`. 45 minutes locked → **45 revolutions** on
   unlock. Wrapping bounds any gap to less than one turn. See the table in
   [realtime-widgets.md](realtime-widgets.md).

   The hour/minute hands are **not** animated today, so their wrap was dormant rather than
   visible — that is exactly why it must stay fixed at the source: the trap re-arms itself
   the moment anyone gives those hands a `.animation`, and the in-app `TimelineView`
   previews render the same views outside the widget's `.animation(nil)` guarantee.

4. **A second indicator must hide itself on freeze-buffer entries.** Beyond the dense run,
   `LeapCheckInWidget` archives a coarse tail whose entries are **minute-aligned** and a
   minute or more apart. A second hand drawn there reads exactly zero on *every* entry, so
   it parks at 12 while the minute hand keeps moving — reported as "the second hand stops
   at 12 and never moves". Those entries carry `LeapEntry.secondsLive = false`, threaded to
   `\.leapSecondsLive`; faces apply **`.opacity(secondsLive ? 1 : 0)`** (an `.opacity`, not
   an `if`, so the view tree keeps the same shape across the dense/buffer seam).

### Minute hands on a dial that shows seconds

Use **`LeapHandAngle.minuteDegrees(of:in:)` / `.hourDegrees(of:in:)`**. They snap to
**whole minutes**, so the minute hand advances exactly as the second hand crosses 12. A
continuously sweeping minute hand is horologically correct but reads as a minute *fast*: at
9:51:50 it already sits 83% of the way to 52, so the face says 9:52 while the phone says
9:51. The hour hand is derived from the same whole minute.

They are monotonic (trap 3) and, unlike the `Calendar` + `DateComponents` version they
replaced, allocate **nothing** — which matters when the expression is evaluated once per
entry, 900+ times per reload. Reduced mod 360 they render **identically** to the old
`minute / 60 * 360`; this is a monotonicity + cost change, not a layout change.

Unlike `LeapSecondAngle` these **do** take the time zone: a zone offset is a whole number
of minutes, which moves both hands. A DST transition therefore steps the value (360° of
minute hand, 30° of hour hand for the usual one-hour shift) — a real clock change, twice a
year, and the correct thing to show.

Monotonic is safe **here** and not for the second hand purely because of scale: at 6°/min
and 0.5°/min even a long lock resumes with a fraction of a turn, whereas the second hand's
360°/min turned every skipped minute into a full revolution on unlock.

### ⛔️ No `:SS` digits on a second-hand face

`clock.timeString(…, seconds:)` must be **`false`** on any face that ships the dense
timeline. **Text cannot be interpolated.** Unlike a `.rotationEffect`, a string can only
change when the *entry* changes, and the host will not present entries faster than
`leapSecondHandStep` (2 s) — so a seconds readout visibly counted 13, 15, 17 and looked
like a *stopped* clock sitting right next to a smoothly gliding hand. The moving indicator
is the face's seconds display; the digits are the time. (This is why `SecondsClockDesign`
shows `7:02`, not the reference's `7:02:13`.)

`CurrentTimeDesign` is the exception — it is **not** on the dense timeline and uses the
genuinely self-updating `Text(.currentDate, format:)`, which the system repaints itself.

---

## The archive budget

**This is the constraint that kills clock faces.** WidgetKit archives the whole view tree
**once per entry**, so at ~950 entries everything you draw is multiplied by ~950. Past the
limit `chronod` rejects the reload outright:

```
reload: failed with too large timeline archive <bytes>   ->  CHSErrorDomain 1050
```

…and retries an **hour** later, stranding the tile on its placeholder. That is the
"widget only shows the loading screen" bug.

**The Simulator is far more permissive than a device** (sim: 10.32MB accepted / 11.30MB
rejected; device: 2.60MB rendered, ~4.0MB did not). **Treat ~1.5MB as the ceiling and
always confirm on hardware.** Sizes measured at the 900-entry dense run: Seconds 1.18MB,
Analog 2.01MB, Segment 2.20MB — the freeze buffer adds a further **~6 %** on top.

Three rules keep a face inside it:

1. **Merge repeated moving primitives.** Hour + minute hands are ONE path
   (`LeapClockHands`), not two rotated capsules (~128 B/entry each).
2. **Never draw N repeated shapes.** 60 rotated `Capsule` tick marks cost ~10KB/entry;
   merging them into a single `Path` still cost ~13KB. Use **`LeapTickMarks`**, which
   strokes ONE dashed circle (`LeapDashArc`) — cost is flat in the mark count. The same
   applies to *anything* built from a `ForEach`: the Dot-Matrix analog hands are one
   dash-stroked `LeapDottedRay` per hand, not a stack of `Circle`s.
3. **Never use `Text(_, format:)` / `Text(.currentDate, format:)`.** A `Date.FormatStyle`
   serialises its calendar + locale + time zone into **every** entry (~5KB each). With one
   entry per tick, `Text(verbatim:)` is already second-accurate and nearly free.

Measured at **~0 bytes** — don't waste time on them: pass-through `ModifiedContent`
wrappers, `.resizable()`/`.frame()`, drop shadows, the ~24 `.environment` modifiers in
`styled(_:)`, and the 66-case `content(now:)` switch. `LeapEntry`'s own fields are not
archived per entry either. **Entry count is the only reliable lever** — which is why the
freeze buffer is graduated rather than flat per-minute.

---

## ⛔️ Do not retry these

Each was implemented, measured, and reverted. They look like good ideas; they are not.

| Idea | Why it fails |
|---|---|
| **Rasterising dial art into an `ImageRenderer` bitmap** (`LeapStaticDial`, `LeapStaticArt`) | **Tried twice, reverted twice.** The prize is real (228 B/entry vs ~1100–1600 B), which is why it keeps coming back. Attempt 1 vanished on dark Home Screens (the renderer resolves dynamic colours as *light*, and a cache key built from a `Color` can't tell the appearances apart). Attempt 2 pre-resolved every colour and keyed on the resolved components — verified correct in both appearances — and *still* produced a **blank** bitmap in the field, so all three flattened faces kept their live hands and lost their ring, ticks, numerals and date badge. Only reproducible on a physical Home Screen. **Face art must be drawn live.** |
| **A 1 s timeline** | The host presents entries at ~0.5Hz regardless. Verified with 1800 × 1 s *and* a tiny 120 × 1 s control that was far under any size limit — the hand still moved every 2 s. It only doubles the archive and peak memory. |
| **A discretely *stepping* second hand** | A stepping indicator can never beat the host's presentation rate; it just steps every 2 s. Glide instead. |
| **A custom `DiscreteFormatStyle`** | Compiles, but is never re-evaluated in the host — 0 changed pixels over 8 frames on a placed widget. |
| **Live `ProgressView(timerInterval:)` on a dense timeline** | Dropped by WidgetKit; strands the tile. They also cap out at ~8 stacked instances anywhere. |
| **`policy: .never`** for an unconfigured placement | It can never recover. |
| **Gating or debouncing the foreground `reloadAllTimelines()`** | Looks like an obvious budget saving. It is not: foreground reloads are **already exempt** — the exemption is based on the containing app's *state*, not on who requested the reload. Gating it saves nothing and removes the user's only way to unstick a frozen tile. (The exemption does **not** extend to `BGAppRefreshTask`.) |
| **A flat per-minute freeze buffer** | +150 entries (+17 % archive) to buy exactly what the graduated buffer buys for +6 %. Entry count is the scarce resource. |
| **Extending the dense 2 s run instead of adding a buffer** | Ruinous: 3 h at 2 s is 5400 entries. The buffer exists precisely because dense entries are the expensive kind. |
| **Private `_clockHandRotationEffect`** | How Clockology/Quike do it. **App Review guideline 2.5.1 risk** — not worth it. |

The one *unused but legitimate* alternative, if per-second motion is ever needed **within**
a single entry (e.g. a blinking `:`), is the public timer-text + custom-font ligature
trick (~8 FPS, needs 16 generated fonts). Unnecessary while the hand glides.

---

## Validation checklist

The Simulator masks live transparency **and** oversized-timeline drops, and none of the
Home-Screen-only failures above can be seen in-app. **Every clock face must be checked on
a physical device.**

```bash
# build + install + force a re-archive (installing alone does NOT re-archive:
# a placed widget keeps playing its old 30-minute timeline)
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Debug \
  -destination 'platform=iOS,id=<UDID>' -derivedDataPath /tmp/LeapDeviceBuild \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=D2Z89UU4R7 build
xcrun devicectl device install app --device <UDID> \
  /tmp/LeapDeviceBuild/Build/Products/Debug-iphoneos/Leap.app
xcrun devicectl device process launch --device <UDID> --terminate-existing \
  com.sololeap.leap.app     # LeapApp.swift calls reloadAllTimelines() on foreground
```

Then confirm, on the Home Screen:

- [ ] The tile renders — **not** stuck on its placeholder (that means the archive was
      rejected; cut the entry count).
- [ ] **All of the face is present** — ring, tick marks, numerals, complications — not
      just the moving parts.
- [ ] The second indicator **glides**, with no stall, freeze or backwards jump. Watch it
      cross **12** and cross the top of a **minute**.
- [ ] The minute hand agrees with the phone's clock.
- [ ] Correct in **both** light and dark, and over a light *and* a dark wallpaper.
- [ ] Still ticking after ~30 minutes (the reload landed).
- [ ] **Still telling the right time after ~1–3 hours of the phone sitting idle**, without
      opening the Leap app. This is the freeze-buffer test and it is the *only* way to
      catch a throttled reload — a face that fails it looks perfect for the first half
      hour.
- [ ] All 4 styles and every supported size.

### Telling the two freeze modes apart

They have opposite fixes, so identify which one you have **before** changing anything:

| Symptom | Cause | Fix |
|---|---|---|
| Frozen at a **stale but plausible time**; opening the Leap app unsticks it | Timeline exhausted or the reload was throttled | **Lengthen** the horizon (freeze buffer) |
| Stuck on the **placeholder** / "loading" card; never renders at all | Archive rejected — `CHSErrorDomain 1050` | **Shrink** the archive (cut entries or per-entry cost) |

Opening the app unsticks the first because a reload requested while the containing app is
in the **foreground is exempt from the budget** — the exemption is based on the app's
*state*, not on who asked for the reload. That is why `LeapApp.swift` issues its foreground
`reloadAllTimelines()` **unconditionally**; do not gate or debounce it, it is the user's
only manual escape hatch.

Device logs are not reachable from the host (`log stream --device-name` is gone from
macOS; `devicectl device sysdiagnose` needs on-device consent), so verification is
visual.

---

## Reference: reusable primitives

All in **`Shared/LeapWidgetTime.swift`**.

| Symbol | Use |
|---|---|
| `LeapLiveSecondHand` | The gliding second hand / bezel mark. Handles the sweep, the angle and Always-On. |
| `LeapSecondAngle.degrees(of:)` | Second angle, wrapped to `0..<360`. Always use this for an animated rotation. |
| `LeapSecondAngle.animates(at:step:)` | `false` on the first entry of each minute — gate every second-indicator `Animation?` on it, or the wrap is drawn as a backwards spin. Pass the caller's real entry spacing: `leapSecondHandStep` in the widget host, `1` in an in-app preview. |
| `\.leapSecondsLive` | `false` on freeze-buffer entries; second indicators must `.opacity()` themselves out rather than park at 12. |
| `LeapHandAngle.minuteDegrees/hourDegrees(of:in:)` | Monotonic, whole-minute-snapped, zone-aware hour/minute angles. Allocation-free. |
| `LeapClockHands` | Hour + minute hands as a single `Shape`. |
| `LeapTickMarks` | N tick marks as ONE dashed circle. `.all` / `.multiples(of:)` / `.nonMultiples(of:)`. |
| `LeapDashArc` | The dashed-circle shape behind `LeapTickMarks`. |
| `LeapDottedRay` | A centre→tip ray meant to be dash-stroked into a column of dots (Dot-Matrix hands). One path, flat in the dot count. |
| `leapSecondHandStep` (2) / `leapSecondHandEntries` (900) | Dense-run spacing and count. `step` must stay 2 — a wider gap cannot be bridged by a ≤2 s animation. |
| `leapClockFreezeHorizon` (3 h) | How far ahead a clock archives so a throttled reload cannot freeze it. |
| `leapClockTailFineMinutes` (30) / `leapClockTailEntryCap` (96) | Freeze-buffer resolution and its hard entry-count stop. |
| `leapSecondsPerMinute` | The 60 divisor for any second-hand or bezel angle. |
