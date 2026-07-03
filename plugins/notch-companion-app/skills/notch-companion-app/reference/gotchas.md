# 8. Gotchas — read this before debugging

Hard-won lessons from building NotchPaw. Most cost a debugging cycle; skim them
first whenever something misbehaves.

## Interaction / window
- **The overlay must be `ignoresMouseEvents = true`.** Setting it `false` and
  claiming a region via `hitTest` *blocks clicks* to apps/menu-bar items in that
  region — a regression users hate. Keep it fully click-through; use global
  monitors for menus/drags. (This is the #1 trap.)
- **Right-click menu pops then closes instantly** → you called `popUp` on
  `.rightMouseDown` while the button was down (press-drag-release mode). Fix:
  trigger on `.rightMouseUp` **and** defer `popUp` via `DispatchQueue.main.async`.
- **Global monitors don't consume events** — good (clicks pass through) but means
  you can't "swallow" a click. Design around observing, not capturing.
- **`NSCursor.set()` from a background agent is best-effort** — the foreground app
  may immediately reset it. Don't rely on the cursor hint; never let it block.
- A click-through window **can't use tracking-area `cursorUpdate`** (no events
  reach it). Set the cursor from the global move monitor instead.

## Coordinate systems
- **AppKit = bottom-left origin (+y up); CGEvent/CGWindowList = top-left (+y down).**
  Mixing them silently puts the cursor at the wrong end of the screen. Convert:
  `y_topLeft = screenHeight - y_bottomLeft`.
- `NSEvent.mouseLocation` is global, bottom-left. Window content view is also
  bottom-left; subtract `window.frame.origin` to get view coords.

## Physics / animation
- **Spring explodes on large `dt`** (breakpoint, stutter) → sub-step the integrator
  by `dt` *and* clamp `dt` (`min(dt, 1/30)`) in the engine.
- **Verlet chain won't extend / stays bunched** → the distance constraint must move
  **both** nodes (except the pinned base). Moving only the child can't straighten a
  collapsed rope. Also seed a direction (e.g. `(0,-1)`) when two nodes coincide.
- **Tail/limb looks like a noodle** → `chainDamping` too high; lower it (~0.80) for
  paws, keep high (~0.92) only for whippy tails.
- **Paw "coils" when the cursor is close** → tie segment length to the actual
  cursor distance (short limb when near), not a fixed max reach.
- **Over-stretch slivers on a strike** → cap squash/stretch and keep it
  volume-preserving (`scaleX = √s`, `scaleY = 1/√s`).
- **Limb base shows a floating angled stub at the notch** → anchor the base ABOVE
  the top edge and `clipsToBounds = true`, so the crossing is clipped flush.

## Performance
- **Idle CPU isn't 0** → first suspect: the **cursor is still near the notch** (it's
  *correctly* animating). Check `NSEvent.mouseLocation` distance from the top before
  assuming a leak. To truly disengage, `CGWarpMouseCursorPosition` **and** post a
  `mouseMoved` (warp alone doesn't fire the monitor).
- **Active CPU too high** → cap the display link to 30fps, dirty-rect only, and
  **cache rigid art as a CGImage** (re-pathing a detailed head every frame is the
  usual culprit — cost roughly halved when cached).
- **Whole-window repaint** → never `clear(bounds)`; invalidate only the creature's
  bounding box (`setNeedsDisplay(dirty.union(lastDirty))`).

## Build / environment
- **`xcodebuild` errors / `import XCTest` fails** → CLT-only Mac (no Xcode). Build
  with SwiftPM, hand-assemble the `.app`, and use a plain-executable test harness.
- **No Homebrew, no `gh`** is common → DMG/icon/git work with built-ins
  (`hdiutil`, `iconutil`, `sips`, `git`); GitHub publish must be handed to the user
  (interactive `gh auth login` — the agent can't authenticate as them).
- **Can't screenshot the running app** (Screen Recording not granted) → verify
  visuals with offscreen `--render`/`--contact` PNGs instead.
- **App icon "missing"?** An `LSUIElement` agent has **no Dock icon by design** —
  the icon appears in Finder/Get Info, not the Dock. Set both `LSUIElement=true`
  and `setActivationPolicy(.accessory)`.
- **Two `git init`s / nested repos** — keep the repo at the project root the
  publish script uses; watch out for a stray parent-dir `.git` swallowing siblings.

## Process management (agent etiquette)
- Kill stray instances by **specific PID** (`kill <pid>`), never by name.
- Launch the shipping app with `open App.app` (detached); for log-watching run the
  binary directly so `NSLog` prints to the terminal.
