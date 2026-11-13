import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// The few things the Mac and iPhone apps do differently, behind one name.
enum Platform {
    static func copy(_ text: String) {
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        #else
        UIPasteboard.general.string = text
        #endif
    }

    @MainActor static func open(_ url: URL) {
        #if os(macOS)
        NSWorkspace.shared.open(url)
        #else
        UIApplication.shared.open(url)
        #endif
    }

    @MainActor static func share(_ items: [Any]) {
        #if os(macOS)
        if let view = NSApp.keyWindow?.contentView {
            NSSharingServicePicker(items: items).show(relativeTo: view.bounds, of: view, preferredEdge: .minY)
        }
        #else
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        guard var top = scene?.keyWindow?.rootViewController else { return }
        while let next = top.presentedViewController { top = next }
        let vc = UIActivityViewController(activityItems: items, applicationActivities: nil)
        vc.popoverPresentationController?.sourceView = top.view
        top.present(vc, animated: true)
        #endif
    }

    static var appIcon: Image {
        #if os(macOS)
        Image(nsImage: NSApp.applicationIconImage)
        #else
        Image("AppIconImage")
        #endif
    }

    static func dynamic(light: (Double, Double, Double), dark: (Double, Double, Double)) -> Color {
        #if os(macOS)
        Color(nsColor: NSColor(name: nil) { a in
            let c = a.bestMatch(from: [.darkAqua, .vibrantDark]) != nil ? dark : light
            return NSColor(srgbRed: c.0, green: c.1, blue: c.2, alpha: 1)
        })
        #else
        Color(uiColor: UIColor { t in
            let c = t.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: c.0, green: c.1, blue: c.2, alpha: 1)
        })
        #endif
    }

    static var isPhone: Bool {
        #if os(iOS)
        true
        #else
        false
        #endif
    }
}

extension View {
    @ViewBuilder func linkButton() -> some View {
        #if os(macOS)
        buttonStyle(.link)
        #else
        buttonStyle(.borderless).tint(Atlas.blue)
        #endif
    }

    /// Fixed sheet sizes are a Mac idiom; on iPhone the sheet fills the screen.
    @ViewBuilder func macFrame(width: CGFloat? = nil, height: CGFloat? = nil) -> some View {
        #if os(macOS)
        frame(width: width, height: height)
        #else
        self
        #endif
    }
}
