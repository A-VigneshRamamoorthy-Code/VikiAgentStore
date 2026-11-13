import AppKit
import Combine
import SwiftUI

/// The menu-bar item: one lens glyph (outlined off, filled when connected) that opens a
/// native popover — rounded, light, and sized to its content.
@MainActor
final class StatusBar: NSObject, NSPopoverDelegate {
    static var shared: StatusBar?
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    let popover = NSPopover()
    private var watch: AnyCancellable?

    init(_ vpn: VPNController) {
        super.init()
        let host = NSHostingController(rootView: MenuBarView().environmentObject(vpn))
        host.sizingOptions = .preferredContentSize
        popover.contentViewController = host
        popover.behavior = .transient
        popover.delegate = self
        item.button?.image = LensIcon.image(filled: false)
        item.button?.setAccessibilityLabel("Leap VPN")
        item.button?.target = self
        item.button?.action = #selector(toggle)
        watch = vpn.$phase.sink { [weak self] p in
            self?.item.button?.image = LensIcon.image(filled: p == .connected)
        }
    }

    @objc func toggle() { popover.isShown ? popover.performClose(nil) : show() }

    func show() {
        guard let button = item.button else { return }
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
        lighten()
    }

    /// The stock popover material reads grey; lay a near-white (or soft dark) fill under
    /// the content, arrow included, so it matches the app's light surfaces.
    private func lighten() {
        guard let frame = popover.contentViewController?.view.window?.contentView?.superview,
              !frame.subviews.contains(where: { $0.identifier?.rawValue == "leap.fill" }) else { return }
        let fill = NSBox()
        fill.identifier = NSUserInterfaceItemIdentifier("leap.fill")
        fill.boxType = .custom
        fill.borderWidth = 0
        fill.fillColor = NSColor(name: nil) { a in
            a.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
                ? NSColor(white: 0.13, alpha: 0.92) : NSColor(white: 0.985, alpha: 0.94)
        }
        fill.frame = frame.bounds
        fill.autoresizingMask = [.width, .height]
        frame.addSubview(fill, positioned: .below, relativeTo: frame.subviews.first)
    }

    func close() { popover.performClose(nil) }
}

/// The menu-bar popover: everything the main window does, in one column.
struct MenuBarView: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if vpn.step != .done {
                Button { StatusBar.shared?.close(); MacWindowBridge.showMainWindow() } label: {
                    Label("Finish setup", systemImage: "arrow.right.circle.fill").frame(maxWidth: .infinity)
                }
                .modifier(ProminentStyle()).controlSize(.large)
            } else {
                locations
                ConnectCard(compact: true)
                if vpn.hasAzure, idle, let c = vpn.choice, !c.isHome, let code = c.region?.code {
                    ServerToggles(code: code, compact: true)
                        .padding(.horizontal, 14).padding(.vertical, 10)
                        .glass(16)
                }
                actions
            }
            Divider().opacity(0.5)
            HStack {
                Button("Open Leap VPN") { StatusBar.shared?.close(); MacWindowBridge.showMainWindow() }
                Spacer()
                Button("Quit") { NSApp.terminate(nil) }.keyboardShortcut("q")
            }
            .buttonStyle(.borderless).font(.callout)
        }
        .padding(16)
        .frame(width: 340)
        .fixedSize(horizontal: false, vertical: true)
    }

    private var header: some View {
        let tone = vpn.phase.tone
        return HStack(spacing: 10) {
            Image(systemName: tone.symbol).font(.system(size: 18, weight: .semibold)).foregroundStyle(tone.color)
                .frame(width: 34, height: 34).background(Circle().fill(tone.color.opacity(0.15)))
            VStack(alignment: .leading, spacing: 1) {
                Text("Leap VPN").font(.headline)
                Text(statusLine).font(.caption.monospacedDigit()).foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer()
        }
    }

    private var statusLine: String {
        if vpn.phase == .connected, let e = vpn.egress { return "\(flag(e.country)) \(e.ip)" }
        return vpn.phase.label
    }

    /// One compact picker instead of a long list: home PCs, your locations, then every
    /// other region (added on first connect).
    private var locations: some View {
        Menu {
            let homes = vpn.choices.filter(\.isHome)
            let built = vpn.choices.filter { !$0.isHome && !$0.unbuilt }
            let more = vpn.choices.filter(\.unbuilt)
            if !homes.isEmpty { Section("Home PCs") { ForEach(homes) { item($0) } } }
            if !built.isEmpty { Section("Your locations") { ForEach(built) { item($0) } } }
            if !more.isEmpty { Menu("More locations") { ForEach(more) { item($0) } } }
        } label: {
            HStack(spacing: 10) {
                Text(vpn.choice?.flag ?? "🌐").font(.title3)
                VStack(alignment: .leading, spacing: 1) {
                    Text(vpn.choice?.title ?? "Choose a location").font(.callout.weight(.medium)).lineLimit(1)
                    Text(vpn.choiceSubtitle).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                Image(systemName: "chevron.up.chevron.down").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden)
        .glass(14, interactive: true)
        .disabled(!idle)
    }

    private func item(_ c: ServerChoice) -> some View {
        Button { vpn.select(c.id) } label: {
            if vpn.choice?.id == c.id { Label("\(c.flag) \(c.title)", systemImage: "checkmark") }
            else { Text("\(c.flag) \(c.title)") }
        }
    }

    private var idle: Bool { vpn.phase == .idle || isFailed }

    private var isFailed: Bool { if case .failed = vpn.phase { return true }; return false }

    private var actions: some View {
        GlassGroup(spacing: 8) {
        HStack(spacing: 8) {
            tile("plus", "Add PC") { open(.addPC) }
            tile("chart.bar.xaxis", "Usage") { open(.history) }
            tile("gearshape", "Settings") { open(.settings) }
        }
        }
    }

    private func tile(_ icon: String, _ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 15, weight: .semibold))
                Text(title).font(.caption2)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 9)
            .contentShape(Rectangle())
            .glass(14, interactive: true)
        }
        .buttonStyle(.plain)
    }

    private func open(_ s: HomeSheet) {
        StatusBar.shared?.close()
        MacWindowBridge.showMainWindow()
        vpn.requestedSheet = s
    }
}
