#if os(macOS)
import AppKit
#endif
import SwiftUI

enum HomeSheet: String, Identifiable { case history, settings, addPC; var id: String { rawValue } }

/// A round glass button; `prominent` fills it with the tint (used for "+").
struct CircleButton: View {
    let icon: String
    var help = ""
    var prominent = false
    var tint: Color = Atlas.blue
    let action: () -> Void

    var body: some View {
        if #available(macOS 26, *) {
            Button(action: action) {
                Image(systemName: icon).font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(prominent ? .white : .primary)
                    .frame(width: 42, height: 42).contentShape(Circle())
            }
            .buttonStyle(.plain)
            .glassEffect(prominent ? .regular.tint(tint).interactive() : .regular.interactive(), in: Circle())
            .help(help)
            .accessibilityLabel(help.isEmpty ? icon : help)
        } else {
            Button(action: action) {
                Image(systemName: icon).font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(prominent ? .white : .primary)
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(prominent ? tint : .clear))
                    .contentShape(Circle())
            }
            .buttonStyle(.plain).glass(20).help(help)
        }
    }
}

/// The big round connect / disconnect button.
struct PowerButton: View {
    let tone: MapTone
    let busy: Bool
    let action: () -> Void

    var body: some View {
        let tint = busy ? Atlas.amber : tone == .secure ? Atlas.green : Atlas.blue
        Group {
            if #available(macOS 26, *) {
                Button(action: action) { icon.foregroundStyle(.white).frame(width: 74, height: 74).contentShape(Circle()) }
                    .buttonStyle(.plain)
                    .glassEffect(.regular.tint(tint).interactive(), in: Circle())
                    .shadow(color: tint.opacity(0.35), radius: 14, y: 4)
            } else {
                Button(action: action) {
                    icon.foregroundStyle(.white).frame(width: 74, height: 74)
                        .background(Circle().fill(LinearGradient(colors: [tint.opacity(0.85), tint], startPoint: .top, endPoint: .bottom)))
                        .shadow(color: tint.opacity(0.4), radius: 12, y: 4)
                }
                .buttonStyle(.plain)
            }
        }
        .accessibilityLabel(tone == .secure ? "Disconnect" : "Connect")
    }

    @ViewBuilder private var icon: some View {
        if busy { ProgressView().controlSize(.regular).tint(.white) }
        else { Image(systemName: "power").font(.system(size: 26, weight: .bold)) }
    }
}

struct AtlasHome: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var sheet = Box<HomeSheet?>(nil)
    @Namespace private var glassNS

    var body: some View {
        ZStack {
            AtlasMap(pins: vpn.mapPins, selected: vpn.choice?.id, home: vpn.home, tone: vpn.phase.tone) { id in
                guard vpn.phase == .idle || isFailed else { return }
                vpn.select(id)
            }
            .ignoresSafeArea()

            VStack {
                HStack(alignment: .center) {
                    StatusCapsule(ns: glassNS)
                    Spacer(minLength: 12)
                    GlassGroup(spacing: 10) {
                        HStack(spacing: 10) {
                            CircleButton(icon: "chart.bar.xaxis", help: "Usage") { sheet.v = .history }
                            CircleButton(icon: "gearshape", help: "Settings") { sheet.v = .settings }
                            CircleButton(icon: "plus", help: "Add a home PC", prominent: true) {
                                sheet.v = .addPC
                            }
                            .disabled(vpn.working)
                        }
                    }
                }
                Spacer()
                ConnectCard().frame(maxWidth: 400)
            }
            .padding(18)
        }
        .sheet(item: $sheet.v) { s in
            Group {
                switch s {
                case .history: HistorySheet()
                case .settings: SettingsSheet()
                case .addPC: AddHomeExitSheet()
                }
            }
            .environmentObject(vpn)
        }
        .onReceive(vpn.$requestedSheet.compactMap { $0 }) { s in
            sheet.v = s
            vpn.requestedSheet = nil
        }
        .onReceive(vpn.$sheetDismissals.dropFirst()) { _ in sheet.v = nil }
        .animation(.spring(duration: 0.4), value: vpn.phase)
    }

    private var isFailed: Bool { if case .failed = vpn.phase { return true }; return false }
}

extension VPNController {
    var choiceSubtitle: String {
        if phase.busy { return phase.label }
        if phase == .connected, let e = egress { return "\(e.city ?? Countries.name(e.country)) · \(e.ip)" }
        return choice?.subtitle ?? ""
    }

    var mapPins: [MapPin] {
        let azure = exitRegions.map {
            MapPin(id: $0.code, title: "\($0.flag) \($0.name)", point: $0.point, kind: .azure,
                   asleep: regionStates[$0.code] != "running")
        }
        let homes = exits.compactMap { e -> MapPin? in
            guard let p = e.point ?? regions.first(where: { $0.code == e.region })?.point else { return nil }
            return MapPin(id: "exit:\(e.id)", title: "\(e.flag) \(e.name)", point: p, kind: .home,
                          asleep: regionStates[e.region] != "running")
        }
        let direct = setup.direct.compactMap { d -> MapPin? in
            d.point.map { MapPin(id: "pc:\(d.id)", title: "\(d.flag) \(d.name)", point: $0, kind: .direct) }
        }
        let available = unbuiltChoices.compactMap { c -> MapPin? in
            c.region.map { MapPin(id: $0.code, title: "\($0.flag) \($0.name)", point: $0.point, kind: .available) }
        }
        return available + azure + homes + direct
    }

    func select(_ id: String) {
        selected = id
        UserDefaults.standard.set(id, forKey: "region")
    }

    /// Typical cost per connected hour for a location, from past sessions there.
    func hourlyRate(_ c: ServerChoice) -> Money? {
        guard let code = c.region?.code else { return nil }
        guard let s = store.sessions.first(where: { $0.region == code && $0.vmPerHour > 0 }) else { return nil }
        return Money(amount: s.vmPerHour, currency: s.currency)
    }
}

struct StatusCapsule: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var pulse = Box(false)
    var ns: Namespace.ID

    var body: some View {
        let tone = vpn.phase.tone
        GlassGroup(spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: tone.symbol)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(tone.color)
                    .scaleEffect(tone == .connecting && pulse.v ? 1.15 : 1)
                    .animation(tone == .connecting ? .easeInOut(duration: 0.7).repeatForever() : .default, value: pulse.v)
                    .onAppear { pulse.v = true }
                    .frame(width: 42, height: 42)
                    .glass(21, interactive: true, tint: tone.color.opacity(0.18), id: "status", in: ns)
                if let detail {
                    Text(detail.text).font(detail.mono ? .caption.monospacedDigit() : .caption)
                        .foregroundStyle(detail.mono ? .primary : .secondary).lineLimit(1)
                        .padding(.horizontal, 14).frame(height: 42)
                        .glass(21, interactive: true, id: "detail", in: ns)
                }
            }
        }
        .help(vpn.phase.label)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(vpn.phase.label)
    }

    private var detail: (text: String, mono: Bool)? {
        if let e = vpn.egress, vpn.phase == .connected { return ("\(flag(e.country)) \(e.ip)", true) }
        if vpn.phase.busy { return (vpn.phase.label, false) }
        return nil
    }
}

func flag(_ country: String) -> String {
    country.uppercased().unicodeScalars.compactMap { UnicodeScalar(127397 + $0.value) }.map(String.init).joined()
}

struct ConnectCard: View {
    @EnvironmentObject var vpn: VPNController
    var compact = false

    var body: some View {
        VStack(spacing: compact ? 12 : 16) {
            if !compact { HStack(spacing: 12) {
                Text(vpn.choice?.flag ?? "🌐").font(.system(size: compact ? 28 : 34))
                VStack(alignment: .leading, spacing: 2) {
                    Text(vpn.choice?.title ?? "Add a location").font(.title3.weight(.semibold)).lineLimit(1)
                    Text(subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                CreditRing()
            } }
            if case .failed(let why) = vpn.phase {
                Label(why, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                    .frame(maxWidth: .infinity, alignment: .leading).lineLimit(2)
            }
            if !compact, showPrefs, let code = vpn.choice?.region?.code {
                ServerToggles(code: code, compact: true)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(Color.primary.opacity(0.04), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
            CostChips()
            if vpn.phase == .connected || vpn.phase == .starting("Switching IP…"),
               let code = vpn.current?.region, vpn.regions.contains(where: { $0.code == code }) {
                HStack(spacing: 8) {
                    Image(systemName: "network").foregroundStyle(.secondary)
                    Text(vpn.egress?.ip ?? "—").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                        .lineLimit(1).truncationMode(.middle).textSelection(.enabled)
                    Spacer(minLength: 4)
                    SwitchIPButton(code: code)
                }
                .padding(.horizontal, 4)
            }
            if vpn.needsSignIn {
                PrimaryButton(title: "Sign in again", icon: "person.crop.circle") { vpn.signIn() }
            } else {
                PowerButton(tone: vpn.phase.tone, busy: vpn.phase.busy) {
                    vpn.phase == .connected ? vpn.disconnect() : vpn.connect()
                }
                .disabled(vpn.phase.busy || vpn.choice == nil || vpn.working)
            }
        }
        .padding(compact ? 16 : 20)
        .glass()
        .overlay { if vpn.phase.busy { RunningBorder(radius: 30, color: vpn.phase.tone.color) } }
    }

    /// Per-location cost switches, offered every time a connection is about to be made.
    private var showPrefs: Bool {
        guard vpn.hasAzure, let c = vpn.choice, !c.isHome else { return false }
        switch vpn.phase { case .idle, .failed: return true; default: return false }
    }

    private var subtitle: String { vpn.choiceSubtitle }
}

/// Light that runs around the card's edge while a connection is being made.
struct RunningBorder: View {
    let radius: CGFloat
    let color: Color

    var body: some View {
        TimelineView(.animation) { tl in
            let f = CGFloat((tl.date.timeIntervalSinceReferenceDate / 1.8).truncatingRemainder(dividingBy: 1))
            let len: CGFloat = 0.22
            let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
            let style = StrokeStyle(lineWidth: 2.5, lineCap: .round)
            ZStack {
                shape.strokeBorder(color.opacity(0.18), lineWidth: 1)
                Group {
                    shape.inset(by: 1.25).trim(from: f, to: min(1, f + len)).stroke(color, style: style)
                    shape.inset(by: 1.25).trim(from: 0, to: max(0, f + len - 1)).stroke(color, style: style)
                }
                .shadow(color: color.opacity(0.8), radius: 6)
            }
        }
        .allowsHitTesting(false)
    }
}

/// Cost at a glance, above the button.
struct CostChips: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        HStack(spacing: 6) {
            if let c = vpn.current, vpn.phase == .connected {
                Chip(icon: "timer", text: formatDuration(c.duration))
                Chip(icon: "arrow.up.arrow.down", text: formatBytes(max(c.rxBytes + c.txBytes, (vpn.tunnel.rx ?? 0) + (vpn.tunnel.tx ?? 0))))
                if c.vmPerHour > 0 {
                    Chip(icon: "dollarsign.circle", text: "≈ " + formatMoney(c.vmPerHour * c.duration / 3600, c.currency), tint: Atlas.green)
                }
            } else if let ch = vpn.choice {
                if ch.direct != nil {
                    Chip(icon: "dollarsign.circle", text: "Free", tint: Atlas.green)
                } else if let r = vpn.hourlyRate(ch) {
                    Chip(icon: "dollarsign.circle", text: "≈ \(formatMoney(r.amount, r.currency))/h", tint: Atlas.green)
                }
                if let code = ch.region?.code {
                    let cold = ch.unbuilt || ["deleted", "building"].contains(vpn.regionStates[code] ?? "")
                    Chip(icon: "timer", text: cold ? "~2 min" : "~40 s", tint: cold ? Atlas.amber : .secondary)
                }
                if let l = vpn.lastCompleted ?? vpn.store.sessions.first, !vpn.phase.busy {
                    Chip(icon: l.vmStoppedAt == nil ? "hourglass" : "checkmark.circle",
                         text: "Last \(formatMoney(l.total, l.currency))", tint: l.vmStoppedAt == nil ? Atlas.amber : Atlas.green)
                        .help("\(formatDuration(l.duration)) · \(l.vmStoppedAt == nil ? "waiting for the server to stop" : "server stopped")")
                }
            }
        }
        .frame(maxWidth: .infinity)
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
