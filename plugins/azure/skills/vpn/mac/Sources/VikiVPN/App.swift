import AppKit
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
struct VikiVPNApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var vpn = VPNController()

    var body: some Scene {
        Window("Leap VPN", id: MacWindowID.main) {
            RootView()
                .environmentObject(vpn)
                .onAppear { delegate.controller = vpn }
                .onOpenURL { vpn.handle(url: $0) }
                .frame(minWidth: 720, minHeight: 560)
        }
        .defaultSize(width: 920, height: 640)
        .handlesExternalEvents(matching: ["*"])
        .commands {
            CommandGroup(replacing: .newItem) {}
            MacWindowCommands()
        }

        MenuBarExtra {
            MenuBarView().environmentObject(vpn)
        } label: {
            if vpn.phase == .connected {
                Image(systemName: "checkmark.shield.fill")
            } else if let img = Self.menuIcon {
                Image(nsImage: img)
            } else {
                Image(systemName: "shield")
            }
        }
    }

    static let menuIcon: NSImage? = {
        guard let img = NSImage(named: "MenuBarTemplate") else { return nil }
        img.isTemplate = true
        img.size = NSSize(width: 18, height: 18)
        return img
    }()
}
