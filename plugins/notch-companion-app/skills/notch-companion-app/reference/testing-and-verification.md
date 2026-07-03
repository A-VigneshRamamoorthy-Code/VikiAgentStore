# 6. Testing & verification (no Xcode, no Screen Recording)

Two problems on a CLT-only Mac: **no XCTest** and **no Screen-Recording grant**.
Solutions: a plain-executable assertion harness for logic, and **offscreen
rendering** for visuals. Plus a few shell checks for the runtime invariants.

## 6a. Logic — a plain executable self-test (XCTest-free)
```swift
// Sources/app-selftest/main.swift
import AppCore
var checks = 0, failures = 0
func check(_ c: Bool, _ m: String) { checks += 1; if !c { failures += 1; print("✗ \(m)") } }

// ... call check(...) on pure-core behaviors ...
check(springConvergesToTarget(),        "spring converges")
check(!engineExplodesOnHugeDt(),        "huge dt can't explode")
check(tipStaysWithinReach(forAllStyles),"limb never exceeds max reach")
check(gestureMovesWithStillCursor(),    "animates when cursor is still")

print("\(checks-failures)/\(checks) passed.")
exit(failures == 0 ? 0 : 1)
```
Run with `swift run app-selftest`. Good things to assert for this app class:
- spring converges & is stable with large `dt`;
- engine never exceeds `maxReach` for **every** style; tip is finite (no NaN);
- starts hidden & `isAtRest`; emerges when engaged; retracts & rests when not;
- **gesture target differs at two close-by times with a fixed cursor** (proves
  "alive when still");
- switching style rebuilds the chain to the right node count without crashing;
- notch geometry: detects the gap between aux areas; falls back when none;
- every renderer icon / app icon renders non-nil with pixels.

## 6b. Visuals — offscreen renders you can actually look at
```bash
swift run App --render  /tmp/poses      # one pose per style
swift run App --contact /tmp/contact    # animation grids (inspect MOTION)
swift run App --icons   /tmp/icons      # menu thumbnails
swift run App --appicon /tmp/icon.png   # app icon
```
Then open the PNGs with the `view` tool and iterate on the art. The contact sheet
is the key trick — it shows the *animation*, catching distortions (over-stretch,
coiling, blobby tails) a single pose hides.

## 6c. Runtime invariants — shell checks
Launch the bundle and verify the four must-holds:
```bash
open build/App.app; sleep 3; PID=$(pgrep -x App | head -1)

# (1) It's an agent: no Dock / menu-bar icon
lsappinfo info -app "$PID" | grep -o 'type="UIElement"'        # → type="UIElement"

# (2) 0% CPU when idle — move cursor FAR from the notch first, then settle:
#     (use CGWarpMouseCursorPosition + a posted mouseMoved so the app disengages)
sleep 6; top -l 4 -s 1 -pid $PID -stats cpu | grep -E '^[0-9.]+ *$'   # → 0.0 …

# (3) Low active CPU while playing (cursor near notch), capped ~30fps → ~4–6%

# (4) Memory sanity
ps -o rss= -p $PID | awk '{printf "%.1f MB\n",$1/1024}'        # ~30–45 MB
```

### Simulating input for tests (no Accessibility needed for synthetic posting)
Drive the cursor / clicks with `CGEvent` (top-left origin, y DOWN — note the flip
from AppKit's bottom-left):
```swift
CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
        mouseCursorPosition: CGPoint(x: midX, y: 8), mouseButton: .left)?.post(tap: .cghidEventTap)
```
- **Right-click test:** post `.rightMouseDown`, wait ~80ms, `.rightMouseUp`.
- **Menu-stays-open check:** after the right-click, count the app's on-screen
  windows over ~2s — an open `NSMenu` adds a second window:
  ```swift
  CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID)
    .filter { $0[kCGWindowOwnerName] == "App" }.count   // 2 = menu open, 1 = closed
  ```
- **Item selection:** open the menu, send Down-arrow ×N + Return (keyCodes 125/36),
  then read the persisted `UserDefaults` value to confirm it changed.
- **Click pass-through (the big one):** create a click-counting helper window at a
  point you've confirmed is *covered* by the overlay (`CGWindowListCopyWindowInfo`
  bounds `.contains` the point), synthesize a click there, and assert the helper
  received it → proves the overlay doesn't block clicks.

## 6d. Gotcha while measuring idle CPU
A "non-zero idle" reading is almost always because the **cursor is still near the
notch** (creature correctly animating). Verify the cursor's real position
(`NSEvent.mouseLocation`, `screen.maxY - y` = distance from top) before trusting an
idle-CPU number. Force it away with `CGWarpMouseCursorPosition` **and** a posted
`mouseMoved` (warp alone doesn't fire the app's monitor, so it won't disengage).

Always clean up temp PNGs/helpers at the end.
