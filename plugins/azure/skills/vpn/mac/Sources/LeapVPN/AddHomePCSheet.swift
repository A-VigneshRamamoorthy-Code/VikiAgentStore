#if os(macOS)
import AppKit
#endif
import SwiftUI

// The sheet is split into small concrete views so each can be built on its own: off screen after
// launch (`AddPCPrewarm`), and on demand. Built cold in one go, SwiftUI's one-time type and layout
// work for the whole tree ran inside the sheet's presentation and froze older iPhones for seconds.

/// Register a Windows PC as an exit: directly, or relayed through Azure (works behind CGNAT).
struct AddHomeExitSheet: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var form = AddExitForm()
    @Environment(\.dismiss) private var dismiss
    /// The first presentation this launch shows a light placeholder and builds the content just
    /// after the sheet has slid in, so its one-time build never runs inside the transition.
    @State private var ready = AddPCWarmup.presented

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            AddPCHeader()
            if ready {
                AddPCContent(form: form) { dismiss() }
                    .transition(.opacity)
            } else {
                AddPCPlaceholder()
                    .task {
                        try? await Task.sleep(for: .milliseconds(AddPCWarmup.isWarm ? 350 : 450))
                        guard !Task.isCancelled else { return }
                        AddPCWarmup.presented = true
                        withAnimation(.easeOut(duration: 0.2)) { ready = true }
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
            form.regionCode = vpn.nearestRegion(to: form.country)
        }
    }
}

@MainActor
enum AddPCWarmup {
    /// Set once every piece of the sheet has been built at least once this launch.
    static var isWarm = false
    /// Set once the sheet's content has been shown on screen this launch.
    static var presented = false
}

/// Builds the Add-PC sheet's pieces off screen, one per frame, once launch has settled, so the first
/// "+" doesn't pay the cold cost. Sits behind the map, invisible and inert.
struct AddPCPrewarm<Final: View>: View {
    /// Built last: the platform's own sheet wrapper, so its type is warm too.
    var final: Final
    @StateObject private var form: AddExitForm = { let f = AddExitForm(); f.choosingCountry = false; return f }()
    @State private var stage = 0
    private static var stages: Int { 8 }

    var body: some View {
        Group {
            switch stage {
            case 1: AddPCPlaceholder()
            case 2: AddPCModePicker(direct: .constant(true))
            case 3: AddPCExplainer(direct: true)
            case 4: DirectPairView(note: false)
            case 5: AddPCExplainer(direct: false)
            case 6: AddPCRelayFlow(form: form)
            case 7: VStack(alignment: .leading, spacing: 16) { AddPCHeader(); AddPCContent(form: form) {} }.sheetChrome(width: 520)
            case 8: final
            default: EmptyView()
            }
        }
        .frame(width: 380)
        .fixedSize(horizontal: false, vertical: true)
        .opacity(0.001)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        #if os(macOS)
        .disabled(true)  // nothing in it may take focus or a keyboard shortcut
        #endif
        .task {
            guard !AddPCWarmup.isWarm else { return }
            try? await Task.sleep(for: .seconds(4))
            for s in 1...Self.stages {
                guard !Task.isCancelled else { return }
                stage = s
                try? await Task.sleep(for: .milliseconds(150))
            }
            stage = 0
            AddPCWarmup.isWarm = true
        }
    }
}

extension AddPCPrewarm where Final == EmptyView {
    init() { final = EmptyView() }
}

struct AddPCHeader: View {
    var body: some View {
        SheetHeader(icon: "house.fill", title: "Add a home PC", tint: Atlas.home,
                    subtitle: "Browse from your home connection")
    }
}

/// Shapes only: cheap to build, roughly the size of the real content so the sheet doesn't jump.
struct AddPCPlaceholder: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 10) { block(52); block(52) }
            block(120)
            block(150)
            ProgressView().frame(maxWidth: .infinity)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
    }

    private func block(_ h: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.primary.opacity(0.05))
            .frame(maxWidth: .infinity).frame(height: h)
    }
}

struct AddPCContent: View {
    @EnvironmentObject var vpn: VPNController
    @ObservedObject var form: AddExitForm
    var onDone: () -> Void

    private var canRelay: Bool { vpn.hasAzure && !vpn.regions.isEmpty }

    var body: some View {
        SheetScroll {
            VStack(alignment: .leading, spacing: 16) {
                if canRelay {
                    AddPCModePicker(direct: $form.direct)
                    // Only the chosen pane is built: laying out both (each with its own pickers and glass)
                    // made the sheet take seconds to open on older iPhones.
                    AddPCPane(form: form, direct: form.direct, onDone: onDone)
                        .id(form.direct)
                        .transition(.opacity)
                } else {
                    DirectPairView(note: true, onPaired: onDone)
                }
            }
        }
    }
}

struct AddPCPane: View {
    @ObservedObject var form: AddExitForm
    let direct: Bool
    var onDone: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            AddPCExplainer(direct: direct)
            if direct { DirectPairView(note: false, onPaired: onDone) } else { AddPCRelayFlow(form: form) }
        }
    }
}

// MARK: mode

struct AddPCModePicker: View {
    @Binding var direct: Bool
    @Namespace private var segment

    var body: some View {
        GlassGroup(spacing: 10) {
            HStack(spacing: 10) {
                option(true, icon: "bolt.horizontal.fill", title: "Direct", caption: "Fastest · free")
                option(false, icon: "cloud.fill", title: "Through Azure", caption: "Works on any network")
            }
        }
    }

    private func option(_ value: Bool, icon: String, title: String, caption: String) -> some View {
        let on = direct == value
        return Button { withAnimation(.spring(response: 0.38, dampingFraction: 0.82)) { direct = value } } label: {
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
}

/// How traffic flows for the chosen mode, and why the relay exists.
struct AddPCExplainer: View {
    let direct: Bool
    @State private var whyOpen = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            flow
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

    private var flow: some View {
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
}

// MARK: relay

struct AddPCRelayFlow: View {
    @EnvironmentObject var vpn: VPNController
    @ObservedObject var form: AddExitForm

    var body: some View {
        GlassGroup(spacing: 16) {
            VStack(alignment: .leading, spacing: 12) {
                SheetStep(n: 1, title: "Where is the PC?") {
                    #if os(macOS)
                    HStack(spacing: 8) { nameField.frame(width: 150); AddPCCountryPicker(form: form) }
                    #else
                    VStack(alignment: .leading, spacing: 8) { nameField; AddPCCountryPicker(form: form) }
                    #endif
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

/// Menu pickers render only text and SF Symbols, so the flag sits beside the menu.
struct AddPCCountryPicker: View {
    @EnvironmentObject var vpn: VPNController
    @ObservedObject var form: AddExitForm

    var body: some View {
        HStack(spacing: 6) {
            FlagBadge(country: form.country, size: 16)
            #if os(macOS)
            Picker("Country", selection: $form.country) {
                ForEach(Countries.all) { c in Text(c.name).tag(c.code) }
            }
            .labelsHidden()
            #else
            // A ~250-item menu Picker is built eagerly with the sheet; a lazy, searchable list opens on demand.
            Button { form.choosingCountry = true } label: {
                HStack(spacing: 4) {
                    Text(Countries.name(form.country)).lineLimit(1)
                    Image(systemName: "chevron.up.chevron.down").font(.caption2)
                }
                .font(.callout).foregroundStyle(.primary)
            }
            .buttonStyle(.borderless)
            .accessibilityLabel("Country, \(Countries.name(form.country))")
            .sheet(isPresented: $form.choosingCountry) {
                CountryList(selection: $form.country)
            }
            #endif
        }
        .onChange(of: form.country) { _, c in if !form.relayPinned { form.regionCode = vpn.nearestRegion(to: c) } }
    }
}

extension VPNController {
    /// The relay region closest to a country, for a PC that hasn't picked one.
    func nearestRegion(to country: String) -> String {
        guard let p = Countries.point(country) else { return regions.first?.code ?? "in" }
        return regions.min { Countries.distance($0.point, p) < Countries.distance($1.point, p) }?.code ?? "in"
    }
}

@MainActor
final class AddExitForm: ObservableObject {
    @Published var direct = true
    @Published var name = ""
    @Published var country = ""
    @Published var regionCode = "in"
    @Published var relayPinned = false
    @Published var choosingCountry = false
    @Published var working = false
    @Published var error: String?
    @Published var installer: VPNController.ExitInstaller?
    var installerRegion = ""

    init() {
        #if DEBUG
        // Screenshot/profiling hooks: open the sheet straight on the relay pane or the country list.
        direct = !UserDefaults.standard.bool(forKey: "LeapAddPCRelay")
        choosingCountry = UserDefaults.standard.bool(forKey: "LeapAddPCCountries")
        #endif
    }
}

#if !os(macOS)
/// Searchable country list; `List` builds rows lazily, unlike a menu Picker.
private struct CountryList: View {
    @Binding var selection: String
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""

    private var rows: [Countries.Entry] {
        let q = query.trimmingCharacters(in: .whitespaces)
        return q.isEmpty ? Countries.all : Countries.all.filter { $0.name.localizedCaseInsensitiveContains(q) || $0.code.caseInsensitiveCompare(q) == .orderedSame }
    }

    var body: some View {
        NavigationStack {
            List(rows) { c in
                Button { selection = c.code; dismiss() } label: {
                    HStack(spacing: 10) {
                        FlagBadge(country: c.code, size: 20)
                        Text(c.name).foregroundStyle(.primary)
                        Spacer()
                        if c.code == selection { Image(systemName: "checkmark").foregroundStyle(Brand.accent) }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(c.code == selection ? .isSelected : [])
            }
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always))
            .navigationTitle("Where is the PC?")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
        .presentationDetents([.large])
    }
}
#endif
