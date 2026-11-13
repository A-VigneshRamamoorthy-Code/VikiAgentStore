import Foundation
import NetworkExtension

struct TunnelStatus: Codable {
    var up: Bool
    var region: String?
    var handshake: Int?
    var rx: Int64?
    var tx: Int64?
}

/// The WireGuard tunnel, run by the LeapVPN packet-tunnel Network Extension.
@MainActor
enum Tunnel {
    static let providerID = (Bundle.main.bundleIdentifier ?? "com.sololeap.leapvpn") + ".tunnel"
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
        try await up(id: region.code, display: "\(region.name) (\(region.endpoint))", peerKey: region.serverPublicKey,
                     endpoint: "\(region.endpoint):51820", addresses: device.addresses)
    }

    /// Straight to a home PC running the Leap VPN direct server (no Azure).
    static func up(_ pc: DirectPC) async throws {
        try await up(id: "pc:\(pc.id)", display: "\(pc.name) (\(pc.endpoint))", peerKey: pc.publicKey,
                     endpoint: pc.endpoint, addresses: ["\(pc.address)/32"] + (pc.address6.map { ["\($0)/128"] } ?? []))
    }

    private static func up(id: String, display: String, peerKey: String, endpoint: String, addresses: [String]) async throws {
        guard let key = Keychain.secret(account: DeviceKey.account) else {
            throw err("This Mac's VPN key is missing.")
        }
        let m = try await load()
        let proto = NETunnelProviderProtocol()
        proto.providerBundleIdentifier = providerID
        proto.serverAddress = display
        m.protocolConfiguration = proto
        m.localizedDescription = "Leap VPN"
        m.isEnabled = true
        m.isOnDemandEnabled = false
        try await m.saveToPreferences()
        try await m.loadFromPreferences()
        let options: [String: NSObject] = [
            "name": id as NSString,
            "privateKey": key as NSString,
            "peerPublicKey": peerKey as NSString,
            "endpoint": endpoint as NSString,
            "addresses": addresses as NSArray,
            "dns": Setup.dns as NSArray,
            "mtu": NSNumber(value: Setup.mtu),
        ]
        try m.connection.startVPNTunnel(options: options)
        self.region = id
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
        // A provider that is stopping may never answer: give up after a few seconds.
        let data: Data? = await withCheckedContinuation { cont in
            let once = ResumeOnce(cont)
            do {
                try session.sendProviderMessage(Data("stats".utf8)) { once.resume($0) }
            } catch {
                once.resume(nil)
            }
            DispatchQueue.global().asyncAfter(deadline: .now() + 4) { once.resume(nil) }
        }
        let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        if region == nil, let name = json["name"] as? String, !name.isEmpty { region = name }  // app was relaunched
        return TunnelStatus(up: true, region: region,
                            handshake: (json["handshake"] as? NSNumber)?.intValue,
                            rx: (json["rx"] as? NSNumber)?.int64Value,
                            tx: (json["tx"] as? NSNumber)?.int64Value)
    }

    private static func err(_ s: String) -> NSError {
        NSError(domain: "LeapVPN.Tunnel", code: 1, userInfo: [NSLocalizedDescriptionKey: s])
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

/// Resumes a continuation exactly once, whichever of the reply or the timeout comes first.
private final class ResumeOnce: @unchecked Sendable {
    private let lock = NSLock()
    private var cont: CheckedContinuation<Data?, Never>?
    init(_ cont: CheckedContinuation<Data?, Never>) { self.cont = cont }
    func resume(_ value: Data?) {
        lock.lock(); let c = cont; cont = nil; lock.unlock()
        c?.resume(returning: value)
    }
}
