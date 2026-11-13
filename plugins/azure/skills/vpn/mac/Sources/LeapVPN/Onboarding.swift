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

    var body: some View {
        ZStack(alignment: .bottom) {
            AtlasMap(pins: pins, selected: nil, home: vpn.home, tone: vpn.step == .building ? .connecting : .exposed) { id in
                guard vpn.step == .locations else { return }
                if picked.v.contains(id) { picked.v.remove(id) } else { picked.v.insert(id) }
            }
            .opacity(vpn.step == .locations || vpn.step == .building ? 1 : 0.55)
            .ignoresSafeArea()

            card.padding(20).frame(maxWidth: vpn.step == .directPC ? 500 : 440)
        }
        .task { if vpn.home == nil, let e = await Egress.lookup() { vpn.home = GeoPoint(e.loc) } }
    }

    private var pins: [MapPin] {
        switch vpn.step {
        case .locations, .building:
            return RegionChoice.all.map { c in
                MapPin(id: c.code, title: "\(c.flag) \(c.name)", point: c.point, kind: .azure,
                       asleep: !(picked.v.contains(c.code) || vpn.regions.contains { $0.code == c.code }))
            }
        default: return []
        }
    }

    @ViewBuilder private var card: some View {
        VStack(alignment: .leading, spacing: 16) {
            switch vpn.step {
            case .welcome, .signIn: welcome
            case .subscription: subscriptions
            case .locations: locations
            case .building: building
            case .homePCs, .done: homePCs
            case .directPC: DirectPairView(onboarding: true)
            }
            if let e = vpn.setupError {
                Label(e, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(22)
        .glass()
        .overlay(alignment: .topTrailing) {
            if vpn.setup.onboarded, vpn.step != .building, !vpn.working {
                Button { vpn.closeOnboarding() } label: {
                    Image(systemName: "xmark").font(.system(size: 12, weight: .bold)).foregroundStyle(.secondary)
                        .frame(width: 28, height: 28).contentShape(Circle())
                }
                .buttonStyle(.plain).glass(14, interactive: true).padding(12)
                .accessibilityLabel("Close setup")
            }
        }
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Platform.appIcon.resizable().frame(width: 52, height: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Leap VPN").font(.title2.weight(.bold))
                    Text("Your own VPN, in your Azure.").foregroundStyle(.secondary)
                }
            }
            VStack(alignment: .leading, spacing: 10) {
                fact("cloud", "Runs in your Azure subscription")
                fact("power", "Servers exist only while you're connected")
                fact("dollarsign.circle", "≈ $0.01 / hour connected")
                fact("moon.zzz", "≈ $0 while off")
            }
            if vpn.askDirectory {
                TextField("Azure directory, e.g. name.onmicrosoft.com", text: $vpn.directory)
                    .textFieldStyle(.roundedBorder).controlSize(.large)
                    .help("Azure portal › Microsoft Entra ID › Overview › Primary domain")
                    .onSubmit { vpn.signIn() }
            }
            PrimaryButton(title: "Sign in with Microsoft", icon: "person.crop.circle", busy: vpn.working) { vpn.signIn() }
                .disabled(vpn.working)
            if !vpn.setup.onboarded || !vpn.hasAzure {
                Button { vpn.skipSignIn() } label: {
                    Label("Skip — use my home PC only", systemImage: "desktopcomputer").font(.callout)
                }
                .linkButton()
                .frame(maxWidth: .infinity)
            }
        }
    }

    private func fact(_ icon: String, _ text: String) -> some View {
        Label { Text(text) } icon: { Image(systemName: icon).foregroundStyle(Atlas.blue).frame(width: 22) }
            .font(.callout)
    }

    private var subscriptions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Choose a subscription").font(.title3.weight(.semibold))
            ForEach(vpn.subscriptions) { s in
                Button { Task { await vpn.choose(s) } } label: {
                    HStack {
                        Image(systemName: "key.icloud")
                        VStack(alignment: .leading) {
                            Text(s.name)
                            Text(s.id).font(.caption2.monospaced()).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                    }
                    .padding(10).contentShape(Rectangle())
                    .background(RoundedRectangle(cornerRadius: 12).fill(.primary.opacity(0.05)))
                }
                .buttonStyle(.plain).disabled(vpn.working)
            }
        }
    }

    private var locations: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Tap the map to pick locations").font(.title3.weight(.semibold))
            FlowChips(items: RegionChoice.all.filter { picked.v.contains($0.code) }.map { "\($0.flag) \($0.name)" })
            HStack(spacing: 8) {
                Chip(icon: "moon.zzz", text: vpn.ephemeral ? "$0 while off" : "≈ $\(picked.v.count * 3) / mo while off")
                Chip(icon: "timer", text: vpn.ephemeral ? "~2 min to connect" : "~40 s to connect")
            }
            PrimaryButton(title: "Add \(picked.v.count) location\(picked.v.count == 1 ? "" : "s")", icon: "bolt.fill") {
                vpn.build(RegionChoice.all.filter { picked.v.contains($0.code) })
            }
            .disabled(picked.v.isEmpty || vpn.working)
            .opacity(picked.v.isEmpty ? 0.5 : 1)
            Button {
                vpn.build([nearestRelay()], relayOnly: true)
            } label: {
                Label("Home PCs only (adds one small relay)", systemImage: "house").font(.caption)
            }
            .linkButton()
        }
    }

    private func nearestRelay() -> RegionChoice {
        guard let h = vpn.home else { return RegionChoice.all[0] }
        return RegionChoice.all.min { Countries.distance($0.point, h) < Countries.distance($1.point, h) } ?? RegionChoice.all[0]
    }

    private var building: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                if vpn.working { ProgressView().controlSize(.small) }
                else { Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Atlas.red) }
                Text(vpn.working ? "Setting up…" : "Setup stopped").font(.title3.weight(.semibold))
            }
            Text(vpn.setupLog.last ?? "Checking your subscription")
                .font(.caption).foregroundStyle(.secondary).lineLimit(2)
            Text("Nothing keeps running once it's done.").font(.caption2).foregroundStyle(.tertiary)
            if !vpn.working {
                PrimaryButton(title: "Try again", icon: "arrow.clockwise") { vpn.step = .locations }
            }
        }
    }

    private var homePCs: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "house.fill").font(.title2).foregroundStyle(Atlas.home)
                Text("Add a home PC?").font(.title3.weight(.semibold))
            }
            Text("Exit through a Windows PC at home. Optional.").font(.callout).foregroundStyle(.secondary)
            if !vpn.pendingExits.isEmpty || !vpn.exits.isEmpty {
                Label("\(vpn.exits.count) added · \(vpn.pendingExits.count) waiting", systemImage: "desktopcomputer")
                    .font(.caption)
            }
            HStack {
                Button("Add PC") { vpn.requestedSheet = .addPC; vpn.finishOnboarding() }.controlSize(.large)
                PrimaryButton(title: "Done", icon: "checkmark") { vpn.finishOnboarding() }
            }
        }
    }
}

struct FlowChips: View {
    let items: [String]
    var body: some View {
        HStack(spacing: 6) {
            ForEach(items, id: \.self) { t in
                Text(t).font(.caption).padding(.horizontal, 10).padding(.vertical, 5)
                    .background(Capsule().fill(Atlas.blue.opacity(0.14)))
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
                HStack(spacing: 10) {
                    Image(systemName: "desktopcomputer").font(.title2).foregroundStyle(Atlas.home)
                    Text("Use your home PC").font(.title3.weight(.semibold))
                }
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
                    Button("Back") { vpn.step = .welcome }.linkButton()
                    Spacer()
                    if !vpn.setup.direct.isEmpty {
                        PrimaryButton(title: "Done", icon: "checkmark") { vpn.finishOnboarding() }.frame(width: 140)
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
            Text("\(n)").font(.callout.weight(.bold)).foregroundStyle(.white)
                .frame(width: 28, height: 28).background(Circle().fill(Atlas.blue.gradient))
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
