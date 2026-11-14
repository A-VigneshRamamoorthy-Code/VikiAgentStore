#if os(macOS)
import AppKit
#endif
import SwiftUI

/// The big round connect / disconnect button. Once connected it wears a mint lock badge.
struct PowerButton: View {
    let tone: MapTone
    let busy: Bool
    var size: CGFloat = 74
    let action: () -> Void

    var body: some View {
        let tint = busy ? Atlas.amber : tone == .secure ? Atlas.green : Atlas.blue
        Group {
            if #available(macOS 26, *) {
                Button(action: action) { icon.foregroundStyle(.white).frame(width: size, height: size).contentShape(Circle()) }
                    .buttonStyle(.plain)
                    .glassEffect(.regular.tint(tint).interactive(), in: Circle())
                    .shadow(color: tint.opacity(0.35), radius: 14, y: 4)
            } else {
                Button(action: action) {
                    icon.foregroundStyle(.white).frame(width: size, height: size)
                        .background(Circle().fill(LinearGradient(colors: [tint.opacity(0.85), tint], startPoint: .top, endPoint: .bottom)))
                        .shadow(color: tint.opacity(0.4), radius: 12, y: 4)
                }
                .buttonStyle(.plain)
            }
        }
        .overlay(alignment: .topTrailing) {
            if tone == .secure && !busy {
                Image(systemName: "lock.fill")
                    .font(.system(size: size * 0.15, weight: .bold))
                    .foregroundStyle(PanelInk.onAccent)
                    .frame(width: size * 0.34, height: size * 0.34)
                    .background(Circle().fill(Atlas.mint))
                    .overlay(Circle().strokeBorder(.white.opacity(0.7), lineWidth: 1.5))
                    .shadow(color: Atlas.mint.opacity(0.5), radius: 6)
                    .offset(x: size * 0.04, y: -size * 0.04)
                    .transition(.scale(scale: 0.3).combined(with: .opacity))
                    .accessibilityHidden(true)
            }
        }
        .animation(.spring(duration: 0.45, bounce: 0.4), value: tone)
        .accessibilityLabel(tone == .secure ? "Disconnect" : "Connect")
    }

    @ViewBuilder private var icon: some View {
        if busy { ProgressView().controlSize(.regular).tint(.white) }
        else { Image(systemName: "power").font(.system(size: size * 0.35, weight: .bold)) }
    }
}

extension VPNController {
    var choiceSubtitle: String {
        if phase.busy { return phase.label }
        if phase == .connected, let e = egress { return e.city ?? Countries.name(e.country) }
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

    /// A new public IP is being fetched for the connected location.
    var switchingIP: Bool { phase == .starting("Switching IP…") }

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
    var ns: Namespace.ID

    var body: some View {
        let tone = vpn.phase.tone
        GlassGroup(spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: tone.lockSymbol)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(tone == .secure ? PanelInk.accent : tone.color)
                    .contentTransition(.symbolEffect(.replace))
                    .symbolEffect(.pulse, isActive: tone == .connecting)
                    .symbolEffect(.bounce, value: tone == .secure)
                    .frame(width: 42, height: 42)
                    .glass(21, interactive: true, tint: tone.color.opacity(0.18), id: "status", in: ns)
                if let detail {
                    Text(detail)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(tone == .secure ? .primary : .secondary).lineLimit(1)
                        .contentTransition(.opacity)
                        .padding(.horizontal, 14).frame(height: 42)
                        .glass(21, interactive: true, id: "detail", in: ns)
                }
            }
        }
        .help(vpn.phase.label)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(vpn.phase == .connected ? "Protected" : vpn.phase.label)
    }

    private var detail: String? {
        if vpn.phase == .connected { return "Protected" }
        if vpn.phase.busy { return vpn.phase.label }
        return nil
    }
}

func flag(_ country: String) -> String {
    country.uppercased().unicodeScalars.compactMap { UnicodeScalar(127397 + $0.value) }.map(String.init).joined()
}

struct ConnectCard: View {
    @EnvironmentObject var vpn: VPNController
    var compact = false
    /// iOS: the card sits flush with the bottom of the screen and follows its corner radius.
    var docked = false

    var body: some View {
        VStack(spacing: compact ? 12 : 18) {
            if !compact { header }
            if case .failed(let why) = vpn.phase {
                Label(why, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                    .frame(maxWidth: .infinity, alignment: .leading).lineLimit(2)
            }
            if showPrefs, let code = vpn.choice?.region?.code {
                ServerToggles(code: code, compact: true, dense: compact)
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
            if vpn.phase == .connected || vpn.switchingIP, vpn.egress != nil || vpn.switchingIP {
                PanelIPRow(code: switchCode, dense: compact)
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
            VStack(spacing: compact ? 10 : 14) {
                CostChips()
                if vpn.needsSignIn {
                    PrimaryButton(title: "Sign in again", icon: "person.crop.circle") { vpn.signIn() }
                } else {
                    PowerButton(tone: vpn.phase.tone, busy: vpn.phase.busy, size: compact ? 64 : 74) {
                        vpn.phase == .connected ? vpn.disconnect() : vpn.connect()
                    }
                    .disabled(vpn.phase.busy || vpn.choice == nil || vpn.working)
                }
            }
        }
        .animation(.snappy(duration: 0.3), value: showPrefs)
        .modifier(PanelCardChrome(compact: compact, docked: docked, busy: vpn.phase.busy, color: vpn.phase.tone.color))
    }

    private var header: some View {
        HStack(spacing: 12) {
            FlagBadge(country: vpn.choice.map(\.country), size: 44)
                .id(vpn.choice?.id)
                .transition(.scale(scale: 0.6).combined(with: .opacity))
            VStack(alignment: .leading, spacing: 2) {
                Text(vpn.choice?.title ?? "Add a location").font(.title3.weight(.semibold)).lineLimit(1)
                Text(vpn.choiceSubtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    .contentTransition(.opacity)
            }
            Spacer()
            CreditRing()
        }
        .animation(.spring(duration: 0.4), value: vpn.choice?.id)
    }

    /// Per-location cost switches, offered every time a connection is about to be made.
    private var showPrefs: Bool {
        guard vpn.hasAzure, let c = vpn.choice, !c.isHome else { return false }
        switch vpn.phase { case .idle, .failed: return true; default: return false }
    }

    /// The connected Azure location, when its address can be switched.
    private var switchCode: String? {
        guard let code = vpn.current?.region, vpn.regions.contains(where: { $0.code == code }) else { return nil }
        return code
    }
}

/// The card's glass and, while busy, the light running round its edge. Docked (iOS), it spans
/// the full width and runs through the bottom safe area, its lower corners following the display.
private struct PanelCardChrome: ViewModifier {
    let compact: Bool
    let docked: Bool
    let busy: Bool
    let color: Color

    func body(content: Content) -> some View {
        #if os(iOS)
        if docked {
            let shape = ConcentricRectangle(uniformTopCorners: .fixed(Self.topRadius),
                                            uniformBottomCorners: .concentric(minimum: .fixed(Self.displayRadius)))
            content
                .padding(.horizontal, 22).padding(.top, 22).padding(.bottom, 6)
                .frame(maxWidth: .infinity)
                .background {
                    Color.clear
                        .glassEffect(.regular, in: shape)
                        .overlay { if busy { RunningBorder(shape: shape, color: color) } }
                        .ignoresSafeArea(.container, edges: .bottom)
                }
        } else { floating(content) }
        #else
        floating(content)
        #endif
    }

    private func floating(_ content: Content) -> some View {
        content
            .padding(compact ? 16 : 20)
            .glass(Self.radius)
            .overlay { if busy { RunningBorder(radius: Self.radius, color: color) } }
    }

    static let radius: CGFloat = 30
    static let topRadius: CGFloat = 34
    /// Modern iPhones' screen corners (used when the system can't resolve them).
    static let displayRadius: CGFloat = 55
}

/// Light that runs around the card's edge while a connection is being made.
struct RunningBorder<S: Shape>: View {
    let shape: S
    let color: Color

    var body: some View {
        TimelineView(.animation) { tl in
            let f = CGFloat((tl.date.timeIntervalSinceReferenceDate / 1.8).truncatingRemainder(dividingBy: 1))
            let len: CGFloat = 0.22
            let style = StrokeStyle(lineWidth: 2.5, lineCap: .round)
            ZStack {
                shape.stroke(color.opacity(0.18), lineWidth: 1)
                Group {
                    shape.trim(from: f, to: min(1, f + len)).stroke(color, style: style)
                    shape.trim(from: 0, to: max(0, f + len - 1)).stroke(color, style: style)
                }
                .shadow(color: color.opacity(0.8), radius: 6)
            }
        }
        .allowsHitTesting(false)
    }
}

extension RunningBorder where S == RoundedRectangle.InsetShape {
    init(radius: CGFloat, color: Color) {
        self.init(shape: RoundedRectangle(cornerRadius: radius, style: .continuous).inset(by: 1.25), color: color)
    }
}

/// Cost and time at a glance: one quiet line instead of a row of chips.
struct CostChips: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let items = self.items
        if !items.isEmpty {
            ViewThatFits(in: .horizontal) {
                line(items)
                line(Array(items.prefix(2)))
            }
            .frame(maxWidth: .infinity)
            .animation(.snappy, value: items.map(\.text))
        }
    }

    private struct Item: Identifiable {
        let icon: String
        let text: String
        var tint: Color = .secondary
        var help = ""
        var id: String { icon }
    }

    private func line(_ items: [Item]) -> some View {
        HStack(spacing: 6) {
            ForEach(Array(items.enumerated()), id: \.element.id) { i, item in
                if i > 0 { Circle().fill(.tertiary).frame(width: 3, height: 3) }
                HStack(spacing: 4) {
                    Image(systemName: item.icon).font(.system(size: 11, weight: .semibold)).foregroundStyle(item.tint)
                    Text(item.text).font(.footnote.weight(.medium)).monospacedDigit().foregroundStyle(.secondary)
                        .contentTransition(.numericText())
                }
                .fixedSize()
                .help(item.help)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var items: [Item] {
        var out: [Item] = []
        if let c = vpn.current, vpn.phase == .connected {
            out.append(Item(icon: "timer", text: formatDuration(c.duration)))
            out.append(Item(icon: "arrow.up.arrow.down",
                            text: formatBytes(max(c.rxBytes + c.txBytes, (vpn.tunnel.rx ?? 0) + (vpn.tunnel.tx ?? 0)))))
            if c.vmPerHour > 0 {
                out.append(Item(icon: "banknote", text: "≈ " + formatMoney(c.vmPerHour * c.duration / 3600, c.currency),
                                tint: PanelInk.accent))
            }
        } else if let ch = vpn.choice {
            if ch.direct != nil {
                out.append(Item(icon: "banknote", text: "Free", tint: PanelInk.accent))
            } else if let r = vpn.hourlyRate(ch) {
                out.append(Item(icon: "banknote", text: "≈ \(formatMoney(r.amount, r.currency))/h", tint: PanelInk.accent,
                                help: "Typical cost per connected hour"))
            }
            if let code = ch.region?.code {
                let cold = ch.unbuilt || ["deleted", "building"].contains(vpn.regionStates[code] ?? "")
                out.append(Item(icon: cold ? "hourglass" : "bolt.fill", text: cold ? "~2 min" : "~40 s",
                                tint: cold ? Atlas.amber : PanelInk.accent,
                                help: cold ? "The server is set up fresh on connect" : "The server is ready to start"))
            }
            if let l = vpn.lastCompleted ?? vpn.store.sessions.first, !vpn.phase.busy {
                let waiting = l.vmStoppedAt == nil
                out.append(Item(icon: waiting ? "hourglass.bottomhalf.filled" : "clock.arrow.circlepath",
                                text: "Last \(formatMoney(l.total, l.currency))",
                                tint: waiting ? Atlas.amber : .secondary,
                                help: "\(formatDuration(l.duration)) · \(waiting ? "waiting for the server to stop" : "server stopped")"))
            }
        }
        return out
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
