#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

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

/// Gives a provisioned location a new public IP. The button that asked owns the warning,
/// so the card and a Settings row never both present it.
struct SwitchIPButton: View {
    @EnvironmentObject var vpn: VPNController
    let code: String
    var label = true
    @State private var asked = false

    var body: some View {
        let busy = vpn.phase == .starting("Switching IP…")
        Button {
            asked = true
            vpn.requestSwitchIP(code)
        } label: {
            if label {
                Label(busy ? "Switching…" : "New IP", systemImage: "arrow.triangle.2.circlepath")
                    .font(.caption.weight(.medium))
            } else {
                Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 12, weight: .semibold))
            }
        }
        .buttonStyle(.borderless)
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
