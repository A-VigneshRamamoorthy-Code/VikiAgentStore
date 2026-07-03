# Variant example: a notch pull-chain that locks the screen

A chain hangs from the notch like a table-lamp pull. Grab the bead, pull down, and
on release past a threshold it **snaps back and locks the screen**. This shows how
to add (a) a **draggable** appendage and (b) a **system action** — reusing
everything in the core skill.

## What changes vs. NotchPaw (small diff)
| Area | Change |
|------|--------|
| `Style` | One style: a long Verlet rope (8–12 segments) under **downward gravity**, a round **bead** at the tip. |
| Engine | Add a **grab/drag/release** mode; track pull distance; add a release **recoil**. |
| Idle | Hang **still** at rest (no ambient sway) so the display link pauses → 0% CPU. |
| Interaction | Global `.leftMouseDown/Dragged/Up` drag state machine (keeps click-through). |
| Action | `lockScreen()` on release past threshold. |
| Renderer | Draw a tapered chain + bead (reuse the ribbon/`headImage` cache). |

Everything else (overlay, notch geometry, CADisplayLink loop, build scripts, tests,
DMG) is **unchanged**.

## 1. The hanging rope (Style + engine)
- Build the Verlet rope exactly as in [animation-core.md](../reference/animation-core.md),
  but the **rest target is straight down under gravity** (no cursor-chasing gesture).
  At rest the rope hangs vertically and is motionless → `isAtRest` true → link
  paused → **0% CPU**.
- The **bead** is the tip node; cache it as a `CGImage` (`headImage`) and blit.
- Optional "notice" flourish: when the cursor enters the notch zone, `resume()` for
  a brief sway, then let it settle and sleep again.

## 2. Grab → drag → release (global monitors, stays click-through)
Add a left-button drag state machine fed by `MouseTracker` (observes, never
consumes — so a stray click near the bead still passes through):
```swift
// AppDelegate / a small DragController
private var dragging = false
private var maxPull: CGFloat = 0
private let grabRadius: CGFloat = 28
private let pullThreshold: CGFloat = 130   // how far down before it triggers

func onLeftDown(_ p: CGPoint) {
    let bead = controller.beadGlobalPosition()
    if hypot(p.x - bead.x, p.y - bead.y) < grabRadius {
        dragging = true; maxPull = 0
        controller.pawView.resume()
    }
}
func onLeftDrag(_ p: CGPoint) {
    guard dragging else { return }
    controller.setChainTipTarget(global: p)        // tip follows the hand (clamped to maxReach)
    maxPull = max(maxPull, controller.pullDistance())  // vertical distance pulled from rest
}
func onLeftUp(_ p: CGPoint) {
    guard dragging else { return }
    dragging = false
    controller.releaseChain(recoil: maxPull)        // springs back with an upward kick
    if maxPull >= pullThreshold { triggerAction() } // ★ fire!
}
```
Add the matching monitors in `MouseTracker` (`.leftMouseDown`, `.leftMouseDragged`,
`.leftMouseUp`), global + local, mirroring the right-click ones.

Engine support:
- While dragging: set the rope's tip target to the cursor (clamped to `maxReach` so
  it can't be pulled infinitely), run the normal Verlet integrate + constraints.
- On release: clear the target and **impart an upward velocity** to the tip
  (`prev[tip] = tip + (0, +kick)`) so it snaps back and overshoots — a satisfying
  "click". Let gravity settle it; when at rest the link pauses again.

## 3. The action — lock the screen
Pick one. The app is un-sandboxed (ad-hoc), so launching a tool / posting a
keystroke both work.

**A. Explicit lock via the system shortcut (recommended — actually locks):**
```swift
import CoreGraphics
func lockScreen() {
    let src = CGEventSource(stateID: .hidSystemState)
    let q: CGKeyCode = 12                                   // 'q'
    for down in [true, false] {
        let e = CGEvent(keyboardEventSource: src, virtualKey: q, keyDown: down)
        e?.flags = [.maskCommand, .maskControl]             // ⌃⌘Q = Lock Screen
        e?.post(tap: .cghidEventTap)
    }
}
```
Note: synthesizing a system keystroke may prompt for **Accessibility** permission
the first time on some setups; if you want zero-permission, use option B.

**B. Sleep the display (zero permission; locks if "require password after
sleep/screen saver" is enabled in System Settings → Lock Screen):**
```swift
func sleepDisplay() {
    let p = Process(); p.executableURL = URL(fileURLWithPath: "/usr/bin/pmset")
    p.arguments = ["displaysleepnow"]; try? p.run()
}
```

**C. Start the screen saver (locks if password-on-screensaver is set):**
`open -a ScreenSaverEngine` via `Process`.

Recommendation: default to **A** for a true "lock"; document the dependency for B/C.
Trigger the action *after* starting the recoil so the snap is visible before the
screen locks (e.g. `DispatchQueue.main.asyncAfter(deadline: .now()+0.15)`).

## 4. Other fun actions (same hook, swap the function)
- Toggle Do-Not-Disturb / Focus, mute audio, start/stop a timer, run an
  AppleScript (`osascript`), put the Mac to sleep (`pmset sleepnow`), trigger a
  Shortcut (`shortcuts run "Name"`), take a screenshot, etc.
- The pattern is always: **interactive appendage → threshold/gesture → 1 function.**

## 5. Verify (reuse the harness)
- Self-test the pure bits: pulling past `pullThreshold` sets the "fire" flag exactly
  once; below it doesn't; the rope returns to rest after release; tip never exceeds
  `maxReach`.
- `--contact` render the pull + recoil to eyeball the motion.
- Live: confirm 0% idle CPU while the chain hangs still; clicks still pass through;
  grabbing+pulling past the threshold runs the action; `type="UIElement"`.
- For the lock action, test the trigger path with a **harmless stand-in** first
  (e.g. `NSLog("LOCK")`) so you don't lock yourself out mid-test; swap in the real
  `lockScreen()` once the gesture is solid.

See the core references for any mechanism reused here:
[overlay-and-notch.md](../reference/overlay-and-notch.md),
[animation-core.md](../reference/animation-core.md),
[interaction-and-menu.md](../reference/interaction-and-menu.md),
[gotchas.md](../reference/gotchas.md).
