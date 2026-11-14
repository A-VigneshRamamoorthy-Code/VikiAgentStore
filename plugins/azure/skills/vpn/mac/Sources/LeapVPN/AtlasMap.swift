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

/// The dot-matrix world map at a fixed framing (onboarding): tap a pin to choose it.
/// The home screens use `AtlasViewport`, which adds the camera, gestures and hover.
struct AtlasMap: View {
    let pins: [MapPin]
    let selected: String?
    let home: GeoPoint?
    let tone: MapTone
    let onSelect: (String) -> Void

    var body: some View {
        GeometryReader { geo in
            let proj = MapProjection(size: geo.size, framing: .still)
            AtlasLayer(pins: pins, selected: selected, home: home, tone: tone, proj: proj, progressive: false, onSelect: onSelect)
                .contentShape(Rectangle())
                .gesture(SpatialTapGesture().onEnded { e in
                    if let id = AtlasLayer.pin(at: e.location, pins: pins, proj: proj) { onSelect(id) }
                })
        }
        .background(Atlas.background)
    }
}
