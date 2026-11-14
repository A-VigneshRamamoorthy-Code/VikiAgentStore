#if os(macOS)
import AppKit
#endif
import SwiftUI

/// The big round connect / disconnect button. Its glyph is the connection itself: an open
/// lock while exposed, pulsing inside a running ring while connecting, and a lock that snaps
/// shut once the tunnel is up.
struct PowerButton: View {
    let tone: MapTone
    let busy: Bool
    var size: CGFloat = 74
    let action: () -> Void
    @State private var closes = 0

    private var locked: Bool { tone == .secure && !busy }

    var body: some View {
        let tint = busy ? Atlas.amber : tone == .secure ? Atlas.green : Atlas.blue
        Group {
            if #available(macOS 26, *) {
                Button(action: action) { face.frame(width: size, height: size).contentShape(Circle()) }
                    .buttonStyle(.plain)
                    .glassEffect(.regular.tint(tint).interactive(), in: Circle())
                    .shadow(color: tint.opacity(0.35), radius: 14, y: 4)
            } else {
                Button(action: action) {
                    face.frame(width: size, height: size)
                        .background(Circle().fill(LinearGradient(colors: [tint.opacity(0.85), tint], startPoint: .top, endPoint: .bottom)))
                        .shadow(color: tint.opacity(0.4), radius: 12, y: 4)
                }
                .buttonStyle(.plain)
            }
        }
        .focusEffectDisabled()
        .onChange(of: locked) { _, now in if now { closes += 1 } }
        .sensoryFeedback(.success, trigger: closes)
        .animation(.spring(duration: 0.45, bounce: 0.4), value: tone)
        .animation(.easeInOut(duration: 0.3), value: busy)
        .accessibilityLabel(tone == .secure ? "Disconnect" : "Connect")
        .accessibilityValue(busy ? "Connecting" : locked ? "Protected" : "Not protected")
    }

    /// White glyph on the filled button; it pulses while busy.
    private var face: some View {
        ZStack {
            Image(systemName: locked ? "lock.fill" : "lock.open.fill")
                .font(.system(size: size * 0.33, weight: .bold))
                .contentTransition(.symbolEffect(.replace.downUp))
                .symbolEffect(.bounce.down, value: closes)
                .symbolEffect(.pulse, isActive: busy)
        }
        .foregroundStyle(.white)
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
            MapPin(id: $0.code, title: $0.name, point: $0.point, kind: .azure,
                   asleep: regionStates[$0.code] != "running", countryCode: $0.country)
        }
        let homes = exits.compactMap { e -> MapPin? in
            guard let p = e.point ?? regions.first(where: { $0.code == e.region })?.point else { return nil }
            return MapPin(id: "exit:\(e.id)", title: e.name, point: p, kind: .home,
                          asleep: regionStates[e.region] != "running", countryCode: e.country)
        }
        let direct = setup.direct.compactMap { d -> MapPin? in
            d.point.map { MapPin(id: "pc:\(d.id)", title: d.name, point: $0, kind: .direct, countryCode: d.country) }
        }
        let available = unbuiltChoices.compactMap { c -> MapPin? in
            c.region.map { MapPin(id: $0.code, title: $0.name, point: $0.point, kind: .available, countryCode: $0.country) }
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

/// Top-left status: a quiet text capsule with a tone dot, shown only while connecting or
/// connected (the connect button's lock carries the idle state).
struct StatusCapsule: View {
    @EnvironmentObject var vpn: VPNController
    var ns: Namespace.ID

    var body: some View {
        let tone = vpn.phase.tone
        GlassGroup(spacing: 8) {
            if let detail {
                HStack(spacing: 8) {
                    Circle().fill(tone.color).frame(width: 7, height: 7)
                        .shadow(color: tone.color.opacity(0.6), radius: 3)
                        .accessibilityHidden(true)
                    Text(detail)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(tone == .secure ? .primary : .secondary).lineLimit(1)
                        .contentTransition(.opacity)
                }
                .padding(.horizontal, 14).frame(height: 42)
                .glass(21, id: "detail", in: ns)
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
                SessionStats(dense: compact)
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

/// The card's glass and, while busy, the light running round its edge. Docked (iOS), it floats
/// just inside the screen's sides and bottom, its lower corners concentric with the display's.
private struct PanelCardChrome: ViewModifier {
    let compact: Bool
    let docked: Bool
    let busy: Bool
    let color: Color

    func body(content: Content) -> some View {
        #if os(iOS)
        if docked {
            content.phoneDock(busy: busy, color: color)
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
}

#if os(iOS)
/// A phone's bottom card: glass that sits just inside the screen's sides and bottom, its lower
/// corners concentric with the display's. Callers let it run through the bottom safe area.
private struct PhoneDock: ViewModifier {
    let busy: Bool
    let color: Color

    func body(content: Content) -> some View {
        let shape = ConcentricRectangle(uniformTopCorners: .fixed(38),
                                        uniformBottomCorners: .concentric(minimum: .fixed(Self.displayRadius - Self.inset)))
        content
            .padding(.horizontal, 22).padding(.top, 22).padding(.bottom, 26)
            .frame(maxWidth: .infinity)
            .background {
                Color.clear
                    .glassEffect(.regular, in: shape)
                    .overlay { if busy { RunningBorder(shape: shape, color: color) } }
            }
            .padding(.horizontal, Self.inset).padding(.bottom, Self.inset)
    }

    /// Modern iPhones' screen corners (used when the system can't resolve them).
    static let displayRadius: CGFloat = 55
    /// Gap between the card and the screen's edges.
    static let inset: CGFloat = 10
}

extension View {
    func phoneDock(busy: Bool = false, color: Color = .clear) -> some View {
        modifier(PhoneDock(busy: busy, color: color))
    }
}
#endif

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

/// Cost and time at a glance: a segmented glass strip of up to three cells — a small
/// monochrome symbol and bold value over a tiny caption. Idle it shows the rate, time to
/// connect and the last session; connected, time on, data and cost so far.
struct SessionStats: View {
    @EnvironmentObject var vpn: VPNController
    var dense = false

    var body: some View {
        let items = self.items
        if !items.isEmpty {
            ViewThatFits(in: .horizontal) {
                strip(items)
                strip(Array(items.prefix(2)))
            }
            .frame(maxWidth: .infinity)
            .animation(.snappy(duration: 0.3), value: items.map(\.id))
        }
    }

    struct Item: Identifiable {
        let id: String
        let icon: String
        let value: String
        let caption: String
        var help = ""
        /// Draws the cell in amber: the value is worse than usual (e.g. a slower connect).
        var warn = false
    }

    private func strip(_ items: [Item]) -> some View {
        HStack(spacing: 0) {
            ForEach(Array(items.enumerated()), id: \.element.id) { i, item in
                if i > 0 {
                    Rectangle().fill(Color.primary.opacity(0.1)).frame(width: 1, height: dense ? 20 : 24)
                }
                cell(item).transition(.opacity)
            }
        }
        .padding(.horizontal, 4)
        .frame(height: dense ? 44 : 50)
        .glass(dense ? 14 : 16)
    }

    private func cell(_ item: Item) -> some View {
        VStack(spacing: 2) {
            HStack(spacing: 5) {
                Image(systemName: item.icon)
                    .font(.system(size: dense ? 10 : 11, weight: .semibold))
                    .foregroundStyle(item.warn ? AnyShapeStyle(Atlas.amber) : AnyShapeStyle(.secondary))
                    .contentTransition(.symbolEffect(.replace))
                    .symbolEffect(.bounce, value: item.warn)
                    .frame(width: dense ? 12 : 14)
                Text(item.value)
                    .font((dense ? Font.footnote : .callout).weight(.semibold).monospacedDigit())
                    .foregroundStyle(item.warn ? AnyShapeStyle(Atlas.amber) : AnyShapeStyle(.primary))
                    .contentTransition(.numericText())
                    .lineLimit(1)
            }
            Text(item.caption)
                .font(.system(size: dense ? 9.5 : 10.5, weight: .medium))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal, dense ? 10 : 12)
        .padding(.vertical, 3)
        .background {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Atlas.amber.opacity(item.warn ? 0.14 : 0))
                .padding(.horizontal, 2)
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.6), value: item.warn)
        .frame(minWidth: dense ? 76 : 88)
        .fixedSize(horizontal: true, vertical: false)
        .help(item.help)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(item.value) \(item.caption)")
    }

    private var items: [Item] {
        var out: [Item] = []
        if let c = vpn.current, vpn.phase == .connected || vpn.switchingIP {
            out.append(Item(id: "time", icon: "timer", value: formatDuration(c.duration), caption: "connected"))
            out.append(Item(id: "data", icon: "arrow.up.arrow.down",
                            value: formatBytes(max(c.rxBytes + c.txBytes, (vpn.tunnel.rx ?? 0) + (vpn.tunnel.tx ?? 0))),
                            caption: "data"))
            if c.vmPerHour > 0 {
                out.append(Item(id: "spent", icon: "banknote", value: "≈ " + formatMoney(c.vmPerHour * c.duration / 3600, c.currency),
                                caption: "this session"))
            }
        } else if let ch = vpn.choice {
            if ch.direct != nil {
                out.append(Item(id: "rate", icon: "banknote", value: "Free", caption: "home PC"))
            } else if let r = vpn.hourlyRate(ch) {
                out.append(Item(id: "rate", icon: "banknote", value: "≈ " + formatMoney(r.amount, r.currency),
                                caption: "per hour", help: "Typical cost per connected hour"))
            }
            if let code = ch.region?.code {
                let state = vpn.regionStates[code] ?? ""
                let saveCost = vpn.ephemeral(code)
                // Not built yet (or removed while in Save cost): the next connect rebuilds it.
                let absent = ch.unbuilt || ["deleted", "building"].contains(state)
                if saveCost && state != "running" {
                    out.append(Item(id: "ready", icon: "hourglass", value: "~2 min", caption: "to connect",
                                    help: "Save cost rebuilds the server on every connect", warn: true))
                } else if absent {
                    // Fast connect keeps the server after this one rebuild.
                    out.append(Item(id: "ready", icon: "hourglass", value: "~2 min", caption: "first, then ~40 s",
                                    help: "The server is rebuilt once, then kept ready, so later connects take ~40 s"))
                } else {
                    out.append(Item(id: "ready", icon: "bolt", value: "~40 s", caption: "to connect",
                                    help: "The server is ready to start"))
                }
            }
            if let l = vpn.lastCompleted ?? vpn.store.sessions.first, !vpn.phase.busy {
                let waiting = l.vmStoppedAt == nil
                out.append(Item(id: "last", icon: "clock.arrow.circlepath", value: formatMoney(l.total, l.currency),
                                caption: waiting ? "server stopping" : "last session",
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
