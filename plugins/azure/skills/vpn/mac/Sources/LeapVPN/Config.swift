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
    var endpoint: String
    let size: String
    var serverPublicKey: String
    var sshHostKey: String?
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

    /// Every public region that offers Standard_B2ats_v2 and the Ubuntu 24.04 image
    /// (southindia and westindia lack the size). Only the ones a user connects to are built.
    static let all: [RegionChoice] = [
        .init(code: "in", name: "India", city: "Pune", flag: "🇮🇳", country: "IN", location: "centralindia"),
        .init(code: "nl", name: "Netherlands", city: "Amsterdam", flag: "🇳🇱", country: "NL", location: "westeurope"),
        .init(code: "us", name: "United States", city: "Virginia", flag: "🇺🇸", country: "US", location: "eastus"),
        .init(code: "ca", name: "Canada", city: "Toronto", flag: "🇨🇦", country: "CA", location: "canadacentral"),
        .init(code: "uk", name: "United Kingdom", city: "London", flag: "🇬🇧", country: "GB", location: "uksouth"),
        .init(code: "sg", name: "Singapore", city: "Singapore", flag: "🇸🇬", country: "SG", location: "southeastasia"),
        .init(code: "in2", name: "India South", city: "Hyderabad", flag: "🇮🇳", country: "IN", location: "indiasouthcentral"),
        .init(code: "usc", name: "US Central", city: "Iowa", flag: "🇺🇸", country: "US", location: "centralus"),
        .init(code: "usn", name: "US North", city: "Illinois", flag: "🇺🇸", country: "US", location: "northcentralus"),
        .init(code: "uss", name: "US South", city: "Texas", flag: "🇺🇸", country: "US", location: "southcentralus"),
        .init(code: "usw", name: "US West", city: "California", flag: "🇺🇸", country: "US", location: "westus"),
        .init(code: "usw2", name: "US Northwest", city: "Washington", flag: "🇺🇸", country: "US", location: "westus2"),
        .init(code: "usw3", name: "US Southwest", city: "Arizona", flag: "🇺🇸", country: "US", location: "westus3"),
        .init(code: "mx", name: "Mexico", city: "Querétaro", flag: "🇲🇽", country: "MX", location: "mexicocentral"),
        .init(code: "br", name: "Brazil", city: "São Paulo", flag: "🇧🇷", country: "BR", location: "brazilsouth"),
        .init(code: "cl", name: "Chile", city: "Santiago", flag: "🇨🇱", country: "CL", location: "chilecentral"),
        .init(code: "ie", name: "Ireland", city: "Dublin", flag: "🇮🇪", country: "IE", location: "northeurope"),
        .init(code: "fr", name: "France", city: "Paris", flag: "🇫🇷", country: "FR", location: "francecentral"),
        .init(code: "de", name: "Germany", city: "Frankfurt", flag: "🇩🇪", country: "DE", location: "germanywestcentral"),
        .init(code: "ch", name: "Switzerland", city: "Zurich", flag: "🇨🇭", country: "CH", location: "switzerlandnorth"),
        .init(code: "at", name: "Austria", city: "Vienna", flag: "🇦🇹", country: "AT", location: "austriaeast"),
        .init(code: "it", name: "Italy", city: "Milan", flag: "🇮🇹", country: "IT", location: "italynorth"),
        .init(code: "es", name: "Spain", city: "Madrid", flag: "🇪🇸", country: "ES", location: "spaincentral"),
        .init(code: "be", name: "Belgium", city: "Brussels", flag: "🇧🇪", country: "BE", location: "belgiumcentral"),
        .init(code: "dk", name: "Denmark", city: "Copenhagen", flag: "🇩🇰", country: "DK", location: "denmarkeast"),
        .init(code: "pl", name: "Poland", city: "Warsaw", flag: "🇵🇱", country: "PL", location: "polandcentral"),
        .init(code: "se", name: "Sweden", city: "Gävle", flag: "🇸🇪", country: "SE", location: "swedencentral"),
        .init(code: "no", name: "Norway", city: "Oslo", flag: "🇳🇴", country: "NO", location: "norwayeast"),
        .init(code: "il", name: "Israel", city: "Tel Aviv", flag: "🇮🇱", country: "IL", location: "israelcentral"),
        .init(code: "ae", name: "UAE", city: "Dubai", flag: "🇦🇪", country: "AE", location: "uaenorth"),
        .init(code: "za", name: "South Africa", city: "Johannesburg", flag: "🇿🇦", country: "ZA", location: "southafricanorth"),
        .init(code: "hk", name: "Hong Kong", city: "Hong Kong", flag: "🇭🇰", country: "HK", location: "eastasia"),
        .init(code: "jp", name: "Japan", city: "Tokyo", flag: "🇯🇵", country: "JP", location: "japaneast"),
        .init(code: "jpw", name: "Japan West", city: "Osaka", flag: "🇯🇵", country: "JP", location: "japanwest"),
        .init(code: "kr", name: "South Korea", city: "Seoul", flag: "🇰🇷", country: "KR", location: "koreacentral"),
        .init(code: "tw", name: "Taiwan", city: "Taipei", flag: "🇹🇼", country: "TW", location: "taiwannorth"),
        .init(code: "my", name: "Malaysia", city: "Kuala Lumpur", flag: "🇲🇾", country: "MY", location: "malaysiawest"),
        .init(code: "id", name: "Indonesia", city: "Jakarta", flag: "🇮🇩", country: "ID", location: "indonesiacentral"),
        .init(code: "au", name: "Australia", city: "Sydney", flag: "🇦🇺", country: "AU", location: "australiaeast"),
        .init(code: "nz", name: "New Zealand", city: "Auckland", flag: "🇳🇿", country: "NZ", location: "newzealandnorth"),
    ]
}

extension RegionChoice {
    /// The record of a location that has no server yet.
    func unbuilt(subscription: String) -> RegionConfig {
        let rg = "leapvpn-\(code)"
        return RegionConfig(code: code, name: name, city: city, flag: flag, country: country,
                            location: location, resourceGroup: rg, vm: rg,
                            vmId: "/subscriptions/\(subscription)/resourceGroups/\(rg)/providers/Microsoft.Compute/virtualMachines/\(rg)",
                            endpoint: "", size: Provisioner.vmSize, serverPublicKey: "", sshHostKey: nil, agentVersion: nil)
    }
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
    /// Fleet options (mirrored in `config/settings.json`); optional so older files still decode.
    var ephemeralPref: Bool?
    var staticIPPref: Bool?
    /// Per-location overrides of the two defaults above.
    var regionPrefs: [String: RegionPrefs]?
    /// Home PCs this Mac connects to directly (no Azure involved).
    var directPCs: [DirectPC]?

    /// "Provision once": delete a region's resources when the last device disconnects.
    var ephemeral: Bool { ephemeralPref ?? true }
    /// Keep the public IP while a server is off (otherwise it is released and re-created).
    var staticIP: Bool { staticIPPref ?? false }
    var direct: [DirectPC] { directPCs ?? [] }
    func ephemeral(for code: String) -> Bool { regionPrefs?[code]?.ephemeral ?? ephemeral }
    func staticIP(for code: String) -> Bool { regionPrefs?[code]?.staticIP ?? staticIP }

    static let leaseTTL = 180
    static let renewEvery = 45
    static let dns = ["1.1.1.1", "1.0.0.1"]
    static let mtu = 1380

    static var supportDir: URL {
        #if os(macOS)
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/LeapVPN", isDirectory: true)
        #else
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("LeapVPN", isDirectory: true)
        #endif
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

/// Shared by every device on the subscription (`config/settings.json`); read by the reconciler.
struct FleetSettings: Codable, Equatable {
    var ephemeral: Bool
    var staticIP: Bool
    /// Regions relaying home PCs: the reconciler never deletes them or releases their IP.
    var relays: [String]? = nil
    /// Per-location overrides; a missing value falls back to the defaults above.
    var regions: [String: RegionPrefs]? = nil
}

/// One location's cost switches; nil means "use the default".
struct RegionPrefs: Codable, Equatable {
    var ephemeral: Bool?
    var staticIP: Bool?
}

/// A Windows PC paired directly with this Mac: it runs a userspace WireGuard server
/// (Install-LeapDirect.ps1) and the Mac connects straight to it — no Azure at all.
struct DirectPC: Codable, Identifiable, Hashable {
    let id: String
    var name: String
    var country: String
    /// "host:port" the PC is reachable on (router port-forward / UPnP).
    var endpoint: String
    var publicKey: String
    /// This Mac's tunnel addresses on the PC's network.
    var address: String
    var address6: String?
    var loc: String?
    var isp: String?
    var createdAt: Date

    var point: GeoPoint? { GeoPoint(loc) ?? Countries.point(country) }
    var flag: String { LeapVPN.flag(country) }

    /// Parses `leapvpn://pair?v=1&n=&k=&e=&a=&a6=&c=&l=&isp=` (printed by the PC script).
    init?(link: String) {
        let trimmed = link.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "LEAP-LINK ", with: "")
        guard let c = URLComponents(string: trimmed), c.scheme == "leapvpn", c.host == "pair" else { return nil }
        func q(_ k: String) -> String? { c.queryItems?.first { $0.name == k }?.value.flatMap { $0.isEmpty ? nil : $0 } }
        guard let k = q("k"), Data(base64Encoded: k)?.count == 32, let e = q("e"), e.contains(":"),
              let a = q("a"), a.split(separator: ".").count == 4 else { return nil }
        id = "d" + String(SHA256Hex.of(k).prefix(10))
        name = q("n") ?? "Home PC"
        country = (q("c") ?? "XX").uppercased()
        endpoint = e
        publicKey = k
        address = a
        address6 = q("a6")
        loc = q("l")
        isp = q("isp")
        createdAt = Date()
    }
}

/// Kept for paths shared with the rest of the app.
enum AppConfig {
    static var supportDir: URL { Setup.supportDir }
}

