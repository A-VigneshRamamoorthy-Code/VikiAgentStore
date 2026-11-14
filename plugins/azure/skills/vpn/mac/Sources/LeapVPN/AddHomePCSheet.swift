#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

/// Register a Windows PC as an exit: directly, or relayed through Azure (works behind CGNAT).
struct AddHomeExitSheet: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var form = AddExitForm()
    @Environment(\.dismiss) private var dismiss

    private var canRelay: Bool { vpn.hasAzure && !vpn.regions.isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SheetHeader(icon: "house.fill", title: "Add a home PC", tint: Atlas.home,
                        subtitle: "Browse from your home connection")
            SheetScroll {
                VStack(alignment: .leading, spacing: 16) {
                    if canRelay {
                        modePicker
                        explainer
                    }
                    if form.direct || !canRelay {
                        DirectPairView(note: !canRelay) { dismiss() }
                    } else {
                        relayFlow
                    }
                }
            }
        }
        .sheetChrome(width: 520)
        .animation(.smooth(duration: 0.3), value: form.direct)
        .onAppear {
            form.direct = true
            if form.country.isEmpty { form.country = Locale.current.region?.identifier ?? "IN" }
            form.regionCode = nearest(form.country)
        }
    }

    // MARK: mode

    private var modePicker: some View {
        GlassGroup(spacing: 10) {
            HStack(spacing: 10) {
                option(true, icon: "bolt.horizontal.fill", title: "Direct", caption: "Fastest · free")
                option(false, icon: "cloud.fill", title: "Through Azure", caption: "Works on any network")
            }
        }
    }

    private func option(_ direct: Bool, icon: String, title: String, caption: String) -> some View {
        let on = form.direct == direct
        return Button { form.direct = direct } label: {
            HStack(spacing: 10) {
                Image(systemName: icon).font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(on ? SheetTheme.accent : .secondary)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(on ? SheetTheme.mint.opacity(0.2) : Color.primary.opacity(0.06)))
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.callout.weight(.semibold)).foregroundStyle(.primary).lineLimit(1)
                    Text(caption).font(.caption2).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.85)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .modifier(GlassButton(prominent: on))
        .buttonBorderShape(.roundedRectangle(radius: 18))
        .tint(on ? SheetTheme.mint.opacity(0.3) : nil)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// How traffic flows for the chosen mode, and why the relay exists.
    private var explainer: some View {
        VStack(alignment: .leading, spacing: 12) {
            flow
            if form.direct {
                Text("Your device connects straight to the PC. Your router must let UDP 51820 in — the setup script tries UPnP.")
            } else {
                Text("**Why a relay?** Most home connections can't accept incoming connections — the router or your ISP's shared address (CGNAT) blocks them. So the PC dials out to a small Azure server of yours and your devices meet it there. No router changes, and sites still see your home connection.")
                Label("Sleeps while nothing is connected; only its disk and fixed address are kept.", systemImage: "moon.zzz.fill")
                    .foregroundStyle(.tertiary)
            }
        }
        .font(.caption).foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheetSurface(18)
    }

    private var flow: some View {
        HStack(spacing: 6) {
            node(Platform.isPhone ? "iphone" : "laptopcomputer", "This device", SheetTheme.accent)
            arrow("arrow.right")
            if !form.direct {
                node("cloud.fill", "Azure relay", Atlas.blue)
                arrow("arrow.left")
            }
            node("desktopcomputer", "Home PC", Atlas.home)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(form.direct ? "This device connects to the home PC" : "This device and the home PC both connect to an Azure relay")
    }

    private func node(_ icon: String, _ label: String, _ tint: Color) -> some View {
        VStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 15, weight: .semibold)).foregroundStyle(tint)
                .frame(width: 38, height: 38).background(Circle().fill(tint.opacity(0.14)))
            Text(label).font(.caption2.weight(.medium)).foregroundStyle(.secondary).lineLimit(1).fixedSize()
        }
    }

    private func arrow(_ icon: String) -> some View {
        Image(systemName: icon).font(.system(size: 11, weight: .bold)).foregroundStyle(.tertiary)
            .frame(maxWidth: 40).padding(.bottom, 16)
    }

    // MARK: relay

    private var relayFlow: some View {
        GlassGroup(spacing: 16) {
            VStack(alignment: .leading, spacing: 12) {
                SheetStep(n: 1, title: "Where is the PC?") {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) { nameField.frame(width: 150); countryPicker }
                        VStack(alignment: .leading, spacing: 8) { nameField; countryPicker }
                    }
                    HStack(spacing: 6) {
                        Image(systemName: "cloud.fill").font(.caption2).foregroundStyle(Atlas.blue)
                        Text("Relay").font(.caption).foregroundStyle(.secondary)
                        Picker("Relay", selection: Binding(get: { form.regionCode }, set: { form.regionCode = $0; form.relayPinned = true })) {
                            ForEach(vpn.regions) { r in Text("\(r.flag) \(r.name)").tag(r.code) }
                        }
                        .labelsHidden().controlSize(.small).fixedSize()
                        if !form.relayPinned { Text("nearest").font(.caption2).foregroundStyle(.tertiary) }
                    }
                }
                SheetStep(n: 2, title: "Copy the setup command") {
                    GlassGroup(spacing: 8) {
                        HStack(spacing: 8) {
                            Button { make(.copy) } label: {
                                Label(form.installer == nil ? "Copy command" : "Copy again", systemImage: "doc.on.doc")
                                    .font(.callout.weight(.semibold)).foregroundStyle(SheetTheme.onAccent)
                                    .lineLimit(1)
                            }
                            .modifier(GlassButton(prominent: true)).tint(SheetTheme.accent)
                            CircleButton(icon: "square.and.arrow.up", help: "Share", size: 36) { make(.share) }
                            CircleButton(icon: "arrow.down.to.line", help: "Download a .cmd", size: 36) { make(.download) }
                            if form.working { ProgressView().controlSize(.small) }
                        }
                    }
                    .disabled(form.working)
                    if let inst = form.installer {
                        Text(inst.command).font(.caption2.monospaced()).lineLimit(1).truncationMode(.middle)
                            .textSelection(.enabled).foregroundStyle(.secondary)
                    }
                }
                SheetStep(n: 3, title: "Run it on the PC") {
                    Text("**Win+X › Terminal**, paste, Enter. No admin needed. It appears on the map once it's online.")
                        .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
                if form.installer != nil {
                    Label("One-time link, valid 48 h. Your own PCs only.", systemImage: "lock.shield")
                        .font(.caption).foregroundStyle(Atlas.amber)
                }
                if let err = form.error {
                    Label(err, systemImage: "exclamationmark.triangle.fill").font(.caption).foregroundStyle(Atlas.red)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private var nameField: some View {
        TextField("PC name", text: $form.name).textFieldStyle(.roundedBorder)
    }

    private var countryPicker: some View {
        Picker("Country", selection: $form.country) {
            ForEach(Countries.all) { c in Text("\(flag(c.code)) \(c.name)").tag(c.code) }
        }
        .labelsHidden()
        .onChange(of: form.country) { _, c in if !form.relayPinned { form.regionCode = nearest(c) } }
    }

    private func nearest(_ country: String) -> String {
        guard let p = Countries.point(country) else { return vpn.regions.first?.code ?? "in" }
        return vpn.regions.min { Countries.distance($0.point, p) < Countries.distance($1.point, p) }?.code ?? "in"
    }

    enum Delivery { case copy, share, download }

    private func make(_ how: Delivery) {
        form.working = true; form.error = nil
        Task {
            do {
                let inst: VPNController.ExitInstaller
                if let prior = form.installer, form.installerRegion == form.regionCode,
                   prior.expires.timeIntervalSinceNow > 3600 {
                    inst = prior  // one invite per sheet: more clicks reuse it, not more slots
                } else {
                    let name = form.name.trimmingCharacters(in: .whitespaces)
                    inst = try await vpn.createExitInstaller(regionCode: form.regionCode,
                                                             name: name.isEmpty ? nil : name, country: form.country)
                }
                form.installer = inst
                form.installerRegion = form.regionCode
                switch how {
                case .copy:
                    Platform.copy(inst.command)
                case .share:
                    Platform.share([inst.command])
                case .download:
                    #if os(macOS)
                    NSWorkspace.shared.activateFileViewerSelecting([inst.file])
                    #else
                    Platform.share([inst.file])
                    #endif
                }
            } catch { form.error = error.localizedDescription }
            form.working = false
        }
    }
}

@MainActor
final class AddExitForm: ObservableObject {
    @Published var direct = false
    @Published var name = ""
    @Published var country = ""
    @Published var regionCode = "in"
    @Published var relayPinned = false
    @Published var working = false
    @Published var error: String?
    @Published var installer: VPNController.ExitInstaller?
    var installerRegion = ""
}
