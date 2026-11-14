#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

/// The two cost switches for one location (`code`) or the defaults (`nil`).
/// `compact` (the connect panel) draws them as two side-by-side option tiles; otherwise they
/// are switch rows. Icons follow state, so the setting reads at a glance.
struct ServerToggles: View {
    @EnvironmentObject var vpn: VPNController
    var code: String? = nil
    var compact = false
    /// Tighter tiles, for the menu-bar popover.
    var dense = false

    private var relay: Bool { code.map { vpn.relayRegions.contains($0) } ?? false }

    var body: some View {
        if compact { tiles } else { Card(title: code == nil ? "Defaults for new locations" : nil) { rows } }
    }

    @ViewBuilder private var tiles: some View {
        if relay {
            Label("Relays a home PC · kept ready", systemImage: "point.3.connected.trianglepath.dotted")
                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                .padding(.horizontal, 14).padding(.vertical, 9)
                .glass(18)
        } else {
            GlassGroup(spacing: 8) {
                HStack(spacing: 8) {
                    CostModePicker(code: code, size: dense ? .dense : .regular)
                    AdBlockPill(code: code, size: dense ? .dense : .regular)
                    StaticIPPill(code: code, size: dense ? .dense : .regular)
                }
            }
        }
    }

    @ViewBuilder private var rows: some View {
        if relay {
            Label("Relays a home PC · kept ready", systemImage: "point.3.connected.trianglepath.dotted")
                .font(.caption).foregroundStyle(.secondary)
        } else {
            HStack(spacing: 8) {
                CostModePicker(code: code, size: .regular, hug: true).layoutPriority(1)
                AdBlockPill(code: code, size: .regular)
                StaticIPPill(code: code, size: .regular)
            }
        }
    }
}

/// Gives a provisioned location a new public IP. The button that asked owns the warning,
/// so the card and a Settings row never both present it.
struct SwitchIPButton: View {
    @EnvironmentObject var vpn: VPNController
    let code: String
    var label = true

    /// A round button whose glyph spins while switching (the connect panel's IP row).
    var circle = false
    @State private var asked = false

    var body: some View {
        let busy = vpn.switchingIP
        Button {
            asked = true
            vpn.requestSwitchIP(code)
        } label: {
            if circle {
                PanelSpinGlyph(name: "arrow.triangle.2.circlepath", spinning: busy)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(busy ? AnyShapeStyle(PanelInk.accent) : AnyShapeStyle(.primary))
                    .frame(width: 36, height: 36)
                    .modifier(IPCircleGlass())
                    .contentShape(Circle())
            } else if label {
                Label { Text(busy ? "Switching…" : "New IP") } icon: {
                    PanelSpinGlyph(name: "arrow.triangle.2.circlepath", spinning: busy)
                }
                .font(.caption.weight(.medium))
            } else {
                PanelSpinGlyph(name: "arrow.triangle.2.circlepath", spinning: busy)
                    .font(.system(size: 12, weight: .semibold))
            }
        }
        .buttonStyle(PressScaleStyle(plain: !circle))
        .focusEffectDisabled()
        .accessibilityLabel(busy ? "Switching IP" : "Switch IP")
        .disabled(busy || !vpn.canSwitchIP(code))
        .help("Get a new public IP for this location")
        .confirmationDialog("Switch IP?", isPresented: Binding(
            get: { asked && vpn.ipSwitchWarning?.code == code },
            set: { if !$0 { if vpn.ipSwitchWarning?.code == code { vpn.ipSwitchWarning = nil }; asked = false } })
        ) {
            Button("Switch IP", role: .destructive) { vpn.switchIP(code) }
            Button("Cancel", role: .cancel) {}
        } message: {
            let n = vpn.ipSwitchWarning?.devices ?? []
            Text("\(n.joined(separator: ", ")) \(n.count == 1 ? "is" : "are") also connected here and will drop until \(n.count == 1 ? "it reconnects" : "they reconnect").")
        }
        .alert("Couldn't switch IP", isPresented: Binding(
            get: { asked && vpn.ipSwitchError != nil },
            set: { if !$0 { vpn.ipSwitchError = nil; asked = false } })
        ) { Button("OK") {} } message: { Text(vpn.ipSwitchError ?? "") }
    }
}

/// A still glass disc: no interactive morph, so a press reads as a simple dip.
private struct IPCircleGlass: ViewModifier {
    func body(content: Content) -> some View {
        if #available(macOS 26, *) {
            content.glassEffect(.regular, in: Circle())
        } else {
            content.background(Circle().fill(Color.primary.opacity(0.07)))
        }
    }
}

/// Dips slightly while pressed; nothing else moves. `plain` (text/glyph-only) buttons take the tint.
private struct PressScaleStyle: ButtonStyle {
    var plain = false
    @Environment(\.isEnabled) private var enabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(plain ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary))
            .opacity(enabled ? (configuration.isPressed ? 0.7 : 1) : 0.85)
            .scaleEffect(configuration.isPressed && !plain ? 0.92 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
