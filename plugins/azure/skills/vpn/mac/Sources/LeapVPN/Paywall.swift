import StoreKit
import SwiftUI

/// Leap VPN Plus: what you get first, then the two plans. Shown from the Upgrade button and,
/// now and then, as a dismissible upsell. Prices and the trial come from the App Store.
struct PaywallView: View {
    @ObservedObject var store = Store.shared
    @Environment(\.dismiss) private var dismiss
    @State private var choice: PlusProduct = .yearly

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                BrandPill(title: "", icon: "xmark") { dismiss() }.accessibilityLabel("Close")
            }
            .padding([.top, .horizontal], 16)

            ScrollView(showsIndicators: false) {
                VStack(spacing: 22) {
                    header
                    ValueList()
                    if store.isPlus { subscribed }
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 12)
            }

            if !store.isPlus { footer.padding(.horizontal, 24).padding(.bottom, 18) }
        }
        #if os(macOS)
        .frame(width: 460, height: 700)
        #endif
        .background(Atlas.background)
        .task { if store.products.isEmpty { await store.loadProducts() }; await store.refresh() }
        .alert(item: Binding(get: { store.showPaywall ? store.message : nil }, set: { store.message = $0 })) { m in
            Alert(title: Text(m.title), message: Text(m.body))
        }
    }

    private var header: some View {
        VStack(spacing: 10) {
            BrandMark(size: 76)
            Text("Leap VPN Plus")
                .font(.system(size: 30, weight: .bold, design: .rounded))
            Text(store.isPlus ? "Thanks for supporting Leap VPN." :
                    store.lapsed ? "Your free trial has ended. Everything still works — Plus keeps Leap VPN going."
                                 : "Your own VPN, on servers only you control.")
                .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: plans

    @ViewBuilder private var plans: some View {
        if store.products.isEmpty {
            VStack(spacing: 8) {
                ProgressView()
                Text("Loading plans from the App Store…").font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 120)
        } else {
            VStack(spacing: 10) {
                ForEach(PlusProduct.allCases, id: \.self) { p in
                    if let product = store.product(p) {
                        PlanRow(product: product, selected: choice == p, badge: p == .yearly ? savings : nil,
                                trial: store.offersTrial(product)) { choice = p }
                    }
                }
            }
        }
    }

    /// "Save 16%" for the yearly plan, from the two real prices.
    private var savings: String? {
        guard let y = store.product(.yearly), let m = store.product(.monthly), m.price > 0 else { return nil }
        let pct = (1 - NSDecimalNumber(decimal: y.price / (m.price * 12)).doubleValue) * 100
        return pct >= 5 ? "Save \(Int(pct.rounded(.down)))%" : nil
    }

    private var selectedProduct: Product? { store.product(choice) }

    private var footer: some View {
        VStack(spacing: 10) {
            plans.padding(.bottom, 4)
            BrandButton(title: ctaTitle, icon: nil, busy: store.purchasing != nil) {
                guard let p = selectedProduct else { return }
                Task { await store.purchase(p) }
            }
            .disabled(selectedProduct == nil || store.purchasing != nil || !store.ready)

            if let p = selectedProduct {
                Text(disclosure(p))
                    .font(.caption2).foregroundStyle(.secondary)
                    .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }

            HStack(spacing: 18) {
                Button(store.restoring ? "Restoring…" : "Restore Purchases") { Task { await store.restore() } }
                    .disabled(store.restoring)
                Link("Terms of Use", destination: Store.terms)
                Link("Privacy Policy", destination: Store.privacy)
            }
            .font(.caption.weight(.semibold))
            .buttonStyle(.plain)
            .foregroundStyle(Brand.accent)
        }
    }

    private var ctaTitle: String {
        guard let p = selectedProduct else { return "Continue" }
        if store.offersTrial(p), let len = p.trialLength { return "Start \(len) free" }
        return "Subscribe for \(p.displayPrice)/\(p.periodWord)"
    }

    private func disclosure(_ p: Product) -> String {
        let trial = store.offersTrial(p) ? (p.trialLength.map { "Free for \($0), then " } ?? "") : ""
        return "\(trial)\(p.displayPrice) per \(p.periodWord). Payment is charged to your Apple Account"
            + (trial.isEmpty ? " at confirmation of purchase" : " when the free trial ends")
            + ". The subscription renews automatically unless cancelled at least 24 hours before the end of the current period. "
            + "Manage or cancel any time in your App Store account settings. One subscription covers Leap VPN on iPhone and Mac."
    }

    // MARK: subscribed

    private var subscribed: some View {
        VStack(spacing: 12) {
            Label("Plus is active", systemImage: "checkmark.seal.fill")
                .font(.headline).foregroundStyle(Brand.accent)
            if case .plus(let e?) = store.entitlement {
                Text("Renews or ends on \(e.formatted(date: .long, time: .omitted))")
                    .font(.caption).foregroundStyle(.secondary)
            }
            BrandButton(title: "Manage Subscription", icon: "gearshape", kind: .secondary) { manage() }
        }
        .padding(.top, 6)
    }

    private func manage() {
        #if os(iOS)
        if let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene {
            Task { try? await AppStore.showManageSubscriptions(in: scene) }
            return
        }
        #endif
        Platform.open(Store.manage)
    }
}

/// The value proposition, all of it true of the app as built.
struct ValueList: View {
    static let points: [(String, String, String)] = [
        ("server.rack", "Servers you own", "Leap sets them up in your own Azure account. We run no servers and never see your traffic."),
        ("hand.raised.fill", "Ads and trackers blocked", "Filtered on your own server, in browsers and apps."),
        ("globe", "\(RegionChoice.all.count) locations", "Connect through any Azure region worldwide, or a PC at home."),
        ("speedometer", "No bandwidth caps from us", "Speed is your server's; Azure bills its data use to you."),
        ("laptopcomputer.and.iphone", "iPhone and Mac", "One subscription covers both."),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(Self.points, id: \.1) { icon, title, line in
                HStack(alignment: .top, spacing: 14) {
                    Image(systemName: icon)
                        .font(.system(size: 17, weight: .semibold)).foregroundStyle(Brand.accent)
                        .frame(width: 36, height: 36)
                        .background(Circle().fill(Brand.accent.opacity(0.14)))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).font(.subheadline.weight(.semibold))
                        Text(line).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct PlanRow: View {
    let product: Product
    let selected: Bool
    let badge: String?
    let trial: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .font(.title3).foregroundStyle(selected ? Brand.accent : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(product.periodWord == "year" ? "Yearly" : "Monthly").font(.headline)
                        if let badge {
                            Text(badge).font(.caption2.weight(.bold)).foregroundStyle(Brand.ink)
                                .padding(.horizontal, 7).padding(.vertical, 2)
                                .background(Capsule().fill(Brand.mint))
                        }
                    }
                    if trial, let len = product.trialLength {
                        Text("\(len) free, then \(product.displayPrice)/\(product.periodWord)")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Text("\(product.displayPrice)/\(product.periodWord)").font(.subheadline.weight(.semibold)).monospacedDigit()
            }
            .padding(14)
            .contentShape(RoundedRectangle(cornerRadius: 18))
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.primary.opacity(selected ? 0.07 : 0.035)))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(selected ? Brand.accent : Color.primary.opacity(0.1), lineWidth: selected ? 2 : 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// Top-left, always there for non-subscribers: opens the Plus screen.
struct UpgradeButton: View {
    @ObservedObject var store = Store.shared

    var body: some View {
        if store.entitlement == .none {
            Button { store.showPaywall = true } label: {
                Label("Upgrade", systemImage: "sparkles")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(Brand.ink)
                    .padding(.horizontal, 14).frame(height: 42)
                    .background(Capsule().fill(Brand.accentGradient))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .help("Leap VPN Plus")
            .transition(.opacity.combined(with: .scale(scale: 0.9)))
        }
    }
}

/// Hosts the Plus screen once, at the root, so the Upgrade button, the upsell and test hooks
/// all open the same sheet.
struct PlusSheetHost: ViewModifier {
    @ObservedObject var store = Store.shared
    @Environment(\.scenePhase) private var phase

    func body(content: Content) -> some View {
        content
        // Store results that arrive after the sheet has closed (e.g. it was dismissed mid-restore).
        .alert(item: Binding(get: { store.showPaywall ? nil : store.message }, set: { store.message = $0 })) { m in
            Alert(title: Text(m.title), message: Text(m.body))
        }
        // A subscription can lapse while the app sits in the background.
        .onChange(of: phase) { _, now in if now == .active { Task { await store.refresh() } } }
        .sheet(isPresented: $store.showPaywall) {
            PaywallView()
                #if os(iOS)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
                #endif
        }
    }
}

/// Offers Plus now and then from the home, only while nothing else is going on.
struct PlusUpsell: ViewModifier {
    @ObservedObject var store = Store.shared
    let idle: Bool

    func body(content: Content) -> some View {
        content
            .onChange(of: store.entitlement) { _, _ in store.maybeUpsell(idle: idle) }
            .onChange(of: idle) { _, now in store.maybeUpsell(idle: now) }
    }
}

extension View {
    func plusUpsell(idle: Bool) -> some View { modifier(PlusUpsell(idle: idle)) }
    func plusSheetHost() -> some View { modifier(PlusSheetHost()) }
}
