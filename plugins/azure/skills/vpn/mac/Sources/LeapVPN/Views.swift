#if os(macOS)
import AppKit
#endif
import SwiftUI

// MARK: shared bits

/// Local view state without the @State macro (no macro plugins in this toolchain).
final class Box<T>: ObservableObject {
    @Published var v: T
    init(_ v: T) { self.v = v }
}

extension View {
    /// Liquid Glass on macOS 26+, a translucent material before that.
    /// `id`/`ns` let shapes inside a `GlassGroup` morph into each other as state changes.
    @ViewBuilder
    func glass(_ radius: CGFloat = 30, interactive: Bool = false, tint: Color? = nil,
               id: String? = nil, in ns: Namespace.ID? = nil) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        if #available(macOS 26, *) {
            let g = Glass.regular.tint(tint).interactive(interactive)
            if let id, let ns { glassEffect(g, in: shape).glassEffectID(id, in: ns) }
            else { glassEffect(g, in: shape) }
        } else {
            background(.ultraThinMaterial, in: shape)
                .overlay(shape.strokeBorder(.white.opacity(0.6), lineWidth: 0.5))
                .shadow(color: .black.opacity(0.08), radius: 18, y: 8)
        }
    }
}

/// `GlassEffectContainer` where available: nearby glass shapes blend and morph together.
struct GlassGroup<Content: View>: View {
    var spacing: CGFloat = 12
    @ViewBuilder let content: Content

    var body: some View {
        if #available(macOS 26, *) { GlassEffectContainer(spacing: spacing) { content } }
        else { content }
    }
}

#if os(macOS)
final class ActionMenuItem: NSMenuItem {
    private let handler: () -> Void
    init(_ title: String, _ handler: @escaping () -> Void) {
        self.handler = handler
        super.init(title: title, action: #selector(fire), keyEquivalent: "")
        target = self
    }
    required init(coder: NSCoder) { fatalError() }
    @objc private func fire() { handler() }
}
#endif

struct ProminentStyle: ViewModifier {
    func body(content: Content) -> some View {
        if #available(macOS 26, *) { content.buttonStyle(.glassProminent) }
        else { content.buttonStyle(.borderedProminent) }
    }
}

struct PrimaryButton: View {
    let title: String
    var icon: String? = nil
    var tint: Color = Atlas.blue
    var busy = false
    let action: () -> Void

    var body: some View {
        if #available(macOS 26, *) {
            Button(action: action) { label.frame(maxWidth: .infinity, minHeight: 30) }
                .buttonStyle(.glassProminent)
                .controlSize(.extraLarge)
                .tint(tint)
        } else {
            Button(action: action) {
                label
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .foregroundStyle(.white)
                    .background(LinearGradient(colors: [tint.opacity(0.85), tint], startPoint: .top, endPoint: .bottom),
                                in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }

    private var label: some View {
        HStack(spacing: 8) {
            if busy { ProgressView().controlSize(.small).tint(.white) }
            else if let icon { Image(systemName: icon) }
            Text(title).fontWeight(.semibold)
        }
    }
}

