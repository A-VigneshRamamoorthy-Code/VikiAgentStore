import AppKit
import Charts
import SwiftUI

// MARK: shared sheet chrome

struct SheetHeader: View {
    let icon: String
    let title: String
    var tint: Color = Atlas.blue
    var trailing: AnyView? = nil
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 16, weight: .semibold)).foregroundStyle(.white)
                .frame(width: 34, height: 34).background(Circle().fill(tint.gradient))
            Text(title).font(.title2.weight(.semibold))
            Spacer()
            trailing
            CircleButton(icon: "xmark", help: "Close") { dismiss() }.keyboardShortcut(.cancelAction)
        }
    }
}

struct Card<Content: View>: View {
    var title: String? = nil
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let title { Text(title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.secondary).tracking(0.6) }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(.primary.opacity(0.045)))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(.primary.opacity(0.07), lineWidth: 0.5))
    }
}

// MARK: usage

struct HistorySheet: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SheetHeader(icon: "chart.bar.xaxis", title: "Usage", tint: Atlas.green, trailing: AnyView(
                CircleButton(icon: "arrow.clockwise", help: "Refresh") { Task { await vpn.refreshCosts() } }))
            ScrollView {
                VStack(spacing: 14) {
                    StatTiles()
                    HStack(alignment: .top, spacing: 14) {
                        Card(title: "Last 14 days") { DailyChart() }
                        Card(title: "By location") { LocationBreakdown() }.frame(width: 230)
                    }
                    Card(title: "Sessions") { SessionList() }
                    Text("Estimates from Azure retail prices. Billed totals lag a few hours.")
                        .font(.caption2).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(22)
        .frame(width: 680, height: 600)
    }
}

private extension VPNController {
    var usageCurrency: String { store.sessions.first?.currency ?? spend?.currency ?? "USD" }
}

struct StatTiles: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let month = Calendar.current.dateInterval(of: .month, for: Date())?.start ?? Date()
        let t = vpn.store.totals(since: month)
        let cur = vpn.usageCurrency
        HStack(spacing: 10) {
            if let spend = vpn.spend, let credit = vpn.monthlyCredit {
                tile("creditcard", "Credit left", formatMoney(max(0, credit - spend.amount), spend.currency),
                     "of \(compactMoney(credit, spend.currency))", Atlas.green)
            }
            tile("calendar", "This month", formatMoney(t.cost, cur), "\(sessionsThisMonth(month)) sessions", Atlas.blue)
            tile("clock", "Server time", String(format: "%.1f h", t.hours), "billed compute", Atlas.amber)
            tile("arrow.up.arrow.down", "Data", String(format: "%.2f GB", t.gb), "through the VPN", .purple)
        }
    }

    private func sessionsThisMonth(_ since: Date) -> Int { vpn.store.sessions.filter { $0.connectedAt >= since }.count }

    private func tile(_ icon: String, _ title: String, _ value: String, _ caption: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: icon).font(.caption).foregroundStyle(tint)
            Text(value).font(.title3.weight(.bold)).monospacedDigit().lineLimit(1).minimumScaleFactor(0.7)
            Text(caption).font(.caption2).foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(tint.opacity(0.09)))
    }
}

struct DailyChart: View {
    @EnvironmentObject var vpn: VPNController

    struct Day: Identifiable { let id: Date; let cost: Double }

    var body: some View {
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        let days: [Day] = (0..<14).reversed().compactMap { i in
            guard let d = cal.date(byAdding: .day, value: -i, to: today) else { return nil }
            let cost = vpn.store.sessions.filter { cal.isDate($0.connectedAt, inSameDayAs: d) }.map(\.total).reduce(0, +)
            return Day(id: d, cost: cost)
        }
        Chart(days) { d in
            BarMark(x: .value("Day", d.id, unit: .day), y: .value("Cost", d.cost))
                .foregroundStyle(Atlas.green.gradient).cornerRadius(4)
        }
        .chartXAxis { AxisMarks(values: .stride(by: .day, count: 3)) { _ in AxisValueLabel(format: .dateTime.day().month(.abbreviated)) } }
        .chartYAxis { AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { v in
            AxisGridLine()
            AxisValueLabel { if let n = v.as(Double.self) { Text(formatMoney(n, vpn.usageCurrency)) } }
        } }
        .frame(height: 150)
    }
}

struct LocationBreakdown: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let groups = Dictionary(grouping: vpn.store.sessions) { "\($0.flag) \($0.regionName)" }
            .map { (name: $0.key, cost: $0.value.map(\.total).reduce(0, +), count: $0.value.count) }
            .sorted { $0.cost > $1.cost }
        let top = groups.first?.cost ?? 0
        VStack(alignment: .leading, spacing: 10) {
            ForEach(groups.prefix(6), id: \.name) { g in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(g.name).font(.caption).lineLimit(1)
                        Spacer()
                        Text(formatMoney(g.cost, vpn.usageCurrency)).font(.caption.weight(.semibold)).monospacedDigit()
                    }
                    GeometryReader { geo in
                        Capsule().fill(.primary.opacity(0.07))
                            .overlay(alignment: .leading) {
                                Capsule().fill(Atlas.blue.gradient).frame(width: max(4, geo.size.width * (top > 0 ? g.cost / top : 0)))
                            }
                    }
                    .frame(height: 6)
                }
            }
            if groups.isEmpty { Text("No sessions yet").font(.caption).foregroundStyle(.tertiary) }
        }
    }
}

struct SessionList: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(vpn.store.sessions.prefix(40).enumerated()), id: \.element.id) { i, s in
                if i > 0 { Divider().opacity(0.5) }
                HStack(spacing: 12) {
                    Text(s.flag).font(.title3)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(s.regionName).font(.callout.weight(.medium))
                        Text(s.connectedAt.formatted(.dateTime.day().month(.abbreviated).hour().minute()))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Chip(icon: "timer", text: formatDuration(s.duration), width: 92)
                    Chip(icon: "arrow.up.arrow.down", text: s.rxBytes + s.txBytes > 0 ? formatBytes(s.rxBytes + s.txBytes) : "—", width: 96)
                    Text(formatMoney(s.total, s.currency)).font(.callout.weight(.semibold)).monospacedDigit()
                        .frame(width: 70, alignment: .trailing)
                        .help("server \(formatMoney(s.vmCost, s.currency)) + data \(formatMoney(s.egressCost, s.currency))")
                }
                .padding(.vertical, 8)
            }
            if vpn.store.sessions.isEmpty { Text("No sessions yet").font(.caption).foregroundStyle(.tertiary) }
        }
    }
}

// MARK: settings

struct SettingsSheet: View {
    @EnvironmentObject var vpn: VPNController
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SheetHeader(icon: "gearshape.fill", title: "Settings", tint: .gray)
            ScrollView {
                VStack(spacing: 12) {
                    account
                    if vpn.hasAzure { ServerToggles() }
                    if !vpn.regions.isEmpty { locations }
                    if !vpn.exits.isEmpty || !vpn.pendingExits.isEmpty || !vpn.setup.direct.isEmpty { homePCs }
                    if let e = vpn.setupError { Text(e).font(.caption).foregroundStyle(Atlas.red).textSelection(.enabled) }
                    if vpn.working { ProgressView(vpn.setupLog.last ?? "Working…").controlSize(.small) }
                }
            }
        }
        .padding(22)
        .frame(width: 460, height: 600)
    }

    private var account: some View {
        Card(title: "Account") {
            if vpn.hasAzure {
                HStack(spacing: 12) {
                    Image(systemName: "person.crop.circle.fill").font(.system(size: 30)).foregroundStyle(Atlas.blue)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(vpn.setup.user?.username ?? "—").font(.callout.weight(.medium))
                        Text(vpn.setup.subscriptionName ?? "—").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Sign out", role: .destructive) { vpn.signOut(); dismiss() }.controlSize(.small)
                }
            } else {
                HStack {
                    Label("Home PCs only", systemImage: "desktopcomputer").font(.callout)
                    Spacer()
                    Button("Add Azure") { dismiss(); vpn.step = .welcome }.modifier(ProminentStyle()).controlSize(.small)
                }
            }
        }
    }

    private var locations: some View {
        Card(title: "Locations") {
            ForEach(vpn.regions) { r in
                HStack {
                    Text(r.flag)
                    Text(r.name).font(.callout)
                    Spacer()
                    StateDot(state: vpn.regionStates[r.code]).frame(width: 74, alignment: .leading)
                    PrefIcons(code: r.code).frame(width: 64, alignment: .trailing)
                    Button(role: .destructive) { vpn.removeRegion(r) } label: { Image(systemName: "trash") }
                        .buttonStyle(.borderless).disabled(vpn.working || vpn.current?.region == r.code)
                }
            }
        }
    }

    private var homePCs: some View {
        Card(title: "Home PCs") {
            ForEach(vpn.exits + vpn.pendingExits) { e in
                HStack {
                    Text(e.pending ? "⏳" : e.flag)
                    Text(e.pending ? "Waiting for PC" : e.name).font(.callout)
                    Chip(icon: "cloud", text: "via \(vpn.regions.first { $0.code == e.region }?.name ?? e.region)", width: 130)
                    Spacer()
                    Button(role: .destructive) { Task { await vpn.removeExit(e) } } label: { Image(systemName: "trash") }
                        .buttonStyle(.borderless)
                }
            }
            ForEach(vpn.setup.direct) { pc in
                HStack {
                    Text(pc.flag)
                    Text(pc.name).font(.callout)
                    Chip(icon: "bolt.horizontal", text: "direct", width: 130)
                    Spacer()
                    Button(role: .destructive) { vpn.removeDirect(pc) } label: { Image(systemName: "trash") }
                        .buttonStyle(.borderless)
                }
            }
        }
    }
}

struct StateDot: View {
    let state: String?
    var body: some View {
        let (color, text): (Color, String) = switch state {
        case "running": (Atlas.green, "On")
        case "building": (Atlas.amber, "Building")
        case "deleted": (.secondary, "Off")
        case "deallocated": (.secondary, "Off")
        case nil: (.secondary, "—")
        default: (Atlas.amber, state ?? "")
        }
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(text).font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// The two cost switches for one location (`code`) or the defaults (`nil`).
/// Icons follow state, so the setting reads at a glance.
struct ServerToggles: View {
    @EnvironmentObject var vpn: VPNController
    var code: String? = nil
    var compact = false

    private var once: Bool { code.map(vpn.ephemeral) ?? vpn.ephemeral }
    private var fixed: Bool { code.map(vpn.staticIP) ?? vpn.staticIP }
    private var relay: Bool { code.map { vpn.relayRegions.contains($0) } ?? false }

    var body: some View {
        if compact { rows } else { Card(title: code == nil ? "Defaults for new locations" : nil) { rows } }
    }

    @ViewBuilder private var rows: some View {
        VStack(alignment: .leading, spacing: compact ? 8 : 10) {
            if relay {
                Label("Relays a home PC · kept ready", systemImage: "arrow.triangle.branch")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                toggle("Provision once", icon: once ? "sparkles" : "externaldrive.fill",
                       tint: once ? Atlas.green : Atlas.blue,
                       caption: once ? "$0 while off · ~2 min to connect" : "≈ $2.40/mo disk while off · ~40 s to connect",
                       on: once) { vpn.setEphemeral($0, for: code) }
                if !compact { Divider().opacity(0.4) }
                toggle("Static IP", icon: fixed && !once ? "pin.fill" : "pin.slash",
                       tint: fixed && !once ? Atlas.blue : .secondary,
                       caption: once ? "New IP each time · not kept while off" : fixed ? "Same IP every time · ≈ $3.65/mo" : "New IP each time · $0",
                       on: fixed && !once) { vpn.setStaticIP($0, for: code) }
                    .disabled(once)
                    .opacity(once ? 0.55 : 1)
            }
        }
    }

    private func toggle(_ title: String, icon: String, tint: Color, caption: String, on: Bool,
                        set: @escaping (Bool) -> Void) -> some View {
        Toggle(isOn: Binding(get: { on }, set: set)) {
            HStack(spacing: 10) {
                Image(systemName: icon).foregroundStyle(tint).frame(width: 20)
                    .contentTransition(.symbolEffect(.replace))
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.callout.weight(.medium))
                    Text(caption).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 0)
            }
        }
        .toggleStyle(.switch)
        .controlSize(compact ? .mini : .small)
        .help(caption)
    }
}

/// Two icon-only switches for a Settings location row.
struct PrefIcons: View {
    @EnvironmentObject var vpn: VPNController
    let code: String

    var body: some View {
        let once = vpn.ephemeral(code), fixed = vpn.staticIP(code) && !once
        if vpn.relayRegions.contains(code) {
            Image(systemName: "arrow.triangle.branch").foregroundStyle(.secondary).help("Relays a home PC · kept ready")
        } else {
            HStack(spacing: 4) {
                icon(once ? "sparkles" : "externaldrive.fill", on: once, tint: Atlas.green,
                     help: once ? "Provision once: on · $0 while off" : "Provision once: off · kept on disk, faster connect") {
                    vpn.setEphemeral(!once, for: code)
                }
                icon(fixed ? "pin.fill" : "pin.slash", on: fixed, tint: Atlas.blue,
                     help: fixed ? "Static IP: on · ≈ $3.65/mo" : "Static IP: off") {
                    vpn.setStaticIP(!fixed, for: code)
                }
                .disabled(once).opacity(once ? 0.4 : 1)
            }
        }
    }

    private func icon(_ name: String, on: Bool, tint: Color, help: String, act: @escaping () -> Void) -> some View {
        Button(action: act) {
            Image(systemName: name)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(on ? tint : .secondary)
                .frame(width: 28, height: 24)
                .background(on ? tint.opacity(0.16) : Color.primary.opacity(0.05), in: Capsule())
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(.plain).help(help)
    }
}

// MARK: add home PC

/// Register a Windows PC as an exit: directly, or relayed through Azure (works behind CGNAT).
struct AddHomeExitSheet: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var form = AddExitForm()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SheetHeader(icon: "house.fill", title: "Add a home PC", tint: Atlas.home)
            if vpn.hasAzure && !vpn.regions.isEmpty {
                Picker("", selection: $form.direct) {
                    Text("Direct").tag(true)
                    Text("Through Azure").tag(false)
                }
                .pickerStyle(.segmented).labelsHidden()
                Text(form.direct ? "Fastest and free. Needs UDP 51820 open on your router."
                                 : "Works behind any router. A small Azure relay runs while connected.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if form.direct || !vpn.hasAzure || vpn.regions.isEmpty {
                DirectPairView(note: !(vpn.hasAzure && !vpn.regions.isEmpty)) { dismiss() }
            } else {
                relayFlow
            }
        }
        .padding(22)
        .frame(width: 500)
        .onAppear {
            form.direct = true
            if form.country.isEmpty { form.country = Locale.current.region?.identifier ?? "IN" }
            form.regionCode = nearest(form.country)
        }
    }

    private var relayFlow: some View {
        GlassGroup(spacing: 16) {
        VStack(alignment: .leading, spacing: 16) {
            StepRow(n: 1, title: "Where is the PC?") {
                HStack(spacing: 8) {
                    TextField("PC name", text: $form.name).textFieldStyle(.roundedBorder).frame(width: 130)
                    Picker("", selection: $form.country) {
                        ForEach(Countries.all) { c in Text("\(flag(c.code)) \(c.name)").tag(c.code) }
                    }
                    .labelsHidden()
                    .onChange(of: form.country) { _, c in if !form.relayPinned { form.regionCode = nearest(c) } }
                }
                HStack(spacing: 6) {
                    Text("Relay").font(.caption).foregroundStyle(.secondary)
                    Picker("", selection: Binding(get: { form.regionCode }, set: { form.regionCode = $0; form.relayPinned = true })) {
                        ForEach(vpn.regions) { r in Text("\(r.flag) \(r.name)").tag(r.code) }
                    }
                    .labelsHidden().controlSize(.small).fixedSize()
                    if !form.relayPinned { Text("nearest").font(.caption2).foregroundStyle(.tertiary) }
                }
            }
            StepRow(n: 2, title: "Copy the setup command") {
                HStack(spacing: 8) {
                    Button { make(.copy) } label: { Label(form.installer == nil ? "Copy command" : "Copy again", systemImage: "doc.on.doc") }
                        .modifier(ProminentStyle())
                    Button { make(.share) } label: { Image(systemName: "square.and.arrow.up") }.help("Share")
                    Button { make(.download) } label: { Image(systemName: "arrow.down.circle") }.help("Download a .cmd")
                    if form.working { ProgressView().controlSize(.small) }
                }
                .disabled(form.working)
                if let inst = form.installer {
                    Text(inst.command).font(.caption2.monospaced()).lineLimit(1).truncationMode(.middle)
                        .textSelection(.enabled).foregroundStyle(.secondary)
                }
            }
            StepRow(n: 3, title: "Run it on the PC") {
                Text("**Win+X › Terminal**, paste, Enter. No admin needed. It appears on the map once it's online.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if form.installer != nil {
                Label("One-time link, valid 48 h. Your own PCs only.", systemImage: "lock.shield")
                    .font(.caption).foregroundStyle(Atlas.amber)
            }
            if let err = form.error { Text(err).font(.caption).foregroundStyle(Atlas.red).textSelection(.enabled) }
        }
        }
    }

    private func nearest(_ country: String) -> String {
        guard let p = Countries.point(country) else { return vpn.regions.first?.code ?? "in" }
        return vpn.regions.min { Countries.distance($0.point, p) < Countries.distance($1.point, p) }?.code ?? "in"
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
                    let name = form.name.trimmingCharacters(in: .whitespaces)
                    inst = try await vpn.createExitInstaller(regionCode: form.regionCode,
                                                             name: name.isEmpty ? nil : name, country: form.country)
                }
                form.installer = inst
                form.installerRegion = form.regionCode
                switch how {
                case .copy:
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(inst.command, forType: .string)
                case .share:
                    if let view = NSApp.keyWindow?.contentView {
                        NSSharingServicePicker(items: [inst.command]).show(relativeTo: view.bounds, of: view, preferredEdge: .minY)
                    }
                case .download:
                    NSWorkspace.shared.activateFileViewerSelecting([inst.file])
                }
            } catch { form.error = error.localizedDescription }
            form.working = false
        }
    }
}

@MainActor
final class AddExitForm: ObservableObject {
    @Published var direct = false
    @Published var name = ""
    @Published var country = ""
    @Published var regionCode = "in"
    @Published var relayPinned = false
    @Published var working = false
    @Published var error: String?
    @Published var installer: VPNController.ExitInstaller?
    var installerRegion = ""
}
