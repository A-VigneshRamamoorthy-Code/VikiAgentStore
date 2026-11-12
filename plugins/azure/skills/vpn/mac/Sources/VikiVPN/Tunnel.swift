import Foundation
import NetworkExtension

struct TunnelStatus: Codable {
    var up: Bool
    var region: String?
    var handshake: Int?
    var rx: Int64?
    var tx: Int64?
}

/// The WireGuard tunnel, run by the VikiVPN packet-tunnel Network Extension.
@MainActor
enum Tunnel {
    static let providerID = (Bundle.main.bundleIdentifier ?? "com.viki.vikivpn") + ".tunnel"
    private static var manager: NETunnelProviderManager?
    private(set) static var region: String?

    /// Loads (or creates, on first run — macOS asks once to "Add VPN Configurations") the VPN profile.
    static func load() async throws -> NETunnelProviderManager {
        if let manager { return manager }
        let all = try await NETunnelProviderManager.loadAllFromPreferences()
        let m = all.first { ($0.protocolConfiguration as? NETunnelProviderProtocol)?.providerBundleIdentifier == providerID }
            ?? NETunnelProviderManager()
        manager = m
        return m
    }

    static func up(_ region: RegionConfig, _ device: DeviceIdentity) async throws {
        guard let key = Keychain.secret(account: DeviceKey.account) else {
            throw err("This Mac's VPN key is missing — sign in again to re-register it.")
        }
        let m = try await load()
        let proto = NETunnelProviderProtocol()
        proto.providerBundleIdentifier = providerID
        proto.serverAddress = "\(region.name) (\(region.endpoint))"
        m.protocolConfiguration = proto
        m.localizedDescription = "Leap VPN"
        m.isEnabled = true
        m.isOnDemandEnabled = false
        try await m.saveToPreferences()
        try await m.loadFromPreferences()
        let options: [String: NSObject] = [
            "name": region.code as NSString,
            "privateKey": key as NSString,
            "peerPublicKey": region.serverPublicKey as NSString,
            "endpoint": "\(region.endpoint):51820" as NSString,
            "addresses": device.addresses as NSArray,
            "dns": Setup.dns as NSArray,
            "mtu": NSNumber(value: Setup.mtu),
        ]
        try m.connection.startVPNTunnel(options: options)
        self.region = region.code
    }

    static func down() async {
        guard let m = try? await load() else { return }
        if m.connection.status == .disconnected || m.connection.status == .invalid { return }
        m.connection.stopVPNTunnel()
        for _ in 0..<40 where m.connection.status != .disconnected {
            try? await Task.sleep(for: .milliseconds(250))
        }
    }

    static func status() async -> TunnelStatus {
        guard let m = try? await load(), m.connection.status == .connected,
              let session = m.connection as? NETunnelProviderSession else {
            return TunnelStatus(up: false)
        }
        let data: Data? = await withCheckedContinuation { cont in
            do {
                try session.sendProviderMessage(Data("stats".utf8)) { cont.resume(returning: $0) }
            } catch {
                cont.resume(returning: nil)
            }
        }
        let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        return TunnelStatus(up: true, region: region,
                            handshake: (json["handshake"] as? NSNumber)?.intValue,
                            rx: (json["rx"] as? NSNumber)?.int64Value,
                            tx: (json["tx"] as? NSNumber)?.int64Value)
    }

    private static func err(_ s: String) -> NSError {
        NSError(domain: "VikiVPN.Tunnel", code: 1, userInfo: [NSLocalizedDescriptionKey: s])
    }
}

struct EgressInfo: Codable {
    var ip: String
    var country: String
    var city: String?
    var org: String?
    /// "lat,lon" from ipinfo.
    var loc: String?

    var coordinate: GeoPoint? { GeoPoint(loc) }

    /// Still leaving from an Azure datacenter (Microsoft, AS8075).
    var isAzure: Bool { (org ?? "").contains("AS8075") || (org ?? "").localizedCaseInsensitiveContains("microsoft") }
}

enum Egress {
    static func lookup() async -> EgressInfo? {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 10
        guard let (data, _) = try? await URLSession(configuration: cfg)
            .data(from: URL(string: "https://ipinfo.io/json")!) else { return nil }
        return try? JSONDecoder().decode(EgressInfo.self, from: data)
    }
}
