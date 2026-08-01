---
name: clock-faces
description: >
  Guide for SwiftUI continuous animation, clock widgets, dense timelines, TimelineProvider, rotating hands, CADisplayLink, and rendering ticks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Building a Clock or Watch Face Widget in iOS

**Read this before building any timeline-driven clock widget.** Clock faces often require a *moving* element (like a second hand) on the iOS Home Screen, which puts them under a set of hard constraints unlike static or occasionally-updating widgets. The rules below are designed to prevent performance crashes, frozen widgets, and battery drain.

---

## The Core Rules

1. **A moving second hand is extremely expensive.** Everything the face draws is archived multiple times per timeline generation. A dense timeline of 30 minutes at 2-second intervals means archiving the view ~900 times.
2. **Motion comes from animation bridging, not from a faster timeline.** The iOS Home Screen presents timeline entries at a capped rate (often ~0.5Hz). You cannot force it to refresh every 16ms.
3. **Nothing here can be fully validated in the Simulator.** A face is only proven to "work" once it survives on a physical device's Home Screen for hours. The Simulator is far more permissive with archive size limits than a real device.

---

## Building the Timeline

A standard widget might refresh every 15-60 minutes. A clock face with a second hand requires a completely different approach.

### Dense Timeline Strategy
- **Entry spacing:** ~2 seconds.
- **Dense entry count:** ~900 entries.
- **Dense run covers:** ~30 minutes.
- **Reload requested:** Just before the dense timeline ends.

The ~30-minute reload cadence is the sweet spot. Shrinking it to 15 minutes doubles the reloads per day, pushing past Apple's typical daily budget (40-70 reloads), causing the face to freeze.

### The Freeze Buffer

**A requested reload is not a guaranteed reload.** The background budget is spent per placed instance, and the system frequently batches or defers widget reloads. If a reload fails to fire, WidgetKit keeps presenting the *last available archived entry*. If your timeline simply ends at 30 minutes, the clock will freeze at a **stale but correct-looking time** until the user forces a foreground reload (e.g., by opening the main app).

**The Fix: Archive further ahead (The Freeze Buffer)**
- After the 30-minute dense run, append coarse, minute-aligned entries out to ~3 hours.
- These buffer entries act as insurance. The second hand cannot glide smoothly at this spacing, so you must dynamically hide the second indicator on these entries.
- The buffer must stay cheap. A graduated approach (e.g., per-minute for 30 mins, then every 5 mins out to 3 hours) adds only ~50 entries, increasing the archive size minimally while buying hours of freeze protection.

---

## Animation & Motion

A placed widget is a **baked archive**. No extension code runs dynamically, so modifiers like `.rotationEffect` are frozen *within* an entry. However, WidgetKit **interpolates animatable modifier parameters between consecutive entries** (with a maximum duration of two seconds). 

A linear animation **exactly as long as the entry spacing** bridges the gap, allowing a hand to glide continuously.

### Common Animation Traps

1. **Duration Must Match Spacing:** The animation duration must exactly match the entry interval (e.g., 2 seconds). A 1-second animation across a 2-second gap will glide for one second, then freeze for the next.
2. **Angle Wrapping:** An animated angle must never wrap *while it is being animated*. Interpolation is numeric, so an angle dropping from 359° to 0° will be drawn as a rapid backward spin. Your angle logic must handle continuous accumulation or ensure the jump occurs without animation.
3. **Monotonic Accumulation Danger:** If you use a continuously accumulating second angle (e.g., extending to thousands of degrees over time), a widget that wakes up after being skipped for 45 minutes will attempt to animate a delta of 45 revolutions. Ensure your wrap logic mitigates this.
4. **No `:SS` Text Digits:** You cannot interpolate `Text`. A string changes only when the entry changes (e.g., every 2s). A seconds readout will skip numbers (e.g., 13, 15, 17) and look broken next to a smoothly gliding hand. Use `Text(.currentDate, format:)` if you need system-managed dynamic time without custom timeline overhead, though it cannot be perfectly synced with custom 2-second shapes.
5. **Minute Hand Snapping:** Consider snapping minute hands to whole minutes rather than sweeping continuously. A sweeping minute hand at 9:51:50 is 83% of the way to 52, making it visually read as 9:52 prematurely.

---

## The Archive Budget Constraints

**This is the constraint that kills clock faces.** WidgetKit archives the view tree **once per entry**. If your view tree is heavy, multiplying it by 900+ entries will exceed the limit. The system daemon (`chronod`) will reject it with an error (e.g., `CHSErrorDomain 1050`), stranding the widget on its placeholder.

- **Limit:** Treat ~1.5MB as the ceiling for the generated archive.
- **Simulator vs Device:** The Simulator might accept a 10MB archive, but a physical device will silently reject anything over ~2-4MB depending on conditions.

### Optimization Rules

1. **Merge Repeated Shapes:** Never draw N repeated shapes in a `ForEach`. For example, 60 rotated `Capsule` tick marks cost massive amounts of bytes per entry. Instead, merge them into a single `Path` or use a dashed `Circle` stroke.
2. **Avoid Heavy Formatters:** Never use complex `Date.FormatStyle` in dense entries. They serialize calendar, locale, and timezone metadata into *every* entry (~5KB each).
3. **Never Rasterize Live Art:** Rasterizing dial art into an `ImageRenderer` bitmap often fails on Home Screens or gets corrupted in dark/light mode transitions. Vector paths are required.

---

## Validation Checklist

Because the Simulator masks performance limits, transparency issues, and background throttling, **every clock face must be checked on a physical device**.

- [ ] The widget renders and does not stick on its placeholder (if it does, the archive size was rejected).
- [ ] All elements of the face are present.
- [ ] The second hand glides without stalling or jumping backward.
- [ ] The face behaves correctly across light, dark, and tinted Home Screen appearances.
- [ ] **The freeze buffer test:** The widget is still telling the correct time after the phone sits idle for ~1-3 hours without opening the host app. This proves your fallback buffer is working when dense reloads are throttled.
