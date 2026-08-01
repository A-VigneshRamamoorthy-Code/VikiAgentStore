---
name: theming
description: >
  Guide for SwiftUI theming, dark mode, color schemes, dynamic colors, asset catalogs, typography, branding, and style-aware widget designs.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Theming (system light/dark)

> Part of the **[iOS Agent Guide](../ios-agent-guide/SKILL.md)**. The user-selectable **accent
> color** system (multiple accents, theming state, and view update propagation gotchas)
> is a key architectural consideration for the app's visual identity.

---

- **App-Wide Scheme Preference**: The main App entry point should apply `.preferredColorScheme()`
  (where a System setting maps to `nil` to follow the OS) and `.tint(Theme.accentColor)`.
- **Dynamic Colors**: The central theme structure should use `Color(light:dark:)` dynamic providers.
  App chrome tokens resolve per scheme: e.g., `primaryText / secondaryText / mutedText / fill /
  hairline / surface / canvas`. Brand-specific colors should adapt appropriately (e.g., deep variant
  in light mode, bright variant in dark mode).
- **Widget Background Independence**: Widget content and in-app widget previews typically remain a
  fixed color (e.g., white or clear) if they float on a custom wallpaper, meaning they must not automatically
  adopt the app's light/dark chrome unless specifically designed to.
- **Cache Invalidation for Themed Bitmaps**: Any cached/rendered bitmap of dynamic content must key on
  the current accent color or theme setting. While `.id(model.accent)` re-runs view code, it cannot
  repaint an already-rendered bitmap from a cache. Ensure your cache keys (and their signatures) include
  the active theme state to re-render thumbnails or previews correctly when the theme changes.
- **Foreground Accessibility on Accent Fills**: Foreground elements sitting ON an accent fill should use
  a calculated `onAccent` color rather than a hardcoded `.white` or `.black`. For example, bright accent
  fills might require near-black text for contrast, while darker jewel accents require white text. Use
  this dynamic foreground color for any icon/label on primary CTAs, premium badges, or paywall buttons.
  This is distinct from `accentText` (accent-colored text on a neutral surface).
- **Adaptive Swatches and Live Previews**: Labels and overlays on dynamic backgrounds (like live system
  wallpapers or camera previews) must be appearance-adaptive. Pass the current `@Environment(\.colorScheme)`
  to calculate text colors (e.g., white in dark mode, near-black in light mode) so overlays remain legible
  in both appearances, while fixed-color panels keep their respective static contrasting colors.
