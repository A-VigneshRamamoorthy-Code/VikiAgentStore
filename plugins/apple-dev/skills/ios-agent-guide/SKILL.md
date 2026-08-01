---
name: ios-agent-guide
description: >
  Master index for iOS development rules, invariants, App Groups, WidgetKit limits, App Store constraints, and agent troubleshooting playbook.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---

# iOS / Swift App Development — Agent Guide

Authoritative technical playbook and guide for agents working on modern iOS applications, particularly those leveraging SwiftUI, WidgetKit, StoreKit, and external services like WeatherKit or Firebase.

> **This file is a lean index.** It provides the core invariants, constraints, and architecture patterns necessary for maintaining and scaling iOS applications. Keep this index up to date when architecture, build commands, or conventions change.

---

## Architecture & Core Patterns

- **SwiftUI & WidgetKit**: Use SwiftUI as the primary UI framework. For widget-heavy applications, utilize a **WidgetKit extension**. If providing multiple widget designs, avoid creating a separate `Widget` struct per design. Instead, register a single configurable widget (e.g., using `AppIntentConfiguration`) and use a dispatcher to render different styles based on user selection.
- **Widget Transparency**: There is **no** public iOS API for a truly transparent widget. Achieving a "see-through" effect requires baking the user's chosen wallpaper into the widget's `containerBackground`. Avoid private APIs as they lead to App Store rejection (Guideline 2.5.1). Use phrasing like "widgets that blend in" rather than "transparent" in user-visible copy.
- **Target Management**: When managing an Xcode project with shared logic across app and extensions, ensure shared source files are explicitly registered in **both** target membership lists.

## Invariants & Critical iOS Constraints

Know these constraints before editing or implementing features to avoid silent failures and App Store rejections:

### 1. Data Sharing & App Groups
- **App Groups are the Only Safe Shared State**: The App Group is the ONLY entity the main app and the extension share. They do not share `UserDefaults.standard` or in-memory state.
- **Keychain Access**: Keychain access groups are target-specific by default. Extensions will fail to read the app's Keychain items unless a shared access group is explicitly configured.

### 2. StoreKit 2 & Monetization
- **Extensions Cannot Call StoreKit**: Extensions must evaluate entitlements using an App-Group mirror. The main app must resolve StoreKit state and write the subscription/trial status to the App Group for the widget to read.
- **Bounded Awaits**: StoreKit calls like `AppStore.sync()` or `Transaction.currentEntitlements` have **no internal deadline** and can hang for minutes if the store is unreachable. Always wrap them in a one-shot timeout mechanism (e.g., `withCheckedThrowingContinuation` + `NSLock`). Do not use `withThrowingTaskGroup` as it awaits all children.
- **StoreKit Testing Bugs**: Local `.storekit` configs may fail to sync to `storekitd` on simulators, causing test sessions to return zero products. Use headless testing or physical devices to verify entitlement chains.

### 3. WeatherKit & Live Data
- **App Services Requirement**: Enabling the WeatherKit capability in Xcode is **not enough**. You MUST also enable it under the **App Services** tab in the Apple Developer Portal. Until authorized server-side, WeatherKit will return authentication errors (`Code=2`), even with the correct capabilities present.
- **Attribution is Mandatory**: Apple requires the Apple Weather mark and a legal link wherever WeatherKit data is shown. Ensure the mark is not clipped by widget corner radii.
- **Widget Network Calls**: Never block `timeline(for:in:)` on an unbounded location or network call. Pass `allowOneShot: false` for CoreLocation (one-shots can hang forever in extensions) and rely on bounded refresh mechanisms.

### 4. Hardware Limitations
- **Battery API Limits**: UIKit deliberately rounds `UIDevice.batteryLevel` to **5% steps**. Attempting to read 1% granular charge via private `IOKit` APIs will result in immediate App Store rejection. 

### 5. Widget Timelines & Animations
- **Dense Timelines for Continuous Motion**: To animate elements like a clock's second hand, rely on WidgetKit's interpolation. A timeline with entries 2 seconds apart allows a 2-second `.linear` animation to bridge the gap perfectly, causing the hand to glide.
- **Archive Limits**: WidgetKit archives the whole view tree per entry. Over ~1.5MB to 2.0MB, the system rejects the timeline, stranding the widget on a loading placeholder. 
- **Rules for Dense Timelines**: 
  1. **Merge Primitives**: Combine repeated paths. Do not draw 60 rotated `Capsule` shapes for clock ticks; stroke a single dashed circle instead.
  2. **No `Text(format:)`**: Using `Text(.currentDate, format:)` serializes calendar/locale/timezone data into *every* entry (~5KB each). Use verbatim text interpolation.
  3. **Freeze Buffers**: Throttled widgets don't re-run the extension, they stop at the last entry. Append a graduated buffer of entries to prevent freezing if a reload is missed.
- **Do NOT use `ImageRenderer` in Widgets**: Flattening complex art to bitmaps drops memory usage but fails silently on the Home Screen due to a fresh environment context, stripping the content entirely. Render shapes natively.

### 6. Telemetry & Analytics
- **Avoid Double Counting**: Add analytics SDKs (e.g., Firebase/GA4) to the **main app target only**. Never link them to the widget extension. The extension should bump App-Group counters, which the main app drains to the analytics provider upon foregrounding.

### 7. Feedback & Support Systems
- **SDK-Free REST APIs**: If building a custom feedback system via Firebase Firestore, use a REST endpoint over `URLSession` instead of importing the bulky Firestore SDK. Use create-only security rules to avoid needing Firebase Auth.

---

## Development Guide Map

| Topic | Description |
|-------|-------------|
| **Architecture & Data Flow** | Target layout, dependency injection, and how in-app state changes reach placed widgets. |
| **Build & Run** | Simulator vs. device build commands, signing, and live-data permission handling. |
| **Widget Rendering** | Managing timelines, background composites, color-scheme handling, and white-label widget designs. |
| **Realtime Updates** | Building self-animating views, managing interpolation, and keeping within timeline archive limits. |
| **Monetization (IAP)** | StoreKit 2 integration, entitlement gating, paywalls, and cross-target entitlement mirroring. |
| **Telemetry & Feedback** | Setting up lightweight, SDK-free telemetry and user feedback flows. |
| **App Store Release** | Validation checklists, screenshot generation, metadata formatting, and submission rules. |
