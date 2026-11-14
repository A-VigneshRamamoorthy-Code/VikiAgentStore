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
            AtlasMap(pins: pins, selected: vpn.step == .building ? settingUp.first?.code : nil, home: vpn.home, tone: vpn.step == .building ? .connecting : .exposed) { id in
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
                #if os(iOS)
                card.ignoresSafeArea(.container, edges: .bottom)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                #else
                card.padding(20).frame(maxWidth: vpn.step == .directPC ? 500 : 440)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                #endif
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

    /// The locations this setup run is building, in display order.
    private var chosen: [RegionChoice] { RegionChoice.all.filter { picked.v.contains($0.code) } }
    private func exists(_ c: RegionChoice) -> Bool { vpn.regions.contains { $0.code == c.code } }
    /// Ready only once this run has finished with it, not merely because it was built before.
    private func isReady(_ c: RegionChoice) -> Bool { vpn.working ? vpn.setupDone.contains(c.code) : exists(c) }
    /// Chosen locations still being set up; the first is highlighted on the map.
    private var settingUp: [RegionChoice] { chosen.filter { !isReady($0) } }

    private var pins: [MapPin] {
        switch vpn.step {
        case .locations, .building:
            return RegionChoice.all.map { c in
                let on = picked.v.contains(c.code) || vpn.regions.contains { $0.code == c.code }
                return MapPin(id: c.code, title: c.name, point: c.point,
                              kind: on ? .azure : .available, asleep: !on, countryCode: c.country)
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
        #if os(iOS)
        .phoneDock()
        #else
        .padding(22)
        .glass()
        #endif
        .overlay(alignment: .topTrailing) {
            if vpn.setup.onboarded, vpn.step != .building, !vpn.working {
                BrandPill(title: "", icon: "xmark") { vpn.closeOnboarding() }
                    .padding(Platform.isPhone ? 24 : 12)
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
            FlowLayout(spacing: 6) {
                ForEach(chosen) { c in
                    LocationChip(choice: c) { picked.v.remove(c.code) }
                }
                if chosen.isEmpty { Text("None yet").font(.caption).foregroundStyle(.tertiary).padding(.vertical, 6) }
            }
            HStack(spacing: 8) {
                Chip(icon: "moon.zzz", text: vpn.ephemeral ? "$0 while off" : "≈ $\(picked.v.count * 3) / mo while off", tint: Brand.accent)
                Chip(icon: "timer", text: vpn.ephemeral ? "~2 min to connect" : "~40 s to connect", tint: Brand.accent)
            }
            let new = picked.v.subtracting(vpn.regions.map(\.code)).count
            GlassGroup(spacing: 10) {
                VStack(spacing: 10) {
                    BrandButton(title: new == 0 ? "Continue" : "Add \(new) location\(new == 1 ? "" : "s")",
                                icon: new == 0 ? "arrow.right" : "bolt.fill") {
                        vpn.build(chosen)
                    }
                    .disabled(picked.v.isEmpty || vpn.working)
                    BrandButton(title: "Add Home PC", icon: "desktopcomputer", kind: .secondary) { vpn.skipSignIn() }
                        .disabled(vpn.working)
                        .help("Pair a Windows PC at home directly. No server needed.")
                }
            }
        }
    }

    private var building: some View {
        let ready = chosen.filter(isReady).count
        return VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 14) {
                if vpn.working { BrandMark(size: 46, tile: true) }
                else { BrandOrb(symbol: "exclamationmark.triangle.fill", size: 46, lit: false) }
                VStack(alignment: .leading, spacing: 2) {
                    Text(vpn.working ? "Setting up" : "Setup stopped").font(.title3.weight(.bold))
                    Text(chosen.isEmpty ? "Preparing your servers"
                         : vpn.working && ready == chosen.count ? "Finishing up"
                         : "\(ready) of \(chosen.count) ready")
                        .font(.callout).foregroundStyle(.secondary).monospacedDigit()
                        .contentTransition(.numericText())
                }
                Spacer(minLength: 24)
            }
            if !chosen.isEmpty {
                VStack(spacing: 6) {
                    ForEach(chosen) { c in
                        BuildRow(choice: c, status: isReady(c) ? .ready : !vpn.working ? .stopped : exists(c) ? .checking : .working,
                                 focused: vpn.working && settingUp.first?.code == c.code)
                    }
                }
                .animation(.smooth(duration: 0.3), value: ready)
            }
            HStack(spacing: 6) {
                Image(systemName: vpn.working ? "gearshape.2" : "info.circle").font(.system(size: 10, weight: .semibold))
                Text(vpn.setupLog.last ?? "Checking your subscription").lineLimit(1).truncationMode(.tail)
                    .contentTransition(.opacity)
            }
            .font(.caption).foregroundStyle(.secondary)
            .animation(.easeInOut, value: vpn.setupLog.count)
            if vpn.working {
                Text("Nothing keeps running once it's done.").font(.caption2).foregroundStyle(.tertiary)
            } else {
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
                BrandButton(title: "Add Home PC", icon: "plus", kind: .secondary) { vpn.requestedSheet = .addPC; vpn.finishOnboarding() }
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

/// A chosen location: flag, name, and a tap to remove it.
struct LocationChip: View {
    let choice: RegionChoice
    var onRemove: () -> Void = {}

    var body: some View {
        Button(action: onRemove) {
            HStack(spacing: 6) {
                FlagBadge(country: choice.country, size: 18)
                Text(choice.name).font(.caption.weight(.semibold)).lineLimit(1)
                Image(systemName: "xmark").font(.system(size: 8, weight: .bold)).foregroundStyle(.tertiary)
            }
            .padding(.leading, 4).padding(.trailing, 10).padding(.vertical, 4)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .modifier(ChipGlass())
        .accessibilityLabel("Remove \(choice.name)")
    }
}

private struct ChipGlass: ViewModifier {
    func body(content: Content) -> some View {
        if #available(macOS 26, iOS 26, *) { content.glassEffect(.regular.tint(Brand.mint.opacity(0.12)).interactive(), in: Capsule()) }
        else { content.background(Capsule().fill(Brand.mint.opacity(0.16))).overlay(Capsule().strokeBorder(.primary.opacity(0.08), lineWidth: 0.5)) }
    }
}

/// One location in the setup card: flag, name and city, then its status.
struct BuildRow: View {
    enum Status { case working, checking, ready, stopped }
    let choice: RegionChoice
    let status: Status
    /// The location highlighted on the map.
    var focused = false

    var body: some View {
        HStack(spacing: 10) {
            FlagBadge(country: choice.country, size: 24)
            VStack(alignment: .leading, spacing: 1) {
                Text(choice.name).font(.callout.weight(.semibold)).lineLimit(1)
                Text(choice.city).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            HStack(spacing: 5) {
                switch status {
                case .working, .checking: ProgressView().controlSize(.mini)
                case .ready: Image(systemName: "checkmark.circle.fill").foregroundStyle(Brand.accent)
                case .stopped: Image(systemName: "exclamationmark.circle.fill").foregroundStyle(Atlas.red)
                }
                Text(label).foregroundStyle(status == .ready ? AnyShapeStyle(Brand.accent) : AnyShapeStyle(.secondary))
            }
            .font(.caption.weight(.semibold))
            .transition(.opacity)
            .id(status)
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(focused ? Brand.mint.opacity(0.12) : Color.primary.opacity(0.04)))
        .accessibilityElement(children: .combine)
    }

    private var label: String {
        switch status {
        case .working: return "Setting up"
        case .checking: return "Checking"
        case .ready: return "Ready"
        case .stopped: return "Stopped"
        }
    }
}

/// Wraps its children onto as many rows as needed.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let w = rows.map(\.width).max() ?? 0
        let h = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? w, height: h)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for i in row.items {
                let size = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row { var items: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows = [Row()]
        for i in subviews.indices {
            let size = subviews[i].sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty, rows[rows.count - 1].width + spacing + size.width > width { rows.append(Row()) }
            var r = rows[rows.count - 1]
            r.width += (r.items.isEmpty ? 0 : spacing) + size.width
            r.height = max(r.height, size.height)
            r.items.append(i)
            rows[rows.count - 1] = r
        }
        return rows.filter { !$0.items.isEmpty }
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
            step(1, "Copy the setup command") {
                HStack(spacing: 8) {
                    TextField("PC name", text: $name.v).textFieldStyle(.roundedBorder).frame(width: 140)
                    primary(copied.v ? "Copied" : "Copy", icon: copied.v ? "checkmark" : "doc.on.doc") {
                        Platform.copy(vpn.directCommand(name: name.v))
                        copied.v = true
                    }
                }
            }
            step(2, "Run it on the PC") {
                Text("**Win+X › Terminal**, paste, Enter. Approve the one prompt.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            step(3, "Paste the link it shows") {
                HStack(spacing: 8) {
                    TextField("leapvpn://pair…", text: $link.v).textFieldStyle(.roundedBorder)
                        .onSubmit(add)
                    primary("Add", icon: "plus", action: add).disabled(link.v.isEmpty)
                }
                if bad.v { Text("That link isn't valid.").font(.caption).foregroundStyle(Atlas.red) }
            }
            if note || onboarding {
                Label("Needs UDP 51820 open on your router — the script tries UPnP.", systemImage: "info.circle")
                    .font(.caption2).foregroundStyle(.tertiary).padding(.horizontal, 4)
            }
            if onboarding {
                HStack {
                    BrandPill(title: "Back", icon: "chevron.left") { vpn.step = vpn.hasAzure ? .locations : .welcome }
                    Spacer()
                    if !vpn.setup.direct.isEmpty {
                        BrandButton(title: "Done", icon: "checkmark") { vpn.finishOnboarding() }.frame(width: 160)
                    }
                }
            }
        }
        }
    }

    /// Onboarding keeps its brand cards; inside the Add-PC sheet the steps match the relay flow.
    @ViewBuilder private func step<C: View>(_ n: Int, _ title: String, @ViewBuilder _ content: () -> C) -> some View {
        if onboarding { StepRow(n: n, title: title, content: content) } else { SheetStep(n: n, title: title, content: content) }
    }

    @ViewBuilder private func primary(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        if onboarding {
            Button(action: action) { Label(title, systemImage: icon) }.modifier(ProminentStyle())
        } else {
            Button(action: action) {
                Label(title, systemImage: icon).font(.callout.weight(.semibold))
                    .foregroundStyle(SheetTheme.onAccent).lineLimit(1)
            }
            .modifier(GlassButton(prominent: true)).tint(SheetTheme.fill)
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
            Text("\(n)").font(.callout.weight(.heavy)).foregroundStyle(.white)
                .frame(width: 28, height: 28).background(Circle().fill(Brand.deep.gradient))
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
