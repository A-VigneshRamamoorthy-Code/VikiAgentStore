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
    @State private var whyOpen = false
    @Namespace private var segment

    private var canRelay: Bool { vpn.hasAzure && !vpn.regions.isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SheetHeader(icon: "house.fill", title: "Add a home PC", tint: Atlas.home,
                        subtitle: "Browse from your home connection")
            SheetScroll {
                VStack(alignment: .leading, spacing: 16) {
                    if canRelay {
                        modePicker
                        // Both panes stay laid out and cross-fade in place, so the sheet never resizes mid-switch.
                        ZStack(alignment: .top) {
                            pane(direct: true)
                            pane(direct: false)
                        }
                    } else {
                        DirectPairView(note: true) { dismiss() }
                    }
                }
            }
        }
        .sheetChrome(width: 520)
        .onAppear {
            #if os(macOS)
            // AppKit focuses the first text field of a new sheet; start with nothing focused.
            DispatchQueue.main.async { NSApp.keyWindow?.makeFirstResponder(nil) }
            #endif
            if form.country.isEmpty { form.country = Locale.current.region?.identifier ?? "IN" }
            form.regionCode = nearest(form.country)
        }
    }

    // MARK: mode

    private func pane(direct: Bool) -> some View {
        let shown = form.direct == direct
        return VStack(alignment: .leading, spacing: 16) {
            explainer(direct: direct)
            if direct { DirectPairView(note: false) { dismiss() } } else { relayFlow }
        }
        .opacity(shown ? 1 : 0)
        .allowsHitTesting(shown)
        .disabled(!shown)
        .accessibilityHidden(!shown)
    }

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
        return Button { withAnimation(.spring(response: 0.38, dampingFraction: 0.82)) { form.direct = direct } } label: {
            HStack(spacing: 10) {
                Image(systemName: icon).font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(on ? Color.white : .secondary)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(on ? Color.white.opacity(0.22) : Color.primary.opacity(0.06)))
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.callout.weight(.semibold)).foregroundStyle(on ? Color.white : .primary).lineLimit(1)
                    Text(caption).font(.caption2).foregroundStyle(on ? Color.white.opacity(0.8) : .secondary).lineLimit(1).minimumScaleFactor(0.85)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background {
            let shape = RoundedRectangle(cornerRadius: 18, style: .continuous)
            ZStack {
                shape.fill(Color.primary.opacity(0.05))
                shape.strokeBorder(SheetTheme.hairline, lineWidth: 0.5)
                if on {
                    shape.fill(SheetTheme.fill)
                        .overlay(shape.strokeBorder(.white.opacity(0.18), lineWidth: 0.5))
                        .matchedGeometryEffect(id: "selected", in: segment)
                }
            }
        }
        .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// How traffic flows for the chosen mode, and why the relay exists.
    private func explainer(direct: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            flow(direct: direct)
            if direct {
                Text("Your device connects straight to the PC. Your router must let UDP 51820 in — the setup script tries UPnP.")
            } else {
                whyRelay
            }
        }
        .font(.caption).foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheetSurface(18)
    }

    /// "Why a relay?" as a disclosure row, collapsed until asked.
    private var whyRelay: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                withAnimation(.smooth(duration: 0.3)) { whyOpen.toggle() }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "questionmark.circle.fill").font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(Atlas.blue)
                    Text("Why a relay?").font(.caption.weight(.semibold)).foregroundStyle(.primary)
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                        .rotationEffect(.degrees(whyOpen ? 90 : 0))
                }
                .padding(.vertical, 8).padding(.horizontal, 10)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Why a relay?")
            .accessibilityValue(whyOpen ? "Expanded" : "Collapsed")
            .accessibilityHint(whyOpen ? "Hides the explanation" : "Shows the explanation")
            if whyOpen {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Most home networks block incoming connections (router or your ISP's shared address, CGNAT). The PC dials out to a small Azure server of yours and your devices meet it there — no router changes, and sites still see your home connection.")
                    Label("Sleeps while idle; only its disk and fixed address are kept.", systemImage: "moon.zzz.fill")
                        .foregroundStyle(.tertiary)
                }
                .padding(.horizontal, 10).padding(.bottom, 10)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Color.primary.opacity(0.04)))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func flow(direct: Bool) -> some View {
        HStack(spacing: 6) {
            node(Platform.isPhone ? "iphone" : "laptopcomputer", "This device", SheetTheme.accent)
            arrow("arrow.right")
            if !direct {
                node("cloud.fill", "Azure relay", Atlas.blue)
                arrow("arrow.left")
            }
            node("desktopcomputer", "Home PC", Atlas.home)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(direct ? "This device connects to the home PC" : "This device and the home PC both connect to an Azure relay")
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
                        FlagBadge(country: vpn.regions.first { $0.code == form.regionCode }?.country, size: 16)
                        Picker("Relay", selection: Binding(get: { form.regionCode }, set: { form.regionCode = $0; form.relayPinned = true })) {
                            ForEach(vpn.regions) { r in Text(r.name).tag(r.code) }
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
                            .modifier(GlassButton(prominent: true)).tint(SheetTheme.fill)
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

    /// Menu pickers render only text and SF Symbols, so the flag sits beside the menu.
    private var countryPicker: some View {
        HStack(spacing: 6) {
            FlagBadge(country: form.country, size: 16)
            Picker("Country", selection: $form.country) {
                ForEach(Countries.all) { c in Text(c.name).tag(c.code) }
            }
            .labelsHidden()
        }
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
    @Published var direct = true
    @Published var name = ""
    @Published var country = ""
    @Published var regionCode = "in"
    @Published var relayPinned = false
    @Published var working = false
    @Published var error: String?
    @Published var installer: VPNController.ExitInstaller?
    var installerRegion = ""
}
