#if os(macOS)
import AppKit
#endif
import SwiftUI

/// Colours and small pieces shared by the connect panel (card, menu-bar popover, Settings rows).
enum PanelInk {
    /// Brand mint: bright on dark surfaces, deepened on light ones so it stays legible.
    static let accent = Platform.dynamic(light: (0.0, 0.62, 0.40), dark: (0.294, 1.0, 0.702))
    /// A solid green fill deep enough for a white glyph in both light and dark mode.
    static let fill = Platform.dynamic(light: (0.0, 0.60, 0.38), dark: (0.05, 0.66, 0.42))
    /// Glyphs drawn on a solid `fill` (or any saturated fill) are white.
    static let onAccent = Color.white
}

/// An SF Symbol that turns continuously while `spinning`.
struct PanelSpinGlyph: View {
    let name: String
    var spinning: Bool

    var body: some View {
        if spinning {
            TimelineView(.animation) { tl in
                let t = tl.date.timeIntervalSinceReferenceDate
                Image(systemName: name).rotationEffect(.degrees((t / 0.9).truncatingRemainder(dividingBy: 1) * 360))
            }
        } else {
            Image(systemName: name)
        }
    }
}

/// The public IP while connected: circular flag, address, and a refresh glyph that spins
/// while a new address is being fetched.
struct PanelIPRow: View {
    @EnvironmentObject var vpn: VPNController
    /// The Azure location whose address can be switched; nil for home PCs.
    let code: String?
    var dense = false

    var body: some View {
        let switching = vpn.switchingIP
        HStack(spacing: 10) {
            FlagBadge(country: vpn.egress?.country ?? vpn.choice?.country, size: dense ? 24 : 28)
            VStack(alignment: .leading, spacing: 0) {
                Text(vpn.egress?.ip ?? "—")
                    .font((dense ? Font.callout : .body).monospacedDigit().weight(.semibold))
                    .lineLimit(1).truncationMode(.middle)
                    .textSelection(.enabled)
                    .contentTransition(.numericText())
                    .opacity(switching ? 0.45 : 1)
                Text(switching ? "Getting a new IP…" : place).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    .contentTransition(.opacity)
            }
            Spacer(minLength: 6)
            Image(systemName: "lock.fill")
                .font(.system(size: 11, weight: .bold))
                .foregroundStyle(PanelInk.accent)
                .accessibilityHidden(true)
            if let code { SwitchIPButton(code: code, circle: true) }
        }
        .padding(.leading, 8).padding(.trailing, code == nil ? 14 : 6).padding(.vertical, 6)
        .glass(dense ? 22 : 24)
        .animation(.snappy, value: switching)
        .animation(.snappy, value: vpn.egress?.ip)
    }

    private var place: String {
        guard let e = vpn.egress else { return "Public IP" }
        return e.city.map { "\($0) · Public IP" } ?? "\(Countries.name(e.country)) · Public IP"
    }
}
