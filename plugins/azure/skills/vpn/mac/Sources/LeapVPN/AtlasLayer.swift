import SwiftUI

/// Land dots as map units, worked out once: projecting them is then a multiply-add per dot.
enum AtlasDots {
    static let units: [(u: CGFloat, v: CGFloat)] = {
        var out: [(u: CGFloat, v: CGFloat)] = []
        for (row, cells) in LandMask.rows.enumerated() {
            let lat = LandMask.topLat - Double(row) * LandMask.step
            for (col, land) in cells.enumerated() where land {
                let lon = LandMask.leftLon + Double(col) * LandMask.step
                out.append((MapProjection.u(lon), MapProjection.v(lat)))
            }
        }
        return out
    }()
}

/// Everything drawn on the map for one camera position: dots, the home dot, pins and labels.
/// Cheap to rebuild every frame: the dots are one path filled twice, and labels are plain shapes.
struct AtlasLayer: View {
    let pins: [MapPin]
    let selected: String?
    let home: GeoPoint?
    let tone: MapTone
    let proj: MapProjection
    var hovered: String? = nil
    /// Names reveal as pins near the centre or the map zooms in; otherwise every placed pin is named.
    var progressive = true

    private var rippling: Bool { tone == .connecting || tone == .secure }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 60, paused: !rippling)) { tl in
            let t = tl.date.timeIntervalSinceReferenceDate
            ZStack(alignment: .topLeading) {
                Canvas(rendersAsynchronously: false) { ctx, _ in drawDots(ctx, t: rippling ? t : 0) }
                if let home, proj.isVisible(proj.point(home), margin: 10) {
                    Circle().fill(Atlas.home).frame(width: 10, height: 10)
                        .overlay(Circle().stroke(Atlas.surface, lineWidth: 2))
                        .shadow(color: .black.opacity(0.15), radius: 3, y: 1)
                        .position(proj.point(home))
                        .accessibilityLabel("You")
                }
                ForEach(visiblePins) { pin in
                    AtlasPin(pin: pin, active: pin.id == selected, hovered: pin.id == hovered, tone: tone, t: t)
                        .position(proj.point(pin.point))
                }
                ForEach(labels) { l in
                    AtlasLabel(pin: l.pin, detailed: l.detailed, active: l.pin.id == selected)
                        .opacity(Double(l.prominence))
                        .scaleEffect(0.78 + 0.22 * l.prominence, anchor: l.anchor)
                        .position(l.centre)
                        .allowsHitTesting(false)
                }
            }
            .frame(width: proj.size.width, height: proj.size.height)
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.62), value: hovered)
        .animation(.easeInOut(duration: 0.6), value: tone)
    }

    private var visiblePins: [MapPin] {
        pins.filter { proj.isVisible(proj.point($0.point), margin: 40) }
    }

    // MARK: hit testing

    /// The pin under a point (taps and hover), preferring the closest within reach.
    static func pin(at p: CGPoint, pins: [MapPin], proj: MapProjection, reach: CGFloat = 24) -> String? {
        var best: (String, CGFloat)?
        for pin in pins {
            let q = proj.point(pin.point)
            let d = hypot(q.x - p.x, q.y - p.y)
            if d <= reach, d < (best?.1 ?? .infinity) { best = (pin.id, d) }
        }
        return best?.0
    }

    // MARK: labels

    struct Placed: Identifiable {
        let pin: MapPin
        let centre: CGPoint
        let anchor: UnitPoint
        let prominence: CGFloat
        let detailed: Bool
        var id: String { pin.id }
    }

    private static func smooth(_ a: CGFloat, _ b: CGFloat, _ x: CGFloat) -> CGFloat {
        let t = min(1, max(0, (x - a) / (b - a)))
        return t * t * (3 - 2 * t)
    }

    /// How much a pin deserves a name right now: near the middle of the view, the map zoomed
    /// in, or chosen/hovered. Fades smoothly so names arrive gradually as the user explores.
    private func prominence(_ pin: MapPin, at p: CGPoint) -> CGFloat {
        if pin.id == selected || pin.id == hovered { return 1 }
        guard progressive else { return pin.kind == .available ? 0 : 1 }
        let c = proj.centre
        let halfW = max(1, proj.size.width / 2)
        let halfH = max(1, (proj.size.height * (1 - proj.framing.bottomFraction) - proj.framing.topInset) / 2)
        let d = hypot((p.x - c.x) / halfW, (p.y - c.y) / halfH)
        let near = 1 - Self.smooth(0.3, 1.0, d)
        let zoomed = Self.smooth(1.3, 2.8, proj.camera.zoom)
        let built: CGFloat = pin.kind == .available ? 0 : 0.15
        let score = near * (0.55 + 0.45 * zoomed) + zoomed * 0.35 + built
        return Self.smooth(0.3, 0.72, score)
    }

    /// Greedy, collision-free placement: most prominent first, each trying right, left, below
    /// then above its pin. Names that don't fit wait until the user zooms in.
    private var labels: [Placed] {
        let bounds = CGRect(origin: .zero, size: proj.size).insetBy(dx: 4, dy: 4)
        var candidates: [(MapPin, CGPoint, CGFloat)] = []
        for pin in pins {
            let p = proj.point(pin.point)
            guard proj.isVisible(p, margin: 0) else { continue }
            let pr = prominence(pin, at: p)
            if pr > 0.04 { candidates.append((pin, p, pr)) }
        }
        candidates.sort {
            let a = $0.0.id == selected || $0.0.id == hovered, b = $1.0.id == selected || $1.0.id == hovered
            if a != b { return a }
            return $0.2 > $1.2
        }
        var taken: [CGRect] = pins.compactMap {
            let p = proj.point($0.point)
            return proj.isVisible(p, margin: 0) ? CGRect(x: p.x - 7, y: p.y - 7, width: 14, height: 14) : nil
        }
        var out: [Placed] = []
        for (pin, p, pr) in candidates {
            let detailed = pin.id == hovered || pin.id == selected
            let size = AtlasLabel.size(for: pin, detailed: detailed)
            let gap: CGFloat = detailed ? 16 : 12
            let spots: [(CGPoint, UnitPoint)] = [
                (CGPoint(x: p.x + gap + size.width / 2, y: p.y), .leading),
                (CGPoint(x: p.x - gap - size.width / 2, y: p.y), .trailing),
                (CGPoint(x: p.x, y: p.y + gap + size.height / 2), .top),
                (CGPoint(x: p.x, y: p.y - gap - size.height / 2), .bottom),
            ]
            for (c, anchor) in spots {
                let r = CGRect(x: c.x - size.width / 2, y: c.y - size.height / 2, width: size.width, height: size.height)
                guard bounds.contains(r) || detailed else { continue }
                // Pins themselves are obstacles, except the label's own pin.
                if taken.contains(where: { $0.intersects(r.insetBy(dx: 2, dy: 2)) && !$0.contains(p) }) { continue }
                taken.append(r)
                out.append(Placed(pin: pin, centre: c, anchor: anchor, prominence: pr, detailed: detailed))
                break
            }
        }
        return out
    }

    // MARK: dots

    /// Land dots in one path; while connecting or secure a ripple spreads from the chosen pin
    /// like a wave across water — quick and bright while connecting, slow and calm once secure.
    private func drawDots(_ ctx: GraphicsContext, t: Double) {
        let s = proj.scale, m = proj.mapSize, c = proj.centre, cam = proj.camera
        // Dots grow with zoom, but not into blobs.
        let r = max(1.0, min(s, proj.unit * 2.4) * 0.55)
        let w = proj.size.width, h = proj.size.height, margin = r * 2
        let ox = c.x - cam.u * m.width, oy = c.y - cam.v * m.height
        let tint = tone.color.opacity(tone == .secure ? 0.28 : 0.22)
        let centre = rippling ? pins.first { $0.id == selected }.map { proj.point($0.point) } : nil

        if let centre {
            let speed = tone == .connecting ? 5.0 : 2.2
            let wavelength = max(36, 70 * s / 2.6)
            let reach = 900 * s / 2.6
            var base = Path()
            var glow = [Path](repeating: Path(), count: 4)
            for d in AtlasDots.units {
                let x = ox + d.u * m.width, y = oy + d.v * m.height
                guard x > -margin, y > -margin, x < w + margin, y < h + margin else { continue }
                let dist = hypot(x - centre.x, y - centre.y)
                let fall = exp(-Double(dist / reach))
                let wave = sin(Double(dist / wavelength) * 2 * .pi - t * speed)
                let rr = r * CGFloat(1 + 0.45 * wave * fall)
                let rect = CGRect(x: x - rr, y: y - rr, width: 2 * rr, height: 2 * rr)
                base.addEllipse(in: rect)
                let g = max(0, wave) * fall
                if g > 0.05 { glow[min(3, Int(g * 4))].addEllipse(in: rect) }
            }
            ctx.fill(base, with: .color(Atlas.dot))
            ctx.fill(base, with: .color(tint))
            for (i, p) in glow.enumerated() {
                ctx.fill(p, with: .color(tone.color.opacity(0.55 * (Double(i) + 0.5) / 4)))
            }
        } else {
            var base = Path()
            let side = 2 * r
            for d in AtlasDots.units {
                let x = ox + d.u * m.width, y = oy + d.v * m.height
                guard x > -margin, y > -margin, x < w + margin, y < h + margin else { continue }
                base.addEllipse(in: CGRect(x: x - r, y: y - r, width: side, height: side))
            }
            ctx.fill(base, with: .color(Atlas.dot))
            ctx.fill(base, with: .color(tint))
        }
    }
}

/// A location's name on the map: its circular flag and name; hovered or chosen, also the city.
struct AtlasLabel: View {
    let pin: MapPin
    let detailed: Bool
    let active: Bool

    static func size(for pin: MapPin, detailed: Bool) -> CGSize {
        if detailed {
            let text = max(CGFloat(pin.name.count) * 7.4, CGFloat(pin.subtitle?.count ?? 0) * 6.2)
            return CGSize(width: 26 + 8 + text + 22, height: 36)
        }
        return CGSize(width: 18 + 6 + CGFloat(pin.name.count) * 6.5 + 16, height: 24)
    }

    var body: some View {
        HStack(spacing: detailed ? 8 : 6) {
            badge
            VStack(alignment: .leading, spacing: 0) {
                Text(pin.name)
                    .font(.system(size: detailed ? 13 : 11, weight: detailed || active ? .semibold : .medium))
                    .foregroundStyle(.primary)
                if detailed, let sub = pin.subtitle {
                    Text(sub).font(.system(size: 10.5, weight: .medium)).foregroundStyle(.secondary)
                }
            }
            .lineLimit(1)
            .fixedSize()
        }
        .padding(.leading, 3)
        .padding(.trailing, detailed ? 12 : 9)
        .padding(.vertical, 3)
        .background(Capsule().fill(Atlas.label))
        .overlay(Capsule().strokeBorder(active ? Atlas.pin.opacity(0.7) : Color.primary.opacity(0.08), lineWidth: active ? 1.5 : 1))
        .shadow(color: .black.opacity(detailed ? 0.2 : 0.12), radius: detailed ? 8 : 4, y: detailed ? 3 : 1)
        .fixedSize()
    }

    @ViewBuilder private var badge: some View {
        let size: CGFloat = detailed ? 28 : 18
        switch pin.kind {
        case .home, .direct, .pending:
            Image(systemName: pin.kind == .pending ? "hourglass" : pin.kind == .direct ? "desktopcomputer" : "house.fill")
                .font(.system(size: size * 0.48, weight: .bold))
                .foregroundStyle(.white)
                .frame(width: size, height: size)
                .background(Circle().fill(Atlas.home))
                .overlay(alignment: .bottomTrailing) {
                    if let c = pin.country, detailed { FlagBadge(country: c, size: 13).offset(x: 3, y: 3) }
                }
        default:
            FlagBadge(country: pin.country, size: size)
        }
    }
}

/// A location on the map. Pulses while it's the active exit; grows under the pointer.
struct AtlasPin: View {
    let pin: MapPin
    let active: Bool
    let hovered: Bool
    let tone: MapTone
    let t: Double

    var body: some View {
        let ring = active ? (tone == .exposed ? Atlas.pin : tone.color)
                          : (pin.kind == .azure || pin.kind == .available ? Atlas.pin : Atlas.home)
        let small = pin.kind == .available && !active && !hovered
        let d: CGFloat = active ? 18 : small ? 9 : 14
        ZStack {
            if active && (tone == .connecting || tone == .secure) {
                // Two staggered rings, so the pin keeps pulsing while it's in use.
                ForEach(0..<2) { i in
                    let phase = CGFloat((t * (tone == .connecting ? 1.2 : 0.55) + Double(i) * 0.5).truncatingRemainder(dividingBy: 1))
                    Circle().fill(ring.opacity(Double(1 - phase) * 0.18))
                        .overlay(Circle().stroke(ring.opacity(Double(1 - phase) * 0.7), lineWidth: 2))
                        .frame(width: 18 + 40 * phase, height: 18 + 40 * phase)
                }
            }
            if hovered {
                Circle().fill(ring.opacity(0.18)).frame(width: d + 16, height: d + 16)
            }
            Circle().fill(active ? ring : Atlas.surface.opacity(small ? 0.75 : 1))
                .frame(width: d, height: d)
                .overlay(Circle().stroke(active ? Atlas.surface : ring.opacity(small ? 0.6 : 1),
                                         lineWidth: active ? 3 : small ? 1.5 : 2.5))
                .scaleEffect(active && tone == .secure ? 1 + 0.08 * CGFloat(sin(t * 3)) : 1)
                .overlay {
                    if pin.kind != .azure && pin.kind != .available {
                        Image(systemName: pin.kind == .pending ? "hourglass" : pin.kind == .direct ? "desktopcomputer" : "house.fill")
                            .font(.system(size: 7, weight: .bold))
                            .foregroundStyle(active ? .white : ring)
                    }
                }
                .shadow(color: .black.opacity(0.18), radius: 4, y: 2)
        }
        .scaleEffect(hovered ? 1.3 : 1)
        .frame(width: 60, height: 60)
        .allowsHitTesting(false)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(pin.title)
        .accessibilityAddTraits(active ? [.isButton, .isSelected] : .isButton)
    }
}
