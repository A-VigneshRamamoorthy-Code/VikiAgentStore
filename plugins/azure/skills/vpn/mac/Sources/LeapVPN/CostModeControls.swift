import SwiftUI

// MARK: - Formatted tooltips

/// A tooltip's content: a title, a few icon-led facts and an optional footnote.
struct TipInfo {
    struct Line: Hashable { let icon: String; let text: String }
    let title: String
    let icon: String
    let lines: [Line]
    var note: String? = nil

    var plain: String { ([title] + lines.map(\.text) + [note].compactMap { $0 }).joined(separator: "\n") }
}

/// The card a tooltip shows: title row, a hairline, then one line per fact.
struct TipCard: View {
    let tip: TipInfo

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: tip.icon)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(PanelInk.fill))
                Text(tip.title).font(.subheadline.weight(.semibold))
            }
            Divider().opacity(0.5)
            VStack(alignment: .leading, spacing: 7) {
                ForEach(tip.lines, id: \.self) { line in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Image(systemName: line.icon)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(PanelInk.accent)
                            .frame(width: 16)
                        Text(line.text).font(.callout)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            if let note = tip.note {
                Text(note).font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(width: 250, alignment: .leading)
    }
}

/// Shows `tip` as a formatted card: on hover (after a short delay) on the Mac, on long-press on iOS.
/// `action` is offered in the iOS long-press menu so the gesture never toggles by surprise.
private struct InfoTipModifier: ViewModifier {
    let tip: TipInfo
    var action: (title: String, run: () -> Void)?
    @State private var shown = false
    @State private var pending: Task<Void, Never>?

    func body(content: Content) -> some View {
        #if os(macOS)
        content
            .onHover { inside in
                pending?.cancel()
                if inside {
                    pending = Task { @MainActor in
                        try? await Task.sleep(for: .milliseconds(550))
                        if !Task.isCancelled { shown = true }
                    }
                } else {
                    shown = false
                }
            }
            .simultaneousGesture(TapGesture().onEnded { pending?.cancel(); shown = false })
            .popover(isPresented: $shown, arrowEdge: .bottom) { TipCard(tip: tip) }
            .accessibilityHint(tip.plain)
        #else
        content
            .contextMenu {
                if let action { Button(action.title, action: action.run) }
            } preview: {
                TipCard(tip: tip).background(.regularMaterial)
            }
            .accessibilityHint(tip.plain)
        #endif
    }
}

extension View {
    func infoTip(_ tip: TipInfo, action: (title: String, run: () -> Void)? = nil) -> some View {
        modifier(InfoTipModifier(tip: tip, action: action))
    }
}

// MARK: - Tips

enum CostTips {
    static let saveCost = TipInfo(
        title: "Save cost", icon: "leaf.fill",
        lines: [.init(icon: "moon.zzz.fill", text: "$0 while off"),
                .init(icon: "clock", text: "About 2 min to connect"),
                .init(icon: "arrow.triangle.2.circlepath", text: "New IP each time")],
        note: "The server is deleted when the last device disconnects, and rebuilt on the next connect.")

    static let fastConnect = TipInfo(
        title: "Fast connect", icon: "bolt.fill",
        lines: [.init(icon: "bolt", text: "About 40 s to connect"),
                .init(icon: "externaldrive.fill", text: "≈ $2.40 a month for the disk while off")],
        note: "The server is kept switched off between sessions, so it starts instead of being rebuilt.")

    static func staticIP(on: Bool, saveCost: Bool) -> TipInfo {
        if saveCost {
            return TipInfo(title: "Static IP", icon: "pin.slash.fill",
                           lines: [.init(icon: "arrow.triangle.2.circlepath", text: "New IP each time")],
                           note: "Needs Fast connect: Save cost deletes the IP along with the server.")
        }
        return on
            ? TipInfo(title: "Static IP", icon: "pin.fill",
                      lines: [.init(icon: "pin", text: "Same IP every time"),
                              .init(icon: "dollarsign.circle", text: "≈ $3.65 a month, kept while off")])
            : TipInfo(title: "Static IP", icon: "pin.slash.fill",
                      lines: [.init(icon: "arrow.triangle.2.circlepath", text: "New IP each time"),
                              .init(icon: "dollarsign.circle", text: "$0 while off")],
                      note: "Turn on to keep one address, e.g. for allow-lists.")
    }
}

// MARK: - Controls

enum CostControlSize { case small, dense, regular }

/// "Save cost | Fast connect" for one location (`code`) or the defaults (`nil`).
/// Save cost is the on-demand mode (`ephemeral`); Fast connect keeps the server.
struct CostModePicker: View {
    @EnvironmentObject var vpn: VPNController
    var code: String? = nil
    var size: CostControlSize = .regular
    @Namespace private var ns

    private var saveCost: Bool { code.map(vpn.ephemeral) ?? vpn.ephemeral }
    private var height: CGFloat { switch size { case .small: 28; case .dense: 34; case .regular: 40 } }

    var body: some View {
        HStack(spacing: 2) {
            segment(true, title: "Save cost", icon: "leaf.fill", tip: CostTips.saveCost)
            segment(false, title: "Fast connect", icon: "bolt.fill", tip: CostTips.fastConnect)
        }
        .padding(3)
        .frame(height: height)
        .glass(height / 2)
        .animation(.spring(response: 0.35, dampingFraction: 0.72), value: saveCost)
        .sensoryFeedback(.selection, trigger: saveCost)
    }

    private func segment(_ value: Bool, title: String, icon: String, tip: TipInfo) -> some View {
        let on = saveCost == value
        let set = { vpn.setEphemeral(value, for: code) }
        return Button(action: set) {
            HStack(spacing: 5) {
                Image(systemName: icon).font(.system(size: size == .small ? 10 : 12, weight: .semibold))
                Text(title).font((size == .regular ? Font.subheadline : .caption).weight(.semibold))
                    .lineLimit(1).minimumScaleFactor(0.8)
            }
            .foregroundStyle(on ? AnyShapeStyle(PanelInk.onAccent) : AnyShapeStyle(.secondary))
            .padding(.horizontal, size == .small ? 8 : 12)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background {
                if on { Capsule().fill(PanelInk.fill).matchedGeometryEffect(id: "pick", in: ns) }
            }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .infoTip(tip, action: on ? nil : (title: "Use \(title)", run: set))
        .accessibilityLabel(title)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// Static IP on/off as a glass capsule: deep fill and white glyph when on.
struct StaticIPPill: View {
    @EnvironmentObject var vpn: VPNController
    var code: String? = nil
    var size: CostControlSize = .regular
    var tint: Color = PanelInk.fill
    /// Fixed width so pills line up in a column (Settings).
    var width: CGFloat? = nil

    var body: some View {
        let saveCost = code.map(vpn.ephemeral) ?? vpn.ephemeral
        let on = (code.map(vpn.staticIP) ?? vpn.staticIP) && !saveCost
        let height: CGFloat = switch size { case .small: 28; case .dense: 34; case .regular: 40 }
        let toggle = { vpn.setStaticIP(!on, for: code) }
        Button(action: toggle) {
            HStack(spacing: 5) {
                Image(systemName: on ? "pin.fill" : "pin.slash")
                    .font(.system(size: size == .small ? 10 : 12, weight: .semibold))
                    .contentTransition(.symbolEffect(.replace))
                Text("Static IP").font((size == .regular ? Font.subheadline : .caption).weight(.semibold))
                    .lineLimit(1).fixedSize()
            }
            .foregroundStyle(on ? AnyShapeStyle(Color.white) : AnyShapeStyle(.secondary))
            .padding(.horizontal, size == .small ? 10 : 14)
            .frame(width: width, height: height)
            .background { if on { Capsule().fill(tint) } }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .glass(height / 2, interactive: true)
        .opacity(saveCost ? 0.45 : 1)
        .allowsHitTesting(!saveCost)
        .infoTip(CostTips.staticIP(on: on, saveCost: saveCost),
                 action: saveCost ? nil : (title: on ? "Turn off Static IP" : "Turn on Static IP", run: toggle))
        .animation(.smooth(duration: 0.25), value: on)
        .accessibilityLabel("Static IP")
        .accessibilityValue(on ? "On" : "Off")
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

// MARK: - Ad blocking

enum AdBlockTips {
    static func tip(on: Bool) -> TipInfo {
        TipInfo(title: on ? "Ad block on" : "Ad block off", icon: on ? "shield.lefthalf.filled" : "shield.slash",
                lines: [.init(icon: "checkmark.circle", text: "Ad networks and trackers, in browsers and apps"),
                        .init(icon: "xmark.circle", text: "Not YouTube, Instagram or Facebook ads: they come from the same servers as the videos and posts"),
                        .init(icon: "server.rack", text: "Filtered on your own server, nothing extra to pay")],
                note: "Netflix and Prime Video are never filtered. A browser or app forced to use its own secure DNS can't look names up while this is on: turn it off for that location.")
    }
}

/// Ad blocking on/off for one location (`code`) or the default for new ones (`nil`).
struct AdBlockPill: View {
    @EnvironmentObject var vpn: VPNController
    var code: String? = nil
    var size: CostControlSize = .regular
    var tint: Color = PanelInk.fill
    var width: CGFloat? = nil

    var body: some View {
        let on = code.map(vpn.adBlock) ?? vpn.adBlock
        let height: CGFloat = switch size { case .small: 28; case .dense: 34; case .regular: 40 }
        let toggle = { vpn.setAdBlock(!on, for: code) }
        Button(action: toggle) {
            HStack(spacing: 5) {
                Image(systemName: on ? "shield.lefthalf.filled" : "shield.slash")
                    .font(.system(size: size == .small ? 10 : 12, weight: .semibold))
                    .contentTransition(.symbolEffect(.replace))
                Text("Ad block").font((size == .regular ? Font.subheadline : .caption).weight(.semibold))
                    .lineLimit(1).fixedSize()
            }
            .foregroundStyle(on ? AnyShapeStyle(Color.white) : AnyShapeStyle(.secondary))
            .padding(.horizontal, size == .small ? 10 : 14)
            .frame(width: width, height: height)
            .background { if on { Capsule().fill(tint) } }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .glass(height / 2, interactive: true)
        .infoTip(AdBlockTips.tip(on: on), action: (title: on ? "Turn off Ad block" : "Turn on Ad block", run: toggle))
        .animation(.smooth(duration: 0.25), value: on)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel("Ad block")
        .accessibilityValue(on ? "On" : "Off")
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
