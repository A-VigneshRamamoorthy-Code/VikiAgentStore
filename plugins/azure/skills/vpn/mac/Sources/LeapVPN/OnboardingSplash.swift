import SwiftUI

/// The first-run story: a few short pages, then the two ways in.
/// Paged and swipeable full-screen on iPhone; a glass card over the atlas on the Mac.
struct OnboardingSplash: View {
    @EnvironmentObject var vpn: VPNController
    @ObservedObject var page: Box<Int>
    @StateObject private var forward = Box(true)

    static let last = SplashPage.allCases.count - 1

    var body: some View {
        #if os(iOS)
        phone
        #else
        mac
        #endif
    }

    private func go(_ i: Int) {
        let i = min(max(i, 0), Self.last)
        guard i != page.v else { return }
        forward.v = i > page.v
        withAnimation(.spring(response: 0.5, dampingFraction: 0.86)) { page.v = i }
    }

    private var isLast: Bool { page.v == Self.last }

    // MARK: bottom bar

    /// Page dots, the primary call to action and a reserved slot for the secondary one.
    /// Its height never changes, so "Next" turns into "Sign in" or "Continue" in exactly the same place.
    private var bottomBar: some View {
        VStack(spacing: Platform.isPhone ? 18 : 14) {
            PageDots(count: Self.last + 1, current: page.v, onSelect: go)
            SplashPrimaryButton(last: isLast) { go(page.v + 1) }
            HomePCButton(visible: isLast)
        }
    }

    // MARK: iPhone

    #if os(iOS)
    private var phone: some View {
        VStack(spacing: 0) {
            HStack {
                if vpn.setup.onboarded, !vpn.working {
                    BrandPill(title: "", icon: "xmark") { vpn.closeOnboarding() }.accessibilityLabel("Close setup")
                }
                Spacer()
                if !isLast { BrandPill(title: "Skip") { go(Self.last) }.transition(.opacity) }
            }
            .frame(height: 44)
            .padding(.horizontal, 20)

            TabView(selection: Binding(get: { page.v }, set: { v in forward.v = v > page.v; page.v = v })) {
                ForEach(SplashPage.allCases) { p in
                    SplashPageView(page: p, active: page.v == p.rawValue, large: true)
                        .padding(.horizontal, 28)
                        .padding(.bottom, 16)
                        .tag(p.rawValue)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            if isLast {
                StartExtras()
                    .padding(.horizontal, 24)
                    .padding(.bottom, 14)
                    .transition(.opacity)
            }

            bottomBar
                .padding(.horizontal, 24)
                .padding(.bottom, 8)
        }
        .animation(.easeInOut(duration: 0.2), value: isLast)
    }
    #endif

    // MARK: Mac

    #if os(macOS)
    private var mac: some View {
        VStack(spacing: 20) {
            ZStack {
                VStack(spacing: 14) {
                    SplashPageView(page: SplashPage(rawValue: page.v) ?? .welcome, active: true, large: false)
                    if isLast { StartExtras() }
                }
                .id(page.v)
                .transition(.asymmetric(
                    insertion: .move(edge: forward.v ? .trailing : .leading).combined(with: .opacity),
                    removal: .move(edge: forward.v ? .leading : .trailing).combined(with: .opacity)))
            }
            .frame(maxWidth: .infinity)
            .frame(height: 300)
            .clipped()
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 30).onEnded { g in
                if g.translation.width < -40 { go(page.v + 1) } else if g.translation.width > 40 { go(page.v - 1) }
            })

            bottomBar
        }
        .padding(.horizontal, 30)
        .padding(.top, 40)
        .padding(.bottom, 24)
        .frame(width: 460)
        .glass(34)
        .overlay(alignment: .topLeading) {
            if page.v > 0 {
                BrandPill(title: "", icon: "chevron.left") { go(page.v - 1) }
                    .padding(14)
                    .accessibilityLabel("Back")
                    .transition(.opacity)
            }
        }
        .overlay(alignment: .topTrailing) {
            if vpn.setup.onboarded, !vpn.working {
                BrandPill(title: "", icon: "xmark") { vpn.closeOnboarding() }
                    .padding(14)
                    .accessibilityLabel("Close setup")
            } else if !isLast {
                BrandPill(title: "Skip") { go(Self.last) }.padding(14)
            }
        }
        .animation(.spring(response: 0.45, dampingFraction: 0.86), value: isLast)
        .focusable()
        .focusEffectDisabled()
        .onKeyPress(.rightArrow) { go(page.v + 1); return .handled }
        .onKeyPress(.leftArrow) { go(page.v - 1); return .handled }
        .onKeyPress(.return) {
            guard !isLast else { return .ignored }
            go(page.v + 1); return .handled
        }
    }
    #endif
}

// MARK: pages

enum SplashPage: Int, CaseIterable, Identifiable {
    case welcome, privacy, pricing, billing, start
    var id: Int { rawValue }

    var title: String {
        switch self {
        case .welcome: return "Leap VPN"
        case .privacy: return "Private by design"
        case .pricing: return "Pay only while connected"
        case .billing: return "Set up Azure billing"
        case .start: return "Ready when you are"
        }
    }

    var line: String {
        switch self {
        case .welcome: return "Your own private VPN."
        case .privacy: return "Your servers, in your own Azure. No logs. No one else's servers."
        case .pricing: return "Servers start when you connect and are removed when you stop."
        case .billing: return "Leap runs on an Azure subscription billed to your personal Microsoft account."
        case .start: return "Sign in to your Azure, or use just a home PC."
        }
    }
}

struct SplashPageView: View {
    let page: SplashPage
    /// The visible page; flips on to replay its symbol effect.
    let active: Bool
    /// iPhone: big type, visual centred in the full screen.
    let large: Bool

    var body: some View {
        // Shrink the visual before anything can spill into the bottom bar; scroll as a last resort.
        ViewThatFits(in: .vertical) {
            content(scale: 1)
            content(scale: 0.72)
            content(scale: 0.5)
            ScrollView(showsIndicators: false) { content(scale: 0.5) }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func content(scale: CGFloat) -> some View {
        VStack(spacing: (large ? 28 : 18) * max(scale, 0.7)) {
            visual(scale)
                .frame(height: (large ? 220 : 136) * scale)
            VStack(spacing: 10) {
                Text(page.title)
                    .font(large ? .system(size: 34, weight: .bold, design: .rounded) : .system(size: 26, weight: .bold, design: .rounded))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Text(page.line)
                    .font(large ? .title3 : .body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: 360)
            }
            if page == .billing { BillingSteps(large: large).padding(.top, 2) }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder private func visual(_ k: CGFloat) -> some View {
        let s: CGFloat = (large ? 168 : 110) * k
        switch page {
        case .welcome: BrandMark(size: (large ? 176 : 120) * k)
        case .privacy: BrandOrb(symbol: "lock.shield.fill", size: s, active: active)
        case .pricing: PricingVisual(size: s, active: active)
        case .billing: BrandOrb(symbol: "creditcard.fill", size: (large ? 140 : 96) * k, active: active)
        case .start: BrandMark(size: (large ? 132 : 100) * k)
        }
    }
}

/// Connect / disconnect on a loop: the orb lights up, then goes dark and costs nothing.
private struct PricingVisual: View {
    let size: CGFloat
    let active: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.periodic(from: .now, by: 2.4)) { ctx in
            let on = reduceMotion || Int(ctx.date.timeIntervalSinceReferenceDate / 2.4) % 2 == 0
            VStack(spacing: 14) {
                BrandOrb(symbol: "power", size: size, active: active, lit: on)
                HStack(spacing: 6) {
                    Circle().fill(on ? Brand.accent : Color.secondary.opacity(0.5)).frame(width: 7, height: 7)
                    Text(on ? "Connected · ≈ $0.01 / hr" : "Off · $0")
                        .font(.caption.weight(.semibold)).monospacedDigit()
                        .contentTransition(.numericText())
                }
                .padding(.horizontal, 12).padding(.vertical, 6)
                .background(Capsule().fill(.primary.opacity(0.06)))
            }
            .animation(.spring(response: 0.5, dampingFraction: 0.8), value: on)
        }
        .accessibilityElement()
        .accessibilityLabel("About a cent an hour while connected, nothing while off")
    }
}

/// The three things to do before signing in, in as few words as possible.
private struct BillingSteps: View {
    let large: Bool
    static let url = URL(string: "https://azure.microsoft.com/free")!

    var body: some View {
        VStack(spacing: 14) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) { steps }
                VStack(spacing: 6) { steps }
            }
            Button { Platform.open(Self.url) } label: {
                HStack(spacing: 4) {
                    Text("azure.microsoft.com/free")
                    Image(systemName: "arrow.up.right").font(.caption.weight(.bold))
                }
                .font(.callout.weight(.semibold))
                .foregroundStyle(Brand.accent)
                .padding(.vertical, 4)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint("Opens Azure sign-up in your browser")
        }
    }

    @ViewBuilder private var steps: some View {
        step(1, "Free account")
        step(2, "Add a card")
        step(3, "Sign in here")
    }

    private func step(_ n: Int, _ text: String) -> some View {
        HStack(spacing: 6) {
            Text("\(n)").font(.caption2.weight(.heavy)).foregroundStyle(.white)
                .frame(width: 18, height: 18).background(Circle().fill(Brand.deep))
            Text(text).font(.caption.weight(.semibold)).lineLimit(1).fixedSize()
        }
        .padding(.leading, 5).padding(.trailing, 10).padding(.vertical, 5)
        .background(Capsule().fill(.primary.opacity(0.06)))
    }
}

// MARK: the two ways in

/// Sign in with Microsoft (primary) or pair a home PC (secondary), plus sign-in progress and errors.
struct OnboardingStartActions: View {
    var body: some View {
        VStack(spacing: 12) {
            SplashPrimaryButton(last: true) {}
            HomePCButton(visible: true, reserve: false)
            StartExtras()
        }
    }
}

/// The splash's one primary button: "Next" on the story pages, then sign in or continue.
struct SplashPrimaryButton: View {
    @EnvironmentObject var vpn: VPNController
    let last: Bool
    let next: () -> Void

    /// One button whose label morphs, so nothing moves when the last page arrives.
    var body: some View {
        BrandButton(title: title, icon: icon, busy: last && vpn.working) {
            if !last { next() } else if vpn.signedIn { vpn.continueSignedIn() } else { vpn.signIn() }
        }
        .disabled(last && vpn.working)
    }

    private var title: String {
        guard last else { return "Next" }
        if vpn.signedIn { return vpn.working ? "Loading…" : "Continue" }
        return vpn.working ? "Waiting for Microsoft…" : "Sign in with Microsoft"
    }

    private var icon: String {
        guard last else { return "arrow.right" }
        return vpn.signedIn ? "arrow.right" : MicrosoftLogo.icon
    }
}

/// Home PCs without Azure: straight to the pairing steps, no sign-in.
/// Keeps its height when hidden so the button above never moves.
struct HomePCButton: View {
    @EnvironmentObject var vpn: VPNController
    var visible: Bool
    var reserve = true

    /// Whether this run of the splash offers the button at all (not when re-running with Azure set up).
    private var offered: Bool { !vpn.setup.onboarded || !vpn.hasAzure }
    private var shown: Bool { visible && offered }

    var body: some View {
        // Reserve its slot only when it will appear, so a re-run has no empty band under the button.
        if shown || (reserve && offered) {
            BrandButton(title: "Add Home PC", icon: "desktopcomputer", kind: .secondary) { vpn.skipSignIn() }
                .disabled(!shown || vpn.working)
                .opacity(shown ? 1 : 0)
                .accessibilityHidden(!shown)
                .animation(.easeInOut(duration: 0.2), value: shown)
        }
    }
}

/// Directory field and sign-in errors: shown above the buttons, never between them.
struct StartExtras: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(spacing: 10) {
            if vpn.askDirectory {
                TextField("Azure directory, e.g. name.onmicrosoft.com", text: $vpn.directory)
                    .textFieldStyle(.roundedBorder).controlSize(.large)
                    .autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.never).keyboardType(.URL)
                    #endif
                    .help("Azure portal › Microsoft Entra ID › Overview › Primary domain")
                    .onSubmit { vpn.signIn() }
            }
            if let e = vpn.setupError {
                Label(e, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption).foregroundStyle(Atlas.red)
                    .multilineTextAlignment(.center)
                    .lineLimit(4)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
