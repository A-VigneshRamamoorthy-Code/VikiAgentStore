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
                    #if DEBUG
                    PurchaseTesting()
                    #endif
                    if vpn.phase == .connected || vpn.phase.busy {
                        Text("Disconnects your VPN first.").font(.caption).foregroundStyle(.secondary)
                    }
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
                        .font(.system(size: 17, weight: .bold, design: .rounded)).foregroundStyle(.white)
                        .frame(width: 40, height: 40)
                        .background(Circle().fill(SheetTheme.fill.gradient))
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
                        .foregroundStyle(.white)
                        .modifier(GlassButton(prominent: true)).tint(SheetTheme.fill).controlSize(.small)
                }
            }
        }
    }

    private var locations: some View {
        Card(title: "Locations", trailing: "\(vpn.regions.count)", padding: 6) {
            VStack(spacing: 0) {
                ForEach(Array(vpn.regions.enumerated()), id: \.element.id) { i, r in
                    if i > 0 { Divider().padding(.leading, 54).opacity(0.5) }
                    HStack(spacing: 10) {
                        FlagBadge(country: r.country, size: 32)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(r.name).font(.callout.weight(.medium)).lineLimit(1).minimumScaleFactor(0.8)
                            if vpn.relayRegions.contains(r.code) {
                                Label("Relays a home PC · kept ready", systemImage: "point.3.connected.trianglepath.dotted")
                                    .font(.caption).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.8)
                            } else {
                                StateDot(state: vpn.regionStates[r.code])
                            }
                        }
                        .layoutPriority(1)
                        Spacer(minLength: 4)
                        LocationPrefs(region: r)
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
        .disabled(vpn.working)
        .help(vpn.phase == .connected || vpn.phase.busy ? "Disconnects first" : "Back to the setup screens")
        .accessibilityHint(vpn.phase == .connected || vpn.phase.busy ? "Disconnects first" : "")
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

/// A location's controls as one line of round buttons, all the size of the delete button:
/// mode (leaf = Economy, bolt = Turbo), ad block (green shield, red when off), Static IP (pin),
/// then switch IP when available, and delete. A relay location keeps only the last two.
struct LocationPrefs: View {
    @EnvironmentObject var vpn: VPNController
    let region: RegionConfig
    private let d: CGFloat = 30

    var body: some View {
        let code = region.code
        GlassGroup(spacing: 6) {
            HStack(spacing: 6) {
                if !vpn.relayRegions.contains(code) {
                    CostModeCircle(code: code, size: d)
                    AdBlockPill(code: code, size: .small, tint: SheetTheme.fill, diameter: d)
                    StaticIPCircle(code: code, size: d, tint: SheetTheme.fill)
                }
                if vpn.canSwitchIP(code) {
                    SwitchIPButton(code: code, label: false)
                        .frame(width: d, height: d)
                        .glass(d / 2, interactive: true)
                }
                CircleButton(icon: "trash", help: "Remove \(region.name)", size: d, iconColor: Atlas.red) {
                    vpn.removeRegion(region)
                }
                .disabled(vpn.working || vpn.current?.region == code)
                .accessibilityLabel("Remove \(region.name)")
            }
        }
        .fixedSize()
    }
}

#if DEBUG
/// Local and capture builds only: open each subscription screen on demand. Real purchases in a
/// local build go to Apple's sandbox (Xcode's StoreKit file on iOS); see reference/testing-purchases.md.
private struct PurchaseTesting: View {
    @ObservedObject var store = Store.shared
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Card(title: "Purchase testing · debug build") {
            VStack(alignment: .leading, spacing: 10) {
                Text(state).font(.caption.monospaced()).foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    BrandPill(title: "Trial offer", icon: "gift") { store.resetTesting(); open { store.previewTrialOffer() } }
                    BrandPill(title: "Trial ended", icon: "hourglass") { open { store.previewTrialEnded(); store.previewGate() } }
                }
                HStack(spacing: 8) {
                    BrandPill(title: "Paywall", icon: "sparkles") { open { store.showUpgrade() } }
                    BrandPill(title: "Reset", icon: "arrow.counterclockwise") { store.resetTesting() }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// The subscription screen is a sheet on the home view, so Settings closes first.
    private func open(_ show: @escaping @MainActor () -> Void) {
        dismiss()
        Task { @MainActor in try? await Task.sleep(for: .seconds(0.8)); show() }
    }

    private var state: String {
        "entitlement: \(store.entitlement) · trial eligible: \(store.trialEligible.map(String.init) ?? "?") · products: \(store.products.count)"
    }
}
#endif
