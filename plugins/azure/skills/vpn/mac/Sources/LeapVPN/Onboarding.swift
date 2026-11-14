import SwiftUI

struct RootView: View {
    @EnvironmentObject var vpn: VPNController
    #if os(macOS)
    @Environment(\.openWindow) private var openWindow
    #endif

    var body: some View {
        Group {
            if vpn.step == .done {
                #if os(iOS)
                PhoneHome()
                #else
                AtlasHome()
                #endif
            } else { OnboardingView() }
        }
        .background(Atlas.background)
        #if os(macOS)
        .onAppear { MacWindowBridge.registerMainWindowOpener { openWindow(id: MacWindowID.main) } }
        #endif
    }
}

// MARK: onboarding

struct OnboardingView: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var picked = Box<Set<String>>(["in"])
    @StateObject private var page = Box(0)

    /// The splash pages cover the first-run story and sign-in; later steps are cards over the map.
    private var splash: Bool { vpn.step == .welcome || vpn.step == .signIn }

    var body: some View {
        ZStack(alignment: .bottom) {
            AtlasMap(pins: pins, selected: nil, home: vpn.home, tone: vpn.step == .building ? .connecting : .exposed) { id in
                guard vpn.step == .locations else { return }
                if picked.v.contains(id) { picked.v.remove(id) } else { picked.v.insert(id) }
            }
            .opacity(vpn.step == .locations || vpn.step == .building ? 1 : splash ? (Platform.isPhone ? 0.25 : 0.4) : 0.55)
            .ignoresSafeArea()

            if splash {
                #if os(iOS)
                LinearGradient(colors: [Atlas.background.opacity(0.2), Atlas.background.opacity(0.9)], startPoint: .top, endPoint: .bottom)
                    .ignoresSafeArea()
                OnboardingSplash(page: page)
                    .transition(.opacity)
                #else
                OnboardingSplash(page: page)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .transition(.scale(scale: 0.96).combined(with: .opacity))
                #endif
            } else {
                card.padding(20).frame(maxWidth: vpn.step == .directPC ? 500 : 440)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.5, dampingFraction: 0.86), value: splash)
        .onChange(of: vpn.step) { _, step in
            if step == .locations, !vpn.regions.isEmpty { picked.v = Set(vpn.regions.map(\.code)) }
            // A cancelled or failed sign-in, or Back from home-PC pairing, lands on the sign-in page.
            if step == .signIn { page.v = OnboardingSplash.last }
        }
        .onChange(of: vpn.working) { _, working in
            if working, splash { withAnimation { page.v = OnboardingSplash.last } }
        }
        .onAppear {
            if vpn.step == .locations, !vpn.regions.isEmpty { picked.v = Set(vpn.regions.map(\.code)) }
            if vpn.step == .signIn || vpn.working { page.v = OnboardingSplash.last }
            // Test aid: `-LeapOnboardPage n` opens the splash on page n.
            if let n = UserDefaults.standard.object(forKey: "LeapOnboardPage") as? Int ?? Int(UserDefaults.standard.string(forKey: "LeapOnboardPage") ?? "") {
                page.v = min(max(n, 0), OnboardingSplash.last)
            }
        }
        .task { if vpn.home == nil, let e = await Egress.lookup() { vpn.home = GeoPoint(e.loc) } }
    }

    private var pins: [MapPin] {
        switch vpn.step {
        case .locations, .building:
            return RegionChoice.all.map { c in
                let on = picked.v.contains(c.code) || vpn.regions.contains { $0.code == c.code }
                return MapPin(id: c.code, title: "\(c.flag) \(c.name)", point: c.point,
                              kind: on ? .azure : .available, asleep: !on)
            }
        default: return []
        }
    }

    @ViewBuilder private var card: some View {
        VStack(alignment: .leading, spacing: 16) {
            switch vpn.step {
            case .welcome, .signIn: OnboardingStartActions()
            case .subscription: subscriptions
            case .locations: locations
            case .building: building
            case .homePCs, .done: homePCs
            case .directPC: DirectPairView(onboarding: true)
            }
            if let e = vpn.setupError, vpn.step != .welcome, vpn.step != .signIn {
                Label(e, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(22)
        .glass()
        .overlay(alignment: .topTrailing) {
            if vpn.setup.onboarded, vpn.step != .building, !vpn.working {
                BrandPill(title: "", icon: "xmark") { vpn.closeOnboarding() }
                    .padding(12)
                    .accessibilityLabel("Close setup")
            }
        }
    }

    private var subscriptions: some View {
        VStack(alignment: .leading, spacing: 12) {
            OnboardingHeader(symbol: "key.fill", title: "Choose a subscription", line: "The one Leap's servers are billed to.")
            ForEach(vpn.subscriptions) { s in
                Button { Task { await vpn.choose(s) } } label: {
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(s.name).font(.callout.weight(.semibold))
                            Text(s.id).font(.caption2.monospaced()).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption.weight(.bold)).foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 11).contentShape(Rectangle())
                    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(.primary.opacity(0.05)))
                }
                .buttonStyle(.plain).disabled(vpn.working)
            }
        }
    }

    private var locations: some View {
        VStack(alignment: .leading, spacing: 14) {
            OnboardingHeader(symbol: "mappin.and.ellipse", title: "Pick your locations", line: "Tap the map to add or remove.")
            FlowChips(items: RegionChoice.all.filter { picked.v.contains($0.code) }.map { "\($0.flag) \($0.name)" })
            HStack(spacing: 8) {
                Chip(icon: "moon.zzz", text: vpn.ephemeral ? "$0 while off" : "≈ $\(picked.v.count * 3) / mo while off", tint: Brand.accent)
                Chip(icon: "timer", text: vpn.ephemeral ? "~2 min to connect" : "~40 s to connect", tint: Brand.accent)
            }
            let new = picked.v.subtracting(vpn.regions.map(\.code)).count
            BrandButton(title: new == 0 ? "Continue" : "Add \(new) location\(new == 1 ? "" : "s")",
                        icon: new == 0 ? "arrow.right" : "bolt.fill") {
                vpn.build(RegionChoice.all.filter { picked.v.contains($0.code) })
            }
            .disabled(picked.v.isEmpty || vpn.working)
            .opacity(picked.v.isEmpty ? 0.5 : 1)
            BrandButton(title: "Home PCs only", icon: "house.fill", kind: .secondary) {
                vpn.build([nearestRelay()], relayOnly: true)
            }
            .disabled(vpn.working)
            .help("Adds one small relay so you can reach your home PCs from anywhere")
        }
    }

    private func nearestRelay() -> RegionChoice {
        guard let h = vpn.home else { return RegionChoice.all[0] }
        return RegionChoice.all.min { Countries.distance($0.point, h) < Countries.distance($1.point, h) } ?? RegionChoice.all[0]
    }

    private var building: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                ZStack {
                    if vpn.working { BrandMark(size: 48, tile: true) }
                    else { BrandOrb(symbol: "exclamationmark.triangle.fill", size: 48, lit: false) }
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(vpn.working ? "Setting up…" : "Setup stopped").font(.title3.weight(.bold))
                    Text(vpn.setupLog.last ?? "Checking your subscription")
                        .font(.caption).foregroundStyle(.secondary).lineLimit(2)
                        .contentTransition(.opacity)
                        .animation(.easeInOut, value: vpn.setupLog.count)
                }
            }
            if vpn.working {
                ProgressView().progressViewStyle(.linear).tint(Brand.mint)
            }
            Text("Nothing keeps running once it's done.").font(.caption2).foregroundStyle(.tertiary)
            if !vpn.working {
                BrandButton(title: "Try again", icon: "arrow.clockwise") { vpn.step = .locations }
            }
        }
    }

    private var homePCs: some View {
        VStack(alignment: .leading, spacing: 14) {
            OnboardingHeader(symbol: "house.fill", title: "Add a home PC?", line: "Exit through a Windows PC at home. Optional.")
            if !vpn.pendingExits.isEmpty || !vpn.exits.isEmpty {
                Chip(icon: "desktopcomputer", text: "\(vpn.exits.count) added · \(vpn.pendingExits.count) waiting", tint: Brand.accent)
            }
            HStack(spacing: 10) {
                BrandButton(title: "Add PC", icon: "plus", kind: .secondary) { vpn.requestedSheet = .addPC; vpn.finishOnboarding() }
                BrandButton(title: "Done", icon: "checkmark") { vpn.finishOnboarding() }
            }
        }
    }
}

/// Small orb + one headline + at most one short line: the header of every setup card.
struct OnboardingHeader: View {
    let symbol: String
    let title: String
    var line: String? = nil

    var body: some View {
        HStack(spacing: 14) {
            BrandOrb(symbol: symbol, size: 46)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.title3.weight(.bold))
                if let line { Text(line).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
            }
            Spacer(minLength: 24)
        }
    }
}

struct FlowChips: View {
    let items: [String]
    var body: some View {
        HStack(spacing: 6) {
            ForEach(items, id: \.self) { t in
                Text(t).font(.caption).padding(.horizontal, 10).padding(.vertical, 5)
                    .background(Capsule().fill(Brand.mint.opacity(0.18)))
            }
            if items.isEmpty { Text("None yet").font(.caption).foregroundStyle(.tertiary) }
        }
    }
}

struct Chip: View {
    let icon: String
    let text: String
    var tint: Color = .secondary
    /// Fixed width, so chips in a column line up.
    var width: CGFloat? = nil

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: icon).font(.system(size: 10, weight: .semibold)).foregroundStyle(tint)
            Text(text).font(.caption.weight(.medium)).monospacedDigit().lineLimit(1)
        }
        .padding(.horizontal, 10).padding(.vertical, 5)
        .frame(width: width)
        .background(Capsule().fill(.primary.opacity(0.06)))
        .overlay(Capsule().strokeBorder(.primary.opacity(0.08), lineWidth: 0.5))
    }
}

/// Pair a Windows PC directly with this Mac: one command on the PC, one link back.
struct DirectPairView: View {
    @EnvironmentObject var vpn: VPNController
    var onboarding = false
    var note = true
    var onPaired: () -> Void = {}
    @StateObject private var name = Box("Home PC")
    @StateObject private var link = Box("")
    @StateObject private var copied = Box(false)
    @StateObject private var bad = Box(false)

    var body: some View {
        GlassGroup(spacing: 16) {
        VStack(alignment: .leading, spacing: 16) {
            if onboarding {
                OnboardingHeader(symbol: "desktopcomputer", title: "Use your home PC", line: "Three steps. No Microsoft account needed.")
            }
            StepRow(n: 1, title: "Copy the setup command") {
                HStack(spacing: 8) {
                    TextField("PC name", text: $name.v).textFieldStyle(.roundedBorder).frame(width: 140)
                    Button {
                        Platform.copy(vpn.directCommand(name: name.v))
                        copied.v = true
                    } label: {
                        Label(copied.v ? "Copied" : "Copy", systemImage: copied.v ? "checkmark" : "doc.on.doc")
                    }
                    .modifier(ProminentStyle())
                }
            }
            StepRow(n: 2, title: "Run it on the PC") {
                Text("**Win+X › Terminal**, paste, Enter. Approve the one prompt.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            StepRow(n: 3, title: "Paste the link it shows") {
                HStack(spacing: 8) {
                    TextField("leapvpn://pair…", text: $link.v).textFieldStyle(.roundedBorder)
                        .onSubmit(add)
                    Button("Add", action: add).disabled(link.v.isEmpty)
                }
                if bad.v { Text("That link isn't valid.").font(.caption).foregroundStyle(Atlas.red) }
            }
            if note || onboarding {
                Label("Needs UDP 51820 open on your router — the script tries UPnP.", systemImage: "info.circle")
                    .font(.caption2).foregroundStyle(.tertiary).padding(.horizontal, 4)
            }
            if onboarding {
                HStack {
                    BrandPill(title: "Back", icon: "chevron.left") { vpn.step = .welcome }
                    Spacer()
                    if !vpn.setup.direct.isEmpty {
                        BrandButton(title: "Done", icon: "checkmark") { vpn.finishOnboarding() }.frame(width: 140)
                    }
                }
            }
        }
        }
    }

    private func add() {
        bad.v = !vpn.pair(link: link.v)
        guard !bad.v else { return }
        link.v = ""
        if onboarding { vpn.finishOnboarding() }
        onPaired()
    }
}

struct StepRow<Content: View>: View {
    let n: Int
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Text("\(n)").font(.callout.weight(.heavy)).foregroundStyle(Brand.ink)
                .frame(width: 28, height: 28).background(Circle().fill(Brand.mint.gradient))
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.callout.weight(.semibold)).padding(.top, 4)
                content
            }
            Spacer(minLength: 0)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glass(18)
    }
}
