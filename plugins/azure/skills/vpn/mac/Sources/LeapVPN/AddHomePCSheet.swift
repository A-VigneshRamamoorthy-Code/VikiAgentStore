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

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SheetHeader(icon: "house.fill", title: "Add a home PC", tint: Atlas.home)
            if vpn.hasAzure && !vpn.regions.isEmpty {
                Picker("", selection: $form.direct) {
                    Text("Direct").tag(true)
                    Text("Through Azure").tag(false)
                }
                .pickerStyle(.segmented).labelsHidden()
                Text(form.direct ? "Fastest and free. Needs UDP 51820 open on your router."
                                 : "Works behind any router. A small Azure relay runs while connected.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if form.direct || !vpn.hasAzure || vpn.regions.isEmpty {
                DirectPairView(note: !(vpn.hasAzure && !vpn.regions.isEmpty)) { dismiss() }
            } else {
                relayFlow
            }
        }
        .padding(22)
        .macFrame(width: 500)
        .onAppear {
            form.direct = true
            if form.country.isEmpty { form.country = Locale.current.region?.identifier ?? "IN" }
            form.regionCode = nearest(form.country)
        }
    }

    private var relayFlow: some View {
        GlassGroup(spacing: 16) {
        VStack(alignment: .leading, spacing: 16) {
            StepRow(n: 1, title: "Where is the PC?") {
                HStack(spacing: 8) {
                    TextField("PC name", text: $form.name).textFieldStyle(.roundedBorder).frame(width: 130)
                    Picker("", selection: $form.country) {
                        ForEach(Countries.all) { c in Text("\(flag(c.code)) \(c.name)").tag(c.code) }
                    }
                    .labelsHidden()
                    .onChange(of: form.country) { _, c in if !form.relayPinned { form.regionCode = nearest(c) } }
                }
                HStack(spacing: 6) {
                    Text("Relay").font(.caption).foregroundStyle(.secondary)
                    Picker("", selection: Binding(get: { form.regionCode }, set: { form.regionCode = $0; form.relayPinned = true })) {
                        ForEach(vpn.regions) { r in Text("\(r.flag) \(r.name)").tag(r.code) }
                    }
                    .labelsHidden().controlSize(.small).fixedSize()
                    if !form.relayPinned { Text("nearest").font(.caption2).foregroundStyle(.tertiary) }
                }
            }
            StepRow(n: 2, title: "Copy the setup command") {
                HStack(spacing: 8) {
                    Button { make(.copy) } label: { Label(form.installer == nil ? "Copy command" : "Copy again", systemImage: "doc.on.doc") }
                        .modifier(ProminentStyle())
                    Button { make(.share) } label: { Image(systemName: "square.and.arrow.up") }.help("Share")
                    Button { make(.download) } label: { Image(systemName: "arrow.down.circle") }.help("Download a .cmd")
                    if form.working { ProgressView().controlSize(.small) }
                }
                .disabled(form.working)
                if let inst = form.installer {
                    Text(inst.command).font(.caption2.monospaced()).lineLimit(1).truncationMode(.middle)
                        .textSelection(.enabled).foregroundStyle(.secondary)
                }
            }
            StepRow(n: 3, title: "Run it on the PC") {
                Text("**Win+X › Terminal**, paste, Enter. No admin needed. It appears on the map once it's online.")
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            if form.installer != nil {
                Label("One-time link, valid 48 h. Your own PCs only.", systemImage: "lock.shield")
                    .font(.caption).foregroundStyle(Atlas.amber)
            }
            if let err = form.error { Text(err).font(.caption).foregroundStyle(Atlas.red).textSelection(.enabled) }
        }
        }
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
