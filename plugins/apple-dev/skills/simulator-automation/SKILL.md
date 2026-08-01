---
name: simulator-automation
description: >
  Apple development skill for Simulator UI automation (hard-won). Use this skill when working on simulator-automation tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Simulator UI automation (hard-won)

> Part of the **[Leap Agent Guide](../../agents.md)**.

---

CGEvent taps via a tiny Swift helper are the reliable way to drive the simulator
(AppleScript `click` hangs; pyobjc-Quartz won't build here).

- **Calibrate from a full-desktop capture, not the device screenshot.**
  `screencapture -x` gives a 2× retina image on this Mac (display logical
  1470×956). **Mac point = screenshot_px / 2** exactly (`CGDisplayBounds`).
- Find the target's glyph centroid in that full capture, divide by 2, tap.
  Device-screenshot→Mac mapping was the source of every missed tap this session.
- `osascript -e 'tell application "Simulator" to activate'` before tapping.
- The tap helper posts `mouseMoved → leftMouseDown → leftMouseUp` at Mac logical
  points to `.cghidEventTap`.
- **Pixel-perfect map for small targets (swatches, menu rows, Remove buttons).**
  When the sim window is *not* full-screen, crop it out of the desktop capture and
  downscale to logical size, then tap `Mac = window_origin + view_px`:
  1. `osascript … get {position, size} of window 1` → e.g. origin `(814,33)` size `422×903`.
  2. `screencapture -x desk.png` (2× retina).
  3. `sips -c $((H*2)) $((W*2)) --cropOffset $((Y*2)) $((X*2)) desk.png --out win.png`
     (sips order is `-c HEIGHT WIDTH`, `--cropOffset TOP LEFT`).
  4. `sips -z H W win.png --out win_map.png` → view-pixel `(vx,vy)` maps to
     `Mac(X+vx, Y+vy)`. Re-crop per screen.
- **Remove a placed widget:** `longpress` it → tap **Remove Widget** → tap
  **Remove** in the confirm alert. Stale widgets from an older extension binary can
  linger as cached snapshots after a reinstall; removing + re-adding forces a fresh
  render with the current code.
- **Config-change / resize "blank" on the sim = per-family fossil snapshot (NOT a
  code bug).** The Edit-Widget config intent (design/style/wallpaper/slot) and every
  design's `.small` layout are correct — proven in-app: the style picker updates the
  preview live, and `styleThumbSize == .small` thumbnails render every design
  (incl. Week Dots) cleanly. The sim caches a widget snapshot **per family**:
  resizing to an *uncached* family (e.g. S→M) renders fresh with the current binary,
  while a *cached* family keeps showing the old fossil (a black pre-rebuild snapshot
  reads as "blank"). Works on device / on a freshly-added widget. Verifying a fresh
  add in-sim is blocked by the iOS-26 synthetic-tap limit on the jiggle
  **Edit → Add Widget** menu button, so verify via in-app previews + on-device.
