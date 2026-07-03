---
name: notch-companion-app
description: >
  Playbook for building lightweight, native macOS "notch companion" apps — agent
  apps (no Dock/menu-bar icon) that hide under the MacBook notch and react to the
  cursor with fluid, physics-driven animation drawn in code. Covers building
  without Xcode (SwiftPM + hand-assembled .app), a transparent click-through
  overlay over the notch, a 0%-idle-CPU animation loop, spring/Verlet physics +
  gesture systems, global mouse monitors, context menus, code-drawn art & app
  icons, headless testing, and DMG/GitHub distribution. Use when building NotchPaw
  or any variant (e.g. a pull-chain that locks the screen, a notch pet, a notch
  gauge/widget, a peeking character).
license: MIT
metadata:
  author: NotchPaw
  version: "1.0.0"
---

# Notch Companion App Skill

A battle-tested blueprint distilled from building **NotchPaw** (a paw that springs
from the notch to catch your cursor). Use it to build the same class of app or any
variant.

## When to apply

Use this skill when the task is a **native macOS app that:**
- lives under / around the **notch** (or top-center of the menu bar),
- has **no Dock icon and no menu-bar (status) icon** — a pure background agent,
- **reacts to the cursor / user** with smooth animation,
- must be **extremely lightweight** (≈0% CPU when idle),
- and is often a "delight" toy (a pet, a paw, a hanging chain, a gauge, a peeking
  character) rather than a conventional windowed app.

If the user describes a variant ("like NotchPaw but it's a …", "a pull chain that
locks the screen", "a cat that sleeps on the notch"), this skill is the playbook.

## The 8 pillars (each has a reference file)

| # | Pillar | Reference |
|---|--------|-----------|
| 1 | Build without Xcode: SwiftPM → hand-assembled `.app`, signing, scripts | [reference/project-setup.md](reference/project-setup.md) |
| 2 | Agent app + transparent click-through overlay + notch geometry | [reference/overlay-and-notch.md](reference/overlay-and-notch.md) |
| 3 | 0%-idle animation loop + spring/Verlet physics + gesture system | [reference/animation-core.md](reference/animation-core.md) |
| 4 | Mouse monitors, draggable appendages, context menu, cursor | [reference/interaction-and-menu.md](reference/interaction-and-menu.md) |
| 5 | Code-drawn CoreGraphics art, image caching, app icon | [reference/rendering-and-icon.md](reference/rendering-and-icon.md) |
| 6 | Headless testing (no XCTest) + offscreen visual verification + CPU checks | [reference/testing-and-verification.md](reference/testing-and-verification.md) |
| 7 | Distribution: DMG via hdiutil, GitHub release, README, launch posts | [reference/distribution.md](reference/distribution.md) |
| 8 | Hard-won gotchas (read this before debugging anything) | [reference/gotchas.md](reference/gotchas.md) |

**Worked variant:** [examples/pull-chain-lock-screen.md](examples/pull-chain-lock-screen.md)
— a chain hanging from the notch you can grab and pull; releasing past a threshold
locks the screen. Shows how to add a *draggable* appendage and a *system action*.

## Architecture at a glance

Split pure logic from AppKit so the brains are unit-testable headlessly:

```
Package.swift                 # SwiftPM: library + executable + selftest exe
Sources/
  <App>Core/                  # PURE, no AppKit: physics, geometry, styles, drawing
    Geometry.swift            #   notch rect + anchor from NSScreen data (CoreGraphics only)
    Spring.swift              #   damped spring solver (sub-stepped for stability)
    Engine.swift              #   Verlet rope / state machine; deterministic
    Gesture.swift             #   time-driven behavior (animates even if cursor still)
    Style.swift               #   per-variant tuning params + palette
    Renderer.swift            #   CoreGraphics drawing (screen + offscreen)
  <App>/                      # AppKit shell
    main.swift                #   entry; also hidden --render/--contact/--appicon modes
    AppDelegate.swift         #   accessory policy, monitors, menu, persistence
    OverlayWindow.swift       #   transparent borderless click-through NSPanel
    OverlayController.swift   #   maps global cursor → view space; owns window+view
    <App>View.swift           #   NSView: CADisplayLink loop, dirty-rect draw
    MouseTracker.swift        #   global+local NSEvent monitors (no permissions)
  <app>-selftest/             # plain executable assertion harness (CLT has no XCTest)
scripts/
  build_app.sh                # SwiftPM build → assemble .app + Info.plist + codesign + icon
  make_dmg.sh                 # hdiutil → drag-to-install DMG
  publish.sh                  # gh: repo create + push + release + topics (user must auth)
```

## Non-negotiable principles (the soul of this app class)

1. **Never block the user.** The overlay must be fully click-through
   (`ignoresMouseEvents = true`). The paw/chain/pet is decorative; clicks always
   reach apps and menu-bar items underneath. (Claiming a hit-test region was a
   real regression — see gotchas.)
2. **0% CPU when idle.** Drive animation with a `CADisplayLink` that you **pause**
   the instant the creature is at rest, and resume on activity. Cap to ~30fps.
   Invalidate only the creature's dirty rect; cache rigid art as images.
3. **It should feel alive.** Drive motion from a **clock**, not just the cursor, so
   it keeps acting (anticipation → action → follow-through → pause + idle sway)
   even when the cursor is still. Use the `motion-design` skill's principles.
4. **No special permissions.** Use global `NSEvent` monitors for the mouse (these
   need no Accessibility/Screen-Recording grant). Verify visuals via **offscreen
   rendering**, not screenshots (Screen Recording is usually not granted).
5. **No Xcode assumed.** Build with SwiftPM and hand-assemble the bundle; test with
   a plain executable harness (Command Line Tools ship no XCTest).

## How to build a variant (decision flow)

1. **Reskin or new behavior?** Pure reskin (new animal/shape) = edit `Style.swift`
   + `Renderer.swift` only. New behavior (draggable, triggers an action) = also
   touch `Engine.swift` + `Interaction`.
2. **Is the appendage interactive (draggable/clickable)?** If yes, read
   [interaction-and-menu.md](reference/interaction-and-menu.md) → use a global
   drag monitor (keeps click-through) rather than claiming a region.
3. **Does it trigger a system action** (lock, sleep, launch, AppleScript)? See the
   pull-chain example for safe ways to lock/sleep the screen and run actions.
4. **Reuse the harness.** Keep the Core/AppKit split; add self-test checks for any
   new pure logic; add an offscreen `--render`/`--contact` mode to eyeball art.
5. **Verify the invariants every time:** 0% idle CPU, click-through intact, no Dock
   icon (`type="UIElement"`), no crash. Commands in
   [testing-and-verification.md](reference/testing-and-verification.md).

## Reference implementation

The complete, working reference app lives at `~/Code/NotchPaw` (Swift + AppKit,
SwiftPM, no Xcode). When in doubt, read its sources — every pattern in this skill
is implemented there.
