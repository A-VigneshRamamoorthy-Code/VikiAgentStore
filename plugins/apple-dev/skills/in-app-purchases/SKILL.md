---
name: in-app-purchases
description: >
  Apple development skill for In-App Purchases (Apple IAP / StoreKit 2). Use this skill when working on in-app-purchases tasks.
license: MIT
metadata:
  author: Apple Dev Plugin
  version: "1.0.0"
---
# In-App Purchases (Apple IAP / StoreKit 2)

> Part of the **[Leap Agent Guide](../../agents.md)**. Design spec + file map for Apple
> in-app payments in Leap. **STATUS: IMPLEMENTED & shipped as "Leap Premium"** — the
> StoreKit 2 purchase experience, 7-day trial, and studio gating are live (see the
> **As-built** box in §0 and [status-and-history.md](status-and-history.md) for the
> changelog). The sections below remain the design rationale + anchors. See also:
> [architecture.md](architecture.md), [build-and-run.md](build-and-run.md),
> [conventions.md](conventions.md).

> **Looking for what state payments are actually in — what was fixed, which App Store
> Connect records exist, and what still blocks a sale?** That is the as-built record in
> **[payment-integration.md](payment-integration.md)**. This file is the *spec*: how the
> code is structured and where to change it.

This document tells the *next* agent exactly **what to build, where, and in what order**
to monetize Leap with Apple in-app purchases. It contains code *sketches* (illustrative,
not committed) plus the precise file/edit anchors in this codebase.

---

## 0. As-built (what actually shipped)

> This doc began as a greenfield spec; the feature is now **implemented**. Where the
> defaults in §3/§5 differ from this box, **the shipped values here win.**

- **Branding:** user-facing **"Leap Premium"**; internal API stays **`isPro` / `Pro`**
  (`LeapProduct`, IDs `com.sololeap.leap.app.pro.{monthly,lifetime}`, App-Group mirror
  `leap.pro.active.v1`) — **do not rename** (keeps `.storekit` product matching intact).
- **Products:** `…pro.monthly` **$0.99/mo** + `…pro.lifetime` **$9.99**, plus a **third,
  never-sold** product `…pro.lifetime.list` (**~$12.99**) that exists only to source the
  struck-through reference price — see §12.4b. **No price is hard-coded any more**
  (`LeapProduct.Fallback` was deleted): both the charged and the struck-through figures
  come from `Product.price`, and the "23% OFF" badge is computed from the two, so the
  discount can be re-priced or ended in App Store Connect with no app update. Inventing a
  price the store never returned is a 3.1.2 / consumer-law risk; sourcing one from a real
  product is not. When `Product.products(for:)` comes back empty the paywall shows
  `--`, a **"Prices unavailable … Try again"** note, and a **disabled** purchase bar. A
  plain `simctl launch` does **not** apply the `.storekit` config, so that redacted state
  is exactly what you see in a CLI-installed simulator build — it is correct, not a bug.
- **Files (all present):** `Shared/LeapEntitlements.swift` (IDs, price constants, trial +
  gating, App-Group `isPro` mirror), `Leap/LeapStoreKitManager.swift` (StoreKit 2 engine +
  `Transaction.updates` listener), `Leap/PaywallView.swift` (paywall UI),
  `Leap/LeapPremiumMark.swift` (tintable award emblem), `Leap/LeapDebugPanel.swift` (shake
  panel), `Leap.storekit` (+ scheme ref). Wired via `LeapViewModel` (`@Published isPro`) +
  `HomeView` (`ScreenHeader` Upgrade, `AddWidgetSheet.save()` gate, Settings row).
- **Gate (as-built — supersedes §5's 2-widget sketch):** a **7-day free trial**
  (`leap.trial.start.v1`, started once from `LeapViewModel.completeOnboarding()` -
  **after** onboarding states the 7-day term, per 3.1.1; `init` only backfills
  installs that finished onboarding under an older build), then
  **`freeWidgetAllowance = 4`** free widgets + a hard cap of **8** (`freeWidgetHardCap` — the
  **9th** add opens the paywall). The **newest** surplus rows (rank ≥ 4, where
  `rankOldestFirst = savedWidgets.count-1-index` because the list is **newest-first**) show a
  red **"N days left in trial"** countdown and **lock** after expiry. **`freePhotoAllowance =
  1`** custom photo — a 2nd import triggers the paywall. The daily check-in / streak is **never**
  gated. **Premium removes every restriction.**
- **Entry points:** the **Upgrade** button (Home header — iOS-26 **Liquid Glass** capsule) and
  the **9th-widget** add attempt open `PaywallView`; Settings has an unlock row. The loss
  banner **"Don't lose access to your [savedCount − 4] trial widgets"** shows only for a
  **restricted-action** trigger (`.widgetLimit` / locked-tap), **not** the proactive Upgrade tap.
  **Premium users see a lime PREMIUM badge by the LEAP eyebrow and all upsell surfaces are hidden.**
- **Contrast:** on-accent icons/text use **`LeapTheme.onAccent`** (lime→ink, others→white) —
  see [theming.md](theming.md).
- **Debug / Internal only:** shake in Settings → password **`NammaLeap@2026`** → toggle plan
  free/premium (`Leap/LeapDebugPanel.swift`; persists `leap.debug.plan.override.v1`, which the
  `storeKit.$isPro` sink respects so the toggle sticks). The panel is gated on
  **`#if DEBUG || LEAP_INTERNAL`** — **compiled out of public Release** (no panel / password /
  `isPro` override), **present** in the release-grade **Internal** build config for QA/TestFlight
  (see [build-and-run.md](build-and-run.md) → "Build configurations"). Public Release derives
  `isPro` **only** from StoreKit. The panel's plan toggle is a **one-way door no longer** —
  it labels the plan "(forced)" vs "(StoreKit)" and offers **"Use real StoreKit entitlement"**
  (`LeapViewModel.debugClearPlanOverride()`), because once pinned the override made every
  subsequent Sandbox purchase test meaningless and there was no way back short of a reinstall.

---

## 0.1 Hardening pass — 2026-07-29 (paid developer account)

> Done on branch **`feature/iap-e2e`** in the `Leap-iap` worktree, after the paid Apple
> Developer Program membership landed. Everything below is **as-built**; a code-review
> audit's BLOCKER/HIGH/MEDIUM findings are all closed.

**Legal (was the App Review 3.1.2 BLOCKER — Leap shipped an auto-renewable subscription
with no EULA and no privacy policy anywhere).**
- `Leap/LeapLegalView.swift` is the **single source of truth**: `LeapLegalDocument`
  (`.privacy` / `.terms`), `LeapLegalSection`, `LeapLegal.contactEmail`. Both documents
  render as themed in-app sheets, so they **work offline and cannot 404**.
- Linked from **both** required places: the **paywall footer** (`legalFootnote` → "Terms of
  Use – Privacy Policy") and **Settings → LEGAL**.
- `docs/legal/privacy-policy.html` + `docs/legal/terms-of-use.html` are **generated from
  that Swift file** for the App Store Connect **Privacy Policy URL** metadata field, which
  cannot point at an in-app screen. **Regenerate them whenever the Swift text changes** or
  the hosted copy silently diverges from the shipped one.
- The paywall carries the full 3.1.2 disclosure (title, length, price-per-period,
  auto-renewal, "manage in your Apple Account settings", "the lifetime unlock does not
  renew"). The price clause **disappears** when the catalog is unavailable.

**Honesty of the offer (a 3.1.2(i) / consumer-law risk, not a cosmetic one).**
- The comparison table lists the gates Leap actually enforces: saved widgets
  (4 → Unlimited), custom photo wallpapers (1 → Unlimited), whether surplus widgets stay
  unlocked, and whether every saved widget stays editable. **Rows are no longer ticked in
  both columns** — an identical pair read as "free gets everything" and made the upsell
  look pointless. The two catalog rows say **"Limited" → "All"** instead; see
  `PaywallView.comparisonRows` for why the wording is deliberately vague, and §12.6 for
  the open 2.3.1 question about it.
- Marketing copy no longer claims "Every widget / Every style / Every wallpaper" (it was
  false: those are free). The paywall headline and the Settings upsell card both promise
  **unlimited widgets + unlimited photo wallpapers**.
- **`LeapProduct.Fallback` was deleted.** Never print a price StoreKit did not return.

**Store reachability + subscription lifecycle.**
- `LeapStoreKitManager.CatalogState` (`.idle/.loading/.loaded/.unavailable`) drives a real
  empty state: `--` prices, a **"Prices unavailable … Try again"** note, a disabled purchase
  bar. `loadProducts()` is idempotent, `loadProductsAndWait()` exists for the paywall's
  `onAppear`, and `purchase(id:)` **retries the catalog once** before failing.
- `displayPrice(for:) -> String?` is **Optional by design** — there is no fallback string.
- `refreshSubscriptionStatus()` + `observeSubscriptionStatus()` publish `hasBillingIssue`
  (billing retry / grace period → Settings banner) and `hasActiveSubscription` (drives
  `.manageSubscriptionsSheet`, so a subscriber can cancel from inside the app).
- `LeapProduct.subscriptionGroupID` must equal the group ID in `Leap.storekit` **and** in
  App Store Connect — a headless test asserts the first half of that.
- **Restore always reports an outcome.** It used to set `errorMessage`, which only the
  paywall was bound to, so a Settings restore was silent and then ambushed the next
  paywall. `SettingsTab.runRestore()` owns its own alert, and the Restore row is now shown
  to Premium users too (a stale entitlement is exactly when you need it).

**⛔️ Bounded StoreKit awaits — and the trap in the obvious implementation.**
`AppStore.sync()` has **no internal deadline**: measured sitting for **857 seconds** against
an unreachable store, i.e. a Restore button spinning for 14 minutes. `Transaction.currentEntitlements`
and `Product.SubscriptionInfo.status(for:)` are equally unbounded, so bounding only `sync()`
still left a **199-second** restore. All three now go through
`LeapStoreKitManager.withTimeout` (`syncTimeout = 30`, `loadTimeout = 20`,
`refreshTimeout = 10`; a timeout raises `TimedOut`, which is deliberately **not** a
`CancellationError` so it reads as a failure, not the user backing out; a timed-out
entitlement read **keeps the cached `isPro`** rather than downgrading the user).
**The first `withTimeout` was written as a `withThrowingTaskGroup` race with
`group.cancelAll()` and it bounded NOTHING** — a task group awaits every child before it
returns, and `AppStore.sync()` ignores cancellation, so the "timeout" still waited the full
199 s. It is now a `withCheckedThrowingContinuation` + `NSLock` one-shot that hands back the
first result and **abandons** the laggard. `testRestoreIsBoundedAndAlwaysReportsAnOutcome`
pins this: it fails at 199 s and passes at 40 s.

**Automated proof — `LeapIAPTests` target + `Leap.xctestplan`.**
See §8.1. `LeapEntitlementChainTests` (10 tests) runs headless and always passes;
`LeapIAPTests` (11 `SKTestSession` tests) **skips loudly** because of Apple bug
**FB22237318**.

---

## 1. TL;DR — the recommended approach

- **Use StoreKit 2** (the modern `Product` / `Transaction` async API), not the legacy
  `SKPaymentQueue`. Leap's deployment target is **iOS 17.0** (`IPHONEOS_DEPLOYMENT_TARGET
  = 17.0`), so **all** of StoreKit 2 — including the SwiftUI store views
  (`SubscriptionStoreView`, `ProductView`, `StoreView`) — is available. No third-party
  SDK (RevenueCat etc.) is needed for a single unlock.
- **Sell one primary product: a non-consumable "Leap Pro" lifetime unlock.** (Optionally
  add an auto-renewable subscription group later — see §3.) Non-consumable is the
  simplest, review-friendliest fit for a "unlock the studio" app and needs no server.
- **Entitlement is authoritative from `Transaction.currentEntitlements`** in the **app**;
  mirror a single `Bool` ("is Pro") into the **App Group** so the **widget extension**
  can read it (widgets must NOT call StoreKit — see §7). This mirrors Leap's existing
  cross-process pattern (the extension already writes `leap.hostTransparent.*` flags that
  the app reads via `LeapStore`; here the direction is reversed).
- **Gate at the points that already exist** (§5): the number of saved widgets, premium
  designs/styles/wallpapers, custom photo wallpaper, and live-data categories. The
  `freeWidgetCredits` counter in `LeapState` is an intentional pre-wired hook
  (`Shared/LeapModel.swift:34`, `docs/PLAN.md:72`).
- **The project is hand-authored** (`project.pbxproj`) — adding new `.swift` files and a
  `.storekit` config requires manual pbxproj edits (§6). Budget for it.

> **Blocking business decisions for the human** (an implementing agent should surface,
> not silently invent, the final answers): **price**, **one-time vs subscription**, and
> the **exact free-vs-Pro split**. §3/§5 give a concrete default so implementation isn't
> blocked, but these are product calls.

---

## 2. Prerequisites (account + capability) — READ FIRST

IAP cannot be fully built/tested without App Store Connect setup. Like WeatherKit (see
[build-and-run.md](build-and-run.md)), some of this **requires a PAID Apple Developer
Program membership**; the current signing team `D2Z89UU4R7` appears to be a
free/personal team (WeatherKit's entitlement is commented out for that reason).

- **Paid membership required** to *create real products* in App Store Connect and to test
  with **Sandbox**/**TestFlight**. **Local testing does NOT need it** — a `.storekit`
  configuration file (§6.7) exercises the full purchase/restore/refund flow in the
  Simulator against a synthetic store, so an agent can build and verify the entire UX on a
  free team. Only shipping real purchases needs the paid account.
- **No special entitlement file entry is needed for StoreKit.** In-app purchase is enabled
  by the app's provisioning/App ID capability ("In-App Purchase", on by default for App
  Store apps), *not* by a key in `Leap.entitlements`. Do **not** add a StoreKit key to the
  `.entitlements` plist.
- **App Store Connect setup (paid, done once, by the account holder):**
  1. Create the app record for bundle id `com.sololeap.leap.app` (if not present).
  2. Create the IAP product(s) with the IDs in §3; set price tier, localized display
     name/description; attach a review screenshot; submit for review (products can be
     submitted alongside the first app version).
  3. Sign the **Paid Apps Agreement** (Business section) — IAPs won't load until it's
     active. `Product.products(for:)` returning `[]` in Sandbox is almost always this.
  4. Create a **Sandbox tester** Apple ID for on-device testing.

---

## 3. Product model (what to sell)

**Recommended default (tunable):** a single **non-consumable** unlock.

| Product ID | Type | Purpose |
|------------|------|---------|
| `com.sololeap.leap.app.pro.lifetime` | Non-consumable | One-time "Leap Pro" unlock — the whole studio |

**Optional (only if the human wants recurring revenue)** — an auto-renewable subscription
group named `Leap Pro`, with the lifetime unlock kept as a non-consumable alternative:

| Product ID | Type |
|------------|------|
| `com.sololeap.leap.app.pro.yearly` | Auto-renewable (group `leap_pro`) |
| `com.sololeap.leap.app.pro.monthly` | Auto-renewable (group `leap_pro`) |

Keep the product IDs in **one Swift enum** (`LeapProduct`) so there's a single source of
truth (see §4, step 2). Don't scatter raw strings.

> **Entitlement model:** treat "Pro" as a single boolean derived from
> `Transaction.currentEntitlements` — true if *any* of the Pro product IDs is a verified,
> non-revoked entitlement. This makes the gate identical whether the user bought the
> lifetime unlock or holds an active subscription.

---

## 4. Where the code goes (files & anchors)

### New files to create

| File | Target(s) | Role |
|------|-----------|------|
| `Shared/LeapEntitlements.swift` | **app + widget** (shared, like `LeapStore`) | App-Group-backed `isPro` mirror + product-ID enum. Readable from both processes. |
| `Leap/LeapStoreKitManager.swift` | **app only** | StoreKit 2: load products, `purchase()`, `Transaction.updates` listener, `currentEntitlements`, `restorePurchases()`. `@MainActor ObservableObject`. |
| `Leap/PaywallView.swift` | **app only** | The "Leap Pro" upsell sheet (reuse `LeapTheme`/`LeapFont`/glass; or embed `SubscriptionStoreView`/`ProductView`). |
| `Leap.storekit` | project (scheme ref) | Local StoreKit config for Simulator testing (§6.7). |

Follow the shared-file rule from [architecture.md](architecture.md): a `Shared/` file must
be registered in **both** target membership lists (`DA…` app build file + `DD…` widget
build file, both referencing a single `FA…` fileRef). App-only files use an `FB…` fileRef
+ a `DA…` build file in the app Sources phase only. See §6 for exact pbxproj steps.

### Existing files to touch

- `Shared/LeapModel.swift` — the App Group id lives in `LeapConstants.appGroup`
  (`group.com.sololeap.leap.app`). Add the new UserDefaults key constant here or in
  `LeapEntitlements`. `freeWidgetCredits` (line 34) is the pre-existing premium hook.
- `Leap/LeapViewModel.swift` — add `@Published private(set) var isPro` and expose
  `storeKit` (the manager) so views can gate/paywall. Refresh `isPro` in `refresh()`
  (called on scene-active in `RootView`, `Leap/RootView.swift:36`).
- `Leap/LeapApp.swift` — start the **transaction-updates listener** for the app's lifetime
  (a `.task` on `RootView`, or in `LeapViewModel.init`). This catches purchases made on
  other devices, Ask-to-Buy approvals, and refunds.
- `Leap/HomeView.swift` — the **gate points**:
  - `AddWidgetSheet.save()` (line ~1084) / `LeapViewModel.addWidget` — enforce the free
    saved-widget cap and premium-design gate; present `PaywallView` instead of saving when
    the user is over the free limit.
  - `SettingsTab` (line ~1261) — add a **"Leap Pro"** row (unlock CTA when free, "Pro
    member" badge when owned) and a **"Restore Purchases"** row (App Store **requires** a
    restore control for non-consumables).
  - Browse tiles / the design drawer / `WallpaperStrip` — show a small lock affordance on
    Pro-only designs/wallpapers/styles.
- `Shared/LeapWallpaperStore.swift` — `LeapLibraryStore.add()` is where a saved widget is
  persisted; the free-cap check can also live here (return unchanged list + surface a
  "needs Pro" signal) if you prefer store-level enforcement over view-level.

---

## 5. The gate: free vs Pro (concrete default)

> **As-built note:** the shipped gate is a **7-day trial + 4 free widgets (hard cap 8) +
> 1 custom photo** (see §0), not the "2 widgets" first-cut sketched below. The free-vs-Premium
> *split philosophy* here still holds; only the numbers moved.

**Never gate the core daily check-in / streak** (`checkIn`, `LeapStore.toggleToday`) — it's
the app's habit loop and must stay free. Gate the "studio" surface instead:

**Free tier (default):**
- The daily check-in + streak, all 3 widget sizes, transparent/solid background.
- Up to **4** saved widgets in *My Widgets* (after a 7-day trial; hard cap 8). _(As-built; the first-cut sketch said 2.)_
- A curated subset of designs (e.g. one per category), **Editorial** style only,
  built-in **system** wallpapers.

**Leap Pro unlocks:**
- **Unlimited** saved widgets.
- **All 66 designs**, **all 4 styles** (Minimal / Dot-Matrix / Neon), **all wallpapers**
  + **custom photo wallpaper** (`importCustomWallpaper`).
- **Live-data** categories (Weather / Calendar) and **host transparency**.

Express this as data, not scattered `if`s — e.g. add `var isPro: Bool` (or
`requiresPro`) to `LeapWidgetKind` / `LeapWidgetStyle` / `LeapWallpaperKind`, then a single
`LeapEntitlements.isLocked(design:style:wallpaper:)` helper the UI consults.

**On the `freeWidgetCredits` stub:** it already grants one credit per 7-day streak
(`Shared/LeapStore.swift:105`) and decodes back-compat safely
(`Shared/LeapModel.swift:66`). Two options:
1. **Ignore it for gating** — IAP is the only unlock (simplest, recommended first cut).
2. **Growth loop** — let each credit unlock one Pro design temporarily, IAP unlocks
   everything permanently. Nice retention hook, more logic. Decide with the human.

---

## 6. Implementation steps (ordered)

### 6.1 App Store Connect + products
Do §2/§3 (paid-account holder). For local-only work, skip to 6.2 and use the `.storekit`
file — you can build the *entire* feature without App Store Connect.

### 6.2 `Shared/LeapEntitlements.swift` — the cross-process mirror
Single source of truth for product IDs + the App-Group `isPro` flag the widget reads.

```swift
import Foundation

enum LeapProduct {
    static let lifetime = "com.sololeap.leap.app.pro.lifetime"
    // Optional subscriptions:
    static let yearly  = "com.sololeap.leap.app.pro.yearly"
    static let monthly = "com.sololeap.leap.app.pro.monthly"
    static let all: Set<String> = [lifetime, yearly, monthly]
}

/// App-Group-backed "is Pro" flag. The APP writes it (from StoreKit); the WIDGET
/// only reads it. Mirrors LeapStore's cross-process convention.
enum LeapEntitlements {
    private static let key = "leap.pro.active.v1"
    private static var defaults: UserDefaults {
        UserDefaults(suiteName: LeapConstants.appGroup) ?? .standard
    }
    static var isProCached: Bool { defaults.bool(forKey: key) }
    static func setPro(_ v: Bool) { defaults.set(v, forKey: key) }
}
```

Register in **both** targets (§6.8).

### 6.3 `Leap/LeapStoreKitManager.swift` — StoreKit 2 (app only)
Load products, purchase, verify, restore, and keep entitlement fresh. Verify every
transaction — **only deliver on `.verified`**; treat `.unverified` as not-entitled.

```swift
import StoreKit

@MainActor
final class LeapStoreKitManager: ObservableObject {
    @Published private(set) var products: [Product] = []
    @Published private(set) var isPro = false

    private var updates: Task<Void, Never>?

    init() {
        updates = observeTransactionUpdates()   // start BEFORE any purchase
        Task { await loadProducts(); await refreshEntitlements() }
    }
    deinit { updates?.cancel() }

    func loadProducts() async {
        products = (try? await Product.products(for: Array(LeapProduct.all))) ?? []
    }

    /// Authoritative gate: true if any Pro product is a verified current entitlement.
    func refreshEntitlements() async {
        var pro = false
        for await result in Transaction.currentEntitlements {
            guard case .verified(let t) = result else { continue }
            if LeapProduct.all.contains(t.productID) && t.revocationDate == nil {
                pro = true
            }
        }
        isPro = pro
        LeapEntitlements.setPro(pro)                 // mirror to App Group
        WidgetCenter.shared.reloadAllTimelines()     // so gated widgets update
    }

    func purchase(_ product: Product) async throws {
        switch try await product.purchase() {
        case .success(let verification):
            if case .verified(let t) = verification { await t.finish() }
            await refreshEntitlements()
        case .userCancelled, .pending: break
        @unknown default: break
        }
    }

    /// App Store REQUIRES a restore control for non-consumables.
    func restore() async { try? await AppStore.sync(); await refreshEntitlements() }

    private func observeTransactionUpdates() -> Task<Void, Never> {
        Task(priority: .background) { [weak self] in
            for await verification in Transaction.updates {
                if case .verified(let t) = verification { await t.finish() }
                await self?.refreshEntitlements()
            }
        }
    }
}
```

> `WidgetCenter` needs `import WidgetKit`. `import UIKit`/`SwiftUI` as needed.

### 6.4 Wire into `LeapViewModel` + app entry
- Add `@Published private(set) var isPro = false` and own a `LeapStoreKitManager`
  (or expose it). Bridge `manager.$isPro` → `model.isPro` (Combine `assign`, or read in
  `refresh()`). `LeapViewModel` is `@MainActor` (`Leap/LeapViewModel.swift:42`).
- Ensure the `Transaction.updates` listener is alive for the whole app session. Creating
  the manager in `LeapViewModel.init` (a `@StateObject` in `LeapApp`,
  `Leap/LeapApp.swift:6`) satisfies this. Also call `refreshEntitlements()` on scene-active
  alongside the existing `model.refresh()` (`Leap/RootView.swift:36`).

### 6.5 `Leap/PaywallView.swift` + Settings entry
- Build the upsell with Leap's design tokens (`LeapTheme`, `LeapFont`, `leapGlass`,
  `ScreenHeader`, `LeapSegment`) for a native look, calling `manager.purchase(...)` /
  `manager.restore()`. **Or** embed Apple's `SubscriptionStoreView(groupID:)` /
  `ProductView(id:)` (iOS 17+) for a zero-boilerplate, auto-localized store UI.
- Present it as a `.sheet` from: the Settings "Leap Pro" row, and from any gated action
  (adding past the free cap, tapping a locked design/style/wallpaper).
- Add both a **"Leap Pro"** row and a **"Restore Purchases"** row to `SettingsTab`
  (`Leap/HomeView.swift:1261`), styled with the existing `settingsRow(...)` helper.

### 6.5b Social proof on the paywall - the catalog pill (SHIPPED)

`PaywallView.catalogProof` is a full-width capsule between the loss warning and the
comparison card: four overlapped 28pt mini widget tiles + one line reading
**"3,500+ unique widgets in Premium"**.

**Why it is shaped this way** (all of this was researched, do not re-litigate):
- **It stacks product, not people.** The rejected design was an avatar stack with
  "210 people upgraded in the last 7 days". Inventing customers on a purchase screen
  is a **guideline 3.2.2(i)** risk (interface designed to mislead into a purchase) plus
  a **UK DMCC Act 2024 / EU Omnibus** fake-review exposure, and a real recency counter
  is impossible here anyway: `firebase/feedback.firestore.rules` is deliberately
  **write-only-create with no client reads**, so a live count would need Cloud Functions
  and therefore **Blaze billing**, which this project avoids on purpose.
- **Every number is true by construction.** They come from **`LeapCatalogStats`**
  (`Shared/LeapWidgetContentView.swift`), which derives them from the enums:
  `designCount` (kinds in `LeapWidgetCategory.browseOrder`), `styleCount`,
  `backgroundCount` (`LeapWallpaperKind.builtIns`) and `uniqueWidgetCount`
  (their product, floored to the nearest 500). Nothing to substantiate, no backend.
- **Browse reads the same source** (`Leap/Browse/BrowseTab.swift`), so the two screens
  can never drift. **Never re-introduce literals on either screen** - adding a design,
  a style or a wallpaper must update both surfaces in the same build.

**Layout constraints that are load-bearing** (the mock caught these; they are tight):
- Content width is 350pt on a 390pt phone. The string is **221.6pt** at
  `LeapFont.mono(11.5)`; available = 350 - 28 (pill padding) - 85 (tile stack) - 11
  (gap) = **226pt**. At `mono(12.5)` it is 240.8pt and **clips**. The narrowest device
  that runs Leap is **375pt** (SE 2/3, 13 mini), where available drops to **211pt** and
  the text scales to ~0.95 - so keep `.lineLimit(1).minimumScaleFactor(0.7)`, which also
  absorbs a longer localised string or a bigger `designCount`. A **320pt** layout would
  leave only 156pt and could not fit even at the floor; if one ever has to be supported,
  wrap the capsule in `ViewThatFits` with a two-tile fallback rather than shrinking
  further.
- Tiles are **28pt with a -9pt overlap** (not 30/-10) purely to buy that width back.
- **9pt of every tile except the last is covered by its neighbour.** Long glyphs
  ("9:41") therefore go in the **last** slot; overlapped slots carry <= 2 characters and
  their content is offset `-4` to sit in the visible band. Ignoring this renders "9:4".
- The tile stack is `.accessibilityHidden(true)` - it is decorative, and without this
  VoiceOver reads "clock, chart pie, 67, 9:41" before the claim itself.
- Wallpaper gradients run dark -> bright and a 28pt tile samples the bright end, so each
  tile gets a `Color.black.opacity(0.18)` scrim or white glyphs wash out.
- The number uses **`LeapTheme.accentText`**, never `LeapTheme.lime` - raw lime fails
  contrast on the light-mode paper canvas. The tile border is `LeapTheme.canvas` so it
  reads as a cut-out in both schemes.

### 6.5c What a CHURNED subscriber actually keeps (verified behaviour)

Scenario: user subscribes, saves 20 widgets, cancels a month later.

| Surface | After the sub lapses (`isPro` -> false) |
|---|---|
| Placed Home-Screen widgets | **Locked past the free 4.** The extension itself evaluates `LeapEntitlements.isSavedWidgetLocked` (see 6.5d) and renders `LeapLockedFace` - blurred face + lock glyph + "PREMIUM" - for any placement bound to a widget with `rankOldestFirst >= 4`. The oldest 4 keep rendering normally. |
| My Widgets list | The **4 oldest** stay editable. Every widget with `rankOldestFirst >= 4` is locked (`LeapEntitlements.isFreeWidgetLocked`) - the row shows a lock and Edit routes to the paywall. |
| Adding a new widget | Blocked: `shouldPaywallNextWidget` is true at `savedCount >= 8` (`AddWidgetSheet.save()`). |
| Adding another custom photo | Blocked once one custom-photo widget exists (`canAddCustomPhoto`). |
| Daily check-in | Never gated. |

Two consequences worth knowing before changing anything here:

1. **The lock is a soft-landing, not a wipe.** The face is still visible behind the blur and
   the oldest 4 are untouched, so a churned user's Home Screen is never blank. Revoking
   outright would be the harshest possible churn experience.
2. **`isFreeWidgetLocked` short-circuits while the trial is active.** The trial clock starts
   at first launch, so a user who subscribes and cancels **within 7 days of installing**
   loses nothing at all. Anyone who churns after a month is past it, so the lock applies.

Which 4 survive is the **oldest** 4, not the favourites - `savedWidgets` is newest-first and
`rankOldestFirst = count - 1 - index`. That is intentional (the first widgets a user made are
the ones they set up on their Home Screen first) but it is the most likely thing to revisit.

### 6.5d Locking a PLACED widget (extension-side enforcement)

The app cannot reach a baked timeline, so the **widget extension** is the only place that can
revoke a placement. It does so with **no new IPC and no StoreKit call** (StoreKit is
unavailable in an extension) because every input already lives in the App Group:

| Input | Source |
|---|---|
| Saved-widget list + ordering | `LeapLibraryStore.shared.load()` (newest-first) |
| Entitlement | `LeapEntitlements.isProCached` mirror (`leap.pro.active.v1`) |
| Trial start | Keychain, falling back to `leap.trial.start.v1` |

**Shared decision helpers** (all in `Shared/LeapEntitlements.swift`, used by BOTH targets so
the app list and the placed widget can never disagree):

- `rankOldestFirst(of:in:)` -> `count - 1 - index`
- `isSavedWidgetLocked(id:in:isPro:now:)` -> the single source of truth
- `willLockAtTrialEnd(id:in:isPro:)` -> true if it is unlocked now only because the trial is running

`LeapViewModel.isWidgetLocked` is now a one-line call to `isSavedWidgetLocked`. **Do not
re-implement the rank arithmetic anywhere else.**

In `LeapWidget/LeapCheckInWidget.swift`:

1. `LeapEntry` carries `var locked: Bool = false`.
2. `timeline(for:in:)` early-returns a **single-entry** timeline with `policy: .after(now + 1h)`
   and `snapshot.history = []` when locked. **This single entry is mandatory** - clock faces
   otherwise archive 900 entries, and archive size is the hard WidgetKit limit (see the
   timeline-archive box in `realtime-widgets.md`).
3. `clampToTrialEnd(_:willLock:)` trims entries dated at/after `trialEndDate()` and sets
   `policy: .after(end)` so the widget re-renders into the locked state the moment the trial
   ends - but **only when the expiry falls inside the timeline's own horizon**
   (`end <= lastEntry.date`), otherwise the natural reload is sooner and replacing the policy
   would push the next refresh days out.
4. `LeapLockedFace` wraps the real face: `blur(3.5 / 4.5)`, `saturation(0.85)`,
   `opacity(0.85)`, a light scrim, then a lock glyph + "PREMIUM" (+ "Tap to unlock" on
   medium/large). **The face must stay recognisable** - an earlier attempt at
   blur 6/8 + saturation 0.4 + opacity 0.55 was unusable; do not go back to it.
5. It is applied in **`LeapWidgetEntryView` only**, never in the shared `LeapWidgetView`, so
   in-app previews, the Browse grid and the Edit sheet keep showing the clean design.
6. `.widgetURL(URL(string: "leap://premium"))` on the locked face. `RootView` handles it via
   `.onOpenURL` and presents `PaywallView(context: .widgetLimit(savedCount:), source:
   "widget_lock")`. **No URL scheme registration is needed** - `widgetURL` is delivered to the
   owning app directly (there is no `CFBundleURLTypes`; the Info.plist is generated).

**Deadline reporting (easy to get wrong):** `buildTimeline` returns `(timeline:deadline:)`
because **`TimelineReloadPolicy` exposes no associated date** - a timeline's reload instant
cannot be recovered from the `Timeline` value. `clampToTrialEnd` compares the expiry against
that reported deadline. An earlier version compared against the LAST ENTRY, which silently
skipped every sparse face (one entry dated `now` + `.after(...)`) and handed out up to a day
of free Premium. **Any new `return` in `buildTimeline` must report its real deadline.**

**The debug plan override must pin the MIRROR, not just the app.**
`LeapEntitlements.debugProOverride` lives in the App Group and `setPro` honours it. It used
to live in `UserDefaults.standard` and pin only `LeapViewModel.isPro`, so
`LeapStoreKitManager.applyPro` (launch + every foreground + transaction listener) overwrote
the mirror with the real StoreKit answer and placed widgets ignored the toggle while the app
looked Premium. Compiled out of public Release.

**The Keychain is NOT shared between the two targets.** `LeapSecureStore` sets no
`kSecAttrAccessGroup`, so the app and the extension each get their own default access group.
Only `LeapConstants.appGroup` is common ground. **ALL** Keychain I/O in `LeapEntitlements` therefore goes through
`secureString` / `secureSet` / `secureRemove`, which no-op when `isAppExtension`. Two real
bugs came from not doing this: an extension-written expiry latch that the app could never
clear (placed widgets locked forever), and `trialStartDate`'s Keychain **promotion** caching
the first trial start the extension ever saw - and re-mirroring that stale value back over
the App-Group key - so trial changes never reached a placed widget.

**Anti-rollback:** the trial is not pure `Date()` arithmetic. `LeapEntitlements` latches
expiry one-way (`leap.trial.ended.v1`, App Group + Keychain) and floors `now` to a clock
high-water mark (`leap.clock.highwater.v1`) via `observedNow(_:)`, so winding the device
clock back cannot revive an expired trial. `debugSetTrialStart` / `debugResetTrialAndSpin`
**must** call `clearTrialEndedLatch()`.

**Stale-state repair:** `LeapViewModel.syncPlacedWidgetLocks()` reloads all timelines on
foreground, but only when the set of locked widget IDs changed
(`leap.locks.signature.v1`) - so trial expiry or a rank shift that happened while Leap was
closed is corrected on next open, without a reload on every foreground.

**Known limitation:** a subscription *lapse* is only observable by the app, so `isProCached`
stays stale until Leap is next opened. *Trial expiry* is exact because the extension computes
it locally. Purchasing unlocks instantly - `LeapStoreKitManager.applyPro(_:)` already calls
`WidgetCenter.shared.reloadAllTimelines()`.

**Verified on the simulator:** small + medium placements blur and lock after the trial is
forced past day 7, tapping one opens Leap on the `.widgetLimit` paywall, and toggling Premium
on restores both faces immediately.

### 6.6 Apply the gates (§5)
- In `AddWidgetSheet.save()` (`Leap/HomeView.swift:~1084`): if `!model.isPro` and saving
  would exceed the free cap **or** the chosen design/style/wallpaper is Pro-only, present
  `PaywallView` and return instead of calling `addWidget`.
- In Browse tiles / the design drawer / `WallpaperStrip` / the style picker: overlay a lock
  glyph on Pro items and route taps to the paywall when `!model.isPro`.
- Keep the check-in path untouched.

### 6.7 `Leap.storekit` — local testing config
Create a StoreKit configuration file describing the §3 products (Xcode: File ▸ New ▸
StoreKit Configuration File, or hand-author the JSON). Then reference it in the **shared
scheme** so `swift`/Simulator runs hit the synthetic store:
- Scheme file: `Leap.xcodeproj/xcshareddata/xcschemes/Leap.xcscheme`, under `<LaunchAction>`
  add a `<StoreKitConfigurationFileReference identifier = "../../../Leap.storekit">`.
- This lets you exercise buy / cancel / restore / **refund** (Debug ▸ StoreKit ▸ Manage
  Transactions) with **no** App Store Connect and **no** paid team.

### 6.8 pbxproj registration (hand-authored — required)
`project.pbxproj` is not auto-synced. For each new file add, mirroring existing entries
(see `Shared/LeapStore.swift` = fileRef `FA0000000000000000000003`, app build file
`DA0B…`, widget build file `DD0B…`):
- **`Shared/LeapEntitlements.swift`** (both targets): one `PBXFileReference` (`FA…`); a
  `PBXBuildFile` in the **app** Sources phase (`DA…`) *and* one in the **widget** Sources
  phase (`DD…`); list it in the `Shared` group `G00000000000000000SHARED`.
- **`Leap/LeapStoreKitManager.swift`, `Leap/PaywallView.swift`** (app only): a `PBXFileReference`
  (`FB…`), a single app `PBXBuildFile` (`DA…`) in the app Sources phase, listed in the
  `Leap` group `G0000000000000000000LEAP`.
- **`Leap.storekit`**: add a `PBXFileReference` (no build phase needed — it's referenced by
  the scheme, not compiled/copied); optionally list it in the main group for visibility.
- After editing, **verify it still builds** with the exact command in
  [build-and-run.md](build-and-run.md) (`xcodebuild … -scheme Leap … build`). A malformed
  pbxproj fails the whole build.

---

## 7. Widget extension & IAP (important constraints)

- **Do NOT call StoreKit from `LeapWidget/`.** Widget extensions run in a restricted
  process; compute entitlement in the **app** and pass a plain `Bool` via the App Group.
  This is exactly the §6.2 mirror. The widget reads `LeapEntitlements.isProCached` inside
  the provider/`LeapEntry` if any *rendered widget content* is Pro-gated.
- Realistically, the widget rarely needs to gate at render time — the gate is on **saving**
  a widget in the app. If you do gate widget content, refresh via
  `WidgetCenter.shared.reloadAllTimelines()` after entitlement changes (already in §6.3).
- Keep the widget's placeholder/how-to behavior intact for unconfigured widgets (see the
  `LeapEntry.unconfigured` path).

---

## 7.5 Restore & reinstall (purchased premium vs the trial)

**Purchased premium is restored automatically — it is NOT stored in the app or the Keychain.**
StoreKit 2 entitlements live with the buyer's **Apple ID**, so a fresh install signed into the
same Apple ID re-grants Pro with **no user action**:

- **Automatic on launch.** `LeapStoreKitManager.init` (`Leap/LeapStoreKitManager.swift:41`) seeds
  `isPro` from the App-Group mirror `LeapEntitlements.isProCached`
  (`Shared/LeapEntitlements.swift:49`) for a correct first frame, then `refreshEntitlements()`
  (`LeapStoreKitManager.swift:85`) iterates `Transaction.currentEntitlements` and sets
  `isPro = true` for any **verified, non-revoked** `LeapProduct` (monthly sub or lifetime unlock).
  It mirrors the result via `LeapEntitlements.setPro` (`:53`, App-Group key `leap.pro.active.v1`)
  so the **widget** sees it, then calls `WidgetCenter.reloadAllTimelines()`.
- **Manual fallback — Restore Purchases.** The paywall's Restore row (`Leap/PaywallView.swift:366`)
  calls `store.restore()` (`LeapStoreKitManager.swift:146`) → `AppStore.sync()` → recompute. App
  Review **requires** this control for the non-consumable; it's also the recovery path if the
  automatic refresh didn't catch a just-completed purchase.
- **Out-of-band changes.** A live `Transaction.updates` listener (`observeTransactionUpdates`,
  `LeapStoreKitManager.swift:164`, started in `init`) catches purchases / renewals / refunds made
  elsewhere (another device, an Ask-to-Buy approval, an App Store refund) and re-refreshes.

**Contrast with the trial (a deliberately different mechanism):** the **7-day trial start** and
the **welcome-spin-once** flag are **Keychain-canonical** (`Shared/LeapSecureStore.swift`, via
`LeapEntitlements`' `trialStartKey` / `welcomeSpunKey`), so they **survive reinstall** and a free
user **cannot re-trigger the trial** by deleting + reinstalling. In short:
**trial = Keychain (anti-abuse persistence); purchase = StoreKit / Apple-ID entitlement (automatic
restore).** The widget extension reads only the `isPro` App-Group boolean — it never reads trial
state and never calls StoreKit (§7).

---

## 8. Testing

- **Simulator (free team):** run with the `.storekit` config (§6.7). Verify: products load,
  purchase succeeds → `isPro` flips → gated designs/styles/wallpapers unlock and the
  saved-widget cap lifts; **Restore** re-grants after deleting the app's purchase; **refund**
  (Manage Transactions) flips `isPro` back to false via `Transaction.updates`.
- **Device (paid team, Sandbox):** sign in with the Sandbox tester in Settings; confirm real
  product metadata/prices load (needs the **Paid Apps Agreement** active), purchase, and
  restore. Verify the App-Group mirror by pulling the plist off the device
  (`devicectl … copy from --domain-type appGroupDataContainer --domain-identifier
  group.com.sololeap.leap.app …` — see the device-debug memory / build-and-run.md) and
  checking `leap.pro.active.v1`.
- **Widget:** after purchase, confirm placed widgets reflect any gated content on the next
  timeline reload. (The Simulator caches 3rd-party widget snapshots aggressively — verify
  gated *widget content*, if any, on a device.)

### 8.1 The `LeapIAPTests` target (automated) — and ⛔️ Apple bug FB22237318

**Run it:**
```bash
cd <worktree>
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.bareRepository GIT_CONFIG_VALUE_0=all \
xcodebuild -project Leap.xcodeproj -scheme Leap -configuration Debug \
  -destination 'platform=iOS Simulator,id=<UDID>' -derivedDataPath /tmp/LeapIAPBuild test
```
(The `GIT_CONFIG_*` prefix is **mandatory inside a git worktree** or SwiftPM refuses to
resolve firebase-ios-sdk: *"safe.bareRepository is 'explicit'"*.)
Expected today: **`Executed 21 tests, with 11 tests skipped and 0 failures` → TEST SUCCEEDED**,
in ~40 s.

`LeapIAPTests/LeapIAPTests.swift` holds **two** classes, and the split is the point:

- **`LeapEntitlementChainTests` (10 tests, always run, always pass)** — everything *after*
  StoreKit hands back a transaction, with no StoreKit dependency at all: the App-Group
  mirror (`group.com.sololeap.leap.app` / `leap.pro.active.v1`), product IDs +
  `displayRank` strict-weak-ordering, the **`Leap.storekit` ↔ code contract** (both product
  IDs and the subscription group ID), every enforced gate, trial parity, newest-first lock
  ranking, the one-way trial latch, the debug-override escape hatch, the
  no-price-when-unavailable rule, and the bounded restore.
- **`LeapIAPTests` (11 `SKTestSession` tests)** — real synthetic purchases. `setUp` calls
  `skipUnlessSyntheticStoreWorks()`, which probes `Product.products(for:)` and throws
  `XCTSkip` naming **FB22237318**, **so a broken toolchain can never be mistaken for broken
  app code**. Their assertions are therefore **unproven** — they compile but have never
  executed.

  **⛔️ "the catalog is empty" is NOT a sufficient skip probe — do not simplify it back.**
  Under FB22237318 the request falls through to the **real** store, so the moment the App
  Store Connect records went live the probe started seeing products and the suite stopped
  skipping. It then ran against **production**: `testCatalogLoadsBothProducts` failed with
  `"22274535" is not equal to "92805D84-…"`, and a purchase test **hung for 30 minutes** on
  a real *"Sign in to Apple Account"* sandbox dialog that no test can dismiss (it also
  outlives the killed test host and blocks the simulator until it is rebooted). The probe
  therefore checks that the monthly product's **subscription group id matches
  `Leap.storekit`** — App Store Connect's id is numeric, so the two environments can never
  be confused. Silver lining: this is also **positive proof that both products vend live**,
  since the test only reached line 89 after asserting both ids loaded with real prices.

**⛔️ StoreKit Testing is non-functional on iOS 26.3–26.5 simulator runtimes
(Apple bug FB22237318): the `.storekit` configuration is never uploaded to `storekitd`.**
Symptoms, in the order you meet them:
1. `SKTestSession(...)` constructs **without throwing**, but `Product.products(for:)`
   returns `[]` with **no error**.
2. `session.buyProduct(identifier:)` throws `StoreKitError.notEntitled`.
3. The simulator log says it all:
   `(StoreKitTest) [SKTestSession] Error saving configuration file: SKInternalErrorDomain Code=3`,
   then `[Client] … Sandbox`, `Requesting products from Media API`,
   `Ignoring empty product response` — i.e. the app is talking to the **real** store.

**Do not re-investigate these — all ruled out:** the config file contents and
`_developerTeamID`; a stale simulator (a **fresh** one behaves identically);
`SKTestSession(contentsOf:)` vs `(configurationFileNamed:)` (the named initialiser resolves
against the **host app** bundle); a scheme-level `StoreKitConfigurationFileReference` on the
Test action; an `.xctestplan` `storeKitConfigurationFileReference`; and missing
`get-task-allow` (**Xcode strips entitlements that aren't on its simulator allowlist**, so a
Debug-only entitlements file cannot even add it — only `application-identifier` +
app-groups survive into `__TEXT,__entitlements`). **Apple's documented workaround — run
once from Xcode.app first — was tried and also failed**, so this is not a CLI-only
limitation. The only known escapes are an **older simulator runtime (~iOS 26.1)** or a
**real device against Sandbox**.

**When Apple fixes it:** delete `skipUnlessSyntheticStoreWorks()` and the 11 tests light up.
`Leap.xctestplan` already carries the StoreKit config reference for that day.

**Diagnostics worth keeping:**
```bash
xcrun simctl spawn <UDID> log stream --level debug \
  --predicate 'subsystem BEGINSWITH "com.apple.storekit" OR subsystem CONTAINS "StoreKitTesting"'
```
is the *only* way to see why StoreKit silently returned nothing. Simulator entitlements live
in the Mach-O `__TEXT,__entitlements` section, **not** the code signature
(`codesign -d --entitlements` prints an empty dict) — read them with
`otool -X -s __TEXT __entitlements`. `StoreKitTest.framework` is on a test bundle's default
search path (no explicit link needed); `SKTestTransaction.state` is an
`SKPaymentTransactionState`, which has **no `.finished`** — use StoreKit 2's
`Transaction.unfinished` instead.

**Scheme note:** `Leap.xcscheme` keeps the `.storekit` config on the **Run** action (local
purchases from Xcode) and references the test plan for **Test**. **`Leap (Internal)`
deliberately has NO StoreKit configuration** — QA/TestFlight builds must talk to the real
Sandbox, and a synthetic store there would make every QA purchase a lie.

---

## 9. App Review / policy checklist

- **Restore Purchases control is mandatory** for non-consumables (§6.5). Missing it is a
  common rejection. **DONE** — paywall + Settings, and it always reports an outcome.
- **No alternative payment methods** for digital unlocks — must use Apple IAP (don't add
  external purchase links for the Pro unlock).
- **Terms of Use (EULA) + Privacy Policy must be functional links on the subscription
  paywall.** **DONE** — `Leap/LeapLegalView.swift`, linked from the paywall footer and
  Settings → LEGAL, plus hosted HTML for the ASC metadata URL (§0.1, §12).
- The paywall must disclose price, period, and auto-renew terms. **DONE** —
  `PaywallView.legalFootnote`.
- **Never state a price the store did not return** (§0.1). The fallback prices were removed.
- **Only claim benefits Leap actually enforces** — the comparison table is generated from
  the real gates, not from marketing copy.
- Provide a working **review screenshot** + demo path so review can reach the paywall.
- **Privacy:** store only the boolean unlock in the App Group — no receipts/PII.

---

## 10. Leap-specific gotchas (don't relearn these)

- **Deployment target is iOS 17.0** → StoreKit 2 + SwiftUI store views are all fair game;
  gate `AppTransaction.appTransactionID` behind `#available(iOS 18.4, *)` if used.
- **Hand-authored pbxproj** — every new file needs manual registration in the right
  target(s) (§6.8); a `Shared/` file must be in **both** membership lists or one target
  won't compile.
- **Keep source ASCII**; gate iOS-only APIs (`#if os(iOS)` / `#available`) —
  [conventions.md](conventions.md).
- **Free team can't create real products**, but the `.storekit` file gives full local
  coverage — you can implement and verify the entire feature without the paid account
  (only shipping needs it). Same "paid-team" caveat family as WeatherKit.
- **Widgets can't call StoreKit** — App Group mirror only (§7).
- **Don't gate the daily check-in** — it's the habit loop, must stay free (§5).
- **A user CANCELLING is not a failure — keep the four outcomes distinct.** `purchase()`
  returns `.userCancelled` and `AppStore.sync()` throws `StoreKitError.userCancelled`; both
  were being reported to the user as an error, and a cancelled *restore* additionally fell
  through to "No previous purchases found", which reads like a lost purchase and is exactly
  the sort of thing that generates refund requests. Restore has **four** distinct results —
  *restored* / *nothing to restore* / *cancelled (say nothing)* / *real error* — and each
  must stay on its own branch. `userCancelled` must also not be logged to telemetry as a
  failure reason, or the funnel over-reports errors.
- **Clear `errorMessage` before every purchase/restore attempt**, or a stale alert from the
  previous attempt fires again on the next one and the user sees an error for an action
  that actually succeeded.
- **Gate the free custom-photo allowance at the point of USE, not just at the picker.**
  `freePhotoAllowance` was enforced when importing, but the already-imported photo was still
  selectable as a wallpaper swatch on every subsequent widget — so one import effectively
  unlocked unlimited use of it. The check belongs on **save** as well. Check `isPro` first so
  the short-circuit keeps Premium users out of the gate entirely.
- After wiring, update [status-and-history.md](status-and-history.md) and flip the
  `docs/PLAN.md:72` backlog item ("Turn the 7-day free-widget stub into real premium
  restrictions").

### 10.1 Troubleshooting: paywall shows "Something went wrong" instead of Apple's sheet

**Symptom.** Tapping **Unlock** on the paywall pops an alert titled **"Something went wrong"**
(`Leap/PaywallView.swift:84`) and Apple's purchase sheet never appears.

**Mechanism.** That alert just renders `store.errorMessage`. The message is *"This product isn't
available right now. Please try again later."*, set by the `guard let product` in
`LeapStoreKitManager.purchase(id:)` (`Leap/LeapStoreKitManager.swift:108-110`): when the product
catalog is empty the call **returns before ever reaching `product.purchase()`** — and
`product.purchase()` is the **only** call that presents Apple's confirmation sheet. So an empty
catalog surfaces as this error, not a sheet.

**Why the catalog is empty** (`Product.products(for:)` returned nothing → `products = []`, silently):
- **Launched outside the Xcode "Leap" scheme.** `Leap.storekit` is a **scheme run-action setting**
  (`Leap.xcodeproj/xcshareddata/xcschemes/Leap.xcscheme:51-53`), **not** baked into the `.app`. A
  plain `xcrun simctl launch`, a direct device install, or TestFlight does **not** apply it, so on
  the Simulator/dev there are no synthetic products. (This is why §0 says "run from Xcode to
  exercise a real buy".)
- **Free team / no App Store Connect products.** The real store has no records for
  `com.sololeap.leap.app.pro.{monthly,lifetime}` because the team is free (`D2Z89UU4R7`); creating
  real IAP products needs a **paid** membership — the same paid-team family as WeatherKit
  ([build-and-run.md](build-and-run.md)).

**How to get a real confirmation sheet:**
- **Local test sheet (now):** run from Xcode with the **Leap scheme** (the `.storekit` config
  applies). You get StoreKit's local-test purchase sheet (not the real Apple-ID sheet), but the
  full buy / cancel / restore / refund flow works with **no paid team**.
- **Real Apple sheet:** paid membership → create the products in App Store Connect (subscriptions
  at least "Ready to Submit") → test with a **Sandbox Apple ID** on a device or via TestFlight.

---

## 11. Open decisions to confirm with the human before shipping

1. **Pricing** and **one-time vs subscription** (or both).
2. The **exact free-vs-Pro split** (§5 is a sensible default, not a mandate).
3. Whether `freeWidgetCredits` stays a decorative streak reward or becomes a real
   temporary-unlock growth loop (§5).

---

## 12. App Store Connect setup — DONE (records live) + how it was automated

The app record itself must be made by hand (`POST /v1/apps` is **403 FORBIDDEN**:
*"resource 'apps' does not allow 'CREATE'"*). **Everything else is automatable** through the
App Store Connect REST API — that is how the records below were created.

### 12.1 Live records (team `D2Z89UU4R7`, account `sololeapinc@gmail.com`)

| Resource | ASC id | State |
|---|---|---|
| App "Leap Widgets" (`com.sololeap.leap.app`, SKU `LEAPWIDGETS2026`) | `6796248408` | created in the UI |
| Non-consumable `com.sololeap.leap.app.pro.lifetime` | `6796248820` | **READY_TO_SUBMIT**, $9.99, worldwide |
| Subscription group "Leap Premium" | `22274535` | localized en-US |
| Auto-renewable `com.sololeap.leap.app.pro.monthly` | `6796249550` | **READY_TO_SUBMIT**, $0.99/mo, 175 territories |

**The ASC group id is `22274535`, NOT the `Leap.storekit` UUID.** `LeapProduct.subscriptionGroupID`
is now only a *fallback*: `refreshSubscriptionStatus()` reads
`monthly?.subscription?.subscriptionGroupID` off the loaded product so the billing-retry
lookup works in **both** environments. Do not "fix" the constant to the numeric id — that
would break the local `.storekit` config and its test.

### 12.2 API credentials + client

```
ASC_KEY_ID=ZCT5D865V5
ASC_ISSUER_ID=b75bbafc-4c57-4d16-803f-25c367d01886
key:    ~/.appstoreconnect/private_keys/AuthKey_ZCT5D865V5.p8
client: swiftc -O /Users/vignesh/Code/NotchPaw/scripts/asc_api.swift -o /tmp/asc/asc_api
usage:  asc_api GET|POST|PATCH <path> [json-body]
```

### 12.3 ASC API gotchas (each one cost a failed request)

- **`subscriptionAvailabilities` must exist BEFORE `POST /v1/subscriptionPrices`.** Otherwise
  you get a 409 `ENTITY_ERROR.RELATIONSHIP.INVALID` that misleadingly blames the *price point*.
  Same ordering applies to `inAppPurchaseAvailabilities`.
- **A subscription needs a price in EVERY available territory to leave `MISSING_METADATA`.**
  A non-consumable price *schedule* auto-equalizes from a base territory; a subscription does
  **not**. Read `/v1/subscriptionPricePoints/{usaPointId}/equalizations?limit=200&include=territory`
  and `POST /v1/subscriptionPrices` once per territory (175 in total). Adding the review
  screenshot alone was **not** enough — the missing prices were the real blocker.
- **Inline-created resources in `included` need local ids of the form `"${price1}"`** — a bare
  `"price1"` is rejected.
- `availableInAllTerritories` is **not** a valid `inAppPurchases` attribute.
- Price point ids are opaque base64 blobs **scoped to the product**; fetch them from
  `/v2/inAppPurchases/{id}/pricePoints` or `/v1/subscriptions/{id}/pricePoints` with
  `filter[territory]=USA` (URL-encode the brackets as `%5B` / `%5D`).
- Localization limits: display name <= 30 chars, description <= 45 chars.
- **Review screenshots are a 3-step upload**: `POST /v1/inAppPurchaseAppStoreReviewScreenshots`
  (relationship `inAppPurchaseV2`) or `/v1/subscriptionAppStoreReviewScreenshots`
  (relationship `subscription`) with `{fileSize, fileName}` -> `curl -X PUT` the bytes to each
  returned `uploadOperations` url with its `requestHeaders` -> `PATCH` with
  `{"uploaded": true, "sourceFileChecksum": "<md5>"}`. Expect `assetDeliveryState.state`
  `UPLOAD_COMPLETE` then `COMPLETE`.
  **That whole dance is now scripted** - `scripts/asc_iap_screenshot.sh iap|sub <id> <png>`
  deletes the existing screenshot, reserves, PUTs every chunk with its `requestHeaders`,
  PATCHes the md5 and polls to `COMPLETE`. It **rejects a PNG with an alpha channel** up
  front, because alpha is accepted at upload time and only surfaces later in
  `assetDeliveryState.errors`.

### 12.3b A review screenshot goes STALE when the price changes - re-capture it

The uploaded screenshots showed **$8.99** long after the configured `customerPrice` became
**9.99**, because the capture was taken before the price was raised. Nothing in the app is
wrong: the paywall has **no hard-coded price** (`store.displayPrice(for:)` reads
`Product.displayPrice`), so only the *image* was stale. **Check the configured ASC price
before assuming the app is at fault** - here the description's "$9.99" was the correct
value and the picture was the lie.

The current capture lives at **`docs/store/screenshots/iap/paywall-plans.png`**
(1320x2868, no alpha) and is uploaded to all three records - lifetime `6796248820`,
list-price `6796395835` and monthly subscription `6796249550`. It is deliberately the
**scrolled** paywall, because that frame is the only one that shows *everything* App
Review needs at once: both plans with live prices, the struck-through list price and the
`23% OFF` badge, `Restore Purchases`, the auto-renew disclosure, and the Terms of
Use / Privacy Policy links. The unscrolled top of the paywall clips the Monthly row.

**To re-capture** (no Xcode needed - see 12.4):

1. `xcodebuild ... -scheme Leap -configuration Debug -destination 'platform=iOS Simulator,id=<udid>'`
   then `xcrun simctl install`.
2. The paywall is **hidden while Premium**, and `leap://premium` is **not** reachable via
   `simctl openurl` - Leap registers **no** `CFBundleURLTypes`, so LaunchServices returns
   `LSApplicationWorkspaceErrorDomain error 115`. `widgetURL` deep links work only because
   WidgetKit hands them straight to the owning app.
3. So force the free tier by editing the **App Group plist directly**:
   `.../Devices/<udid>/data/Containers/Shared/AppGroup/<guid>/Library/Preferences/group.com.sololeap.leap.app.plist`,
   setting `leap.debug.pro.override.v1` and `leap.pro.active.v1` to `false`.
   **⛔️ `xcrun simctl spawn <udid> defaults write group.com.sololeap.leap.app ...` does NOT
   work** - `simctl spawn` runs outside the sandbox, so it writes (and reads back!) a
   *different* plist and silently appears to succeed. Use `PlistBuddy`, not `plutil`:
   `plutil` treats the `.` in `leap.debug.pro.override.v1` as a key-path separator.
   Then `simctl shutdown` + `boot` so `cfprefsd` re-reads.
4. Launch, tap **Upgrade** (top-right of Home), drag the sheet up, `simctl io ... screenshot`.
5. Flatten the alpha (`PIL ... .convert("RGB")`) before uploading.
6. **Restore** `leap.debug.pro.override.v1` to its previous value afterwards.

### 12.4 A simulator build DOES fetch live App Store prices

Contrary to the usual advice, a plain `simctl install` build (no Xcode, no StoreKit config)
resolves **real** prices from App Store Connect: the client environment is `Sandbox`, which
hits the real Media API. Live App Store pricing rendered in the paywall **before** the Paid Applications
Agreement was Active. So a blank price is evidence about the **ASC record**, not proof that
the agreement is the blocker.

### 12.4b The struck-through list price is a THIRD product — not a hard-coded number

`com.sololeap.leap.app.pro.lifetime.list` (**`6796395835`**, $12.99 / EUR 12.99) exists
**only to carry the undiscounted list price.** It is never offered for sale, grants
nothing, and is deliberately excluded from `LeapProduct.all` (the entitlement set) while
being included in `LeapProduct.allFetchable` (the fetch set). `performLoad()` splits it
into `lifetimeListProduct` before the catalog reaches the paywall, so it can never appear
in the plan picker or make `catalogState` look `.loaded` on its own.

**Why a whole product:** StoreKit has **no "was" price for a non-consumable** - Apple's
introductory and promotional offers are subscription-only. A hard-coded `"12.99"` would be
a figure nobody is ever charged, wrong in every storefront but one, and a fabricated
reference price under App Review 3.1.2 and the UK DMCC / EU price-indication rules. A
second product is the only way to source a reference price that is **live, localized to
every currency, and re-pricable in App Store Connect after launch with no app update.**

Both prices sit on aligned price-point tiers so the discount is the same everywhere:

| Tier | USD | EUR | Used by |
|---|---|---|---|
| `10127` | 9.99 | 9.99 | `...pro.lifetime` (charged) |
| `10142` | 12.99 | 12.99 | `...pro.lifetime.list` (reference) |

`PaywallView.lifetimeSavingsPercent` derives **23% OFF** from those two live prices and
rounds **down**, so the badge can never overstate the discount, and
`lifetimeReference` falls back to twelve months of the monthly plan, then to nothing -
a paywall that cannot prove a saving must not claim one.

**⛔️ The price-point "tier" index is NOT aligned across territories — never assume it is.**
A price point id is a base64 JSON blob, `{"s":"<productId>","t":"<territory>","p":"<tier>"}`,
which is trivially constructible - but the same `p` means different money in different
storefronts. Pinning both products to "matching" tiers looked right in USD/EUR/GBP and
silently produced a **list price BELOW the charged price in India** (tier 10142 = INR 479
against a INR 999 unlock), which the paywall then correctly refused to draw. Equally, letting
Apple auto-equalize is wrong for the *display*: EUR price points are VAT-inclusive, so a
USD 12.99 base equalizes to **EUR 14.99**, and the badge read 33% off instead of 23%.

The reference product is therefore priced **per territory**, by taking each storefront's
actual charged price and selecting the nearest price point **at or above** `charged x 1.3003`
(`/tmp/asc/pin3.py`). That gives 23-25% off in all 175 storefronts - 12.99/9.99 in USD, EUR
and GBP, 1299/999 in INR, 1960/1500 in JPY. Because this product is never purchased, pinning
it has **zero revenue impact**; it only controls what the strikethrough reads.

To page the ~140,000 price points, use `/v2/inAppPurchases/{id}/pricePoints?limit=8000` and
follow `links.next` (18 pages). A per-territory `filter[territory]` query with `limit=1000`
returns **HTTP 500**; 200 is the safe per-page maximum there.

**⚠️ Flag at review time:** an IAP that is never purchasable can draw a reviewer question.
The product carries a `reviewNote` explaining its purpose. If Apple objects, delete it -
the paywall degrades automatically to the 12-months-of-Monthly anchor with no code change.

**⛔️ Do not put rows where free and Premium are identical in the comparison table.** They
render as a grey tick beside an accent tick, which reads as "free already gets everything"
and makes the upsell look pointless. The table lists only the four gates the code really
enforces (saved widgets, custom photos, surplus widgets staying unlocked, editing every
saved widget); what is free for everyone is stated once in prose underneath. Equally, do
**not** put a cross against something the app does not gate - that is an unenforced claim.

### 12.5 Still outstanding (human)

1. **Paid Applications Agreement is `Pending`** (enrolled as an **Individual**). Complete
   Contact Info, Bank Account (personal, name must match the legal name) and Tax Forms
   (**W-8BEN**, not W-8BEN-E). There is no API for agreements. Until it is *Active* a Sandbox
   **purchase** cannot complete, even though prices already vend.
2. **Host the legal pages** and paste the Privacy Policy URL into App Information (and the
   EULA/Terms URL on the subscription group). Source files: `docs/legal/privacy-policy.html`,
   `docs/legal/terms-of-use.html` — **regenerate them from `Leap/LeapLegalView.swift` whenever
   the in-app text changes.**
3. **Create a Sandbox tester** (Users and Access -> Sandbox Testers).
4. **Run the real purchase on a DEVICE** — sign the sandbox tester in under
   Settings -> Developer -> Sandbox Apple Account, install the **`Leap (Internal)`** scheme
   (no synthetic StoreKit config), **clear the debug plan override** in the shake panel, then
   verify in order: prices load -> buy lifetime -> `isPro` flips -> the widget cap lifts ->
   delete + reinstall -> **Restore** re-grants -> refund in Manage Transactions flips `isPro`
   back off via `Transaction.updates`. Confirm the App-Group mirror with
   `devicectl ... copy from --domain-type appGroupDataContainer --domain-identifier
   group.com.sololeap.leap.app` and check `leap.pro.active.v1`.
   **This device run is the only remaining way to prove the StoreKit half end-to-end**,
   because of FB22237318 (§8.1).


# User requirement

> **Historical.** Recorded verbatim as first stated. **The lifetime price shipped at
> `$9.99`, not `$8.99`** — it was raised before launch. `docs/agents/payment-integration.md`
> is the source of truth for live pricing.

- there should be 2 option for user to choose from, 0.99$/ month and 8.99 (12.99 striked out calling out offer) one time purcahse
- user should be shown a table on what user gets on free vs premium
  - in free user get 4 widgets. premium provides full access
  - add atleast 3 in the tab
- should show "no commitment, cancel anytime"
- this should show up for free users when user tries to add 9th widget to their list or when an upgrade button on the top right is clicked 
- there should be an info that you'll loose access to [user added widget count - 4 ] wigets if they dont upgrade 
- on purchase complete upgrade should be remove and user gets full access. this is will implented seperatly
this task should only focus on the purcahse experience 
### 12.6 The catalog rows say "Limited" / "All", and the code does NOT gate designs

`PaywallView.comparisonRows` contrasts **Designs** and **Styles** as `Limited` against
`All`. Nothing in `LeapEntitlements` gates a design or a style: a free user can open any
of the 67 designs in any of the 4 styles. What is gated is **how many saved widgets you
may keep** (`freeWidgetAllowance = 4`, hard cap 8) and **how many may use your own photo**
(`freePhotoAllowance = 1`).

So "Limited" is a claim about the *tier*, not about per-design locking — with four slots
a free user can have at most four designs in play at once. The cells deliberately carry
**no number**: an earlier revision read "All 67 / All 67", which made the rows pointless,
and "4 of 67" would assert a gate that does not exist in code. Two reviewers flagged the
current wording as a **2.3.1 accurate-metadata** risk anyway, because a reviewer's first
action is to tap a design and find it opens. **The owner chose this wording knowing that**;
treat it as a product decision, not an oversight.

If App Review does push back, the two safe rewrites are:
- **Designs in use → `4` / `Unlimited`** (states the real gate), or
- **delete both rows** — the widget-count and photo rows already carry the pitch.

Do **not** "fix" it by adding gating code: locking designs would break every already-placed
widget of a lapsed subscriber, which §6.5c deliberately avoids.
