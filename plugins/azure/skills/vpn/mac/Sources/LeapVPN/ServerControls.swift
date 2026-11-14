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

    private var once: Bool { code.map(vpn.ephemeral) ?? vpn.ephemeral }
    private var fixed: Bool { code.map(vpn.staticIP) ?? vpn.staticIP }
    private var relay: Bool { code.map { vpn.relayRegions.contains($0) } ?? false }

    var body: some View {
        if compact { tiles } else { Card(title: code == nil ? "Defaults for new locations" : nil) { rows } }
    }

    private var onceIcon: String { once ? "sparkles" : "externaldrive.fill" }
    private var fixedIcon: String { fixed && !once ? "pin.fill" : "pin.slash.fill" }
    private var onceHint: String { once ? "$0 while off\n~2 min to connect" : "≈ $2.40/mo disk while off\n~40 s to connect" }
    private var fixedHint: String {
        once ? "New IP each time\nNot kept while off" : fixed ? "Same IP every time\n≈ $3.65/mo" : "New IP each time\n$0"
    }

    @ViewBuilder private var tiles: some View {
        if relay {
            Label("Relays a home PC · kept ready", systemImage: "point.3.connected.trianglepath.dotted")
                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                .padding(.horizontal, 14).padding(.vertical, 9)
                .glass(18)
        } else {
            GlassGroup(spacing: 10) {
                HStack(spacing: 10) {
                    Toggle("Provision once", isOn: Binding(get: { once }, set: { vpn.setEphemeral($0, for: code) }))
                        .toggleStyle(PanelTileToggleStyle(icon: onceIcon, hint: onceHint, dense: dense))
                    Toggle("Static IP", isOn: Binding(get: { fixed && !once }, set: { vpn.setStaticIP($0, for: code) }))
                        .toggleStyle(PanelTileToggleStyle(icon: fixedIcon, hint: fixedHint, dense: dense))
                        .disabled(once)
                }
            }
        }
    }

    @ViewBuilder private var rows: some View {
        VStack(alignment: .leading, spacing: 10) {
            if relay {
                Label("Relays a home PC · kept ready", systemImage: "point.3.connected.trianglepath.dotted")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                toggle("Provision once", icon: onceIcon, on: once,
                       caption: onceHint.replacingOccurrences(of: "\n", with: " · ")) { vpn.setEphemeral($0, for: code) }
                Divider().opacity(0.4)
                toggle("Static IP", icon: fixedIcon, on: fixed && !once,
                       caption: fixedHint.replacingOccurrences(of: "\n", with: " · ")) { vpn.setStaticIP($0, for: code) }
                    .disabled(once)
                    .opacity(once ? 0.55 : 1)
            }
        }
    }

    private func toggle(_ title: String, icon: String, on: Bool, caption: String,
                        set: @escaping (Bool) -> Void) -> some View {
        Toggle(isOn: Binding(get: { on }, set: set)) {
            HStack(spacing: 10) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(on ? PanelInk.onAccent : Color.secondary)
                    .contentTransition(.symbolEffect(.replace))
                    .frame(width: 26, height: 26)
                    .background(Circle().fill(on ? AnyShapeStyle(PanelInk.accent) : AnyShapeStyle(Color.primary.opacity(0.08))))
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.callout.weight(.medium))
                    Text(caption).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer(minLength: 0)
            }
        }
        .toggleStyle(.switch)
        .tint(PanelInk.accent)
        .controlSize(.small)
        .help(caption)
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
                    .foregroundStyle(busy ? PanelInk.accent : .primary)
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(Color.primary.opacity(0.07)))
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
        .buttonStyle(.borderless)
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
