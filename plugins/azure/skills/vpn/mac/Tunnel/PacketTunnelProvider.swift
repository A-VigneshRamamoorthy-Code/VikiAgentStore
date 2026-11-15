import Foundation
import NetworkExtension
import os
import StoreKit

/// WireGuard packet tunnel for AvenVPN.
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
        if let e = options["plusExpires"] as? NSNumber {
            let expires = Date(timeIntervalSince1970: e.doubleValue)
            let renews = (options["plusRenews"] as? NSNumber)?.boolValue ?? false
            watchQueue.sync { setPlus(expires: expires, renews: renews) }
        }
        adapter.start(tunnelConfiguration: config) { [weak self, log] error in
            if let error { log.error("adapter start failed: \(String(describing: error), privacy: .public)") }
            else { self?.startWatchdog() }
            completionHandler(error)
        }
    }

    override func stopTunnel(with reason: NEProviderStopReason, completionHandler: @escaping () -> Void) {
        watchQueue.sync { watchdog?.cancel(); watchdog = nil }
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

    /// When the watchdog's clock (re)started: the tunnel's start, or the end of a sleep. While the
    /// device sleeps nothing handshakes, so a stale handshake right after waking is not a dead server.
    /// Only touched on `watchQueue`.
    private var graceFrom = Date()
    private let watchQueue = DispatchQueue(label: "com.sololeap.leapvpn.tunnel.watchdog", qos: .utility)

    override func wake() {
        super.wake()
        watchQueue.async { self.graceFrom = Date() }
    }

    private func startWatchdog() {
        watchQueue.async { self.graceFrom = Date() }
        var lastTick = Date()
        let timer = DispatchSource.makeTimerSource(queue: watchQueue)
        timer.schedule(deadline: .now() + 30, repeating: 30)
        timer.setEventHandler { [weak self] in
            guard let self else { return }
            // A tick far later than scheduled means the device was asleep (iOS may not call wake()).
            if Date().timeIntervalSince(lastTick) > 75 { self.graceFrom = Date() }
            lastTick = Date()
            if let due = self.plusCheckAt, Date() >= due { self.checkPlus() }
            let asked = Date()
            self.adapter.getRuntimeConfiguration { uapi in
                self.watchQueue.async {
                    // A poll that spanned a sleep says nothing about the server; the next one will.
                    guard self.watchdog != nil, Date().timeIntervalSince(asked) < 20 else { return }
                    let last = (uapi ?? "").split(separator: "\n").compactMap { line -> TimeInterval? in
                        let kv = line.split(separator: "=", maxSplits: 1)
                        return kv.count == 2 && kv[0] == "last_handshake_time_sec" ? TimeInterval(kv[1]) : nil
                    }.max() ?? 0
                    let now = Date().timeIntervalSince1970
                    let since = min(last > 0 ? now - last : .infinity, now - self.graceFrom.timeIntervalSince1970)
                    guard since > Self.staleAfter else { return }
                    self.log.error("no handshake for \(Int(since), privacy: .public)s; stopping tunnel")
                    self.watchdog?.cancel(); self.watchdog = nil
                    self.cancelTunnelWithError(NEVPNError(.connectionFailed))
                }
            }
        }
        watchQueue.async {
            self.watchdog?.cancel()
            self.watchdog = timer
            timer.resume()
        }
    }

    // MARK: Aven VPN Plus

    /// When Aven VPN Plus (or its free trial) runs out. The app passes it at start and again
    /// whenever StoreKit tells it of a renewal, but the app may be suspended or quit when the
    /// moment comes, so the tunnel enforces it itself: at the expiry it asks StoreKit once more
    /// and, unless a newer entitlement turned up, stops. Only touched on `watchQueue`.
    private var plusExpires: Date?
    /// The subscription is set to renew: allow StoreKit some hours to show the renewal before
    /// treating the expiry as final. A cancelled trial or subscription ends at its expiry.
    private var plusRenews = false
    private var plusCheckAt: Date?
    private var plusChecking = false
    private static let renewalGrace: TimeInterval = 6 * 3600
    private static let plusIDs: Set<String> = ["com.sololeap.leapvpn.plus.yearly", "com.sololeap.leapvpn.plus.monthly"]

    private func setPlus(expires: Date, renews: Bool) {
        plusExpires = expires
        plusRenews = renews
        plusCheckAt = expires.addingTimeInterval(5)
    }

    /// Runs on `watchQueue` once `plusCheckAt` has passed.
    private func checkPlus() {
        guard !plusChecking, let expires = plusExpires else { return }
        plusChecking = true
        plusCheckAt = nil
        Task {
            // currentEntitlements already keeps a subscription in its billing grace period, whose
            // transaction expiry is past: any verified, unrevoked entry means Plus is still on.
            var entitled = false
            var latest: Date?
            for await result in Transaction.currentEntitlements {
                guard case .verified(let t) = result, Self.plusIDs.contains(t.productID), t.revocationDate == nil else { continue }
                entitled = true
                latest = max(latest ?? .distantPast, t.expirationDate ?? .distantFuture)
            }
            let renewing = entitled ? nil : await Self.renewalState()
            self.watchQueue.async {
                self.plusChecking = false
                guard self.plusExpires == expires else { return }  // the app sent a newer expiry meanwhile
                let now = Date()
                if entitled {
                    if let latest, latest > now {
                        self.log.info("plus renewed until \(latest, privacy: .public)")
                        self.setPlus(expires: latest, renews: self.plusRenews)
                    } else {
                        self.plusCheckAt = now.addingTimeInterval(15 * 60)  // billing grace
                    }
                } else if renewing ?? self.plusRenews, now < expires.addingTimeInterval(Self.renewalGrace) {
                    // Set to renew, but the renewal hasn't reached this device yet.
                    self.plusCheckAt = now.addingTimeInterval(15 * 60)
                } else {
                    self.log.error("plus ended at \(expires, privacy: .public); stopping tunnel")
                    self.watchdog?.cancel(); self.watchdog = nil
                    self.cancelTunnelWithError(NSError(domain: "AvenVPN.Plus", code: 1, userInfo: [
                        NSLocalizedDescriptionKey: "Your Aven VPN Plus free trial or subscription has ended."]))
                }
            }
        }
    }

    /// The subscription's verified renewal intent, read fresh at the expiry (the user may have
    /// cancelled after this tunnel started): true while set to renew, false once cancelled or
    /// ended, nil when StoreKit can't say, in which case the app's last word stands.
    private static func renewalState() async -> Bool? {
        var group: String?
        for id in plusIDs {
            if case .verified(let t)? = await Transaction.latest(for: id) { group = t.subscriptionGroupID ?? group }
        }
        guard let group, let statuses = try? await Product.SubscriptionInfo.status(for: group), !statuses.isEmpty else { return nil }
        var verified = false
        for s in statuses {
            guard case .verified(let r) = s.renewalInfo else { continue }
            verified = true
            if r.willAutoRenew, s.state != .expired, s.state != .revoked { return true }
        }
        return verified ? false : nil
    }

    /// Messages from the app: "stats" → JSON {rx, tx, handshake, name};
    /// "plus:<expiry epoch>:<1 if renewing>" → a newer Plus expiry.
    override func handleAppMessage(_ messageData: Data, completionHandler: ((Data?) -> Void)?) {
        let text = String(decoding: messageData, as: UTF8.self)
        if text.hasPrefix("plus:") {
            let parts = text.split(separator: ":")
            if parts.count == 3, let e = TimeInterval(parts[1]) {
                watchQueue.async { self.setPlus(expires: Date(timeIntervalSince1970: e), renews: parts[2] == "1") }
            }
            completionHandler?(nil)
            return
        }
        guard text == "stats" else { completionHandler?(nil); return }
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
