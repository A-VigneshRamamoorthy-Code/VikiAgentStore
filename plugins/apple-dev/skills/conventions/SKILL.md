---
name: conventions
description: >
  Guide for iOS Swift coding conventions, SwiftUI style, async/await usage, unowned/weak self, explicit types, trailing closures, and project rules.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# Conventions

> General playbook and conventions for iOS/Swift app development.

---

- **Keep source ASCII** unless a file already uses non-ASCII.
- **Gate platform-specific APIs** (`#if os(iOS)` / `#available`) where relevant to ensure cross-platform compatibility (e.g., macOS, watchOS, tvOS).
- **macOS is not iOS with a mouse.** A Mac target owes the user a real menu bar: a **single-window app must keep a Window-menu item that reopens its closed window** (or save and quit on close), plus the standard ⌘W / ⌘M / ⌘, behaviours. See [macos-app.md](../macos-app/SKILL.md) — this is a hand-checked App Review rejection, not a nicety.
- **Component Architecture:** Design UI components to be modular and reusable. When adding new designs, extend the relevant domain models and create private, style-aware design structs or views. Wire them into the main dispatcher or view builder.
- **Widgets and App Extensions:** Minimize the number of `Widget` structs and extension bundles. Prefer a single configurable widget where possible. Ensure widget content is legible on varied backgrounds.
- **Time and Background Tasks:** Be mindful of strict system rules for widgets and background tasks (e.g., dense timelines, archive budgets, retry limits). Always consult Apple's documentation before implementing time-sensitive features.
- **OS Permissions:** Request OS permissions conditionally and contextually—ideally when the user attempts an action that requires them, rather than upfront at app launch.
- **Data Sharing:** For live-data and shared state between the main app and extensions, cache data to an App Group. Views should prefer real data but fall back gracefully to sample data when unavailable.
- **Info.plist Management:** Manage app configuration keys appropriately. Place main app keys in the Xcode project settings (`INFOPLIST_KEY_*` when using `GENERATE_INFOPLIST_FILE`), and extension keys in their respective `Info.plist` files.
- **Code Comments:** Comment only where it clarifies complex logic; avoid noise and redundant comments.
