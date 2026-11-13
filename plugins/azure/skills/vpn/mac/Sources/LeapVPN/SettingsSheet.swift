#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

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
                    rerun
                    if !vpn.regions.isEmpty { locations }
                    if !vpn.exits.isEmpty || !vpn.pendingExits.isEmpty || !vpn.setup.direct.isEmpty { homePCs }
                    if let e = vpn.setupError { Text(e).font(.caption).foregroundStyle(Atlas.red).textSelection(.enabled) }
                    if vpn.working { ProgressView(vpn.setupLog.last ?? "Working…").controlSize(.small) }
                }
            }
        }
        .padding(22)
        .macFrame(width: 460, height: 600)
    }

    private var account: some View {
        Card(title: "Account") {
            if vpn.hasAzure {
                HStack(spacing: 12) {
                    Image(systemName: "person.crop.circle.fill").font(.system(size: 30)).foregroundStyle(Atlas.blue)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(vpn.setup.user?.username ?? "—").font(.callout.weight(.medium)).lineLimit(1).truncationMode(.middle)
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

    private var rerun: some View {
        Card(title: "Setup") {
            Button {
                dismiss()
                vpn.rerunOnboarding()
            } label: {
                Label("Run setup again", systemImage: "arrow.counterclockwise").frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.borderless)
            .disabled(vpn.phase.busy || vpn.phase == .connected || vpn.working)
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
                    SwitchIPButton(code: r.code, label: false).frame(width: 22)
                        .opacity(vpn.canSwitchIP(r.code) ? 1 : 0)
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
