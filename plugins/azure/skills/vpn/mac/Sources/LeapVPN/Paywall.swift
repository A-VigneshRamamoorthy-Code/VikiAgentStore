import StoreKit
import SwiftUI

/// Leap VPN Plus: a short pitch up top, the plans and the subscribe button pinned at the bottom.
/// Opens from the Upgrade button, from Connect when there's no subscription, and now and then
/// as an upsell. Prices and the trial come from the App Store.
struct PaywallView: View {
    @ObservedObject var store = Store.shared
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var scheme
    @State private var choice: PlusProduct = .yearly

    var body: some View {
        VStack(spacing: 0) {
            ScrollView(showsIndicators: false) {
                VStack(spacing: Platform.isPhone ? 22 : 16) {
                    header
                    if store.isPlus { subscribed } else { BenefitList() }
                }
                .padding(.horizontal, 26)
                .padding(.top, Platform.isPhone ? 44 : 22)
                .padding(.bottom, 20)
            }
            // Content that runs under the plans fades out instead of looking cut off.
            .mask(VStack(spacing: 0) {
                Color.black
                LinearGradient(colors: [.black, .clear], startPoint: .top, endPoint: .bottom).frame(height: 18)
            })
            if !store.isPlus { footer }
        }
        .overlay(alignment: .topTrailing) {
            BrandPill(title: "", icon: "xmark") { dismiss() }
                .accessibilityLabel("Close")
                .padding(16)
        }
        #if os(macOS)
        .frame(width: 460, height: 600)  // fits inside the 640pt main window
        #endif
        .background(PaywallBackground())
        .onAppear { store.trialOfferAppeared() }
        .task { if store.products.isEmpty { await store.loadProducts() }; await store.refresh() }
        .alert(item: Binding(get: { store.showPaywall ? store.message : nil }, set: { store.message = $0 })) { m in
            Alert(title: Text(m.title), message: Text(m.body))
        }
    }

    private var header: some View {
        VStack(spacing: Platform.isPhone ? 12 : 9) {
            BrandMark(size: Platform.isPhone ? 84 : 48)
                .shadow(color: Brand.accent.opacity(0.45), radius: 26, y: 6)
            Text("LEAP VPN PLUS")
                .font(.system(size: 12, weight: .bold, design: .monospaced)).tracking(3)
                .foregroundStyle(Brand.accent)
            Text(headline)
                .font(.system(size: Platform.isPhone ? 34 : 27, weight: .heavy, design: .rounded))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Text(subline)
                .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var headline: String {
        if store.isPlus { return "You're all set" }
        if store.trialEnded { return Platform.isPhone ? "Your free trial\nhas ended" : "Your free trial has ended" }
        if store.lapsed { return "Keep your VPN on" }
        if store.reason == .trialOffer, store.trialOffered, let len = store.trialProduct?.trialLength {
            return "\(len.prefix(1).uppercased() + len.dropFirst()) free,\non us"
        }
        return Platform.isPhone ? "Your network.\nYour rules." : "Your network. Your rules."
    }

    private var subline: String {
        if store.isPlus { return "Thanks for supporting Leap VPN." }
        if store.trialEnded { return "Subscribe to reconnect. Your setup is saved." }
        if store.lapsed { return "Your subscription has ended. Subscribe to connect again." }
        if store.reason == .trialOffer, store.trialOffered { return "Everything included. Cancel any time." }
        if store.waitingToConnect, store.trialOffered { return "Start your free trial to connect." }
        return "A private VPN on servers only you own."
    }

    // MARK: plans

    @ViewBuilder private var plans: some View {
        if store.products.isEmpty {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Loading plans…").font(.caption).foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 76)
        } else {
            HStack(spacing: 10) {
                ForEach(PlusProduct.allCases, id: \.self) { p in
                    if let product = store.product(p) {
                        PlanCard(product: product, selected: choice == p, badge: p == .yearly ? savings : nil) {
                            withAnimation(.snappy(duration: 0.2)) { choice = p }
                        }
                    }
                }
            }
        }
    }

    /// "Save 16%" for the yearly plan, from the two real prices.
    private var savings: String? {
        guard let y = store.product(.yearly), let m = store.product(.monthly), m.price > 0 else { return nil }
        let pct = (1 - NSDecimalNumber(decimal: y.price / (m.price * 12)).doubleValue) * 100
        return pct >= 5 ? "SAVE \(Int(pct.rounded(.down)))%" : nil
    }

    private var selectedProduct: Product? { store.product(choice) }

    private var footer: some View {
        VStack(spacing: Platform.isPhone ? 12 : 10) {
            plans
            BrandButton(title: ctaTitle, icon: nil, kind: .upgrade, busy: store.purchasing != nil) {
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
                if store.reason == .trialOffer { Button("Not now") { dismiss() } }
                Button(store.restoring ? "Restoring…" : "Restore") { Task { await store.restore() } }
                    .disabled(store.restoring)
                Link("Terms", destination: Store.terms)
                Link("Privacy", destination: Store.privacy)
            }
            .font(.caption.weight(.semibold))
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 22)
        .padding(.top, 14)
        .padding(.bottom, Platform.isPhone ? 8 : 14)
    }

    private var ctaTitle: String {
        guard let p = selectedProduct else { return "Continue" }
        if store.offersTrial(p), let len = p.trialLength { return "Try \(len) free" }
        return "Subscribe"
    }

    /// Apple's required terms, kept to two short lines.
    private func disclosure(_ p: Product) -> String {
        let price = "\(p.displayPrice)/\(p.periodWord)"
        let lead = store.offersTrial(p) ? (p.trialLength.map { "\($0) free, then \(price)" } ?? price) : price
        return "\(lead). Renews automatically until cancelled at least 24 hours before the period ends; "
            + "manage it in your Apple Account. One subscription covers iPhone and Mac."
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

/// The sheet's own backdrop: the plain window colour with a mint glow behind the mark — no grey.
private struct PaywallBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        ZStack(alignment: .top) {
            (scheme == .dark ? Color.black : Color.white)
            RadialGradient(colors: [Brand.accent.opacity(scheme == .dark ? 0.32 : 0.22), .clear],
                           center: .top, startRadius: 0, endRadius: 360)
                .frame(height: 460)
        }
        .ignoresSafeArea()
    }
}

/// The value proposition: four one-liners, all true of the app as built.
struct BenefitList: View {
    static let points: [(String, String)] = [
        ("lock.shield.fill", "Servers only you own and control"),
        ("hand.raised.fill", "Ads and trackers blocked"),
        ("globe", "\(RegionChoice.all.count) locations, no data caps"),
        ("laptopcomputer.and.iphone", "iPhone and Mac, one subscription"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: Platform.isPhone ? 14 : 8) {
            ForEach(Self.points, id: \.1) { icon, title in
                HStack(spacing: 14) {
                    Image(systemName: icon)
                        .font(.system(size: Platform.isPhone ? 15 : 13, weight: .bold)).foregroundStyle(.white)
                        .frame(width: Platform.isPhone ? 32 : 28, height: Platform.isPhone ? 32 : 28)
                        .background(Circle().fill(LinearGradient(colors: [Color(red: 0.0, green: 0.62, blue: 0.42), Brand.deep],
                                                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
                    Text(title).font(.body.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .frame(maxWidth: 360, alignment: .leading)
    }
}

private struct PlanCard: View {
    let product: Product
    let selected: Bool
    let badge: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(product.periodWord == "year" ? "Yearly" : "Monthly").font(.subheadline.weight(.semibold))
                    Spacer(minLength: 4)
                    Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(selected ? Brand.accent : .secondary)
                }
                Text(product.displayPrice).font(.title2.weight(.bold)).monospacedDigit()
                Text(perLine).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(RoundedRectangle(cornerRadius: 18))
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous)
                .fill(selected ? Brand.accent.opacity(0.12) : Color.primary.opacity(0.04)))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(selected ? Brand.accent : Color.primary.opacity(0.12), lineWidth: selected ? 2 : 1))
            .overlay(alignment: .topTrailing) {
                if let badge {
                    Text(badge).font(.system(size: 10, weight: .heavy)).foregroundStyle(Brand.ink)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Capsule().fill(Brand.mint))
                        .offset(x: -10, y: -10)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    private var perLine: String {
        if product.periodWord == "year" {
            let monthly = product.price / 12
            return "\(monthly.formatted(product.priceFormatStyle))/month"
        }
        return "per month"
    }
}

/// Top-left, always there for non-subscribers: opens the Plus screen.
struct UpgradeButton: View {
    @ObservedObject var store = Store.shared

    var body: some View {
        if store.entitlement == .none {
            Button { store.showUpgrade() } label: {
                Label("Upgrade", systemImage: "sparkles")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14).frame(height: 42)
                    .background(Capsule().fill(Brand.deepUpgrade)
                        .overlay(Capsule().strokeBorder(Color.white.opacity(0.25), lineWidth: 0.75)))
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
        .sheet(isPresented: $store.showPaywall, onDismiss: { store.paywallClosed() }) {
            PaywallView()
                #if os(iOS)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
                .presentationBackground(.clear)
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
