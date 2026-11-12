import SwiftUI

struct GeoPoint: Hashable, Codable {
    var lat: Double
    var lon: Double

    init(lat: Double, lon: Double) { self.lat = lat; self.lon = lon }

    /// Parses ipinfo's "lat,lon".
    init?(_ s: String?) {
        let parts = (s ?? "").split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
        guard parts.count == 2 else { return nil }
        lat = parts[0]; lon = parts[1]
    }
}

/// Approximate datacenter coordinates for the Azure regions the app offers.
enum AzureGeo {
    static let points: [String: GeoPoint] = [
        "centralindia": .init(lat: 18.6, lon: 73.9), "southindia": .init(lat: 12.9, lon: 80.2),
        "westeurope": .init(lat: 52.4, lon: 4.9), "northeurope": .init(lat: 53.3, lon: -6.3),
        "uksouth": .init(lat: 51.5, lon: -0.1), "eastus": .init(lat: 37.4, lon: -79.8),
        "westus2": .init(lat: 47.2, lon: -119.9), "canadacentral": .init(lat: 43.7, lon: -79.4),
        "southeastasia": .init(lat: 1.3, lon: 103.8), "eastasia": .init(lat: 22.3, lon: 114.2),
        "japaneast": .init(lat: 35.7, lon: 139.8), "australiaeast": .init(lat: -33.9, lon: 151.2),
        "uaenorth": .init(lat: 25.3, lon: 55.3), "brazilsouth": .init(lat: -23.6, lon: -46.6),
        "germanywestcentral": .init(lat: 50.1, lon: 8.7), "francecentral": .init(lat: 46.3, lon: 2.4),
    ]
}

/// How safe the user currently is; drives the whole map's tint.
enum MapTone: Equatable {
    case exposed, connecting, secure, failed

    var color: Color {
        switch self {
        case .exposed: return Atlas.amber
        case .connecting: return Atlas.blue
        case .secure: return Atlas.green
        case .failed: return Atlas.red
        }
    }
    var symbol: String {
        switch self {
        case .exposed: return "shield.slash.fill"
        case .connecting: return "shield.lefthalf.filled"
        case .secure: return "checkmark.shield.fill"
        case .failed: return "exclamationmark.shield.fill"
        }
    }
}

enum Atlas {
    static let background = Color(red: 0.953, green: 0.957, blue: 0.969)
    static let dot = Color(red: 0.773, green: 0.792, blue: 0.827)
    static let blue = Color(red: 0.039, green: 0.518, blue: 1.0)
    static let green = Color(red: 0.204, green: 0.78, blue: 0.349)
    static let amber = Color(red: 1.0, green: 0.62, blue: 0.04)
    static let red = Color(red: 1.0, green: 0.27, blue: 0.23)
    static let home = Color(red: 1.0, green: 0.624, blue: 0.039)
}

struct MapPin: Identifiable, Hashable {
    enum Kind { case azure, home, pending }
    let id: String
    let title: String
    let point: GeoPoint
    let kind: Kind
    var asleep = true
}

/// Equirectangular projection of a fixed window, scaled to fit the width so every
/// region stays visible, and pushed toward the top to leave room for the bottom card.
struct MapProjection {
    let size: CGSize
    static let lonSpan = (-130.0, 160.0)
    static let latSpan = (75.0, -45.0)
    var scale: CGFloat {
        min(size.width / CGFloat(Self.lonSpan.1 - Self.lonSpan.0), size.height / CGFloat(Self.latSpan.0 - Self.latSpan.1))
    }
    private var top: CGFloat {
        let mapHeight = CGFloat(Self.latSpan.0 - Self.latSpan.1) * scale
        return max(0, (size.height - mapHeight) * 0.22)
    }
    func point(_ g: GeoPoint) -> CGPoint {
        let cx = (Self.lonSpan.0 + Self.lonSpan.1) / 2
        return CGPoint(x: size.width / 2 + CGFloat(g.lon - cx) * scale,
                       y: top + CGFloat(Self.latSpan.0 - g.lat) * scale)
    }
}

/// The dot-matrix world map: tap a pin to choose where traffic exits.
struct AtlasMap: View {
    let pins: [MapPin]
    let selected: String?
    let home: GeoPoint?
    let tone: MapTone
    let onSelect: (String) -> Void

    var body: some View {
        GeometryReader { geo in
            let proj = MapProjection(size: geo.size)
            TimelineView(.animation(minimumInterval: 1 / 30, paused: tone != .connecting && tone != .secure)) { tl in
                let t = tl.date.timeIntervalSinceReferenceDate
                ZStack {
                    Canvas { ctx, size in
                        drawDots(ctx, proj)
                        drawArc(ctx, proj, t: t)
                    }
                    if let home {
                        let p = proj.point(home)
                        Circle().fill(Atlas.home).frame(width: 10, height: 10)
                            .overlay(Circle().stroke(.white, lineWidth: 2))
                            .shadow(color: .black.opacity(0.15), radius: 3, y: 1)
                            .position(p)
                            .accessibilityLabel("You")
                    }
                    let offsets = labelOffsets(proj)
                    ForEach(pins) { pin in
                        PinView(pin: pin, active: pin.id == selected, tone: tone, t: t,
                                labelOffset: offsets[pin.id] ?? CGSize(width: 0, height: 22))
                            .position(proj.point(pin.point))
                            .onTapGesture { onSelect(pin.id) }
                    }
                }
            }
        }
        .background(Atlas.background)
        .animation(.easeInOut(duration: 0.6), value: tone)
    }

    /// Greedy label placement: try below, above, right, then left of each pin and take
    /// the first spot that clears every pin and every label already placed.
    private func labelOffsets(_ proj: MapProjection) -> [String: CGSize] {
        let ordered = pins.sorted { ($0.id == selected ? 0 : 1) < ($1.id == selected ? 0 : 1) }
        var placed: [CGRect] = pins.map {
            let p = proj.point($0.point); return CGRect(x: p.x - 10, y: p.y - 10, width: 20, height: 20)
        }
        var result: [String: CGSize] = [:]
        for pin in ordered {
            let p = proj.point(pin.point)
            let w = CGFloat(pin.title.count) * 6.6 + 16, h: CGFloat = 20
            let candidates = [CGSize(width: 0, height: 22), CGSize(width: 0, height: -22),
                              CGSize(width: w / 2 + 14, height: 0), CGSize(width: -(w / 2 + 14), height: 0),
                              CGSize(width: w / 2 + 8, height: 18), CGSize(width: -(w / 2 + 8), height: -18)]
            let rect = { (o: CGSize) in CGRect(x: p.x + o.width - w / 2, y: p.y + o.height - h / 2, width: w, height: h) }
            let pick = candidates.first { o in !placed.contains { $0.intersects(rect(o)) } } ?? candidates[0]
            placed.append(rect(pick))
            result[pin.id] = pick
        }
        return result
    }

    private func drawDots(_ ctx: GraphicsContext, _ proj: MapProjection) {
        let r = max(1.1, proj.scale * 0.55)
        let tint = tone == .connecting ? Atlas.dot : tone.color.opacity(0.28)
        for (row, cells) in LandMask.rows.enumerated() {
            let lat = LandMask.topLat - Double(row) * LandMask.step
            for (col, land) in cells.enumerated() where land {
                let lon = LandMask.leftLon + Double(col) * LandMask.step
                let p = proj.point(GeoPoint(lat: lat, lon: lon))
                ctx.fill(Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r)),
                         with: .color(Atlas.dot))
                if tone != .connecting {
                    ctx.fill(Path(ellipseIn: CGRect(x: p.x - r, y: p.y - r, width: 2 * r, height: 2 * r)),
                             with: .color(tint))
                }
            }
        }
    }

    private func drawArc(_ ctx: GraphicsContext, _ proj: MapProjection, t: Double) {
        guard let home, let pin = pins.first(where: { $0.id == selected }),
              tone == .connecting || tone == .secure else { return }
        let a = proj.point(home), b = proj.point(pin.point)
        let mid = CGPoint(x: (a.x + b.x) / 2, y: min(a.y, b.y) - max(40, abs(b.x - a.x) * 0.25))
        var path = Path()
        path.move(to: a)
        path.addQuadCurve(to: b, control: mid)
        let gradient = Gradient(colors: [Atlas.home, tone == .secure ? Atlas.green : Atlas.blue])
        if tone == .connecting {
            // Marching dashes while the server is waking up.
            ctx.stroke(path, with: .linearGradient(gradient, startPoint: a, endPoint: b),
                       style: StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [6, 8], dashPhase: CGFloat(-t * 40)))
        } else {
            ctx.stroke(path, with: .linearGradient(gradient, startPoint: a, endPoint: b),
                       style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            // A packet travelling along the secure link.
            let f = CGFloat((t * 0.4).truncatingRemainder(dividingBy: 1))
            let x = (1 - f) * (1 - f) * a.x + 2 * (1 - f) * f * mid.x + f * f * b.x
            let y = (1 - f) * (1 - f) * a.y + 2 * (1 - f) * f * mid.y + f * f * b.y
            ctx.fill(Path(ellipseIn: CGRect(x: x - 3, y: y - 3, width: 6, height: 6)), with: .color(.white))
        }
    }
}

private struct PinView: View {
    let pin: MapPin
    let active: Bool
    let tone: MapTone
    let t: Double
    var labelOffset = CGSize(width: 0, height: 22)

    var body: some View {
        let ring = active ? (tone == .exposed ? Atlas.blue : tone.color)
                          : (pin.kind == .azure ? Atlas.blue : Atlas.home)
        ZStack {
            if active && (tone == .connecting || tone == .secure) {
                let phase = CGFloat((t * (tone == .connecting ? 1.2 : 0.5)).truncatingRemainder(dividingBy: 1))
                Circle().stroke(ring.opacity(Double(1 - phase) * 0.6), lineWidth: 2)
                    .frame(width: 18 + 34 * phase, height: 18 + 34 * phase)
            }
            Circle().fill(active ? ring : .white)
                .frame(width: active ? 18 : 14, height: active ? 18 : 14)
                .overlay(Circle().stroke(active ? .white : ring, lineWidth: active ? 3 : 2.5))
                .overlay {
                    if pin.kind != .azure {
                        Image(systemName: pin.kind == .pending ? "hourglass" : "house.fill")
                            .font(.system(size: 7, weight: .bold))
                            .foregroundStyle(active ? .white : ring)
                    }
                }
                .shadow(color: .black.opacity(0.18), radius: 4, y: 2)
            Text(pin.title)
                .font(.system(size: 11, weight: active ? .semibold : .medium))
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(.regularMaterial, in: Capsule())
                .offset(labelOffset)
                .opacity(active ? 1 : 0.85)
        }
        .frame(width: 60, height: 60)
        .contentShape(Circle().inset(by: 12))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(pin.title)
        .accessibilityAddTraits(active ? [.isButton, .isSelected] : .isButton)
    }
}
