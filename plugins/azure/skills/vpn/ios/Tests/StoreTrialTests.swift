import StoreKit
import StoreKitTest
import XCTest
@testable import LeapVPN

/// Runs the real Store against StoreKit's local test environment (LeapVPN.storekit):
/// the 2-week free trial, its expiry, and a paid period's expiry.
@MainActor
final class StoreTrialTests: XCTestCase {
    private var session: SKTestSession!

    override func setUp() async throws {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "LeapVPN", withExtension: "storekit"))
        session = try SKTestSession(contentsOf: url)
        session.resetToDefaultState()
        session.disableDialogs = true
        session.clearTransactions()
        await Store.shared.loadProducts()
        await Store.shared.refresh()
    }

    /// Leaves the simulator's StoreKit state clean (trial eligible) for the app itself.
    override func tearDown() async throws {
        session.timeRate = .realTime
        session.clearTransactions()
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
}
