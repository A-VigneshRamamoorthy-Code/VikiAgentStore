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
            SheetHeader(icon: "gearshape.fill", title: "Settings", tint: SheetTheme.accent)
            ScrollView {
                VStack(spacing: 18) {
                    account
                    if !vpn.regions.isEmpty { locations }
                    if !vpn.exits.isEmpty || !vpn.pendingExits.isEmpty || !vpn.setup.direct.isEmpty { homePCs }
                    if vpn.hasAzure { ServerToggles() }
                    if let e = vpn.setupError {
                        Label(e, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                            .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    }
                    if vpn.working { ProgressView(vpn.setupLog.last ?? "Working…").controlSize(.small) }
                    rerun
                }
                .padding(.bottom, 20)
            }
            .scrollIndicators(.hidden)
        }
        .sheetChrome(width: 480, height: 640)
    }

    private var account: some View {
        Card(title: "Account") {
            if vpn.hasAzure {
                let user = vpn.setup.user?.username ?? "—"
                HStack(spacing: 12) {
                    Text(String(user.prefix(1)).uppercased())
                        .font(.system(size: 17, weight: .bold, design: .rounded)).foregroundStyle(SheetTheme.base)
                        .frame(width: 40, height: 40)
                        .background(Circle().fill(LinearGradient(colors: [SheetTheme.mintSoft, SheetTheme.mint],
                                                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(user).font(.callout.weight(.semibold)).lineLimit(1).truncationMode(.middle)
                        Label(vpn.setup.subscriptionName ?? "Azure", systemImage: "cloud.fill")
                            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    Button("Sign out", role: .destructive) { vpn.signOut(); dismiss() }
                        .modifier(GlassButton()).controlSize(.small)
                }
            } else {
                HStack(spacing: 12) {
                    Image(systemName: "desktopcomputer").font(.system(size: 15, weight: .semibold)).foregroundStyle(Atlas.home)
                        .frame(width: 40, height: 40).background(Circle().fill(Atlas.home.opacity(0.15)))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Home PCs only").font(.callout.weight(.semibold))
                        Text("Add Azure for servers worldwide").font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 8)
                    Button("Add Azure") { dismiss(); vpn.step = .welcome }
                        .modifier(GlassButton(prominent: true)).tint(SheetTheme.accent).controlSize(.small)
                }
            }
        }
    }

    private var locations: some View {
        Card(title: "Locations", trailing: "\(vpn.regions.count)", padding: 6) {
            VStack(spacing: 0) {
                ForEach(Array(vpn.regions.enumerated()), id: \.element.id) { i, r in
                    if i > 0 { Divider().padding(.leading, 54).opacity(0.5) }
                    HStack(spacing: 12) {
                        FlagBadge(country: r.country, size: 32)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(r.name).font(.callout.weight(.medium)).lineLimit(1)
                            StateDot(state: vpn.regionStates[r.code])
                        }
                        Spacer(minLength: 6)
                        if vpn.canSwitchIP(r.code) { SwitchIPButton(code: r.code, label: false) }
                        PrefIcons(code: r.code)
                        CircleButton(icon: "trash", help: "Remove \(r.name)", size: 30, iconColor: Atlas.red) {
                            vpn.removeRegion(r)
                        }
                        .disabled(vpn.working || vpn.current?.region == r.code)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 8)
                }
            }
        }
    }

    private var homePCs: some View {
        Card(title: "Home PCs", padding: 6) {
            VStack(spacing: 0) {
                let relayed = vpn.exits + vpn.pendingExits
                ForEach(Array(relayed.enumerated()), id: \.element.id) { i, e in
                    if i > 0 { Divider().padding(.leading, 54).opacity(0.5) }
                    pcRow(country: e.pending ? nil : e.country, pending: e.pending,
                          title: e.pending ? "Waiting for the PC" : e.name,
                          detail: "via \(vpn.regions.first { $0.code == e.region }?.name ?? e.region)",
                          icon: "cloud.fill") { Task { await vpn.removeExit(e) } }
                }
                ForEach(Array(vpn.setup.direct.enumerated()), id: \.element.id) { i, pc in
                    if i > 0 || !relayed.isEmpty { Divider().padding(.leading, 54).opacity(0.5) }
                    pcRow(country: pc.country, pending: false, title: pc.name,
                          detail: ["Direct", pc.isp].compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: " · "),
                          icon: "bolt.horizontal.fill") { vpn.removeDirect(pc) }
                }
            }
        }
    }

    private func pcRow(country: String?, pending: Bool, title: String, detail: String, icon: String,
                       remove: @escaping () -> Void) -> some View {
        HStack(spacing: 12) {
            if pending {
                Image(systemName: "hourglass").font(.system(size: 13, weight: .semibold)).foregroundStyle(Atlas.amber)
                    .frame(width: 32, height: 32).background(Circle().fill(Atlas.amber.opacity(0.15)))
            } else {
                FlagBadge(country: country, size: 32)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.callout.weight(.medium)).lineLimit(1)
                Label(detail, systemImage: icon).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 6)
            CircleButton(icon: "trash", help: "Remove \(title)", size: 30, iconColor: Atlas.red, action: remove)
        }
        .padding(.horizontal, 8).padding(.vertical, 8)
    }

    private var rerun: some View {
        Button {
            dismiss()
            vpn.rerunOnboarding()
        } label: {
            Label("Run setup again", systemImage: "arrow.counterclockwise")
                .font(.callout.weight(.medium)).frame(maxWidth: .infinity)
        }
        .modifier(GlassButton())
        .controlSize(.large)
        .disabled(vpn.phase.busy || vpn.phase == .connected || vpn.working)
    }
}

/// A location's server state in plain words.
struct StateDot: View {
    let state: String?
    var body: some View {
        let (color, text): (Color, String) = switch state {
        case "running": (SheetTheme.mint, "On")
        case "building": (Atlas.amber, "Setting up")
        case "starting": (Atlas.amber, "Starting")
        case "stopping", "deallocating": (Atlas.amber, "Turning off")
        case "deleted", "deallocated", "stopped": (.secondary, "Off")
        case nil: (.secondary, "—")
        default: (Atlas.amber, (state ?? "").capitalized)
        }
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 6, height: 6)
                .shadow(color: state == "running" ? SheetTheme.mint.opacity(0.8) : .clear, radius: 3)
            Text(text).font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }
}

/// Two icon-only glass switches for a Settings location row.
struct PrefIcons: View {
    @EnvironmentObject var vpn: VPNController
    let code: String

    var body: some View {
        let once = vpn.ephemeral(code), fixed = vpn.staticIP(code) && !once
        if vpn.relayRegions.contains(code) {
            Image(systemName: "arrow.triangle.branch").font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Atlas.home).frame(width: 30, height: 30)
                .background(Circle().fill(Atlas.home.opacity(0.14)))
                .help("Relays a home PC · kept ready")
        } else {
            GlassGroup(spacing: 4) {
                HStack(spacing: 4) {
                    icon(once ? "sparkles" : "externaldrive.fill", on: once, tint: SheetTheme.accent,
                         help: once ? "Provision once: on · $0 while off" : "Provision once: off · kept on disk, faster connect") {
                        vpn.setEphemeral(!once, for: code)
                    }
                    icon(fixed ? "pin.fill" : "pin.slash", on: fixed, tint: Atlas.blue,
                         help: fixed ? "Static IP: on · ≈ $3.65/mo" : "Static IP: off") {
                        vpn.setStaticIP(!fixed, for: code)
                    }
                    .disabled(once).opacity(once ? 0.45 : 1)
                }
            }
        }
    }

    private func icon(_ name: String, on: Bool, tint: Color, help: String, act: @escaping () -> Void) -> some View {
        Button(action: act) {
            Image(systemName: name)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(on ? AnyShapeStyle(tint) : AnyShapeStyle(.secondary))
                .frame(width: 18, height: 16)
                .contentTransition(.symbolEffect(.replace))
        }
        .modifier(GlassButton(prominent: on))
        .buttonBorderShape(.capsule)
        .controlSize(.small)
        .tint(on ? tint.opacity(0.28) : nil)
        .help(help)
        .accessibilityLabel(help)
    }
}
