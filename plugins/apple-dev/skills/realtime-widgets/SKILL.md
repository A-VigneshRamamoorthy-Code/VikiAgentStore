---
name: realtime-widgets
description: >
  Apple development skill for Realtime / live widget updates (how-to). Use this skill when working on realtime-widgets tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Realtime / live widget updates (how-to)

> Part of the **[Leap Agent Guide](../../agents.md)**. Event-driven reloads tie into
> the data flow in [architecture.md](architecture.md). For clock / watch faces
> specifically, start with **[clock-faces.md](clock-faces.md)**.

---

A placed widget's SwiftUI body is rendered to a **static archived snapshot**, one per
timeline entry — it does NOT keep running on the Home Screen. There are exactly **three**
ways to make a placed widget change over time; use the cheapest one that fits.

1. **Timeline entries — for minute-or-coarser changes.** In the provider's
   `timeline(for:in:)` pre-render a buffer of `TimelineEntry`s stamped with FUTURE dates
   and return `Timeline(entries:, policy:)`; WidgetKit swaps to each at its date with no
   code running. Leap stamps **180 per-minute entries from ONE snapshot** for every
   face whose **`kind.showsLiveTime`** is true (all `.time` faces **plus** `workSchedule`,
   which draws a live work-hours bar) with `policy: .atEnd`
   (`LeapWidget/LeapCheckInWidget.swift` `timeline(for:in:)`), so clock digits, dates and
   the analog hour/minute hands stay accurate to the minute and keep advancing even if the
   `.atEnd` reload is throttled/batched. The cadence is **capability-flag-driven, not
   category-driven**, so weather/date **combos that also show a clock** (`greetingClock`,
   `sceneClock`) are `.time`-category and therefore ALSO get the per-minute timeline — a
   clock that shows time but sits in another family must never freeze (that is a bug).
   Faces with a **second hand** (`kind.showsSecondHand` — Analog, Segment, Seconds)
   instead spend `leapSecondHandEntries` (**900**) entries at `leapSecondHandStep`
   (**2 s**). That is the *same* 30-minute horizon and the *same* ~48 reloads/day as a
   180-entry 10 s timeline — only the entry **count** differs, and entry count is free as
   long as the archive fits (next bullet).

   ### ✅ A 2 s timeline still gives you a CONTINUOUSLY GLIDING hand

   The host presents a new **entry** roughly every 2 s and you cannot make it present them
   faster (measured below). But entry cadence is **not** the motion cadence: WidgetKit
   **interpolates animatable modifier parameters between consecutive entries** and renders
   that interpolation at full frame rate. Apple, *[Animating data updates in widgets and
   Live Activities](https://developer.apple.com/documentation/widgetkit/animating-data-updates-in-widgets-and-live-activities)*:

   > "Widgets and Live Activities support **all built-in SwiftUI transitions and
   > animations**." … "**Note:** Animations in widgets and Live Activities have a
   > **maximum duration of two seconds**."

   So a `.linear(duration: 2)` on the second hand's `.rotationEffect` bridges the entire
   gap between two entries and the hand **sweeps smoothly** — exactly what commercial
   clock widgets do, and device-confirmed here. This is also why `leapSecondHandStep` must
   stay at **2**: Apple caps animation duration at 2 s, so a wider entry spacing could not
   be bridged and the hand would glide, stall, glide.

   Corroborating evidence that predates the discovery: `LeapSecondAngle.degrees` had to be
   made **monotonic** because a wrapped `second % 60` angle made the hand *visibly sweep
   anti-clockwise* once a minute — only possible if the host is interpolating the rotation.

   #### ⛔️ Wrapping vs. monotonic: BOTH break, in opposite directions

   Because the interpolation is **numeric**, the rendered motion is proportional to the
   *difference* between consecutive entries' values. That makes both obvious designs wrong,
   and the fix is a **wrapped angle plus a one-entry animation gate**:

   | Angle source | Wraps | Symptom once animated |
   |---|---|---|
   | `second % 60 * 6` | every minute | hand sweeps anti-clockwise once a minute |
   | seconds since **local midnight** | daily, + on DST changes | 518400 deg -> 0 deg = **1440 backwards revolutions** at midnight; 60 more at a DST change |
   | seconds since a **fixed anchor** (monotonic) | never | value is proportional to *absolute* time, and the host does **not** present every archived entry: a resume after skipped entries animates `elapsed x 6` deg. **45 min locked = 45 revolutions on unlock** |
   | **`second-of-minute * 6`, wrapped, with `animates(at:step:)` gating the one decreasing step** (shipping) | every minute, but **never while animating** | none; a resume is bounded to a single sub-360 deg flick |

   `LeapSecondAngle.animates(at: date, step:)` is simply `secondOfMinute >= step`,
   i.e. **false on the first entry of each minute** — the only transition where the wrapped
   value drops. `step` is the caller's **real entry spacing** and must not be guessed
   (`leapSecondHandStep` in the widget host, `1` in the in-app `TimelineView` preview —
   read `\.leapIsWidgetHost`). Both mismatches are real bugs, measured:

   | Threshold | Cadence | Result over 30 min |
   |---|---|---|
   | 2 s | 2 s host, either parity | 30 snaps, **0** animated backwards steps ✅ |
   | 1 s | 1 s preview, any sub-second phase | 30 snaps, **0** animated backwards steps ✅ |
   | **2 s** | 1 s preview | **60** snaps — an extra visible stutter every minute |
   | **1 s** | 2 s host on **odd** seconds | **30 animated backwards steps** — the original once-a-minute spin is back |

   The animation *duration* is the opposite: it must stay `leapSecondHandStep`
   unconditionally (see below). Only the wrap **threshold** is cadence-dependent.

   A residual remains and is **not** removable from a view: a resumed entry can land earlier
   in its minute than the last one drawn, giving one backwards flick of up to 354 deg. A
   view cannot see which entry was previously on screen, and a skipped entry is
   indistinguishable from a presented one. Bounding it is the goal, not eliminating it.

   The time zone is deliberately **not** applied: a second hand only expresses seconds
   within a minute and every real zone offset is a whole number of minutes (a whole
   multiple of 360 deg), so an offset cannot move the hand — it can only reintroduce the
   DST discontinuity. Note the first two bugs were **invisible while entry animations were
   suppressed**, because the pre- and post-wrap values are the same picture. Adding the
   glide is what exposed them, so treat any *animated* wrap as a live bug.

   #### ⛔️ A second indicator must HIDE on freeze-buffer entries

   The coarse tail past the dense run (see the freeze buffer below) is **minute-aligned**,
   so a second hand drawn on it reads exactly zero on every entry: it parks at **12** and
   stays there while the minute hand keeps advancing. Buffer entries therefore carry
   `LeapEntry.secondsLive = false` -> `\.leapSecondsLive`, and `LeapLiveSecondHand` /
   `SecondsClockDesign`'s bezel mark apply `.opacity(secondsLive ? 1 : 0)`. Use `.opacity`,
   **not** an `if`, so the view tree keeps the same shape across the dense/buffer seam.

   #### ⚠️ Leap disables animation GLOBALLY — opt back in at the leaf

   `LeapWidget/LeapCheckInWidget.swift` suppresses animation in three places:

   - `.animation(nil, value: entry.date)` on the content `Group`
   - `.animation(nil, value: entry.date)` on the `containerBackground`
   - `.contentTransition(.identity).animation(nil, value: entry.date)` in `LeapWidget.body`

   **Keep them.** They fix a real bug: the default cross-dissolve between entries dipped
   static gradients to ~0.75 alpha and made antialiased tick strokes appear to change size,
   i.e. the whole tile flickered once every entry. (`Transaction` is *not* available to
   widgets, so `.animation(nil, value:)` is the supported disable lever.)

   #### ⛔️ The animation duration MUST equal the entry spacing

   `sweep` returns `.linear(duration: leapSecondHandStep)` and that duration is
   **unconditional on purpose**. An attempt to shorten it outside the widget host —
   `.linear(duration: isWidgetHost ? leapSecondHandStep : 1)`, so the in-app preview would
   match its own 1 s `TimelineView` cadence — silently put **every** second hand back to a
   2 s step on the Home Screen. A 1 s animation across a 2 s entry gap glides for one
   second and then **freezes for the next**, which is indistinguishable from a tick. It
   also fails *closed and silently*: it compiles, it looks right in the app, and it regresses
   all three faces at once. Do not reintroduce a per-context duration. If the in-app preview
   ever needs a different cadence, change the preview's `TimelineView` schedule, not the
   animation.

   The fix is to re-enable animation **only on the thing that moves**, at the leaf, with an
   inner `.animation(_:value:)` — an inner animation overrides the outer `nil`
   (device-confirmed). `LeapLiveSecondHand.sweep` is the reference implementation, and it
   returns `nil` when `isLuminanceReduced` so nothing animates in Always-On, as Apple asks.

   ### ⚠️ STEPPING is not an option — EVERY second indicator must glide

   The obvious objection is the Seconds face, whose lit bezel mark sits on one of 60
   printed ticks: surely it should *step* onto them rather than glide between them? It was
   built that way (`secondHandStepsDiscretely` → its own **1800 x 1 s** timeline plus a
   0.1 s snap animation, so it had a real entry for every position it could occupy),
   installed on device — and it **still stepped once every 2 s**, because the host simply
   does not present entries faster than that. A stepping indicator can therefore never beat
   the presentation rate, and reads as a 2 s stutter. That work was **reverted**: the mark
   now carries the same 2 s `sweep` as the hands and glides continuously around the bezel,
   passing over every printed tick in real time. **Do not reintroduce a per-second
   timeline for it.**

   ### ⛔️ Sub-second motion is still out of reach — do not chase it

   The host will not *present entries* faster than ~0.5 Hz no matter how dense the timeline
   is. Tested directly on a physical iPhone (iOS 26, Low Power Mode **off**), with
   animations globally suppressed:

   | Timeline | Archive | Observed entry cadence |
   |---|---|---|
   | 1800 entries x 1 s (Analog / Segment / Seconds) | 2.27 / 2.60 / 2.22MB — all **rendered**, none stranded | ~2 s |
   | 120 entries x 1 s (deliberately tiny, far under any limit) | ~0.16MB | ~2 s |
   | 900 entries x 2 s | 1.15 / 1.30 / 1.12MB | ~2 s |

   So the presentation cadence is **not** an archive-size, memory or battery throttle you
   can optimise away. Smooth motion comes from **animation**, not from more entries. The
   only public views iOS repaints every second are **`Text(timerInterval:)`** and
   **`ProgressView(timerInterval:)`**, and **neither can rotate a hand** (see below for why
   you cannot stack the latter either). There is **no public API to force a true 1 Hz
   Home-Screen repaint** of arbitrary content.
   *(The in-app Add/Edit preview is a live `TimelineView`, not a baked archive, so it ticks
   per second natively; `sweep` animates there too so in-app and Home Screen match.)*

   #### Two ways OTHER apps get sub-second motion — both rejected here

   Independently researched (two agents + Apple docs) after a report that shipping App Store
   clock widgets sweep faster than 1 Hz. Both are real; neither is worth adopting:

   - **Private `_clockHandRotationEffect(.secondHand, in:anchor:)`** — SwiftUI's own
     internal modifier; the render server rotates the layer off the system clock with zero
     CPU wakeups. Apple pulled it from the SDK headers in Xcode 14, so apps ship it via an
     Xcode-13-built `.xcframework` or a `_typeByName` runtime bridge. **Do not ship it** —
     App Review guideline **2.5.1** (public APIs only), same rule that already bit Leap over
     the `IOPS*` battery symbols.
   - **The timer-text + custom-font glyph trick** (public API, genuinely works). Build an
     OpenType font whose `00`…`59` **`liga`** ligatures *are* the hand artwork, render
     `Text(date, style: .timer)` in it and clip to the seconds glyph — the host's own text
     renderer does the substitution, so no extension code runs and **one** timeline entry
     suffices. Stacking phase-offset timer texts masked by a blinking timer glyph pushes it
     to ~8 FPS (`brycebostwick/WidgetAnimation`, `Kyome22/AnimationLimitBreaker`). Rejected
     for now: it needs 1–16 generated fonts (~165KB each), is an undocumented composition
     Apple could throttle, and the 2 s animation bridge already delivers a *fully*
     continuous glide for far less. Revisit only if the glide is ever removed.
   - **⛔️ HARD LIMIT — the TIMELINE ARCHIVE. Budget ~1.5MB; the DEVICE limit is far
     stricter than the Simulator's.** WidgetKit archives the **entire view tree once per
     entry**, so on a 900-entry timeline everything the face draws is multiplied by 900.
     Over the limit `chronod` logs
     `reload: failed with too large timeline archive <bytes>` → `CHSErrorDomain 1050
     timelineReloadFailed`, retries **an hour later**, and the tile is stranded on its
     `placeholder(in:)` skeleton — which reads as "the widget only shows the loading
     screen", and makes Edit-Widget picks look like no-ops because every pick re-hits the
     dropped path. Measured brackets on this project — note how far apart they are:
     **Simulator: 10.32MB accepted, 11.30MB rejected. Physical iPhone: 2.60MB rendered but
     ~4.0MB did NOT.** A green Simulator run proves nothing here; always confirm on
     hardware and keep the worst face under ~1.5MB. (The extension's ~30MB memory cap is a
     second, independent reason to keep entry counts down.) Four rules keep a dense face
     inside budget (early rows measured at 1800 entries, systemSmall — halve for today's 900):

     | Face content | Archive | Per entry |
     |---|---|---|
     | `Color.clear` (containerBackground only) | 0.10MB | ~55 B |
     | Seconds face: 60 rotated `Capsule` marks + `Text(.currentDate, format:)` | **24.0MB** ❌ | ~13.3KB |
     | … 60 marks merged into ONE `Path` | 18.4MB ❌ | ~10.2KB |
     | … marks as one dashed circle (`LeapTickMarks`) | 11.4MB ❌ | ~6.3KB |
     | … **plus** `Text(verbatim:)` instead of a `FormatStyle` | **2.2MB** | ~1.2KB |
     | **shipping config: 900 x 2 s** — Seconds / Analog / Segment | **1.18 / 2.01 / 2.20MB** ✅ | ~1.3 / 2.3 / 2.5KB |

     Per-entry breakdown of the analog face (systemSmall), which is where the rules below
     come from:

     | Component | B/entry |
     |---|---|
     | WidgetKit floor (`Color.clear` + a solid `containerBackground`) | 373 |
     | `containerBackground` (`LeapWidgetBackground` wallpaper) | 240 |
     | wrappers (`widgetURL`, `.onAppear`, `.animation(nil,value:)`, `Group`) | 96 |
     | `dialDate` (2 `Text` runs) | 769 |
     | tick marks (2x `LeapTickMarks`) | 256 |
     | hour + minute hands (2 capsules) | 256 |
     | second hand | 128 |
     | centre pin | 128 |
     | face ring | 96 |
     | **total** | **2339** |

     1. **Merge repeated moving primitives.** The hour + minute hands are ONE path
        (`LeapClockHands`) rather than two rotated capsules (~128 B/entry each).
     2. **Never draw N repeated shapes on a dense timeline.** Use **`LeapTickMarks`**, which
        strokes **ONE** dashed circle (`LeapDashArc`) whose dash pattern lays down the marks
        — cost is flat in the mark count. Merging into a single `Path` is NOT enough: the
        path's point data is what is expensive.
     3. **Never use `Text(_, format:)` on a dense timeline.** A `Date.FormatStyle` serialises
        its calendar + locale + time zone into **every** entry (~5KB each). With one entry
        per tick `Text(verbatim:)` is already second-accurate and nearly free.
     4. **Then just cut the ENTRY COUNT.** Once (1)-(3) are done, entry count is the only
        reliable lever left.

     **⛔️ Do NOT rasterise the dial with `ImageRenderer`. Tried TWICE, reverted twice —
     do not try a third time.** The prize is real (a shared `Image` node costs a flat
     **228 B/entry** against ~1100–1600 B/entry of drawn dial art, taking the worst face
     from 2.008MB to 1.148MB), which is exactly why this keeps getting re-attempted. It
     does not work:

     - **Attempt 1 (`LeapStaticDial`) — reverted.** `ImageRenderer` renders in a **fresh
       environment that resolves dynamic colours as LIGHT**, and a cache key built from an
       unresolved `Color` cannot distinguish light from dark, so every flattened dial, tick
       ring and numeral **disappeared on a dark Home Screen**.
     - **Attempt 2 (`LeapStaticArt`) — reverted.** This one pre-resolved every `Color` to
       concrete sRGB (`leapResolvedColor(_:dark:)`) and keyed the cache on the **resolved**
       components + `colorScheme`, which genuinely fixed the dark-mode symptom — and it was
       verified correct in both appearances. It still failed in the field: on the Home
       Screen the bitmap came out **blank**, so all three flattened faces (analog dial,
       segment dial, seconds bezel) kept their live hands and **lost their ring, tick marks,
       numerals and date badge**, while the one clock face that did not use it rendered
       perfectly. Colour resolution was not the whole problem.

     Note how expensive this is to diagnose: flattening is only ever on **in the widget
     host**, so neither the Simulator, nor the in-app preview, nor a code review can see
     the failure — only a physical Home Screen can. **Face art must be drawn LIVE.** If a
     face is over budget, cut the entry count instead.

     Things that are **NOT** the cost, all measured — don't chase them: the ~24
     `.environment(\_:_:)` modifiers in `LeapWidgetView.styled(_:)` (identical archive with
     all of them removed), the 66-case `@ViewBuilder` switch in `content(now:)` (identical
     when type-erased to `AnyView`), and pass-through modifier wrappers — collapsing 521
     no-op `ModifiedContent`s (`legible()` / `legibleContent()` / `neonGlow()` / `neonIf()`)
     moved the archive by **16 bytes**. Also measured at ~0: `.resizable()` + `.frame()` on an
     `Image`, and the content drop shadows. `LeapEntry`'s own stored properties are **not**
     archived per entry either (it is not `Codable`) — don't chase them.

   - **⛔️ The second-hand angle WRAPS to `0..<360`, and the wrap step must NOT be animated.**
     `LeapSecondAngle.degrees(of:)` is `secondOfMinute * 6` and takes **no time zone**; the
     face gates its `Animation?` on `LeapSecondAngle.animates(at:step:)`
     (`secondOfMinute >= leapSecondHandStep`), which is false on the first entry of each
     minute. A strictly-increasing angle is *also* a bug — it is proportional to absolute
     time and the host skips entries, so unlocking after 45 min spun the hand 45 times.
     Full table above. It is pure arithmetic on purpose: it runs once per entry, 900 times
     per reload, so it must not build a `Calendar`. The hour/minute hands
     (**`LeapHandAngle`**) stay monotonic — at 6 deg/min they never accumulate a full turn.

   - **⛔️ A dashed tick ring must not put a mark on the path's start angle.** A stroked
     circle is an **open** path: its first and last point coincide at the start angle, so a
     dash that straddles that join is emitted as **two abutting butt-capped half-marks**.
     They overlap on the shared edge, so that one mark renders heavier than its neighbours,
     and because every timeline entry is rasterised independently it visibly **swells and
     shrinks as the clock ticks** (issue6 #1 — the 12 o'clock mark on the Analog, Segment
     and Seconds faces). `LeapDashArc.seamShift` rolls the ring's seam back by half a
     pattern period and `LeapTickMarks.phase(period:)` compensates, so the seam lands in
     the middle of a **gap** while every mark stays on exactly the same angle. Only
     `.all` and `.multiples` were affected; `.nonMultiples` already skips the 12 o'clock
     slot, which is why the defect only ever showed on the long hour marks.

     The **Simulator does not enforce** the older "too many entries" drop, but it **does**
     enforce this one — the reject line above is visible with
     `xcrun simctl spawn <UDID> log show --last 2m --predicate 'process == "chronod"'`, and
     accepted archives can be measured directly on disk:
     `find ~/Library/Developer/CoreSimulator/Devices/<UDID>/data -name '*.chrono-timeline'`
     then `stat -f%z`. Delete them between runs so you never read a stale one. Sub-minute
     reloads are still throttled (~1/min) and the widget still has a per-day reload budget
     (~40–70), so **do not shorten the horizon** to get finer steps.

    - **⛔️ Suppress WidgetKit's implicit entry animation, or STATIC content pulses on
     every tick.** Since iOS 17 WidgetKit gives each timeline-entry change an implicit
     animation and **cross-dissolves the old render tree into the new one**. Mid-
     transition the tile is composited at partial opacity, so content that is provably
     unchanged still changes appearance once per entry: a gradient background dips toward
     ~0.75 alpha over the platter (reads as a **hue flicker**) and antialiased tick
     strokes gain/lose edge coverage (reads as **marks changing size**). On a 2 s
     second-hand timeline that fires 1 800 times an hour. `LeapWidget.body` applies
     `.contentTransition(.identity)` + `.animation(nil, value: entry.date)` to the entry
     view, and `LeapWidgetEntryView` repeats `.animation(nil, value: entry.date)` on
     **both** the foreground `Group` **and** inside `.containerBackground` — they are
     composited as separate layers, so one opt-out does not cover the other.
     **`Transaction` is explicitly not honoured** for widget update animations; use
     `.animation(nil, value:)`. The cost is that the second hand **steps** between
     entries instead of sweeping — that interpolation *was* the bug. Diagnostic tell:
     the artifact is synchronised with the tick, not with app launches or reloads.

2. **Self-animating views — for per-second motion, ZERO timeline cost.** These are the
   only SwiftUI views the system repaints every second on the Home Screen *without any
   new timeline entries* (it drives them itself):
   - `Text(_, style: .timer | .relative | .offset)`, or on **iOS 18+**
     `Text(TimeDataSource.currentDate, format:)` — a live wall-clock / countdown readout.
   - `ProgressView(timerInterval:)` — a determinate bar/ring that fills across an interval.
   Leap uses both:
   - **`LeapDayProgressBar`** — the Day Timer / Live Clock day bars, built on
     `ProgressView(timerInterval:)` (with `countsDown:` to drain instead of fill).
   - `CurrentTimeDesign` / `GreetingClockDesign` — `Text(.currentDate, format:)` HH:MM:SS.
     **Not** the clock faces with second hands: they ship one entry per second, where a
     `Date.FormatStyle` is both redundant and ruinously expensive to archive (§3).
   `LeapDayProgressBar` falls back to an equivalent **drawn** shape when
   `\.leapIsWidgetHost` is false, because outside the host `ProgressView(timerInterval:)`
   degrades to a slider-like control with a stray knob whose lime tint reads gold.
   - **⛔️ Live-view budget: about 8 per widget.** Measured on a placed systemSmall tile:
     6 and 8 live `ProgressView(timerInterval:)`s render; **10, 12 and 60 strand the tile on
     its placeholder forever**. A clean A/B (same build, 0 vs 10) confirmed it is the
     live-view count, not the simulator. Re-measure before raising it. This is why a bezel
     of 60 live marks is not an option, and why second hands use a dense timeline instead.
   - **⛔️ A ROTATING second hand cannot tick *within* one entry.** `Text(TimeDataSource
     .currentDate, format:)` compiles with **any** `DiscreteFormatStyle`, which suggests 60
     statically-rotated bars each gated by its own live `Text`. **It does not work:** the
     host renders a baked archive and can only decode Apple's OWN format styles — a 4-node
     probe on a *placed* widget changed **0 pixels across 8 frames** — and 60 live nodes
     blow the budget above. `.rotationEffect` is baked; `_clockHandRotationEffect` is
     private (guideline 2.5.1). A rotated hand therefore moves once per **entry**, which is
     exactly why the clock faces ship one entry per second (§3).
   - **The known escape hatch (not implemented).** Arbitrary per-second animation — a true
     single moving hand, a blinking `:` — *is* possible with public API via the
     **timer-text + custom-font mask** trick: ship a font whose glyphs are opaque/transparent
     blocks, render `Text(_, style: .timer)` in it, and use that live text as a `.mask()`
     over pre-rendered frames. The host repaints the timer glyphs, so the mask changes.
     Proven by `Kyome22/AnimationLimitBreaker` and `brycebostwick/WidgetAnimation` (8–30 fps,
     iOS 18+). It costs a font file + generated glyphs and has accessibility implications —
     evaluate before committing.
   - **Gotchas:** `TimeDataSource` is **iOS 18+** — gate with `#available(iOS 18.0, *)` and
     fall back to `Text(date, style: .time)` / a drawn shape (deployment target is
     **iOS 17.0**). `ProgressView(timerInterval:).progressViewStyle(.circular)` renders as a
     centered **spinner**, NOT a dial-tracing ring — use `.linear`. A **custom
     `ProgressViewStyle` cannot animate one**: a timer-interval progress view never reports a
     `fractionCompleted`, so only the system `.linear` style moves.
   - **In-app ticking is Edit-sheet only.** The Browse gallery renders **cached snapshot
     images** (`BrowsePreviewCache`) and must stay static — running 60+ live clocks in a
     scrolling grid is a perf hit. Only the Add/Edit sheet preview runs the live
     `TimelineView`.
   - **Locale / time-zone gotcha:** SwiftUI resolves the locale AND time zone of
     `Text(_:format:)` / `Text(_, style:)` from the **environment** and silently OVERRIDES
     anything set on the `Date.FormatStyle` itself (`f.timeZone = …`, `.locale(…)` are
     ignored). Any per-widget 12h/24h or time-zone choice must therefore be applied as
     `.environment(\.locale, …)` / `.environment(\.timeZone, …)` —
     `LeapWidgetView.styled(_:)` does this centrally for every face. `DateFormatter`-built
     verbatim strings (World Clock, Matrix styles) are unaffected.
   - **An unconfigured placement must never return `policy: .never`.** That is a one-way
     door: if the Edit-Widget selection fails to decode on the first request the tile is
     frozen on the how-to card forever, because WidgetKit never calls back on its own.
     `LeapProvider` re-asks after 15 min so the placement self-heals.

3. **Reload on data change — event-driven.** When app data changes, call
   `WidgetCenter.shared.reloadAllTimelines()` (or `reloadTimelines(ofKind:)`) so the
   provider rebuilds with fresh values. Leap calls this so in-app edits reflect on placed
   widgets (see the data flow in [architecture.md](architecture.md)); interactive
   `AppIntent` buttons reload the same way.

**Live Calendar / Weather data.** The `showsWeather` and `showsCalendar` branches of
`timeline(for:in:)` (`LeapWidget/LeapCheckInWidget.swift`) top up a best-effort App Group
cache from **inside the extension** (a no-op without access), then return one entry with
`policy: .after(+30 min)` (weather) / `.after(+15 min)` (calendar) so placed widgets re-poll
periodically. `showsWeather` is **capability-flag-driven** (`= usesTempUnit`): every
`.weather` face **plus** the weather combos `greetingClock` / `sceneClock` / `dateTemp`, so
their conditions stay current (a combo that ALSO shows a live clock gets the per-minute
timeline above instead, and the weather sample is attached to every entry). Real data ALSO
refreshes app-side on scene-active
(`LeapViewModel.refreshLiveDataIfAuthorized()` + `reloadAllTimelines()`). Permissions are
requested only on widget-add, never here — see "Live widget data" in
[architecture.md](architecture.md).

> ### ⛔️ NEVER block `timeline(for:in:)` on an unbounded location / network call
> **This is the #1 "widget goes blank / never loads / could not run" bug — it recurred
> and cost multiple sessions. Do NOT reintroduce it.** WidgetKit gives the provider a
> short budget; if `timeline()` is `await`-suspended past it (or forever), the placed
> widget is stranded on its blank placeholder ("blank loading widget that never shows
> up") and iOS may surface **"The action 'Leap Widget' could not run because an unknown
> error occurred."** The specific trap: **`CLLocationManager.requestLocation()` can
> silently NEVER call its delegate back inside an extension**, suspending the awaiting
> provider indefinitely (its `withCheckedContinuation` is not cancellation-aware, so even
> a task-group timeout can't free it). Weather faces are the usual victims.
> **Rules for any live-data refresh added to the timeline:**
> 1. The extension MUST pass **`allowOneShot: false`** to
>    `LeapWeatherService.refresh(allowOneShot:)` / `LeapLocationProvider.currentCoordinate(allowOneShot:)`
>    so it uses the app-cached coordinate and never runs the one-shot GPS fix.
> 2. Wrap every refresh in **`leapRefreshBounded(_:_:)`** (`Shared/LeapLiveData.swift`) so a
>    slow WeatherKit/EventKit call can't exceed the budget. The operation MUST be
>    cancellation-aware (URLSession-backed WeatherKit is; a bare `withCheckedContinuation`
>    is NOT).
>    **⛔️ Do not "simplify" it back to a `withTaskGroup` race.** That was the original
>    implementation and it enforced **nothing**: `withTaskGroup` implicitly awaits *all* its
>    children before returning, so cancelling the loser does not free the caller if that
>    loser is a blocking synchronous call (`EKEventStore.events(matching:)` ignores
>    cancellation entirely). Measured: a 6 s operation under a 2.5 s "timeout" returned after
>    **6.01 s**. It now runs the work in a **detached** task and resumes a single-resume
>    actor gate from whichever of work/timeout arrives first — same call, **2.65 s**. The
>    gate is proven safe against double-resume, never-resume and lost wakeups; keep those
>    properties if you touch it.
> 3. ALWAYS build the returned timeline from the **cached** `LeapLiveStore` values, whether
>    or not the refresh completed. The refresh only warms the cache for next time.
> Verify on a **physical device** (the Simulator never regenerates a 3rd-party timeline, so
> it hides both the hang and its fix).

**Battery faces (`showsBattery`, `= category == .battery`).** These return one entry with
`policy: .after(+20 min)` so the shown percentage tracks the phone. The charge is read
**live in-process at render time** through `LeapLiveStore.liveBatteryReading()`, which works
in BOTH the app and the extension on a real device (no permission gate), so every reload
shows the current battery.

> **The percentage moves in 5% steps and that is an iOS limitation, not a Leap bug.**
> Since iOS 17 (still true on 18 and 26) UIKit deliberately rounds `UIDevice.batteryLevel`
> to 5% steps, so faces sit on 85 / 80 / 75. Apple engineers call this "expected and
> intended behavior". **Do not try to work around it** - it was investigated end to end and
> both routes are closed:
>
> - **Private `IOPS*` IOKit** returns the exact 1% charge and does work on device in both
>   processes - but `IOPSCopyPowerSourcesInfo` / `IOPSCopyPowerSourcesList` /
>   `IOPSGetPowerSourceDescription` are named *verbatim* in Apple's canned **2.5.1**
>   rejection (the one that blocked Adobe AIR apps for months). `dlsym` keeps them out of the
>   import table but they remain plaintext for a `strings` scan, so it is not shippable.
> - **Public IOKit** (`IOServiceMatching` / `IOServiceGetMatchingService` /
>   `IORegistryEntryCreateCFProperties`, all SDK-declared) is not an escape hatch either: the
>   sandbox *does* resolve `IOPMPowerSource` and `AppleSmartBattery`, but iOS redacts the
>   property dictionary to `{BatteryInstalled, ExternalConnected}` - no capacity keys at all.
>
> So Leap reads the plain public `UIDevice.batteryLevel` on **one code path for every build**.
> No private API, and deliberately no Debug/Internal-vs-Release divergence - a widget must not
> behave differently for the developer than for the user. Full evidence in
> [status-and-history.md](status-and-history.md).

The app is still the primary freshness path: `LeapViewModel` re-reads on every battery
notification, on foreground/background, **and on a 30 s foreground poll** (UIKit's change
notification only fires on its coarse 5% steps), caches to the App Group, and reloads placed
widgets — throttled to once per 5 min for small changes so a slow discharge can't burn
WidgetKit's refresh budget (a charging-state flip or a >= 5-point jump reloads immediately).
Storage faces read real volume capacity via `LeapSystemInfo.storage()`
(`.volumeTotalCapacityKey` / `.volumeAvailableCapacityForImportantUsageKey`) — never
hardcode GB.

**In-app previews are NOT bound by the above.** My Widgets / Browse / Add-sheet previews
run a real `TimelineView(.periodic(from: .now, by: 1))` for `.time`-category designs when
`clockLive`, so faces and the seconds sweep animate smoothly *in the app*
(`LeapWidgetView`) — this path is for on-screen previews only, never the Home Screen.

---

## The reload budget, and why a timeline must out-live its own reload

Three facts decide almost every "my widget stopped updating" bug. All three were verified
against Apple's documentation and on device:

1. **The budget is spent PER PLACED INSTANCE** (roughly 40–70 reloads/day), not per widget
   kind and not per app. Five copies of a clock each get their own allowance — and each can
   be throttled independently.
2. **A requested reload is not a guaranteed reload.** `.atEnd` / `.after(_:)` are *hints*.
   When one is dropped or batched, WidgetKit does **not** run the extension; it keeps
   presenting entries that are already archived. So a provider must archive **past** the
   point at which it asks to be reloaded — that surplus is the **freeze buffer**, and it is
   the only thing standing between a throttled reload and a visibly stuck widget. See
   [clock-faces.md](clock-faces.md) for the clock implementation
   (`leapClockFreezeHorizon`, `leapClockTailFineMinutes`).
3. **Reloads requested while the containing app is in the FOREGROUND are exempt** from the
   budget. The exemption is **state-based, not initiator-based** — it is about the app being
   foreground, not about who called `reloadAllTimelines()`. This is why `LeapApp.swift`
   reloads unconditionally on `scenePhase == .active`: it costs nothing and it is the user's
   only manual way to unstick a frozen tile. **Do not gate, debounce or "optimise" it** —
   that was tried, and it was a pure regression. The exemption does *not* extend to
   `BGAppRefreshTask`.

**Two freeze modes, opposite fixes.** Diagnose before changing anything:

| Symptom | Cause | Fix |
|---|---|---|
| Stale but plausible time; opening the app fixes it | Timeline exhausted / reload throttled | **Lengthen** the horizon |
| Stuck on the placeholder, never renders | Archive rejected (`CHSErrorDomain 1050`) | **Shrink** the archive |

**ALWAYS smoke-test timeline changes on a real device** — the Simulator masks the
dropped-oversized-timeline failure and re-renders placed widgets on its own ~2s clock.
Freeze bugs additionally need a **long idle test** (leave the phone alone for 1–3 h without
opening the app); everything looks perfect for the first half hour.
