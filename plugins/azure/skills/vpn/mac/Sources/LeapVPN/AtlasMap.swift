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
        "centralindia": .init(lat: 18.6, lon: 73.9), "indiasouthcentral": .init(lat: 17.4, lon: 78.5),
        "westeurope": .init(lat: 52.4, lon: 4.9), "northeurope": .init(lat: 53.3, lon: -6.3),
        "uksouth": .init(lat: 51.5, lon: -0.1), "eastus": .init(lat: 37.4, lon: -79.8),
        "centralus": .init(lat: 41.6, lon: -93.6), "northcentralus": .init(lat: 41.9, lon: -87.6),
        "southcentralus": .init(lat: 29.4, lon: -98.5), "westus": .init(lat: 37.8, lon: -122.4),
        "westus2": .init(lat: 47.2, lon: -119.9), "westus3": .init(lat: 33.4, lon: -112.1),
        "canadacentral": .init(lat: 43.7, lon: -79.4), "mexicocentral": .init(lat: 20.6, lon: -100.4),
        "brazilsouth": .init(lat: -23.6, lon: -46.6), "chilecentral": .init(lat: -33.4, lon: -70.7),
        "francecentral": .init(lat: 46.3, lon: 2.4), "germanywestcentral": .init(lat: 50.1, lon: 8.7),
        "switzerlandnorth": .init(lat: 47.5, lon: 8.6), "austriaeast": .init(lat: 48.2, lon: 16.4),
        "italynorth": .init(lat: 45.5, lon: 9.2), "spaincentral": .init(lat: 40.4, lon: -3.7),
        "belgiumcentral": .init(lat: 50.8, lon: 4.4), "denmarkeast": .init(lat: 55.7, lon: 12.6),
        "polandcentral": .init(lat: 52.2, lon: 21.0), "swedencentral": .init(lat: 60.7, lon: 17.1),
        "norwayeast": .init(lat: 59.9, lon: 10.8), "israelcentral": .init(lat: 32.1, lon: 34.8),
        "uaenorth": .init(lat: 25.3, lon: 55.3), "southafricanorth": .init(lat: -25.7, lon: 28.2),
        "southeastasia": .init(lat: 1.3, lon: 103.8), "eastasia": .init(lat: 22.3, lon: 114.2),
        "japaneast": .init(lat: 35.7, lon: 139.8), "japanwest": .init(lat: 34.7, lon: 135.5),
        "koreacentral": .init(lat: 37.6, lon: 127.0), "taiwannorth": .init(lat: 25.0, lon: 121.4),
        "malaysiawest": .init(lat: 3.1, lon: 101.7), "indonesiacentral": .init(lat: -6.2, lon: 106.8),
        "australiaeast": .init(lat: -33.9, lon: 151.2), "newzealandnorth": .init(lat: -36.8, lon: 174.8),
        "southindia": .init(lat: 12.9, lon: 80.2),
    ]
}

/// How safe the user currently is; drives the whole map's tint.
enum MapTone: Equatable {
    case exposed, connecting, secure, failed

    var color: Color {
        switch self {
        case .exposed: return Atlas.red
        case .connecting: return Atlas.amber
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
    static let background = dynamic(light: (0.953, 0.957, 0.969), dark: (0.043, 0.078, 0.063))
    static let dot = dynamic(light: (0.773, 0.792, 0.827), dark: (0.20, 0.27, 0.24))
    /// Pin rings: system blue on the light map, the brand mint on the dark one.
    static let pin = dynamic(light: (0.039, 0.518, 1.0), dark: (0.294, 1.0, 0.702))
    /// Location labels on the map: opaque enough to read over dots in either mode.
    static let label = dynamic(light: (1, 1, 1), dark: (0.10, 0.16, 0.13))
    /// Pin and card fills that sit on the map.
    static let surface = dynamic(light: (1, 1, 1), dark: (0.16, 0.17, 0.20))
    static let blue = Color(red: 0.039, green: 0.518, blue: 1.0)
    static let green = Color(red: 0.204, green: 0.78, blue: 0.349)
    static let amber = Color(red: 1.0, green: 0.62, blue: 0.04)
    static let red = Color(red: 1.0, green: 0.27, blue: 0.23)
    static let home = Color(red: 1.0, green: 0.624, blue: 0.039)
    static let mint = Color(red: 0.294, green: 1.0, blue: 0.702)

    private static func dynamic(light: (Double, Double, Double), dark: (Double, Double, Double)) -> Color {
        Platform.dynamic(light: light, dark: dark)
    }
}

struct MapPin: Identifiable, Hashable {
    enum Kind { case azure, available, home, direct, pending }
    let id: String
    let title: String
    let point: GeoPoint
    let kind: Kind
    var asleep = true
}

extension MapPin {
    private var region: RegionChoice? { RegionChoice.all.first { $0.code == id } }

    /// ISO country code, from the region or the flag emoji the title starts with.
    var country: String? {
        if let r = region { return r.country }
        let letters = title.unicodeScalars.prefix(2).compactMap { s -> Character? in
            (0x1F1E6...0x1F1FF).contains(s.value) ? Character(UnicodeScalar(s.value - 0x1F1E6 + 65)!) : nil
        }
        guard letters.count == 2 else { return nil }
        let code = String(letters)
        return code == "XX" ? nil : code
    }

    /// The title without its leading flag emoji.
    var name: String {
        let scalars = title.unicodeScalars.drop { (0x1F1E6...0x1F1FF).contains($0.value) || $0 == " " }
        let s = String(String.UnicodeScalarView(scalars))
        return s.isEmpty ? title : s
    }

    var subtitle: String? {
        switch kind {
        case .azure, .available: return region?.city
        case .home: return "Home PC"
        case .direct: return "Direct PC"
        case .pending: return "Setting up"
        }
    }
}

/// Equirectangular projection of the world window, seen through a `MapCamera`.
struct MapProjection {
    let size: CGSize
    var camera: MapCamera = .world
    var framing: MapFraming = .desktop

    static let lonSpan = (-130.0, 180.0)
    static let latSpan = (75.0, -48.0)
    static let lonWidth = CGFloat(lonSpan.1 - lonSpan.0)
    static let latHeight = CGFloat(latSpan.0 - latSpan.1)
    static func u(_ lon: Double) -> CGFloat { CGFloat(lon - lonSpan.0) / lonWidth }
    static func v(_ lat: Double) -> CGFloat { CGFloat(latSpan.0 - lat) / latHeight }

    private var bandHeight: CGFloat { max(1, size.height * (1 - framing.bottomFraction) - framing.topInset) }
    /// Points per degree that fit the whole world in the uncovered band.
    private var wholeUnit: CGFloat { max(0.01, min(size.width / Self.lonWidth, bandHeight / Self.latHeight) * 0.96) }
    /// Points per degree at zoom 1.
    var unit: CGFloat {
        switch framing.fit {
        case .whole: return wholeUnit
        case .height(let f): return max(0.01, size.height * f / Self.latHeight)
        }
    }
    var wholeWorldZoom: CGFloat { wholeUnit / unit }
    /// Points per degree at the camera's zoom.
    var scale: CGFloat { unit * camera.zoom }
    var mapSize: CGSize { CGSize(width: Self.lonWidth * scale, height: Self.latHeight * scale) }
    /// Where the camera centre sits on screen: the middle of the band left uncovered by chrome.
    var centre: CGPoint { CGPoint(x: size.width / 2, y: framing.topInset + bandHeight / 2) }

    func point(_ g: GeoPoint) -> CGPoint { point(u: Self.u(g.lon), v: Self.v(g.lat)) }

    func point(u: CGFloat, v: CGFloat) -> CGPoint {
        let m = mapSize
        return CGPoint(x: centre.x + (u - camera.u) * m.width, y: centre.y + (v - camera.v) * m.height)
    }

    func mapUnits(at p: CGPoint) -> (u: CGFloat, v: CGFloat) {
        let m = mapSize
        return (camera.u + (p.x - centre.x) / m.width, camera.v + (p.y - centre.y) / m.height)
    }

    func isVisible(_ p: CGPoint, margin: CGFloat) -> Bool {
        p.x > -margin && p.y > -margin && p.x < size.width + margin && p.y < size.height + margin
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
                    Canvas { ctx, size in drawDots(ctx, proj, t: t) }
                    if let home {
                        let p = proj.point(home)
                        Circle().fill(Atlas.home).frame(width: 10, height: 10)
                            .overlay(Circle().stroke(Atlas.surface, lineWidth: 2))
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
        let labelled = pins.filter { $0.kind != .available || $0.id == selected }
        let ordered = labelled.sorted { ($0.id == selected ? 0 : 1) < ($1.id == selected ? 0 : 1) }
        var placed: [CGRect] = labelled.map {
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

    /// Land dots; while connecting or secure a ripple spreads from the chosen pin like a
    /// wave across water — quick and bright while connecting, slow and calm once secure.
    private func drawDots(_ ctx: GraphicsContext, _ proj: MapProjection, t: Double) {
        let r = max(1.1, proj.scale * 0.55)
        let tint = tone.color.opacity(tone == .secure ? 0.28 : 0.22)
        let center = (tone == .connecting || tone == .secure)
            ? pins.first { $0.id == selected }.map { proj.point($0.point) } : nil
        let speed = tone == .connecting ? 5.0 : 2.2
        let wavelength = max(36, 70 * proj.scale / 2.6)
        let reach = 900 * proj.scale / 2.6
        for (row, cells) in LandMask.rows.enumerated() {
            let lat = LandMask.topLat - Double(row) * LandMask.step
            for (col, land) in cells.enumerated() where land {
                let lon = LandMask.leftLon + Double(col) * LandMask.step
                let p = proj.point(GeoPoint(lat: lat, lon: lon))
                var rr = r, glow = 0.0
                if let c = center {
                    let d = hypot(p.x - c.x, p.y - c.y)
                    let fall = exp(-Double(d / reach))
                    let w = sin(Double(d / wavelength) * 2 * .pi - t * speed)
                    glow = max(0, w) * fall
                    rr = r * CGFloat(1 + 0.45 * w * fall)
                }
                let dot = CGRect(x: p.x - rr, y: p.y - rr, width: 2 * rr, height: 2 * rr)
                ctx.fill(Path(ellipseIn: dot), with: .color(Atlas.dot))
                ctx.fill(Path(ellipseIn: dot), with: .color(tint))
                if glow > 0.05 { ctx.fill(Path(ellipseIn: dot), with: .color(tone.color.opacity(0.55 * glow))) }
            }
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
                          : (pin.kind == .azure || pin.kind == .available ? Atlas.blue : Atlas.home)
        let small = pin.kind == .available && !active
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
            Circle().fill(active ? ring : Atlas.surface.opacity(small ? 0.7 : 1))
                .frame(width: active ? 18 : small ? 9 : 14, height: active ? 18 : small ? 9 : 14)
                .overlay(Circle().stroke(active ? Atlas.surface : ring.opacity(small ? 0.55 : 1),
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
            if !small {
            Text(pin.title)
                .font(.system(size: 11, weight: active ? .semibold : .medium))
                .lineLimit(1)
                .fixedSize()
                .padding(.horizontal, 7).padding(.vertical, 3)
                .glass(10)
                .offset(labelOffset)
                .opacity(active ? 1 : 0.85)
            }
        }
        .frame(width: 70, height: 70)
        .contentShape(Circle().inset(by: small ? 24 : 12))
        .help(pin.title)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(pin.title)
        .accessibilityAddTraits(active ? [.isButton, .isSelected] : .isButton)
    }
}
