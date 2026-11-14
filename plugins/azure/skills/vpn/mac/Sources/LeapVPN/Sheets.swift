#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

// MARK: brand

/// Sheet palette: Leap mint on a deep green-black in dark mode, a soft mint-white in light.
enum SheetTheme {
    static let mint = Color(red: 0.294, green: 1.0, blue: 0.702)        // #4BFFB3
    static let mintSoft = Color(red: 0.714, green: 1.0, blue: 0.878)    // #B6FFE0
    /// Mint for text and icons: the brand mint in dark mode, a deeper shade that reads on white.
    static let accent = Platform.dynamic(light: (0.0, 0.58, 0.38), dark: (0.294, 1.0, 0.702))
    /// Label colour on an accent-filled button.
    static let onAccent = Platform.dynamic(light: (1, 1, 1), dark: (0.043, 0.078, 0.063))
    static let base = Platform.dynamic(light: (0.965, 0.98, 0.973), dark: (0.043, 0.078, 0.063))  // #0B1410
    /// Card surface: white on the light base, a whisper of white on the dark one. Never a grey slab.
    static let surface = Platform.dynamic(light: (1, 1, 1), dark: (0.075, 0.118, 0.098))
    static let hairline = Platform.dynamic(light: (0.85, 0.9, 0.88), dark: (0.16, 0.24, 0.2))
}

/// The backdrop every sheet sits on: a deep base with a faint mint and blue glow, so glass
/// controls have something to refract instead of a flat grey fill.
struct SheetBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        ZStack {
            SheetTheme.base
            RadialGradient(colors: [SheetTheme.mint.opacity(scheme == .dark ? 0.16 : 0.22), .clear],
                           center: .topLeading, startRadius: 0, endRadius: 420)
            RadialGradient(colors: [Atlas.blue.opacity(scheme == .dark ? 0.10 : 0.07), .clear],
                           center: .bottomTrailing, startRadius: 0, endRadius: 460)
        }
        .ignoresSafeArea()
    }
}

extension View {
    /// Common chrome for a sheet's root view: padding, brand backdrop and the Mac size.
    @ViewBuilder
    func sheetChrome(width: CGFloat? = nil, height: CGFloat? = nil) -> some View {
        #if os(iOS)
        padding(.horizontal, 18).padding(.top, 20)
            .macFrame(width: width, height: height)
            .background { SheetBackground() }
            .presentationBackground { SheetBackground() }
            .presentationCornerRadius(34)
        #else
        padding(22)
            .macFrame(width: width, height: height)
            .background { SheetBackground() }
        #endif
    }
}

// MARK: header

struct SheetHeader: View {
    let icon: String
    let title: String
    var tint: Color = Atlas.blue
    var trailing: AnyView? = nil
    var subtitle: String? = nil
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 15, weight: .semibold)).foregroundStyle(tint)
                .frame(width: 36, height: 36)
                .background(Circle().fill(tint.opacity(0.16)))
                .overlay(Circle().strokeBorder(tint.opacity(0.3), lineWidth: 0.5))
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.title2.weight(.bold)).lineLimit(1).minimumScaleFactor(0.8)
                if let subtitle { Text(subtitle).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            }
            Spacer(minLength: 8)
            GlassGroup(spacing: 8) {
                HStack(spacing: 8) {
                    trailing
                    CircleButton(icon: "xmark", help: "Close") { dismiss() }.keyboardShortcut(.cancelAction)
                }
            }
        }
    }
}

// MARK: sections

/// A grouped section: a small caps title over a clean surface (white in light, near-black
/// in dark) with a hairline edge — translucent, not a grey slab.
struct Card<Content: View>: View {
    var title: String? = nil
    var trailing: String? = nil
    var padding: CGFloat = 14
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if title != nil || trailing != nil {
                HStack(alignment: .firstTextBaseline) {
                    if let title { Text(title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.secondary).tracking(0.7) }
                    Spacer()
                    if let trailing { Text(trailing).font(.caption.weight(.semibold)).foregroundStyle(.secondary).monospacedDigit() }
                }
                .padding(.horizontal, 4)
            }
            VStack(alignment: .leading, spacing: 10) { content }
                .padding(padding)
                .frame(maxWidth: .infinity, alignment: .leading)
                .sheetSurface()
        }
    }
}

extension View {
    /// The surface under a section or tile.
    func sheetSurface(_ radius: CGFloat = 18, tint: Color? = nil) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        return background {
            ZStack {
                shape.fill(SheetTheme.surface.opacity(0.72))
                if let tint { shape.fill(tint.opacity(0.07)) }
            }
        }
        .overlay(shape.strokeBorder(SheetTheme.hairline.opacity(0.9), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.04), radius: 10, y: 4)
    }
}

/// A numbered step in a setup flow.
struct SheetStep<Content: View>: View {
    let n: Int
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(n)").font(.footnote.weight(.bold)).foregroundStyle(SheetTheme.accent)
                .frame(width: 26, height: 26)
                .background(Circle().fill(SheetTheme.mint.opacity(0.16)))
                .overlay(Circle().strokeBorder(SheetTheme.mint.opacity(0.35), lineWidth: 0.5))
            VStack(alignment: .leading, spacing: 8) {
                Text(title).font(.callout.weight(.semibold)).padding(.top, 3)
                content
            }
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheetSurface()
    }
}

/// Scrolls on iPhone (keyboard, small screens); a Mac sheet sizes to its content instead.
struct SheetScroll<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        #if os(iOS)
        ScrollView { content.padding(.bottom, 24) }.scrollIndicators(.hidden).scrollDismissesKeyboard(.interactively)
        #else
        content
        #endif
    }
}

// MARK: usage

extension VPNController {
    var usageCurrency: String { store.sessions.first?.currency ?? spend?.currency ?? CurrencyResolver.current }
}
