import CryptoKit
import StoreKit
import StoreKitTest
import XCTest
@testable import AvenVPN

/// Runs the real Store against StoreKit's local test environment (AvenVPN.storekit):
/// the 2-week free trial, its expiry, and a paid period's expiry.
@MainActor
final class StoreTrialTests: XCTestCase {
    private var session: SKTestSession!

    override func setUp() async throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "AvenVPN", withExtension: "storekit"))
        session = try SKTestSession(contentsOf: url)
        session.resetToDefaultState()
        session.disableDialogs = true
        session.clearTransactions()
        UserDefaults.standard.removeObject(forKey: "launchLockedInSubscriptions")
        await Store.shared.loadProducts()
        await Store.shared.refresh()
        Store.shared.signOffer = Self.localSigner(url)
    }

    /// Signs launch offers like the server does, with the test-only key in AvenVPN.storekit
    /// (StoreKitTest checks signatures against that key, not the App Store one).
    static func localSigner(_ url: URL) -> (String, String) async throws -> OfferSignature {
        { productID, offerID in
            let json = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
            let pair = json["subscriptionOffersKeyPair"] as! [String: String]
            let key = try P256.Signing.PrivateKey(derRepresentation: Data(base64Encoded: pair["privateKey"]!)!)
            let nonce = UUID(), ts = Int(Date().timeIntervalSince1970 * 1000)
            let msg = [Bundle.main.bundleIdentifier!, pair["id"]!, productID, offerID, "",
                       nonce.uuidString.lowercased(), String(ts)].joined(separator: "\u{2063}")
            let sig = try key.signature(for: Data(msg.utf8)).derRepresentation.base64EncodedString()
            return OfferSignature(keyId: pair["id"]!, nonce: nonce, timestamp: ts, signature: sig)
        }
    }

    /// Leaves the simulator's StoreKit state clean (trial eligible) for the app itself.
    override func tearDown() async throws {
        session.timeRate = .realTime
        session.clearTransactions()
        Store.shared.signOffer = OfferSigner.fetch
        await Store.shared.refresh()
    }

    private func buyYearly() async throws -> StoreKit.Transaction {
        let yearly = try XCTUnwrap(Store.shared.product(.yearly))
        let result = try await yearly.purchase()
        guard case .success(let v) = result, case .verified(let t) = v else {
            XCTFail("purchase didn't succeed: \(result)"); throw CancellationError()
        }
        await t.finish()
        return t
    }

    /// StoreKit applies an expiry asynchronously (and slower after an earlier test's session),
    /// so expire, then refresh until the entitlement drops, expiring again now and then.
    private func expireAndWait() async throws {
        for i in 0..<60 {
            if i == 0 { try session.expireSubscription(productIdentifier: PlusProduct.yearly.rawValue) }
            else if i % 10 == 0 { try? session.expireSubscription(productIdentifier: PlusProduct.yearly.rawValue) }
            await Store.shared.refresh()
            if Store.shared.entitlement == .none { return }
            try await Task.sleep(for: .milliseconds(500))
        }
    }

    func testTrialEndsWithoutRenewing() async throws {
        let store = Store.shared
        XCTAssertEqual(store.entitlement, .none)
        XCTAssertTrue(store.trialOffered)
        XCTAssertEqual(store.trialProduct?.trialLength, "2 weeks")

        let t = try await buyYearly()
        XCTAssertTrue(Store.isFreeTrial(t), "first purchase should start the free trial")
        await store.refresh()
        XCTAssertTrue(store.isPlus)
        XCTAssertFalse(store.trialEnded)

        try await expireAndWait()
        XCTAssertEqual(store.entitlement, .none)
        XCTAssertTrue(store.lapsed)
        XCTAssertTrue(store.trialEnded, "Connect should now say the free trial has ended")
        XCTAssertFalse(store.trialOffered, "one trial per subscription group")
    }

    func testPaidPeriodEndingIsNotATrialEnding() async throws {
        let store = Store.shared
        // Let the trial convert into a paid renewal before cancelling.
        session.timeRate = .oneRenewalEveryTwoSeconds
        _ = try await buyYearly()
        var renewed = false
        for _ in 0..<30 where !renewed {
            try await Task.sleep(for: .seconds(1))
            for await r in StoreKit.Transaction.all {
                if case .verified(let t) = r, t.productID == PlusProduct.yearly.rawValue, !Store.isFreeTrial(t) { renewed = true }
            }
        }
        XCTAssertTrue(renewed, "expected a paid renewal")
        session.timeRate = .realTime
        try await expireAndWait()
        XCTAssertEqual(store.entitlement, .none)
        XCTAssertTrue(store.lapsed)
        XCTAssertFalse(store.trialEnded)
    }

    /// Connect is gated without Plus and goes straight through once a purchase completes.
    func testPurchaseLiftsRestrictions() async throws {
        let store = Store.shared
        var ran = false
        XCTAssertFalse(store.unlock { ran = true }, "Connect must be gated before purchase")
        XCTAssertTrue(store.showPaywall)
        store.showPaywall = false; store.paywallClosed()

        _ = try await buyYearly()
        await store.refresh()
        XCTAssertTrue(store.isPlus)
        XCTAssertTrue(store.unlock { ran = true }, "Connect must go through with Plus")
        XCTAssertFalse(ran, "an unlocked action runs directly, not via the callback")
        XCTAssertFalse(store.showPaywall)
    }

    /// Cancelling after a few paid months keeps Plus until the paid period ends, then brings
    /// the gate back and ends a live session.
    func testCancellingAfterPaidMonthsRestoresRestrictions() async throws {
        let store = Store.shared
        session.timeRate = .oneRenewalEveryTwoSeconds
        _ = try await buyYearly()
        var paid = 0
        for _ in 0..<40 where paid < 2 {
            try await Task.sleep(for: .seconds(1))
            paid = 0
            for await r in StoreKit.Transaction.all {
                if case .verified(let t) = r, t.productID == PlusProduct.yearly.rawValue, !Store.isFreeTrial(t) { paid += 1 }
            }
        }
        XCTAssertGreaterThanOrEqual(paid, 2, "expected several paid renewals")

        // Cancel: turn off auto-renew on the current period.
        guard case .verified(let current)? = await StoreKit.Transaction.latest(for: PlusProduct.yearly.rawValue) else {
            return XCTFail("no current transaction")
        }
        try session.disableAutoRenewForTransaction(identifier: UInt(current.id))
        await store.refresh()
        XCTAssertTrue(store.isPlus, "a cancelled subscription keeps Plus until the paid period ends")
        XCTAssertTrue(store.unlock {}, "Connect still works until then")

        var lapsedCalled = false
        store.onLapse = { lapsedCalled = true }
        defer { store.onLapse = nil }
        for _ in 0..<60 where store.isPlus {
            try await Task.sleep(for: .milliseconds(500))
            await store.refresh()
        }
        session.timeRate = .realTime
        XCTAssertEqual(store.entitlement, .none, "the period ended without renewing")
        XCTAssertTrue(lapsedCalled, "an open session must be ended when Plus lapses")
        XCTAssertFalse(store.unlock {}, "Connect must be gated again")
        XCTAssertTrue(store.showPaywall)
        store.showPaywall = false; store.paywallClosed()
    }

    /// A refunded (revoked) subscription loses access immediately.
    func testRefundRestoresRestrictions() async throws {
        let store = Store.shared
        let t = try await buyYearly()
        await store.refresh()
        XCTAssertTrue(store.isPlus)
        try session.refundTransaction(identifier: UInt(t.id))
        for _ in 0..<40 where store.isPlus {
            await store.refresh()
            try await Task.sleep(for: .milliseconds(500))
        }
        XCTAssertEqual(store.entitlement, .none)
        XCTAssertFalse(store.unlock {})
        store.showPaywall = false; store.paywallClosed()
    }

    /// Eligibility comes from the App Store, not the device: wiping the app's local state
    /// (as an uninstall does) does not bring the free trial back.
    func testTrialOnlyOnceEvenAfterReinstall() async throws {
        let store = Store.shared
        let first = try await buyYearly()
        XCTAssertTrue(Store.isFreeTrial(first))
        try await expireAndWait()
        XCTAssertTrue(store.trialEnded)

        // "Reinstall": wipe local state and rebuild the store from StoreKit alone.
        if let id = Bundle.main.bundleIdentifier { UserDefaults.standard.removePersistentDomain(forName: id) }
        let fresh = Store()
        await fresh.loadProducts()
        await fresh.refresh()
        XCTAssertEqual(fresh.entitlement, .none)
        XCTAssertEqual(fresh.trialEligible, false, "eligibility must come from the Apple Account, not the device")
        XCTAssertFalse(fresh.trialOffered)
        XCTAssertFalse(fresh.unlock {})
        XCTAssertNotEqual(fresh.reason, .trialOffer, "Connect must not offer the trial again")
        fresh.showPaywall = false; fresh.paywallClosed()

        // The App Store decides whether a purchase gets the trial from this per-account answer.
        // (StoreKitTest re-delivers the expired transaction on a second purchase here, so the
        // purchase result itself can't show it.)
        let yearly = try XCTUnwrap(fresh.product(.yearly))
        let eligible = await yearly.subscription?.isEligibleForIntroOffer
        XCTAssertEqual(eligible, false, "the Apple Account has used its trial")
    }

    // MARK: launch price

    /// The launch prices come from the App Store with the regular price alongside, and the
    /// percentage is rounded down so it never overstates the saving.
    func testLaunchOfferPricesAndPercent() async throws {
        let store = Store.shared
        let yearly = try XCTUnwrap(store.product(.yearly)), monthly = try XCTUnwrap(store.product(.monthly))
        XCTAssertEqual(yearly.displayPrice, "$79.99")
        XCTAssertEqual(monthly.displayPrice, "$11.99")
        XCTAssertEqual(store.launchOffer(yearly)?.displayPrice, "$9.99")
        XCTAssertEqual(store.launchOffer(monthly)?.displayPrice, "$0.99")
        XCTAssertEqual(store.percentOff(yearly), 87)
        XCTAssertEqual(store.percentOff(monthly), 91)
        XCTAssertEqual(Store.offerTerms(try XCTUnwrap(store.launchOffer(monthly)), monthly), "$0.99/month for 12 months")
        XCTAssertEqual(Store.offerTerms(try XCTUnwrap(store.launchOffer(yearly)), yearly), "$9.99 for the first year")
        XCTAssertNil(store.lockInProduct, "nothing to lock in without a subscription")
    }

    /// A new subscriber starts the trial, then confirms the launch price on the same plan as a
    /// second purchase; a pending Connect waits for both steps.
    /// (The App Store schedules that offer for the first billing event after the trial — "For the
    /// same subscription in an introductory offer, this promotional offer period goes into effect
    /// at the next scheduled billing event" — but StoreKitTest doesn't model scheduled offers, so
    /// the renewal price itself is checked in the sandbox, not here.)
    func testTrialThenLockInLaunchPrice() async throws {
        let store = Store.shared
        var signed: [String] = []
        let original = store.signOffer
        store.signOffer = { p, o in signed.append("\(p)|\(o)"); return try await original(p, o) }
        defer { store.signOffer = original }
        var ran = false
        XCTAssertFalse(store.unlock { ran = true })
        await store.purchase(try XCTUnwrap(store.product(.yearly)))
        XCTAssertNil(store.message, "unexpected message: \(String(describing: store.message))")
        XCTAssertEqual(signed, ["com.sololeap.leapvpn.plus.yearly|launch_yearly"], "trial, then one signed launch-price step")
        XCTAssertTrue(store.isPlus)
        XCTAssertFalse(store.showPaywall)
        try await Task.sleep(for: .seconds(1))
        XCTAssertTrue(ran, "the waiting Connect carries on after both steps")
    }

    /// If the second sheet is skipped, the trial still runs and the home screen offers to lock in.
    func testSkippedLockInStaysAvailable() async throws {
        let store = Store.shared
        _ = try await buyYearly()
        await store.refresh()
        XCTAssertTrue(store.isPlus)
        XCTAssertFalse(store.offerUsed)
        XCTAssertEqual(store.lockInProduct?.id, PlusProduct.yearly.rawValue)
        var signed = 0
        let original = store.signOffer
        store.signOffer = { p, o in signed += 1; return try await original(p, o) }
        defer { store.signOffer = original }
        await store.lockInLaunchPrice()
        XCTAssertNil(store.message, "unexpected message: \(String(describing: store.message))")
        XCTAssertEqual(signed, 1)
        XCTAssertTrue(store.isPlus, "locking in never interrupts the trial")
    }

    /// A returning subscriber whose trial lapsed gets the launch price straight away.
    func testLapsedSubscriberGetsLaunchPriceImmediately() async throws {
        let store = Store.shared
        _ = try await buyYearly()
        try await expireAndWait()
        XCTAssertTrue(store.trialEnded)
        let monthly = try XCTUnwrap(store.product(.monthly))
        XCTAssertNotNil(store.launchOffer(monthly))
        await store.purchase(monthly)
        XCTAssertNil(store.message, "unexpected message: \(String(describing: store.message))")
        XCTAssertTrue(store.isPlus)
        guard case .verified(let t)? = await StoreKit.Transaction.latest(for: monthly.id) else { return XCTFail("no transaction") }
        XCTAssertTrue(Store.isPromotional(t), "charged at the launch price, not the regular price")
        XCTAssertEqual(t.price, Decimal(string: "0.99"))
        XCTAssertTrue(store.offerUsed)
    }

    /// Without a signature there is no silent fallback to the full price.
    func testSigningFailureDoesNotChargeFullPrice() async throws {
        let store = Store.shared
        _ = try await buyYearly()
        try await expireAndWait()
        let original = store.signOffer
        store.signOffer = { _, _ in throw URLError(.notConnectedToInternet) }
        defer { store.signOffer = original }
        await store.purchase(try XCTUnwrap(store.product(.monthly)))
        XCTAssertEqual(store.message?.title, "Couldn't load the launch price")
        XCTAssertFalse(store.isPlus)
        store.message = nil
    }

    /// A new subscriber never starts the trial unless the launch price can be signed first.
    func testSigningFailureDoesNotStartTrial() async throws {
        let store = Store.shared
        let original = store.signOffer
        store.signOffer = { _, _ in throw URLError(.notConnectedToInternet) }
        defer { store.signOffer = original }
        await store.purchase(try XCTUnwrap(store.product(.yearly)))
        XCTAssertEqual(store.message?.title, "Couldn't load the launch price")
        XCTAssertFalse(store.isPlus)
        XCTAssertEqual(store.trialEligible, true, "the trial is still unused")
        store.message = nil
    }
}
