---
name: in-app-purchases
description: >
  Guide for In-App Purchases (Apple IAP / StoreKit 2) and payment integration. Triggers on keywords like IAP, StoreKit, subscription, paywall, non-consumable, revenue, restore purchases. Includes the Guideline 3.1.2(c) paywall checks that actually get failed: a disclosure defined but never rendered, a legal link that 404s, and declaring Apple's standard EULA while the app shows a custom one.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# In-App Purchases (Apple IAP / StoreKit 2) Playbook

This document is a comprehensive guide for implementing Apple In-App Purchases (IAP) using StoreKit 2 in any iOS/Swift application. It covers architecture, best practices, implementation steps, testing strategies, and App Review requirements.

## 1. TL;DR — The Recommended Approach

- **Use StoreKit 2**: Leverage the modern `Product` / `Transaction` async API rather than the legacy `SKPaymentQueue`. If your deployment target is iOS 17.0+, you can also use SwiftUI store views (`SubscriptionStoreView`, `ProductView`, `StoreView`).
- **Product Model**: Choose between a non-consumable lifetime unlock or auto-renewable subscriptions based on your business needs. 
- **Authoritative Entitlement**: Always rely on `Transaction.currentEntitlements` in the main app to determine access.
- **Cross-Process Sharing**: If you have App Extensions (e.g., Widgets), mirror the entitlement state into an App Group `UserDefaults` so the extension can read it (extensions should NOT call StoreKit directly).
- **Local Testing**: Use a local `.storekit` configuration file to test the full purchase flow in the Simulator without needing App Store Connect or a paid developer account.

## 2. Baseline Requirements & State

A complete payment integration should achieve the following baseline before launch:

| Component | Standard |
|---|---|
| Build | Release + Internal, app + extensions, clean |
| Tests | Comprehensive IAP test suite with SKTestSession and logic tests |
| Device Validation | Installed and launched on a physical iPhone |
| App Store Connect | Products **attached to the app version submission** — `READY_TO_SUBMIT` is **not** enough |
| Sandbox Purchase | Successfully reaches Apple's "Confirm with Side Button" sheet |
| Launch Blockers | Active Paid Applications Agreement, sandbox tester account, uploaded build, hosted legal URLs |

> ⛔️ **`READY_TO_SUBMIT` products are NOT submitted.** On a **first** submission the
> first non-consumable *and* the first subscription must be attached to the app
> version submission, or App Review rejects under **Guideline 2.1(b)** ("one or more
> of the In-App Purchase products have not been submitted for review"). A product
> left in `READY_TO_SUBMIT` and *not* attached re-triggers it, so every product must
> be attached or moved out of that state. Each also needs its own App Review
> screenshot. **The REST API cannot attach them — it is a web-UI-only step.** Full
> procedure and traps: [app-store-submission](../app-store-submission/SKILL.md) §9.

## 3. Product Architecture & Implementation

Keep product IDs in a single Swift enum to maintain a single source of truth.

```swift
enum AppProduct {
    static let lifetime = "com.example.app.pro.lifetime"
    static let yearly   = "com.example.app.pro.yearly"
    static let monthly  = "com.example.app.pro.monthly"
    static let all: Set<String> = [lifetime, yearly, monthly]
}
```

### 3.1 StoreKit Manager (Main App)

Create an `@MainActor` StoreKit manager to load products, handle purchases, and listen for transaction updates.

- Listen to `Transaction.updates` immediately upon app launch to catch external renewals or refunds.
- Verify every transaction: only deliver content on `.verified`.
- Provide a `restorePurchases()` function that calls `AppStore.sync()`.

### 3.2 Cross-Process Entitlement Mirror (For Widgets/Extensions)

Widget extensions cannot reliably call StoreKit. Instead, the main app should evaluate entitlements and write a simple `Bool` to an App Group.

```swift
enum AppEntitlements {
    private static let key = "app.pro.active"
    private static var defaults: UserDefaults {
        UserDefaults(suiteName: "group.com.example.app") ?? .standard
    }
    static var isProCached: Bool { defaults.bool(forKey: key) }
    static func setPro(_ value: Bool) { defaults.set(value, forKey: key) }
}
```

When entitlements change in the main app, update this boolean and call `WidgetCenter.shared.reloadAllTimelines()`.

## 4. Paywall & UI best practices

- Build your paywall using custom SwiftUI or use Apple's `SubscriptionStoreView`.
- **Mandatory App Review requirement**: Include a "Restore Purchases" button on the paywall or in the app's settings.
- **Mandatory for Subscriptions**: Display links to your Terms of Use (EULA) and Privacy Policy. Render both natively in-app, and host HTML versions for the ASC metadata fields. Guideline 3.1.2(c) also wants the subscription's **title, length and price** on the paywall — see [app-store-submission](../app-store-submission/SKILL.md) §3.2 for both halves of that rule.
- **Inaccurate comparison tables**: Never claim features are "Premium-only" if they are not genuinely gated in code. Claiming otherwise is a Guideline 2.3.1 metadata risk. Ensure your paywall comparison matches exactly what the code enforces.
- **Silent restore failures**: Restoring purchases must not fail silently or leak errors into subsequent paywall presentations. Include a loading spinner and an alert that always reports a definitive outcome, including the "nothing to restore" case.
- **Invisible billing retry / grace period**: Subscribers whose renewals fail silently lose access. Observe `Product.SubscriptionInfo.Status` and surface billing issues in the app so users have a path to update payment methods.

## 5. Paywall Pricing Architecture

**Rule: No price, count, or percentage should be written down in the app source.**

Apple's StoreKit has no native "was" price for non-consumables. To display a savings badge (e.g., "23% OFF") on a lifetime tier, create an additional **reference product** in App Store Connect.

**Safety rails for reference products:**
- Exclude the reference product from the entitling set.
- Filter it out before the paywall renders so it cannot be purchased.
- If the reference product cannot be fetched, fall back to a multiplier of the monthly price, or show no discount. A paywall must not claim a saving it cannot mathematically prove.
- Round savings percentages **down** so the badge never overstates the discount.

## 6. Testing Strategy

1. **Local `.storekit` testing**: In Xcode: File ▸ New ▸ StoreKit Configuration File. Replicate ASC products. Edit your app's Scheme ▸ Run ▸ Options ▸ StoreKit Configuration and select the file.
2. **SKTestSession**: Write tests to prove catalog loading, lifetime and monthly purchases, entitlement survival, restore behavior, refund revocations, and expiry.
3. **Logic Tests**: App-Group mirroring, product identifier matching, feature gating under Pro/Trial states.

**Critical Testing Traps:**
- **Scheme-pinned `.storekit` configuration**: If an internal or release scheme pins a StoreKit configuration file on its Run action, it **replaces the real App Store**. Every Sandbox purchase attempt on a real device will be served by a local synthetic store and can never produce a real transaction. Pin local storekit files to development schemes only.
- **SKTestSession fall-through bug**: On some simulator versions, `SKTestSession` probes can fall through to the real App Store. This can cause tests to hang on Sandbox sign-in dialogs.

## 7. App Review Checklist

- [ ] **Restore Purchases**: Must be visible and functional.
- [ ] **EULA & Privacy Policy**: Must be linked on the subscription paywall and accessible within the app.
- [ ] **The disclosure is actually on screen**: a subscription footnote defined as a computed property but never referenced by `body` compiles and ships invisible. Grep for the *call site*, not the definition — this alone fails Guideline 3.1.2(c).
- [ ] **Every legal URL returns 200**: `curl -s -o /dev/null -w '%{http_code}' -L "$URL"`, for the apex *and* `www.` forms. "Functional link" is the exact wording Apple rejects on, and a 404 is invisible from inside App Store Connect.
- [ ] **One agreement, not two**: if the paywall opens your own Terms of Use, the App Store metadata must declare that same custom EULA — not Apple's `stdeula` link. Keep the in-app copy, the hosted page and the metadata identical.
- [ ] **Accurate Pricing**: Never hardcode prices. Always read `Product.displayPrice` so the UI matches the storefront.
- [ ] **Accurate Marketing**: Don't claim features you don't enforce. If showing a comparison table, ensure it reflects actual gated features.
- [ ] **Review Screenshots**: Provide clear screenshots of the paywall for App Store Connect. If the price changes, update the screenshots.
- [ ] **No product left in `READY_TO_SUBMIT` unattached** — including any reference-price product. See [app-store-submission](../app-store-submission/SKILL.md) §9; a product already in `MISSING_METADATA` must be **left alone** until after approval.

## 8. Common Transaction Logic Bugs

When auditing transaction logic, ensure the following critical flaws are addressed:

- **Charged but not entitled**: If the post-purchase validation refresh fails (e.g., network timeout), the user is charged but remains on the free tier. Ensure you process the verified transaction and grant entitlements *before* relying on a full receipt refresh. **This bug costs money and trust.**
- **Restore lying to paying customers**: A restore timeout should not fall through to a "No previous purchases were found" message. Differentiate between timeouts and actual empty purchase histories.
- **Double pay**: Do not send users to Apple's payment sheet if they are already entitled. Check the entitlement state first and block redundant purchases natively.
- **Cross-currency discount math**: Ensure you are comparing identical currencies before computing a discount percentage between two prices. Match the currency code first.
