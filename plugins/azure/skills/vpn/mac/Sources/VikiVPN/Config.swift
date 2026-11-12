import Foundation

/// A deployed VPN server (shared across the user's devices in `config/regions.json`).
struct RegionConfig: Codable, Identifiable, Hashable {
    let code: String
    let name: String
    let city: String
    let flag: String
    let country: String
    let location: String
    let resourceGroup: String
    let vm: String
    let vmId: String
    let endpoint: String
    let size: String
    let serverPublicKey: String
    let sshHostKey: String?
    var agentVersion: Int?
    var id: String { code }
    var point: GeoPoint { AzureGeo.points[location] ?? GeoPoint(lat: 0, lon: 0) }
}

/// Azure locations the app can deploy to. All run Ubuntu 24.04 on Standard_B2ats_v2.
struct RegionChoice: Identifiable, Hashable {
    let code: String
    let name: String
    let city: String
    let flag: String
    let country: String
    let location: String
    var id: String { code }
    var point: GeoPoint { AzureGeo.points[location] ?? GeoPoint(lat: 0, lon: 0) }

    static let all: [RegionChoice] = [
        .init(code: "in", name: "India", city: "Pune", flag: "🇮🇳", country: "IN", location: "centralindia"),
        .init(code: "nl", name: "Netherlands", city: "Amsterdam", flag: "🇳🇱", country: "NL", location: "westeurope"),
        .init(code: "us", name: "United States", city: "Virginia", flag: "🇺🇸", country: "US", location: "eastus"),
        .init(code: "ca", name: "Canada", city: "Toronto", flag: "🇨🇦", country: "CA", location: "canadacentral"),
        .init(code: "uk", name: "United Kingdom", city: "London", flag: "🇬🇧", country: "GB", location: "uksouth"),
        .init(code: "sg", name: "Singapore", city: "Singapore", flag: "🇸🇬", country: "SG", location: "southeastasia"),
    ]
}

struct DeviceIdentity: Codable, Hashable {
    var name: String
    var ip4: String
    var ip6: String
    var publicKey: String
    var addresses: [String] { ["\(ip4)/32", "\(ip6)/128"] }
}

/// Everything the app remembers between launches. Not secret: the refresh token
/// and the WireGuard private key live only in the Keychain.
struct Setup: Codable {
    var user: MicrosoftUser?
    var tenantId: String?
    var subscriptionId: String?
    var subscriptionName: String?
    var quotaId: String?
    var storageAccount: String?
    var device: DeviceIdentity?
    var regions: [RegionConfig] = []
    /// Regions kept only to relay home PCs (not offered as exits on the map).
    var relayOnly: Set<String> = []
    var onboarded = false
    /// Monthly Azure credit in USD (Visual Studio subscriptions), if any.
    var monthlyCreditUSD: Double?

    static let leaseTTL = 180
    static let renewEvery = 45
    static let dns = ["1.1.1.1", "1.0.0.1"]
    static let mtu = 1380

    static var supportDir: URL {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/VikiVPN", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }
    private static var url: URL { supportDir.appendingPathComponent("setup.json") }

    static func load() -> Setup {
        (try? JSONDecoder.iso.decode(Setup.self, from: Data(contentsOf: url))) ?? Setup()
    }

    func save() {
        try? FileManager.default.createDirectory(at: Self.supportDir, withIntermediateDirectories: true)
        if let data = try? JSONEncoder.iso.encode(self) { try? data.write(to: Self.url, options: .atomic) }
    }

    var ready: Bool { subscriptionId != nil && storageAccount != nil && device != nil }
}

/// Kept for paths shared with the rest of the app.
enum AppConfig {
    static var supportDir: URL { Setup.supportDir }
}

