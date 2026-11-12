import AppKit
import SwiftUI

// MARK: shared bits

/// Local view state without the @State macro (no macro plugins in this toolchain).
final class Box<T>: ObservableObject {
    @Published var v: T
    init(_ v: T) { self.v = v }
}

extension View {
    func glass(_ radius: CGFloat = 30) -> some View {
        background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(.white.opacity(0.6), lineWidth: 0.5))
            .shadow(color: .black.opacity(0.08), radius: 18, y: 8)
    }
}

struct PrimaryButton: View {
    let title: String
    var icon: String? = nil
    var tint: Color = Atlas.blue
    var busy = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if busy { ProgressView().controlSize(.small).tint(.white) }
                else if let icon { Image(systemName: icon) }
                Text(title).fontWeight(.semibold)
            }
            .frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(.white)
            .background(LinearGradient(colors: [tint.opacity(0.85), tint], startPoint: .top, endPoint: .bottom),
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct RootView: View {
    @EnvironmentObject var vpn: VPNController
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Group {
            if vpn.step == .done { AtlasHome() } else { OnboardingView() }
        }
        .background(Atlas.background)
        .onAppear { MacWindowBridge.registerMainWindowOpener { openWindow(id: MacWindowID.main) } }
    }
}

// MARK: onboarding

struct OnboardingView: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var picked = Box<Set<String>>(["in"])
    @StateObject private var showAddPC = Box(false)

    var body: some View {
        ZStack(alignment: .bottom) {
            AtlasMap(pins: pins, selected: nil, home: vpn.home, tone: vpn.step == .building ? .connecting : .exposed) { id in
                guard vpn.step == .locations else { return }
                if picked.v.contains(id) { picked.v.remove(id) } else { picked.v.insert(id) }
            }
            .opacity(vpn.step == .locations || vpn.step == .building ? 1 : 0.55)
            .ignoresSafeArea()

            card.padding(20).frame(maxWidth: 440)
        }
        .sheet(isPresented: $showAddPC.v) { AddHomeExitSheet().environmentObject(vpn) }
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
            }
            if let e = vpn.setupError {
                Label(e, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(22)
        .glass()
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 52, height: 52)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Leap VPN").font(.title2.weight(.bold))
                    Text("Your own VPN, in your Azure.").foregroundStyle(.secondary)
                }
            }
            VStack(alignment: .leading, spacing: 10) {
                fact("cloud", "Runs in your Azure subscription")
                fact("power", "Servers start on connect, stop when you leave")
                fact("dollarsign.circle", "≈ $0.01 / hour connected")
                fact("moon.zzz", "≈ $6 / month per server while off")
            }
            if vpn.askDirectory {
                TextField("Azure directory, e.g. name.onmicrosoft.com", text: $vpn.directory)
                    .textFieldStyle(.roundedBorder).controlSize(.large)
                    .help("Azure portal › Microsoft Entra ID › Overview › Primary domain")
                    .onSubmit { vpn.signIn() }
            }
            PrimaryButton(title: "Sign in with Microsoft", icon: "person.crop.circle", busy: vpn.working) { vpn.signIn() }
                .disabled(vpn.working)
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
                    .background(RoundedRectangle(cornerRadius: 12).fill(.white.opacity(0.5)))
                }
                .buttonStyle(.plain).disabled(vpn.working)
            }
        }
    }

    private var locations: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Tap the map to pick servers").font(.title3.weight(.semibold))
            FlowChips(items: RegionChoice.all.filter { picked.v.contains($0.code) }.map { "\($0.flag) \($0.name)" })
            HStack {
                Image(systemName: "moon.zzz").foregroundStyle(.secondary)
                Text("≈ $\(picked.v.count * 6) / month while off").font(.caption).foregroundStyle(.secondary)
            }
            PrimaryButton(title: "Create \(picked.v.count) server\(picked.v.count == 1 ? "" : "s")", icon: "bolt.fill") {
                vpn.build(RegionChoice.all.filter { picked.v.contains($0.code) })
            }
            .disabled(picked.v.isEmpty || vpn.working)
            .opacity(picked.v.isEmpty ? 0.5 : 1)
            Button {
                vpn.build([nearestRelay()], relayOnly: true)
            } label: {
                Label("Home PCs only (adds one small relay)", systemImage: "house").font(.caption)
            }
            .buttonStyle(.link)
        }
    }

    private func nearestRelay() -> RegionChoice {
        guard let h = vpn.home else { return RegionChoice.all[0] }
        return RegionChoice.all.min { a, b in
            pow(a.point.lat - h.lat, 2) + pow(a.point.lon - h.lon, 2) < pow(b.point.lat - h.lat, 2) + pow(b.point.lon - h.lon, 2)
        } ?? RegionChoice.all[0]
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
            Text("Takes a few minutes. Nothing runs once it's done.").font(.caption2).foregroundStyle(.tertiary)
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
                Button("Add PC") { showAddPC.v = true }.controlSize(.large)
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
                    .background(Capsule().fill(Atlas.blue.opacity(0.12)))
            }
            if items.isEmpty { Text("None yet").font(.caption).foregroundStyle(.tertiary) }
        }
    }
}

// MARK: home

enum HomeSheet: String, Identifiable { case history, settings, addPC; var id: String { rawValue } }

struct AtlasHome: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var sheet = Box<HomeSheet?>(nil)

    var body: some View {
        ZStack {
            AtlasMap(pins: pins, selected: vpn.selected, home: vpn.home, tone: vpn.phase.tone) { id in
                guard vpn.phase == .idle || isFailed else { return }
                vpn.selected = id
                UserDefaults.standard.set(id, forKey: "region")
            }
            .ignoresSafeArea()

            VStack {
                HStack(alignment: .top) {
                    StatusCapsule()
                    Spacer()
                    HStack(spacing: 2) {
                        iconButton("clock.arrow.circlepath", "History") { sheet.v = .history }
                        iconButton("gearshape", "Settings") { sheet.v = .settings }
                    }
                    .padding(4).glass(20)
                    addMenu
                }
                Spacer()
                ConnectCard().frame(maxWidth: 420)
            }
            .padding(18)
        }
        .sheet(item: $sheet.v) { s in
            switch s {
            case .history: HistorySheet().environmentObject(vpn)
            case .settings: SettingsSheet().environmentObject(vpn)
            case .addPC: AddHomeExitSheet().environmentObject(vpn)
            }
        }
        .onReceive(vpn.$requestedSheet.compactMap { $0 }) { s in
            sheet.v = s
            vpn.requestedSheet = nil
        }
        .animation(.spring(duration: 0.4), value: vpn.phase)
    }

    private var isFailed: Bool { if case .failed = vpn.phase { return true }; return false }

    private var pins: [MapPin] {
        let azure = vpn.exitRegions.map {
            MapPin(id: $0.code, title: "\($0.flag) \($0.name)", point: $0.point, kind: .azure,
                   asleep: vpn.regionStates[$0.code] != "running")
        }
        let homes = vpn.exits.compactMap { e -> MapPin? in
            guard let p = e.point ?? vpn.regions.first(where: { $0.code == e.region })?.point else { return nil }
            return MapPin(id: "exit:\(e.id)", title: "🏠 \(e.name)", point: p, kind: .home,
                          asleep: vpn.regionStates[e.region] != "running")
        }
        return azure + homes
    }

    private func iconButton(_ icon: String, _ help: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon).font(.system(size: 15, weight: .medium)).frame(width: 34, height: 34).contentShape(Rectangle())
        }
        .buttonStyle(.plain).help(help)
    }

    private var addMenu: some View {
        Menu {
            let have = Set(vpn.regions.map(\.code))
            ForEach(RegionChoice.all) { c in
                if !have.contains(c.code) {
                    Button("\(c.flag) \(c.name)") { vpn.build([c]) }
                } else if vpn.setup.relayOnly.contains(c.code) {
                    Button("\(c.flag) \(c.name)") { vpn.build([c]) }
                }
            }
            Divider()
            Button { sheet.v = .addPC } label: { Label("Home PC", systemImage: "house") }
        } label: {
            Image(systemName: vpn.working ? "hourglass" : "plus").font(.system(size: 17, weight: .semibold))
                .frame(width: 42, height: 42)
        }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        .glass(21)
        .padding(.leading, 10)
        .help("Add a server")
        .disabled(vpn.working)
    }
}

struct StatusCapsule: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var pulse = Box(false)

    var body: some View {
        let tone = vpn.phase.tone
        HStack(spacing: 8) {
            Image(systemName: tone.symbol)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(tone.color)
                .scaleEffect(tone == .connecting && pulse.v ? 1.15 : 1)
                .animation(tone == .connecting ? .easeInOut(duration: 0.7).repeatForever() : .default, value: pulse.v)
                .onAppear { pulse.v = true }
            if let e = vpn.egress, vpn.phase == .connected {
                Text("\(flag(e.country)) \(e.ip)").font(.caption.monospacedDigit())
            } else if vpn.phase.busy {
                Text(vpn.phase.label).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.horizontal, 14).frame(height: 42)
        .glass(21)
        .overlay(Capsule().strokeBorder(tone.color.opacity(0.45), lineWidth: 1.5))
        .help(vpn.phase.label)
        .accessibilityLabel(vpn.phase.label)
    }
}

func flag(_ country: String) -> String {
    country.uppercased().unicodeScalars.compactMap { UnicodeScalar(127397 + $0.value) }.map(String.init).joined()
}

struct ConnectCard: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(spacing: 14) {
            HStack(spacing: 12) {
                Text(vpn.choice?.flag ?? "🌐").font(.system(size: 34))
                VStack(alignment: .leading, spacing: 2) {
                    Text(vpn.choice?.title ?? "Tap a pin").font(.title3.weight(.semibold))
                    Text(subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                CreditRing()
            }
            if case .failed(let why) = vpn.phase {
                Label(why, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                    .frame(maxWidth: .infinity, alignment: .leading).lineLimit(2)
            }
            if vpn.needsSignIn {
                PrimaryButton(title: "Sign in again", icon: "person.crop.circle") { vpn.signIn() }
            } else if vpn.phase == .connected {
                PrimaryButton(title: "Disconnect", icon: "power", tint: Atlas.green) { vpn.disconnect() }
            } else {
                PrimaryButton(title: vpn.phase.busy ? vpn.phase.label : "Connect", icon: "power",
                              tint: vpn.phase.busy ? Atlas.blue : Atlas.blue, busy: vpn.phase.busy) { vpn.connect() }
                    .disabled(vpn.phase.busy || vpn.choice == nil || vpn.working)
            }
            if let l = vpn.lastCompleted, vpn.phase != .connected, !vpn.phase.busy {
                HStack(spacing: 6) {
                    Image(systemName: l.vmStoppedAt == nil ? "hourglass" : "moon.zzz.fill")
                        .foregroundStyle(l.vmStoppedAt == nil ? Atlas.amber : Atlas.green)
                    Text("Last session \(formatDuration(l.duration)) · \(formatMoney(l.total, l.currency))")
                    Spacer()
                }
                .font(.caption).foregroundStyle(.secondary)
                .help(l.vmStoppedAt == nil ? "Waiting for the server to stop" : "Server stopped")
            }
        }
        .padding(20)
        .glass()
    }

    private var subtitle: String {
        if let c = vpn.current, vpn.phase == .connected {
            return "\(formatDuration(c.duration)) · \(formatBytes(c.rxBytes + c.txBytes))"
        }
        guard let ch = vpn.choice else { return "" }
        if let e = ch.exit { return "Home PC via \(ch.region.city)" + (e.isp.map { " · \($0)" } ?? "") }
        return ch.region.city
    }
}

struct CreditRing: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        if let spend = vpn.spend, let credit = vpn.monthlyCredit, credit > 0 {
            let left = max(0, credit - spend.amount)
            ZStack {
                Circle().stroke(Atlas.dot.opacity(0.5), lineWidth: 4)
                Circle().trim(from: 0, to: left / credit)
                    .stroke(left / credit > 0.2 ? Atlas.green : Atlas.amber, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text(compactMoney(left, spend.currency)).font(.system(size: 10, weight: .semibold)).minimumScaleFactor(0.6)
                    .padding(4)
            }
            .frame(width: 50, height: 50)
            .help("≈ \(formatMoney(left, spend.currency)) Azure credit left (estimate)")
        }
    }
}

func compactMoney(_ amount: Double, _ currency: String) -> String {
    let f = NumberFormatter()
    f.numberStyle = .currency
    f.currencyCode = currency
    f.maximumFractionDigits = 0
    return f.string(from: NSNumber(value: amount)) ?? "\(Int(amount))"
}

// MARK: sheets

struct HistorySheet: View {
    @EnvironmentObject var vpn: VPNController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text("Usage").font(.title2.weight(.semibold))
                Spacer()
                Button { Task { await vpn.refreshCosts() } } label: { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.borderless)
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            .padding([.horizontal, .top], 20)
            CreditsStrip().padding(.horizontal, 20)
            HistoryView()
        }
        .frame(width: 640, height: 480)
    }
}

struct CreditsStrip: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        HStack(spacing: 24) {
            if let spend = vpn.spend {
                if let credit = vpn.monthlyCredit {
                    item("Credit left (est.)", formatMoney(max(0, credit - spend.amount), spend.currency))
                }
                item("Spent this period", formatMoney(spend.amount, spend.currency))
                item("VPN billed", formatMoney(vpn.vpnBilled.values.reduce(0, +), spend.currency))
            } else {
                ProgressView().controlSize(.small)
            }
        }
    }

    private func item(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3.weight(.semibold))
        }
    }
}

struct SettingsSheet: View {
    @EnvironmentObject var vpn: VPNController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Settings").font(.title2.weight(.semibold))
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
            GroupBox {
                VStack(alignment: .leading, spacing: 4) {
                    Label(vpn.setup.user?.username ?? "—", systemImage: "person.crop.circle")
                    Label(vpn.setup.subscriptionName ?? "—", systemImage: "key.icloud").foregroundStyle(.secondary)
                    Label(vpn.setup.device?.name ?? "—", systemImage: "laptopcomputer").foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            GroupBox("Servers") {
                ForEach(vpn.regions) { r in
                    HStack {
                        Text("\(r.flag) \(r.name)")
                        if vpn.setup.relayOnly.contains(r.code) { Text("relay").font(.caption2).foregroundStyle(.secondary) }
                        Spacer()
                        Image(systemName: vpn.regionStates[r.code] == "running" ? "bolt.fill" : "moon.zzz")
                            .foregroundStyle(vpn.regionStates[r.code] == "running" ? Atlas.green : .secondary)
                            .help(vpn.regionStates[r.code] ?? "")
                        Button(role: .destructive) { vpn.removeRegion(r) } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless).disabled(vpn.working || vpn.current?.region == r.code)
                    }
                }
            }
            if !vpn.exits.isEmpty || !vpn.pendingExits.isEmpty {
                GroupBox("Home PCs") {
                    ForEach(vpn.exits + vpn.pendingExits) { e in
                        HStack {
                            Text(e.pending ? "⏳ waiting for PC" : "\(e.flag) \(e.name)")
                            Spacer()
                            Button(role: .destructive) { Task { await vpn.removeExit(e) } } label: { Image(systemName: "trash") }
                                .buttonStyle(.borderless)
                        }
                    }
                }
            }
            if let e = vpn.setupError { Text(e).font(.caption).foregroundStyle(Atlas.red).textSelection(.enabled) }
            if vpn.working { ProgressView(vpn.setupLog.last ?? "Working…").controlSize(.small) }
            Spacer()
            Button("Sign out", role: .destructive) { vpn.signOut(); dismiss() }
        }
        .padding(22)
        .frame(width: 420, height: 520)
    }
}

struct HistoryView: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            let month = Calendar.current.dateInterval(of: .month, for: Date())?.start ?? Date()
            let t = vpn.store.totals(since: month)
            let currency = vpn.store.sessions.first?.currency ?? vpn.spend?.currency ?? "INR"
            HStack(spacing: 24) {
                stat("This month", formatMoney(t.cost, currency))
                stat("Server hours", String(format: "%.1f", t.hours))
                stat("Data", String(format: "%.2f GB", t.gb))
            }
            .padding(.horizontal, 20)
            Table(vpn.store.sessions) {
                TableColumn("Server") { s in Text("\(s.flag) \(s.regionName)") }.width(min: 140, ideal: 150)
                TableColumn("Start") { s in Text(s.connectedAt.formatted(.dateTime.day().month(.abbreviated).hour().minute())) }
                    .width(min: 150, ideal: 170)
                TableColumn("Duration") { s in Text(formatDuration(s.duration)) }.width(ideal: 90)
                TableColumn("Data") { s in Text(s.rxBytes + s.txBytes > 0 ? formatBytes(s.rxBytes + s.txBytes) : "—") }
                    .width(ideal: 90)
                TableColumn("Cost") { s in
                    Text(formatMoney(s.total, s.currency))
                        .help("server \(formatMoney(s.vmCost, s.currency)) + data \(formatMoney(s.egressCost, s.currency))")
                }
            }
            Text("Estimates from Azure retail prices. Billed totals lag a few hours.")
                .font(.caption).foregroundStyle(.secondary).padding(.horizontal, 20).padding(.bottom, 10)
        }
    }

    private func stat(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading) {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.title3.weight(.semibold))
        }
    }
}

struct MenuBarView: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        Text(vpn.phase == .connected ? "\(vpn.choice?.flag ?? "") \(vpn.choice?.title ?? "")" : vpn.phase.label)
        if vpn.step == .done {
            if vpn.phase == .connected { Button("Disconnect") { vpn.disconnect() } }
            else if !vpn.phase.busy { Button("Connect") { vpn.connect() } }
        }
        Button("Open VikiVPN") { MacWindowBridge.showMainWindow() }
        Divider()
        Button("Quit") { NSApp.terminate(nil) }
    }
}

/// Register a PC on a home connection as an exit and produce its one-time Windows setup script.
struct AddHomeExitSheet: View {
    @EnvironmentObject var vpn: VPNController
    @Environment(\.dismiss) private var dismiss
    @StateObject private var form = AddExitForm()

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Add a home PC").font(.title2.weight(.semibold))
            Text("Streaming services block datacenter IPs. A home PC lets your devices exit through a home internet connection instead. Run the installer once on a Windows PC: it registers itself here with its own country and ISP, dials out to the relay (no router changes), and the relay still runs only while you are connected.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Picker("Relay server", selection: $form.regionCode) {
                ForEach(vpn.regions) { r in Text("\(r.flag) \(r.name)").tag(r.code) }
            }
            Text("Pick the relay in the same country as the PC for the lowest latency.")
                .font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Button { make(.copy) } label: { Label("Copy command", systemImage: "doc.on.doc") }
                    .buttonStyle(.borderedProminent)
                Button { make(.share) } label: { Label("Share…", systemImage: "square.and.arrow.up") }
                Button { make(.download) } label: { Label("Download .cmd", systemImage: "arrow.down.circle") }
                if form.working { ProgressView().controlSize(.small) }
            }
            .disabled(form.working)
            if let inst = form.installer {
                Divider()
                Label(form.done, systemImage: "checkmark.seal.fill").foregroundStyle(.green)
                Text("On the Windows PC: press **Win+X**, choose **Terminal** (or PowerShell), paste the command and press Enter. No admin rights, no downloads, no security prompts. The PC appears in the server list within a minute.")
                    .font(.callout).fixedSize(horizontal: false, vertical: true)
                Text(inst.command).font(.caption2.monospaced()).lineLimit(2).truncationMode(.middle)
                    .textSelection(.enabled)
                    .padding(6).background(RoundedRectangle(cornerRadius: 6).fill(.quaternary))
                Text("The command holds a one-time registration link valid for 48 hours. Share it only with your own PCs. The .cmd in Downloads is a fallback for copying by USB stick; if it arrives by browser or email, Windows SmartScreen will warn about it.")
                    .font(.caption).foregroundStyle(.orange).fixedSize(horizontal: false, vertical: true)
                Button("Show .cmd in Finder") { NSWorkspace.shared.activateFileViewerSelecting([inst.file]) }
                    .buttonStyle(.link).font(.caption)
            }
            if let err = form.error { Text(err).font(.caption).foregroundStyle(.red).textSelection(.enabled) }
            HStack {
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
            }
        }
        .padding(22)
        .frame(width: 480)
    }

    enum Delivery { case copy, share, download }

    private func make(_ how: Delivery) {
        form.working = true; form.error = nil
        Task {
            do {
                let inst: VPNController.ExitInstaller
                if let prior = form.installer, form.installerRegion == form.regionCode,
                   prior.expires.timeIntervalSinceNow > 3600 {
                    inst = prior  // one invite per sheet: more clicks reuse it, not more slots
                } else {
                    inst = try await vpn.createExitInstaller(regionCode: form.regionCode)
                }
                form.installer = inst
                form.installerRegion = form.regionCode
                switch how {
                case .copy:
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(inst.command, forType: .string)
                    form.done = "Command copied"
                case .share:
                    form.done = "Command ready to share"
                    if let view = NSApp.keyWindow?.contentView {
                        NSSharingServicePicker(items: [inst.command])
                            .show(relativeTo: view.bounds, of: view, preferredEdge: .minY)
                    }
                case .download:
                    form.done = "\(inst.file.lastPathComponent) saved to Downloads"
                    NSWorkspace.shared.activateFileViewerSelecting([inst.file])
                }
            } catch { form.error = error.localizedDescription }
            form.working = false
        }
    }
}

@MainActor
final class AddExitForm: ObservableObject {
    @Published var regionCode = "in"
    @Published var working = false
    @Published var error: String?
    @Published var installer: VPNController.ExitInstaller?
    @Published var done = ""
    var installerRegion = ""
}
