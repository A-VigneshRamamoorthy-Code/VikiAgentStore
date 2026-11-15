import OSLog
import StoreKit
import SwiftUI

/// Leap VPN Plus: one auto-renewable subscription group shared by the iPhone and Mac apps
/// (universal purchase), monthly or yearly, each with a 2-week free-trial introductory offer
/// configured in App Store Connect. Signing in and setting up servers are free; connecting
/// needs Plus (the trial counts), and Connect opens the subscription screen without it.
enum PlusProduct: String, CaseIterable {
    case yearly = "com.sololeap.leapvpn.plus.yearly"
    case monthly = "com.sololeap.leapvpn.plus.monthly"

    static let ids = Set(allCases.map(\.rawValue))
}

@MainActor
final class Store: ObservableObject {
    static let shared = Store()

    enum Entitlement: Equatable { case unknown, none, plus(expires: Date?) }

    @Published private(set) var products: [Product] = []
    @Published private(set) var entitlement: Entitlement = .unknown
    /// Whether this Apple Account can still take the free trial (one per subscription group);
    /// nil until StoreKit has answered, and purchases wait for the answer.
    @Published private(set) var trialEligible: Bool?
    /// The account subscribed once and it lapsed (e.g. the trial ended without renewing).
    @Published private(set) var lapsed = false
    /// The lapsed subscription ended at the close of its free trial, rather than a paid period.
    @Published private(set) var trialEnded = false
    /// Why the subscription screen is open, which picks its headline.
    enum Reason { case upgrade, trialOffer, gated }
    @Published private(set) var reason: Reason = .upgrade
    @Published private(set) var purchasing: String?
    @Published private(set) var restoring = false
    @Published var message: StoreMessage?
    @Published var showPaywall = false

    private var updates: Task<Void, Never>?
    private static let log = Logger(subsystem: "com.sololeap.leapvpn", category: "store")
    private var started = false
    private var refreshing: Task<Void, Never>?
    private var refreshAgain = false
    private var recheck: Task<Void, Never>?
    private var preview = false

    #if DEBUG
    /// Test aid (URL control only): shows the subscriber UI for this run, for App Store captures.
    func previewPlus() {
        preview = true
        entitlement = .plus(expires: nil)
        showPaywall = false
    }

    /// Test aid (URL control only): poses as an account whose free trial ran out, for this run.
    func previewTrialEnded() {
        preview = true
        entitlement = .none
        lapsed = true
        trialEnded = true
        trialEligible = false
    }

    /// Test aid: the subscription screen exactly as Connect shows it to an account in this state.
    func previewGate() { reason = gateReason; presentPaywall() }

    /// Test aid: drop every preview and "already shown" flag, then ask StoreKit again.
    func resetTesting() {
        preview = false
        lapsed = false
        trialEnded = false
        UserDefaults.standard.removeObject(forKey: Self.trialOfferKey)
        UserDefaults.standard.removeObject(forKey: Self.lastUpsellKey)
        Task { await loadProducts(); await refresh() }
    }

    /// Test aid (URL control only): opens the first-connect trial offer, ignoring "shown once".
    func previewTrialOffer() {
        UserDefaults.standard.removeObject(forKey: Self.trialOfferKey)
        offerTrial()
    }
    #endif

    var isPlus: Bool { if case .plus = entitlement { return true }; return false }

    /// Runs after the user subscribes from a gated action (e.g. Connect).
    private var afterUnlock: (() -> Void)? { didSet { waitingToConnect = afterUnlock != nil } }
    /// The subscription screen was opened by a gated action rather than the Upgrade button.
    @Published private(set) var waitingToConnect = false

    /// Gate for Plus-only actions. Returns true if the action may go ahead now. Otherwise it
    /// opens the subscription screen (or, if StoreKit hasn't answered yet, checks first) and
    /// runs `then` once Plus is active.
    func unlock(then: @escaping () -> Void) -> Bool {
        switch entitlement {
        case .plus: return true
        case .none where ready:
            afterUnlock = then
            reason = gateReason
            presentPaywall()
        case .none, .unknown:
            // Products or trial eligibility aren't known yet: settle them first, so an eligible
            // account still gets the trial offer rather than the plain subscription screen.
            afterUnlock = then
            Task {
                if products.isEmpty { await loadProducts() }
                await refresh()
                if isPlus { runAfterUnlock() } else if afterUnlock != nil { reason = gateReason; presentPaywall() }
            }
        }
        return false
    }

    /// The first Connect of an account that can still take the trial announces the trial;
    /// after that (or once the trial is used) it is the plain subscription screen.
    private var gateReason: Reason { trialOffered ? .trialOffer : .gated }

    private func runAfterUnlock() {
        let next = afterUnlock
        afterUnlock = nil
        next?()
    }

    /// The subscription screen closed. A purchase hands its pending action off before closing the
    /// sheet, so whatever is still pending here was abandoned.
    func paywallClosed() { afterUnlock = nil; reason = .upgrade }

    /// The Upgrade button.
    func showUpgrade() { reason = .upgrade; showPaywall = true }

    private static let trialOfferKey = "trialOfferShown"

    /// Set while the trial offer is being checked, so the periodic upsell can't take its place.
    private var trialOfferPending = false

    /// Test aid: announce the free trial as the first Connect does. It only counts as shown once
    /// the sheet has actually appeared (`trialOfferAppeared`).
    func offerTrial() {
        guard !UserDefaults.standard.bool(forKey: Self.trialOfferKey), !trialOfferPending else { return }
        trialOfferPending = true
        Task {
            defer { trialOfferPending = false }
            if products.isEmpty { await loadProducts() }
            await refresh()
            guard entitlement == .none, trialOffered, !showPaywall,
                  !UserDefaults.standard.bool(forKey: Self.trialOfferKey) else { return }
            reason = .trialOffer
            presentPaywall()
        }
    }

    /// The trial offer is on screen: don't offer it again, and restart the upsell timer so the
    /// home doesn't offer an upgrade again straight away.
    func trialOfferAppeared() {
        guard reason == .trialOffer else { return }
        UserDefaults.standard.set(true, forKey: Self.trialOfferKey)
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: Self.lastUpsellKey)
    }

    /// Called when a confirmed check finds no Plus, so an open session can be ended.
    var onLapse: (() -> Void)?

    private func presentPaywall() {
        #if os(macOS)
        // Connect can come from the menu bar; the sheet lives on the main window.
        StatusBar.shared?.close()
        MacWindowBridge.showMainWindow()
        #endif
        showPaywall = true
    }

    static let terms = URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!
    static let privacy = URL(string: "https://agentstore.sololeapinc.com/leapvpn/privacy.html")!
    static let manage = URL(string: "https://apps.apple.com/account/subscriptions")!

    /// Starts listening for transactions (renewals, Ask to Buy, purchases on the other device)
    /// and loads products and entitlements. Call once at launch.
    func start() {
        guard !started else { return }
        started = true
        updates = Task { [weak self] in
            for await result in Transaction.updates {
                if case .verified(let t) = result { await t.finish() }
                await self?.refresh()
            }
        }
        Task {
            await loadProducts()
            await refresh()
        }
    }

    func loadProducts() async {
        do {
            let loaded = try await Product.products(for: PlusProduct.ids)
            products = PlusProduct.allCases.compactMap { id in loaded.first { $0.id == id.rawValue } }
        } catch {
            products = []
        }
    }

    /// Recomputes the entitlement from the device's verified transactions.
    /// Refreshes are serialised: a call made while one is running schedules exactly one more,
    /// so an older, slower pass can never overwrite a newer entitlement.
    func refresh() async {
        refreshAgain = true
        if let running = refreshing { await running.value; return }
        let task = Task { @MainActor in
            while refreshAgain {
                refreshAgain = false
                await computeEntitlement()
            }
        }
        refreshing = task
        await task.value
        refreshing = nil
    }

    private func computeEntitlement() async {
        // currentEntitlements already drops expired subscriptions but keeps ones in a billing
        // grace period, so it is trusted as-is apart from revocation.
        var active: Date?? = nil
        for await result in Transaction.currentEntitlements {
            guard case .verified(let t) = result, PlusProduct.ids.contains(t.productID),
                  t.revocationDate == nil else { continue }
            active = .some(t.expirationDate)
        }
        var eligible = trialEligible
        var wasLapsed = false
        var wasTrial = false
        if let product = products.first, let sub = product.subscription {
            eligible = await sub.isEligibleForIntroOffer
            if active == nil, let statuses = try? await sub.status {
                // Billing retry has no access either: a first renewal that failed after the trial
                // still means the trial has ended.
                let ended = statuses.filter { [.expired, .revoked, .inBillingRetryPeriod].contains($0.state) }
                wasLapsed = !ended.isEmpty
                // The status carries the latest transaction of the group: if that was the free
                // trial, the trial ran out without becoming a paid subscription.
                wasTrial = ended.contains { s in
                    guard case .verified(let t) = s.transaction else { return false }
                    return Self.isFreeTrial(t)
                }
            }
        }
        if preview { return }
        trialEligible = eligible
        if let a = active {
            entitlement = .plus(expires: a); lapsed = false; trialEnded = false
        } else {
            entitlement = .none; lapsed = wasLapsed; trialEnded = wasLapsed && wasTrial
        }
        if isPlus, let next = afterUnlock {
            // Bought (here or on the other device) while a gated action waited: close the sheet, carry on.
            afterUnlock = nil
            showPaywall = false
            Task { try? await Task.sleep(for: .milliseconds(500)); next() }
        } else if entitlement == .none {
            onLapse?()
        }
        scheduleRecheck(active ?? nil)
        Self.log.info("plus: \(String(describing: self.entitlement), privacy: .public) trial=\(String(describing: self.trialEligible), privacy: .public) offers=\(self.products.map { "\($0.id):\($0.subscription?.introductoryOffer?.paymentMode.rawValue ?? "none")" }, privacy: .public)")
    }

    static func isFreeTrial(_ t: StoreKit.Transaction) -> Bool {
        if #available(macOS 14.2, iOS 17.2, *) { return t.offer?.paymentMode == .freeTrial }
        return t.offerType == .introductory
    }

    /// An expiry creates no transaction, so look again just after it (or hourly while in grace).
    private func scheduleRecheck(_ expires: Date?) {
        recheck?.cancel()
        guard let expires else { return }
        let wait = max(expires.timeIntervalSinceNow + 5, 3600 * (expires < .now ? 1 : 0) + 5)
        recheck = Task { [weak self] in
            try? await Task.sleep(for: .seconds(min(wait, 7 * 24 * 3600)))
            guard !Task.isCancelled else { return }
            await self?.refresh()
        }
    }

    /// Products can be bought once StoreKit has said whether the trial applies.
    var ready: Bool { !products.isEmpty && trialEligible != nil }

    /// A product carrying a free-trial offer, if the App Store has one for us.
    var trialProduct: Product? {
        products.first { $0.subscription?.introductoryOffer?.paymentMode == .freeTrial }
    }

    /// True only when this account is confirmed eligible and a real free-trial offer exists.
    var trialOffered: Bool { trialEligible == true && trialProduct != nil }

    func product(_ p: PlusProduct) -> Product? { products.first { $0.id == p.rawValue } }

    /// Whether `product` will start with the free trial for this account.
    func offersTrial(_ product: Product) -> Bool {
        trialEligible == true && product.subscription?.introductoryOffer?.paymentMode == .freeTrial
    }

    func purchase(_ product: Product) async {
        guard purchasing == nil, ready else { return }
        purchasing = product.id
        defer { purchasing = nil }
        do {
            let result = try await product.purchase()
            switch result {
            case .success(let v):
                guard case .verified(let t) = v else {
                    message = .init(title: "Purchase not verified", body: "The App Store couldn't verify this purchase. You haven't been given Plus; try again or restore purchases.")
                    return
                }
                await t.finish()
                await refresh()
                if isPlus { showPaywall = false }
            case .pending:
                message = .init(title: "Waiting for approval", body: "The purchase needs approval (for example Ask to Buy). Plus turns on as soon as it's approved.")
            case .userCancelled:
                break
            @unknown default:
                break
            }
        } catch {
            message = .init(title: "Purchase failed", body: error.localizedDescription)
        }
    }

    /// Syncs with the App Store, with a time limit so the button never spins forever.
    func restore() async {
        guard !restoring else { return }
        restoring = true
        defer { restoring = false }
        // Whichever finishes first wins; a late sync result is ignored. Unlike a task group,
        // this doesn't wait for a stuck AppStore.sync() to return.
        let synced = await Self.firstOf(seconds: 30) { (try? await AppStore.sync()) != nil }
        let refreshed = await Self.firstOf(seconds: 15) { await Store.shared.refresh(); return true }
        if !refreshed {
            message = .init(title: "Couldn't reach the App Store", body: "Check your connection and try again.")
        } else if isPlus {
            // Close the sheet first; the root host then shows the alert.
            showPaywall = false
            try? await Task.sleep(for: .milliseconds(600))
            message = .init(title: "Plus restored", body: "Your subscription is active on this device.")
        } else if synced {
            message = .init(title: "Nothing to restore", body: "No active Leap VPN Plus subscription was found for this Apple Account.")
        } else {
            message = .init(title: "Couldn't reach the App Store", body: "Check your connection and try again.")
        }
    }

    private final class Once: @unchecked Sendable {
        private let lock = NSLock()
        private var done = false
        func claim() -> Bool { lock.lock(); defer { lock.unlock() }; if done { return false }; done = true; return true }
    }

    /// Runs `work`, returning false if it hasn't finished within `seconds`.
    private static func firstOf(seconds: Double, _ work: @escaping @Sendable () async -> Bool) async -> Bool {
        await withCheckedContinuation { (c: CheckedContinuation<Bool, Never>) in
            let once = Once()
            Task { let r = await work(); if once.claim() { c.resume(returning: r) } }
            Task { try? await Task.sleep(for: .seconds(seconds)); if once.claim() { c.resume(returning: false) } }
        }
    }

    // MARK: upsell

    private static let lastUpsellKey = "plusUpsellShown"
    private static let upsellEvery: TimeInterval = 3 * 24 * 3600

    /// Offers Plus unprompted at most every few days, never mid-connection, and never to
    /// subscribers.
    func maybeUpsell(idle: Bool) {
        guard idle, entitlement == .none, ready, !showPaywall, !trialOfferPending else { return }
        // An account that can still take the trial hears about it first, at its first Connect.
        guard UserDefaults.standard.bool(forKey: Self.trialOfferKey) || trialEligible == false else { return }
        let last = UserDefaults.standard.double(forKey: Self.lastUpsellKey)
        guard Date().timeIntervalSince1970 - last > Self.upsellEvery else { return }
        UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: Self.lastUpsellKey)
        reason = .upgrade
        showPaywall = true
    }
}

struct StoreMessage: Identifiable {
    let id = UUID()
    let title: String
    let body: String
}

extension Product {
    /// "month" / "year" for the subscription period.
    var periodWord: String {
        guard let p = subscription?.subscriptionPeriod else { return "" }
        switch p.unit {
        case .day: return p.value == 7 ? "week" : "day"
        case .week: return "week"
        case .month: return p.value == 12 ? "year" : "month"
        case .year: return "year"
        @unknown default: return ""
        }
    }

    /// The free trial's length in words, e.g. "2 weeks", read from the offer itself.
    var trialLength: String? {
        guard let o = subscription?.introductoryOffer, o.paymentMode == .freeTrial else { return nil }
        var n = o.period.value * o.periodCount
        var u = o.period.unit
        if u == .day, n % 7 == 0 { n /= 7; u = .week }  // the App Store reports "2 weeks" as 14 days
        let unit: String
        switch u {
        case .day: unit = n == 1 ? "day" : "days"
        case .week: unit = n == 1 ? "week" : "weeks"
        case .month: unit = n == 1 ? "month" : "months"
        case .year: unit = n == 1 ? "year" : "years"
        @unknown default: return nil
        }
        return "\(n) \(unit)"
    }
}
