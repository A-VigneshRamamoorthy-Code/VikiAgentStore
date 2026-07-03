# 4. Interaction — mouse monitors, draggable appendages, context menu

The overlay is **click-through** (`ignoresMouseEvents = true`), so you never get
`mouseDown`/`mouseMoved` on the view. Instead, **observe** input with global
`NSEvent` monitors, which need **no special permission** and **do not consume**
the event (the app underneath still gets it).

## MouseTracker — global + local monitors
```swift
final class MouseTracker {
    var onMove: ((CGPoint) -> Void)?
    var onContextClick: ((CGPoint) -> Void)?   // right-click
    private var monitors: [Any] = []
    func start() {
        let move: NSEvent.EventTypeMask = [.mouseMoved, .leftMouseDragged, .rightMouseDragged]
        add(global: move) { self.onMove?(NSEvent.mouseLocation) }
        // Local monitor too, for when OUR app happens to be active:
        addLocal(move) { self.onMove?(NSEvent.mouseLocation); return $0 }
        let click: NSEvent.EventTypeMask = [.rightMouseUp]      // ★ see menu gotcha below
        add(global: click) { self.onContextClick?(NSEvent.mouseLocation) }
        addLocal(click) { self.onContextClick?(NSEvent.mouseLocation); return $0 }
    }
    func stop() { monitors.forEach(NSEvent.removeMonitor); monitors.removeAll() }
}
```
- `NSEvent.mouseLocation` is the cursor in **global screen coords (bottom-left)**.
- Global monitors observe events headed to *other* apps; local monitors catch
  events headed to *us*. Add both.
- Feed `onMove` into the controller to update the cursor target + engaged flag and
  `resume()` the display link when in range.

## ★ Context menu without a status item (and without dismissing itself)
Open a normal `NSMenu` at the cursor on right-click in the notch zone. Two
**critical** details or the menu pops and vanishes instantly:

1. **Trigger on `.rightMouseUp`, not `.rightMouseDown`.** If you `popUp` while the
   right button is still physically down, the menu opens in *press-drag-release*
   mode and the following `rightMouseUp` dismisses it immediately.
2. **Defer the `popUp` one runloop turn** so the OS finishes delivering the click
   before the menu's modal tracking loop starts.
```swift
func handleContextClick(_ p: CGPoint) {
    guard controller.isInNotchHotZone(globalPoint: p) else { return }  // notchRect padded
    DispatchQueue.main.async {                       // ★ defer
        NSApp.activate(ignoringOtherApps: true)
        self.buildMenu().popUp(positioning: nil, at: p, in: nil)       // p in screen coords
    }
}
```
The global monitor does **not** consume the right-click, so it never blocks the app
underneath. Right-clicking the notch cutout normally does nothing, so this is safe.

### Polished menu items
```swift
item.attributedTitle = bold(name) + "\n" + grey(tagline)   // two-line styled title
item.image = NSImage(cgImage: Renderer.icon(for: style, size: .init(34,26)), size:_)  // thumbnail
item.state = (style == current) ? .on : .off               // checkmark on current
```
Persist the choice in `UserDefaults` (`set/string(forKey:)`); load it at launch.

## Cursor hint (best-effort)
Because the window is click-through you can't use tracking-area `cursorUpdate`.
Instead, in the global `onMove`, set the cursor when inside the notch zone:
```swift
if controller.isInNotchHotZone(globalPoint: p) { NSCursor.contextualMenu.set() }
```
It's best-effort (the foreground app may reset the cursor) but harmless — it never
blocks anything. Outside the zone, leave the cursor alone.

## Draggable appendages (pull-chain, grab-the-pet) — keep click-through
You can make part of the creature *grabbable* without breaking click-through by
running a small **drag state machine off global monitors**:
```
on .leftMouseDown  (global): if |cursor - beadPos| < grabRadius { dragging = true }
on .leftMouseDragged (global): if dragging { engine.tipTarget = cursor; resume() }
on .leftMouseUp    (global): if dragging { dragging = false; evaluateRelease() }
```
- While `dragging`, feed the cursor straight to the Verlet tip target so the chain
  follows the hand.
- On release, measure pull distance / velocity and fire the action if past a
  threshold (see the pull-chain example), then let the chain spring back.
- This **observes** clicks (doesn't consume), so a stray click near the bead still
  reaches whatever is underneath. Acceptable because the grab radius is tiny and
  sits at the notch where nothing is clickable.
- Alternative (only if you truly must capture the click): claim a *tiny* moving
  hit-test rect for just the bead — but prefer the monitor approach to preserve the
  "never block the user" invariant.

See [gotchas.md](gotchas.md) for the full list of interaction traps.
