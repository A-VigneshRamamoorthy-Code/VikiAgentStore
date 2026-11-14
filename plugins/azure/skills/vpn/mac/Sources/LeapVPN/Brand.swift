import SwiftUI

/// Leap's brand palette: mint on near-black ink.
enum Brand {
    /// #4BFFB3
    static let mint = Color(red: 0.294, green: 1.0, blue: 0.702)
    /// #B6FFE0
    static let mintSoft = Color(red: 0.714, green: 1.0, blue: 0.878)
    /// #0B1410
    static let ink = Color(red: 0.043, green: 0.078, blue: 0.063)
    /// Mint that stays readable as text or a glyph on a light background.
    static let accent = Platform.dynamic(light: (0.0, 0.58, 0.38), dark: (0.294, 1.0, 0.702))
    static let accentGradient = LinearGradient(colors: [accent, Platform.dynamic(light: (0.0, 0.47, 0.42), dark: (0.714, 1.0, 0.878))],
                                               startPoint: .topLeading, endPoint: .bottomTrailing)
    static let orbFill = Platform.dynamic(light: (0.93, 0.99, 0.96), dark: (0.07, 0.13, 0.10))
    /// Deep, saturated green for filled surfaces that carry white text or glyphs.
    static let deep = Color(red: 0.0, green: 0.47, blue: 0.31)
}

// MARK: the lens mark

/// The Leap lens: a noisy wave that comes out of the glass as one clean line.
/// A vector redraw of the app icon, crisp at any size, with an optional drifting wave.
struct BrandMark: View {
    var size: CGFloat = 120
    /// Draw the dark app-icon tile behind the lens.
    var tile = true
    var animated = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: !moving)) { ctx in
            mark(phase: moving ? ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1000) * 1.4 : 0.9)
        }
        .frame(width: size, height: size)
        .accessibilityElement()
        .accessibilityLabel("Leap VPN")
    }

    private var moving: Bool { animated && !reduceMotion }

    private func mark(phase: Double) -> some View {
        let d = size * 0.5
        let tileShape = RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
        return ZStack {
            if tile {
                tileShape
                    .fill(LinearGradient(colors: [Color(red: 0.2, green: 0.22, blue: 0.21), Color(red: 0.03, green: 0.05, blue: 0.04)],
                                         startPoint: .topLeading, endPoint: .bottomTrailing))
                    .overlay(tileShape.strokeBorder(.white.opacity(0.1), lineWidth: max(0.5, size * 0.004)))
                    .shadow(color: .black.opacity(0.28), radius: size * 0.08, y: size * 0.04)
            }
            LensWave(phase: phase)
                .stroke(Brand.mint, style: StrokeStyle(lineWidth: size * 0.04, lineCap: .round, lineJoin: .round))
                .shadow(color: Brand.mint.opacity(0.6), radius: size * 0.03)
                .mask(LensCutout(radius: d / 2 * 1.02).fill(style: FillStyle(eoFill: true)))
                .mask(tile ? AnyView(tileShape) : AnyView(LinearGradient(colors: [.clear, .black, .black, .clear],
                                                                          startPoint: .leading, endPoint: .trailing)))
            lens(d)
            Capsule()
                .fill(Brand.mintSoft)
                .frame(width: d * 0.96, height: size * 0.036)
                .shadow(color: Brand.mint.opacity(0.9), radius: size * 0.025)
        }
    }

    private func lens(_ d: CGFloat) -> some View {
        let glass = RadialGradient(colors: [Color(red: 0.25, green: 0.36, blue: 0.30), Color(red: 0.11, green: 0.17, blue: 0.14)],
                                   center: UnitPoint(x: 0.4, y: 0.3), startRadius: 0, endRadius: d * 0.7)
        let rim: CGFloat = max(0.75, size * 0.01)
        return Circle()
            .fill(glass)
            .overlay(Circle().strokeBorder(Color.white.opacity(0.32), lineWidth: rim))
            .overlay(highlight(d))
            .shadow(color: Brand.mint.opacity(0.4), radius: size * 0.06)
            .frame(width: d, height: d)
    }

    private func highlight(_ d: CGFloat) -> some View {
        let sheen = LinearGradient(colors: [Color.white.opacity(0.8), Color.white.opacity(0)], startPoint: .top, endPoint: .bottom)
        return Ellipse()
            .fill(sheen)
            .frame(width: d * 0.4, height: d * 0.15)
            .rotationEffect(.degrees(-32))
            .offset(x: -d * 0.12, y: -d * 0.3)
    }
}

private struct LensWave: Shape {
    var phase: Double
    var animatableData: Double { get { phase } set { phase = newValue } }

    func path(in rect: CGRect) -> Path {
        let amp = rect.height * 0.095, wavelength = rect.width * 0.36
        var p = Path()
        let steps = 120
        for i in 0...steps {
            let x = rect.minX + rect.width * CGFloat(i) / CGFloat(steps)
            let y = rect.midY - amp * CGFloat(sin(Double(x / wavelength) * 2 * .pi + phase))
            i == 0 ? p.move(to: CGPoint(x: x, y: y)) : p.addLine(to: CGPoint(x: x, y: y))
        }
        return p
    }
}

private struct LensCutout: Shape {
    let radius: CGFloat
    func path(in rect: CGRect) -> Path {
        var p = Path(rect.insetBy(dx: -40, dy: -40))
        p.addEllipse(in: CGRect(x: rect.midX - radius, y: rect.midY - radius, width: radius * 2, height: radius * 2))
        return p
    }
}

// MARK: glyphs

/// One symbol in a softly lit glass orb, with a slow mint ring. Bounces when `active` flips on.
struct BrandOrb: View {
    let symbol: String
    var size: CGFloat = 120
    var active = true
    /// Dims the ring and glow (used to show "off").
    var lit = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme
    @StateObject private var appeared = Box(false)

    var body: some View {
        ZStack {
            Circle()
                .fill(Brand.mint.opacity(lit ? 0.28 : 0.06))
                .blur(radius: size * 0.22)
                .scaleEffect(1.1)
            orb
            TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion || !lit)) { ctx in
                Circle()
                    .strokeBorder(AngularGradient(colors: [Brand.mint, Brand.mint.opacity(0), Brand.mintSoft.opacity(0.8), Brand.mint.opacity(0), Brand.mint],
                                                  center: .center),
                                  lineWidth: max(1.2, size * 0.014))
                    .rotationEffect(.degrees(reduceMotion ? 0 : ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 360) * 24))
                    .opacity(lit ? 0.9 : 0.15)
            }
            Image(systemName: symbol)
                .font(.system(size: size * 0.36, weight: .semibold))
                .foregroundStyle(glyphStyle)
                .symbolEffect(.bounce, value: active && appeared.v)
                .contentTransition(.symbolEffect(.replace))
        }
        .frame(width: size, height: size)
        .onAppear { DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { appeared.v = true } }
        .accessibilityHidden(true)
    }

    /// Mint on the pale light-mode orb; white once the orb turns dark.
    private var glyphStyle: AnyShapeStyle {
        guard lit else { return AnyShapeStyle(.secondary) }
        return scheme == .dark ? AnyShapeStyle(Color.white) : AnyShapeStyle(Brand.accentGradient)
    }

    @ViewBuilder private var orb: some View {
        if #available(macOS 26, iOS 26, *) {
            Circle().fill(Brand.orbFill.opacity(0.5))
                .glassEffect(.regular.tint(Brand.mint.opacity(lit ? 0.1 : 0)), in: Circle())
        } else {
            Circle().fill(Brand.orbFill).overlay(Circle().fill(.ultraThinMaterial).opacity(0.4))
                .overlay(Circle().strokeBorder(.white.opacity(0.25), lineWidth: 0.5))
        }
    }
}

/// Page indicator: the current page stretches into a mint capsule.
struct PageDots: View {
    let count: Int
    let current: Int
    var onSelect: (Int) -> Void = { _ in }

    var body: some View {
        HStack(spacing: 7) {
            ForEach(0..<count, id: \.self) { i in
                Capsule()
                    .fill(i == current ? AnyShapeStyle(Brand.accent) : AnyShapeStyle(.primary.opacity(0.18)))
                    .frame(width: i == current ? 22 : 7, height: 7)
                    .contentShape(Rectangle().inset(by: -6))
                    .onTapGesture { onSelect(i) }
            }
        }
        .animation(.spring(response: 0.4, dampingFraction: 0.75), value: current)
        .accessibilityElement()
        .accessibilityLabel("Page \(current + 1) of \(count)")
    }
}

// MARK: buttons

/// Onboarding call-to-action: a tall glass capsule. `.primary` is tinted deep green with white
/// text, `.secondary` clear glass. Both share one shape and height, so they line up exactly.
struct BrandButton: View {
    enum Kind { case primary, secondary }
    let title: String
    var icon: String? = nil
    var kind: Kind = .primary
    var busy = false
    let action: () -> Void

    static var height: CGFloat { Platform.isPhone ? 52 : 46 }

    var body: some View {
        Button(action: action) {
            label
                .frame(maxWidth: .infinity)
                .frame(height: Self.height)
                .contentShape(Capsule())
        }
        .buttonStyle(BrandButtonStyle(kind: kind))
    }

    private var label: some View {
        HStack(spacing: 8) {
            if busy { ProgressView().controlSize(.small).tint(kind == .primary ? .white : .primary) }
            else if let icon { Image(systemName: icon).fontWeight(.semibold).contentTransition(.symbolEffect(.replace)) }
            Text(title).fontWeight(.semibold).lineLimit(1).contentTransition(.interpolate)
        }
        .font(.body)
        .animation(.smooth(duration: 0.25), value: title)
    }
}

private struct BrandButtonStyle: ButtonStyle {
    let kind: BrandButton.Kind

    func makeBody(configuration: Configuration) -> some View {
        Styled(configuration: configuration, kind: kind)
    }

    private struct Styled: View {
        let configuration: ButtonStyleConfiguration
        let kind: BrandButton.Kind
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .foregroundStyle(kind == .primary ? AnyShapeStyle(Color.white) : AnyShapeStyle(.primary))
                .modifier(BrandButtonGlass(kind: kind))
                .scaleEffect(configuration.isPressed ? 0.98 : 1)
                .opacity(enabled ? 1 : 0.5)
                .animation(.spring(response: 0.3, dampingFraction: 0.7), value: configuration.isPressed)
        }
    }
}

private struct BrandButtonGlass: ViewModifier {
    let kind: BrandButton.Kind

    func body(content: Content) -> some View {
        if #available(macOS 26, iOS 26, *) {
            if kind == .primary {
                // Solid fill under the tinted glass so the button stays deep green wherever glass renders pale.
                content
                    .background(Capsule().fill(Brand.deep))
                    .glassEffect(.regular.tint(Brand.deep).interactive(), in: Capsule())
            } else {
                content.glassEffect(.regular.interactive(), in: Capsule())
            }
        } else {
            content.background {
                let shape = Capsule()
                if kind == .primary {
                    shape.fill(LinearGradient(colors: [Brand.deep.opacity(0.88), Brand.deep], startPoint: .top, endPoint: .bottom))
                        .overlay(shape.strokeBorder(.white.opacity(0.25), lineWidth: 0.5))
                } else {
                    shape.fill(.ultraThinMaterial).overlay(shape.strokeBorder(.primary.opacity(0.12), lineWidth: 0.5))
                }
            }
        }
    }
}

/// A small icon-only glass pill (Skip, Close, Back).
struct BrandPill: View {
    let title: String
    var icon: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                if let icon { Image(systemName: icon).font(.system(size: 12, weight: .bold)) }
                if !title.isEmpty { Text(title).font(.callout.weight(.semibold)) }
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, title.isEmpty ? 0 : 14)
            .frame(minWidth: 34, minHeight: 34)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .modifier(PillGlass())
        .accessibilityLabel(title.isEmpty ? (icon ?? "") : title)
    }
}

private struct PillGlass: ViewModifier {
    func body(content: Content) -> some View {
        if #available(macOS 26, iOS 26, *) { content.glassEffect(.regular.interactive(), in: Capsule()) }
        else { content.background(.ultraThinMaterial, in: Capsule()).overlay(Capsule().strokeBorder(.primary.opacity(0.1), lineWidth: 0.5)) }
    }
}
