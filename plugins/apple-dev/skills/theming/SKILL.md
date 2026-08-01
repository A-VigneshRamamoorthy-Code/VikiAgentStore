---
name: theming
description: >
  Apple development skill for Theming (system light/dark). Use this skill when working on theming tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Theming (system light/dark)

> Part of the **[Leap Agent Guide](../../agents.md)**. The user-selectable **accent
> color** system (7 accents, `LeapAccentStore`, the `.id(model.appAccent)`
> propagation gotcha) is documented in
> [status-and-history.md](status-and-history.md) under "Later refinement passes".

---

- `Leap/LeapApp.swift` applies `.preferredColorScheme(model.appearance.colorScheme)`
  (System ⇒ `nil` ⇒ follows the OS) and `.tint(LeapTheme.accentText)`.
- `Shared/LeapTheme.swift` uses `Color(light:dark:)` dynamic providers. App chrome
  tokens resolve per scheme: `primaryText / secondaryText / mutedText / fill /
  hairline / surface / canvas`; `lime` / `ink` are constant; `accentText` is deep
  lime in light, bright lime in dark.
- **Widget content and in-app widget previews stay `.white`** — they float on the
  wallpaper and must not adopt the app's light/dark chrome.
- **Any cached/rendered BITMAP of widget content must key on the accent.**
  `.id(model.appAccent)` re-runs view code but cannot repaint an already-rendered
  bitmap, so `BrowsePreviewCache.Key` (and its `signature`) include
  `LeapAccentStore.shared.current`, and `setAppAccent` re-renders the Edit-Widget picker
  thumbnails. Skipping this is what left Browse previews lime under an amber app —
  see [status-and-history.md](status-and-history.md), "Theme propagation gotcha #2".
- **Foreground ON an accent fill uses `LeapTheme.onAccent`** (not a hardcoded `.white`).
  `LeapAppAccent.onAccentColor = self == .lime ? LeapTheme.ink : .white` — near-black on the
  bright **lime** accent, white on the darker jewel accents (coral/teal/indigo/amber/azure/
  rose). Use it for any icon/label that sits **on** the accent colour: the Home **Upgrade**
  button, the `isPro` **PREMIUM** badge, the locked-widget **PREMIUM** pill, the **Save to
  Home** CTA, and the paywall hero/SAVE-30%/Unlock CTA. This is distinct from **`accentText`**
  (accent-**coloured** text on a neutral surface, `Color(light: deep, dark: bright)`) — the
  Settings unlock row keeps `accentText`, not `onAccent`.
- **The SYSTEM wallpaper swatch label is appearance-adaptive** — its vertical caption uses
  `LeapWallpaperKind.systemInk(for: scheme)` (white in dark, near-black in light) via an
  `@Environment(\.colorScheme)` on `WallpaperStrip`, so "SYSTEM" stays legible against the live
  wallpaper preview in both appearances. The fixed panels (WHITE/FROSTY/BLACK) keep their ink.
