import Foundation
import NetworkExtension
import os

/// WireGuard packet tunnel for LeapVPN.
///
/// The containing app passes the WireGuard settings as start options, so the private key
/// is kept only in memory here and is never written to the system VPN preferences.
final class PacketTunnelProvider: NEPacketTunnelProvider {
    private let log = Logger(subsystem: "com.sololeap.leapvpn.tunnel", category: "tunnel")
    private lazy var adapter = WireGuardAdapter(with: self) { [log] level, message in
        log.log(level: level == .error ? .error : .info, "\(message, privacy: .public)")
    }

    override func startTunnel(options: [String: NSObject]?, completionHandler: @escaping (Error?) -> Void) {
        guard let options, let config = Self.configuration(from: options) else {
            log.error("start without a valid configuration")
            completionHandler(NEVPNError(.configurationInvalid))
            return
        }
        name = options["name"] as? String
        adapter.start(tunnelConfiguration: config) { [weak self, log] error in
            if let error { log.error("adapter start failed: \(String(describing: error), privacy: .public)") }
            else { self?.startWatchdog() }
            completionHandler(error)
        }
    }

    override func stopTunnel(with reason: NEProviderStopReason, completionHandler: @escaping () -> Void) {
        watchdog?.cancel(); watchdog = nil
        adapter.stop { _ in completionHandler() }
    }

    /// If the app dies, the server deallocates itself and this tunnel would keep routing
    /// every packet into a dead peer. WireGuard re-handshakes every 2 minutes (keepalive keeps it busy) while the
    /// peer is alive, so a handshake older than `staleAfter` means the server is gone:
    /// drop the tunnel so the Mac falls back to its normal connection.
    private var watchdog: DispatchSourceTimer?
    /// The server this tunnel goes to, so a relaunched app can pick the session back up.
    private var name: String?
    private static let staleAfter: TimeInterval = 200

    private func startWatchdog() {
        let started = Date()
        let timer = DispatchSource.makeTimerSource(queue: .global(qos: .utility))
        timer.schedule(deadline: .now() + 30, repeating: 30)
        timer.setEventHandler { [weak self] in
            guard let self else { return }
            self.adapter.getRuntimeConfiguration { uapi in
                let last = (uapi ?? "").split(separator: "\n").compactMap { line -> TimeInterval? in
                    let kv = line.split(separator: "=", maxSplits: 1)
                    return kv.count == 2 && kv[0] == "last_handshake_time_sec" ? TimeInterval(kv[1]) : nil
                }.max() ?? 0
                let since = last > 0 ? Date().timeIntervalSince1970 - last : Date().timeIntervalSince(started)
                guard since > Self.staleAfter else { return }
                self.log.error("no handshake for \(Int(since), privacy: .public)s; stopping tunnel")
                self.watchdog?.cancel(); self.watchdog = nil
                self.cancelTunnelWithError(NEVPNError(.connectionFailed))
            }
        }
        watchdog = timer
        timer.resume()
    }

    /// Messages from the app: "stats" → JSON {rx, tx, handshake, name}.
    override func handleAppMessage(_ messageData: Data, completionHandler: ((Data?) -> Void)?) {
        guard String(decoding: messageData, as: UTF8.self) == "stats" else { completionHandler?(nil); return }
        let name = self.name ?? ""
        adapter.getRuntimeConfiguration { uapi in
            var rx: Int64 = 0, tx: Int64 = 0, handshake: Int64 = 0
            for line in (uapi ?? "").split(separator: "\n") {
                let kv = line.split(separator: "=", maxSplits: 1)
                guard kv.count == 2, let v = Int64(kv[1]) else { continue }
                switch kv[0] {
                case "rx_bytes": rx += v
                case "tx_bytes": tx += v
                case "last_handshake_time_sec": handshake = max(handshake, v)
                default: break
                }
            }
            completionHandler?(try? JSONSerialization.data(withJSONObject: ["rx": rx, "tx": tx, "handshake": handshake, "name": name] as [String: Any]))
        }
    }

    static func configuration(from o: [String: NSObject]) -> TunnelConfiguration? {
        guard let key = (o["privateKey"] as? String).flatMap(PrivateKey.init(base64Key:)),
              let peerKey = (o["peerPublicKey"] as? String).flatMap(PublicKey.init(base64Key:)),
              let endpoint = (o["endpoint"] as? String).flatMap(Endpoint.init(from:)) else { return nil }
        var iface = InterfaceConfiguration(privateKey: key)
        iface.addresses = ((o["addresses"] as? [String]) ?? []).compactMap(IPAddressRange.init(from:))
        iface.dns = ((o["dns"] as? [String]) ?? []).compactMap(DNSServer.init(from:))
        iface.mtu = (o["mtu"] as? NSNumber)?.uint16Value
        var peer = PeerConfiguration(publicKey: peerKey)
        peer.endpoint = endpoint
        peer.allowedIPs = ["0.0.0.0/0", "::/0"].compactMap(IPAddressRange.init(from:))
        peer.persistentKeepAlive = 25
        return TunnelConfiguration(name: o["name"] as? String, interface: iface, peers: [peer])
    }
}
