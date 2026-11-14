#if os(macOS)
import AppKit
#endif
import SwiftUI

/// Colours and small pieces shared by the connect panel (card, menu-bar popover, Settings rows).
enum PanelInk {
    /// Brand mint: bright on dark surfaces, deepened on light ones so it stays legible.
    static let accent = Platform.dynamic(light: (0.0, 0.62, 0.40), dark: (0.294, 1.0, 0.702))
    /// Ink drawn on a solid mint fill.
    static let onAccent = Color(red: 0.043, green: 0.078, blue: 0.063)
}

extension MapTone {
    /// Lock-based status glyph: open while exposed, shielded lock once the tunnel is up.
    var lockSymbol: String {
        switch self {
        case .exposed: return "lock.open.fill"
        case .connecting: return "lock.rotation"
        case .secure: return "lock.shield.fill"
        case .failed: return "exclamationmark.shield.fill"
        }
    }
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

/// A Control-Center-style option tile: icon and a small switch on top, title and a
/// two-line trade-off hint below. The whole tile is the hit target.
struct PanelTileToggleStyle: ToggleStyle {
    let icon: String
    let hint: String
    var tint: Color = PanelInk.accent
    var dense = false

    func makeBody(configuration: Configuration) -> some View {
        PanelTile(configuration: configuration, icon: icon, hint: hint, tint: tint, dense: dense)
    }
}

private struct PanelTile: View {
    let configuration: ToggleStyleConfiguration
    let icon: String
    let hint: String
    let tint: Color
    let dense: Bool
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        let on = configuration.isOn
        Button { configuration.isOn.toggle() } label: {
            VStack(alignment: .leading, spacing: dense ? 6 : 8) {
                HStack(alignment: .center) {
                    Image(systemName: icon)
                        .font(.system(size: dense ? 12 : 13, weight: .semibold))
                        .foregroundStyle(on ? PanelInk.onAccent : Color.secondary)
                        .contentTransition(.symbolEffect(.replace))
                        .frame(width: dense ? 26 : 30, height: dense ? 26 : 30)
                        .background(Circle().fill(on ? AnyShapeStyle(tint) : AnyShapeStyle(Color.primary.opacity(0.08))))
                    Spacer(minLength: 4)
                    PanelMiniSwitch(on: on, tint: tint)
                }
                VStack(alignment: .leading, spacing: 2) {
                    configuration.label
                        .font((dense ? Font.caption : .subheadline).weight(.semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    Text(hint)
                        .font(dense ? .system(size: 10) : .caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2, reservesSpace: true)
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)
                }
            }
            .padding(dense ? 10 : 12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        }
        .buttonStyle(.plain)
        .glass(dense ? 16 : 20, interactive: true, tint: on ? tint.opacity(0.16) : nil)
        .opacity(enabled ? 1 : 0.5)
        .animation(.snappy(duration: 0.25), value: on)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(on ? "On" : "Off")
        .help(hint.replacingOccurrences(of: "\n", with: " · "))
    }
}

/// A tiny drawn switch: reads as a toggle without the weight of a full system switch.
private struct PanelMiniSwitch: View {
    let on: Bool
    let tint: Color

    var body: some View {
        Capsule()
            .fill(on ? AnyShapeStyle(tint) : AnyShapeStyle(Color.primary.opacity(0.14)))
            .frame(width: 28, height: 17)
            .overlay(alignment: on ? .trailing : .leading) {
                Circle().fill(.white).padding(2)
                    .shadow(color: .black.opacity(0.18), radius: 1, y: 0.5)
            }
            .accessibilityHidden(true)
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
                Text(switching ? "New IP…" : vpn.egress?.ip ?? "—")
                    .font((dense ? Font.callout : .body).monospacedDigit().weight(.semibold))
                    .lineLimit(1).truncationMode(.middle)
                    .textSelection(.enabled)
                    .contentTransition(.numericText())
                    .opacity(switching ? 0.55 : 1)
                Text(place).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
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
