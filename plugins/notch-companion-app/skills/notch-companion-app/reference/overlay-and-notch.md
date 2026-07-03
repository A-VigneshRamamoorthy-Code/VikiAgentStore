# 2. Agent app, transparent overlay & notch geometry

## Make it a true background agent (no Dock / no menu-bar icon)
- `Info.plist`: `LSUIElement = true`.
- Runtime: `NSApp.setActivationPolicy(.accessory)` in `applicationDidFinishLaunching`.
- **Do not** create an `NSStatusItem` (that's a menu-bar icon — the whole point is
  to avoid it). Open settings another way (right-click the notch — see
  [interaction-and-menu.md](interaction-and-menu.md)).
- Verify it really is an agent:
  ```bash
  lsappinfo info -app "$(pgrep -x App|head -1)" | grep -o 'type="UIElement"'
  ```

## The overlay window — transparent, floating, CLICK-THROUGH
A borderless non-activating `NSPanel` placed *above the menu bar*:
```swift
final class OverlayWindow: NSPanel {
    init(contentRect: NSRect) {
        super.init(contentRect: contentRect,
                   styleMask: [.borderless, .nonactivatingPanel],
                   backing: .buffered, defer: false)
        isFloatingPanel = true
        level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.mainMenuWindow)) + 2)
        backgroundColor = .clear
        isOpaque = false
        hasShadow = false
        ignoresMouseEvents = true     // ★ CRITICAL: never block clicks underneath
        isMovable = false
        isReleasedWhenClosed = false
        hidesOnDeactivate = false
        collectionBehavior = [.canJoinAllSpaces, .stationary,
                              .fullScreenAuxiliary, .ignoresCycle]
    }
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}
```

### ★ `ignoresMouseEvents = true` is non-negotiable
This tells the window server to pass **all** mouse events through the window. The
creature is purely decorative; the user can always click apps/menu-bar items that
sit in the overlay's rectangle, even mid-animation.

**Anti-pattern that caused a real regression:** setting `ignoresMouseEvents = false`
and overriding `hitTest` to "claim" a notch region. Even a small claimed region
blocks clicks there. Keep the window click-through and open menus / detect drags
via **global monitors** instead (see interaction doc).

## Compute the notch geometry from NSScreen
macOS exposes the notch indirectly. The notch is the gap between the two menu-bar
"auxiliary" areas; `safeAreaInsets.top > 0` signals a notch exists.
```swift
// All in AppKit global coords (origin bottom-left, +y up).
static func compute(screenFrame: CGRect, safeAreaTop: CGFloat,
                    auxLeft: CGRect?, auxRight: CGRect?) -> NotchGeometry {
    let topY = screenFrame.maxY
    if let l = auxLeft, let r = auxRight, r.minX > l.maxX {
        let w = r.minX - l.maxX                                   // gap = notch width
        let h = max(l.height, r.height, safeAreaTop)
        let notch = CGRect(x: l.maxX, y: topY - h, width: w, height: h)
        let shoulder = CGPoint(x: notch.midX, y: notch.minY)     // where the limb emerges
        return .init(notchRect: notch, shoulder: shoulder, hasNotch: true)
    }
    // Fallback for Macs WITHOUT a notch: synthesize a centered region so the app
    // still works (top-center of the menu bar).
    let h = safeAreaTop > 0 ? safeAreaTop : 32, w: CGFloat = 200
    let notch = CGRect(x: screenFrame.midX - w/2, y: topY - h, width: w, height: h)
    return .init(notchRect: notch, shoulder: CGPoint(x: notch.midX, y: notch.minY),
                 hasNotch: safeAreaTop > 0)
}
```
Feed it real values from the notch screen:
```swift
let screen = NSScreen.screens.first { $0.safeAreaInsets.top > 0 } ?? NSScreen.main!
NotchGeometry.compute(screenFrame: screen.frame,
                      safeAreaTop: screen.safeAreaInsets.top,
                      auxLeft: screen.auxiliaryTopLeftArea,
                      auxRight: screen.auxiliaryTopRightArea)
```
Rebuild the overlay on `NSApplication.didChangeScreenParametersNotification`
(display changes, clamshell, external monitors).

## Window frame & "flush to the top edge" trick
- Size the overlay to comfortably contain the creature at full extension
  (`notch.width + ~560` wide, ~340 tall), centered on the notch, hugging the top:
  `y = screen.maxY - height`.
- **Anchor the limb base ABOVE the visible top edge** (e.g. `shoulderY = frameHeight + 16`)
  and set the view's `clipsToBounds = true`. Then wherever the arm crosses the top
  edge it's clipped to a clean horizontal line — it stays flush on both sides at
  any tilt angle (instead of showing a floating, angled stub).

## Map the global cursor into the view
Window content view uses bottom-left origin. Subtract the window frame origin:
```swift
let v = CGPoint(x: global.x - window.frame.minX, y: global.y - window.frame.minY)
```
Judge "engaged" by distance from the **nearest point of the notch span** (not just
a single point), so it wakes whether the cursor approaches from left or right.

See: [interaction-and-menu.md](interaction-and-menu.md) for mouse monitors,
[animation-core.md](animation-core.md) for the render loop.
