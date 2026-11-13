import AppKit
import Combine
import SwiftUI

enum MacWindowID { static let main = "main" }

/// Lets AppKit callbacks (Dock reopen, menu bar) reach SwiftUI's openWindow.
@MainActor
enum MacWindowBridge {
    private static var openMainWindow: (() -> Void)?

    static func registerMainWindowOpener(_ open: @escaping () -> Void) { openMainWindow = open }

    static func showMainWindow(using open: OpenWindowAction? = nil) {
        NSApp.activate(ignoringOtherApps: true)
        if let open { open(id: MacWindowID.main) }
        else if let openMainWindow { openMainWindow() }
        else { NSApp.windows.first { $0.canBecomeMain }?.makeKeyAndOrderFront(nil) }
    }
}

struct MacWindowCommands: Commands {
    @Environment(\.openWindow) private var openWindow

    var body: some Commands {
        CommandGroup(after: .windowList) {
            Button("Leap VPN") { MacWindowBridge.showMainWindow(using: openWindow) }
                .keyboardShortcut("0", modifiers: .command)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var controller: VPNController?

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let controller else { return .terminateNow }
        Task { @MainActor in
            await controller.shutdownForQuit()
            sender.reply(toApplicationShouldTerminate: true)
        }
        return .terminateLater
    }

    /// The VPN keeps running from the menu bar with the window closed.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { Task { @MainActor in MacWindowBridge.showMainWindow() } }
        return true
    }
}

@main
struct LeapVPNApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var vpn = VPNController()

    var body: some Scene {
        Window("Leap VPN", id: MacWindowID.main) {
            RootView()
                .environmentObject(vpn)
                .onAppear {
                    delegate.controller = vpn
                    if StatusBar.shared == nil { StatusBar.shared = StatusBar(vpn) }
                }
                .onOpenURL { vpn.handle(url: $0) }
                .frame(minWidth: 720, minHeight: 560)
        }
        .defaultSize(width: 920, height: 640)
        .handlesExternalEvents(matching: ["*"])
        .commands {
            CommandGroup(replacing: .newItem) {}
            MacWindowCommands()
        }

    }
}

/// The Leap lens glyph as an 18pt template: outlined when off, filled when connected.
enum LensIcon {
    private static var cache: [Bool: NSImage] = [:]

    static func image(filled: Bool) -> NSImage {
        if let img = cache[filled] { return img }
        let img = NSImage(size: NSSize(width: 18, height: 18), flipped: true) { _ in
            guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
            ctx.setStrokeColor(NSColor.black.cgColor)
            ctx.setFillColor(NSColor.black.cgColor)
            ctx.setLineCap(.round)
            let lens = CGRect(x: 9 - 5.2, y: 9 - 5.2, width: 10.4, height: 10.4)
            if filled {
                ctx.fillEllipse(in: lens.insetBy(dx: -0.8, dy: -0.8))
                ctx.setBlendMode(.clear)
                ctx.setLineWidth(1.6)
                ctx.move(to: CGPoint(x: 5.6, y: 9)); ctx.addLine(to: CGPoint(x: 12.4, y: 9)); ctx.strokePath()
                ctx.setBlendMode(.normal)
            } else {
                ctx.setLineWidth(1.6)
                ctx.strokeEllipse(in: lens)
                ctx.move(to: CGPoint(x: 5.6, y: 9)); ctx.addLine(to: CGPoint(x: 12.4, y: 9)); ctx.strokePath()
            }
            ctx.setLineWidth(1.2)
            ctx.move(to: CGPoint(x: 0.8, y: 9)); ctx.addQuadCurve(to: CGPoint(x: 3, y: 9), control: CGPoint(x: 1.9, y: 6.6))
            ctx.move(to: CGPoint(x: 15, y: 9)); ctx.addQuadCurve(to: CGPoint(x: 17.2, y: 9), control: CGPoint(x: 16.1, y: 11.4))
            ctx.strokePath()
            return true
        }
        img.isTemplate = true
        cache[filled] = img
        return img
    }
}
