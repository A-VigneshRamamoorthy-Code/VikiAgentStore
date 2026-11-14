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

#if os(macOS)
import AppKit
#endif
import SwiftUI

/// A round Liquid Glass button; `prominent` fills it with the tint (used for "+").
///
/// On macOS/iOS 26 this is the system `.glass` / `.glassProminent` button style with a circular
/// border shape — the same rendering as native toolbar buttons (specular rim, press response).
/// A plain button wrapped in `.glassEffect` sitting on a flat sheet background reads as a grey
/// disc, which is why the sheet buttons used not to look like glass.
struct CircleButton: View {
    let icon: String
    var help = ""
    var prominent = false
    var tint: Color = Atlas.blue
    /// Outer diameter in points.
    var size: CGFloat = 42
    /// Icon colour for a plain (non-prominent) button, e.g. red for delete.
    var iconColor: Color? = nil
    let action: () -> Void
    @Environment(\.isEnabled) private var enabled

    var body: some View {
        // Disabled, a prominent button would show a white glyph on a blank disc.
        let prominent = prominent && enabled
        if #available(macOS 26, *) {
            Button(action: action) {
                Image(systemName: icon).font(.system(size: size * 0.36, weight: .semibold))
                    .foregroundStyle(prominent ? AnyShapeStyle(.white) : iconColor.map { AnyShapeStyle($0) } ?? AnyShapeStyle(.primary))
                    .frame(width: size - Self.inset, height: size - Self.inset)
                    #if os(macOS)
                    // macOS renders glassProminent untinted here, so the fill is drawn under plain glass.
                    .background { if prominent { Circle().fill(tint.gradient) } }
                    #endif
                    .contentShape(Circle())
            }
            .modifier(GlassButton(prominent: prominent && Self.nativeProminent))
            .buttonBorderShape(.circle)
            .tint(prominent ? tint : nil)
            .help(help)
            .accessibilityLabel(help.isEmpty ? icon : help)
        } else {
            Button(action: action) {
                Image(systemName: icon).font(.system(size: size * 0.36, weight: .semibold))
                    .foregroundStyle(prominent ? .white : iconColor ?? .primary)
                    .frame(width: size - 2, height: size - 2)
                    .background(Circle().fill(prominent ? tint : .clear))
                    .contentShape(Circle())
            }
            .buttonStyle(.plain).glass(size / 2).help(help)
        }
    }

    #if os(macOS)
    private static let nativeProminent = false
    #else
    private static let nativeProminent = true
    #endif

    /// The padding the glass button style adds around its label.
    private static var inset: CGFloat {
        #if os(macOS)
        return 8
        #else
        return 12
        #endif
    }
}

/// `.glass` / `.glassProminent` where available, bordered styles before that.
struct GlassButton: ViewModifier {
    var prominent = false

    func body(content: Content) -> some View {
        if #available(macOS 26, *) {
            if prominent { content.buttonStyle(.glassProminent) } else { content.buttonStyle(.glass) }
        } else {
            if prominent { content.buttonStyle(.borderedProminent) } else { content.buttonStyle(.bordered) }
        }
    }
}
