import CryptoKit
import Foundation

enum ProvisionError: LocalizedError {
    case permission
    case quota(String)
    case failed(String)
    var errorDescription: String? {
        switch self {
        case .permission: return "You need Owner (or User Access Administrator) on this subscription."
        case .quota(let s): return s
        case .failed(let s): return s
        }
    }
}

/// This Mac's WireGuard key: generated on first use, kept only in the Keychain.
enum DeviceKey {
    static let account = "wg-device"

    static func publicKey() -> String {
        if let b64 = Keychain.secret(account: account), let raw = Data(base64Encoded: b64),
           let key = try? Curve25519.KeyAgreement.PrivateKey(rawRepresentation: raw) {
            return key.publicKey.rawRepresentation.base64EncodedString()
        }
        let key = Curve25519.KeyAgreement.PrivateKey()
        Keychain.set(key.rawRepresentation.base64EncodedString(), account: account, label: "Aven VPN WireGuard key")
        return key.publicKey.rawRepresentation.base64EncodedString()
    }

    /// Like `publicKey()`, but fails when the Keychain did not keep a new key: registering a key
    /// the tunnel can't read back would leave the server waiting for a handshake that never comes.
    static func persisted() throws -> String {
        let pub = publicKey()
        guard let b64 = Keychain.secret(account: account), let raw = Data(base64Encoded: b64),
              let key = try? Curve25519.KeyAgreement.PrivateKey(rawRepresentation: raw),
              key.publicKey.rawRepresentation.base64EncodedString() == pub else {
            throw ProvisionError.failed("Couldn't save this device's VPN key. Unlock the device and try again.")
        }
        return pub
    }

    static func reset() { Keychain.delete(account: account) }
}

/// Builds and maintains the user's VPN in their own subscription with their own
/// delegated ARM/Storage tokens — the same steps `scripts/vpnctl.py` performs with
/// the Azure CLI. Every step is idempotent, so a failed or interrupted setup is
/// resumed by running it again.
///
/// Layout (all tagged `avenvpn=1`):
///   avenvpn-ctl      storage account (leases / config / exits) + Automation reconciler
///   avenvpn-<code>   one WireGuard VM per region, deallocated whenever unused
actor Provisioner {
    static let controlRG = "avenvpn-ctl"
    static let controlLocation = "centralindia"
    static let vmSize = "Standard_B2ats_v2"
    static let automation = "avenvpn-reconciler"
    static let runbook = "Reconcile-AvenVPN"
    static let stopperRole = "AvenVPN Stopper"

    private let az: AzureClient
    private let sub: String
    private let tenant: String
    private let log: @Sendable (String) -> Void
    private var userOID: String?

    private enum Role {
        static let blobContributor = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
        static let blobReader = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
        static let contributor = "b24988ac-6180-42a0-ab88-20f7382dd24c"
    }
    private enum API {
        static let rg = "2021-04-01"
        static let storage = "2023-05-01"
        static let network = "2024-05-01"
        static let compute = "2024-07-01"
        static let auth = "2022-04-01"
        static let automation = "2023-11-01"
    }

    init(_ az: AzureClient, subscription: String, tenant: String, log: @escaping @Sendable (String) -> Void) {
        self.az = az
        self.sub = subscription
        self.tenant = tenant
        self.log = log
    }

    private var subPath: String { "/subscriptions/\(sub)" }

    // MARK: discovery

    /// Finds an existing Aven VPN deployment in the subscription (set up from another device).
    func discover() async throws -> (account: String, regions: [RegionConfig])? {
        let list = try await az.arm("GET", "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts?api-version=\(API.storage)",
                                    accept: [200, 404])
        let accounts = (list["value"] as? [[String: Any]] ?? []).compactMap { a -> String? in
            guard let name = a["name"] as? String, name.hasPrefix("avenvpn") else { return nil }
            return name
        }
        guard let account = accounts.first else { return nil }
        return (account, try await readRegions(account: account).regions)
    }

    // MARK: migration from before the rename

    /// Prefix of every Azure name used before the app was renamed to Aven VPN.
    static let legacyPrefix = "leap" + "vpn"
    private static var legacyControlRG: String { "\(legacyPrefix)-ctl" }

    /// Written to the new control storage once everything is copied; until then a retry redoes the copy.
    private static let migratedMarker = "config/migrated.json"

    struct LegacyMigration {
        var account: String
        var regions: [RegionConfig]
        /// Old resources that couldn't be removed yet (still in use); call again later.
        var cleanupPending: Bool
    }

    /// Home PCs that were paired with the old relays, as recorded by `migrateLegacy`: each must
    /// run the installer again (new relay address and host key).
    func homeExitRepairs(account: String) async throws -> [String] {
        let m = try await retry403 { try await self.az.blobRaw("GET", Self.migratedMarker, account: account) }
        if m.status == 404 { return [] }
        guard m.status == 200 else { throw AzureError.http(m.status, String(decoding: m.data, as: UTF8.self)) }
        return ((try? JSONSerialization.jsonObject(with: m.data) as? [String: Any])?["homeExits"] as? [String]) ?? []
    }

    /// Azure resources can't be renamed, so a deployment made under the old name is moved: a new
    /// control plane is created, devices and settings are copied across, every location is recorded
    /// unbuilt (its server is rebuilt under the new name on the next connect), and the old resource
    /// groups and roles are deleted once nothing is connected to them.
    /// Resumable: the copy is redone until its marker is written, and old resources are only
    /// deleted after that. Returns nil when there is nothing to migrate.
    func migrateLegacy() async throws -> LegacyMigration? {
        let legacyGroups = try await az.arm("GET", "\(subPath)/resourcegroups?$filter=tagName%20eq%20'\(Self.legacyPrefix)'&api-version=\(API.rg)")
        let groups = ((legacyGroups["value"] as? [[String: Any]]) ?? []).compactMap { $0["name"] as? String }
            .filter { $0.lowercased().hasPrefix("\(Self.legacyPrefix)-") }
        // The app creates its role under a fixed id, which setup renames in place rather than deleting.
        let keepRole = "\(subPath)/providers/Microsoft.Authorization/roleDefinitions/\(Self.uuid("stopper|\(sub)"))".lowercased()
        let legacyRoles = try await legacyRoleIDs().filter { $0.lowercased() != keepRole }
        guard !groups.isEmpty || !legacyRoles.isEmpty else { return nil }
        log("Moving your servers to Aven VPN names")

        let list = try await az.arm("GET", "\(subPath)/resourceGroups/\(Self.legacyControlRG)/providers/Microsoft.Storage/storageAccounts?api-version=\(API.storage)",
                                    accept: [200, 404])
        let oldAccount = (list["value"] as? [[String: Any]] ?? []).compactMap { $0["name"] as? String }
            .first { $0.hasPrefix(Self.legacyPrefix) }

        let account: String
        if let found = try await discover() { account = found.account } else { account = try await ensureControlPlane(existing: nil) }
        let legacyAz = oldAccount.map {
            AzureClient(AzureContext(tenantId: tenant, subscriptionId: sub, storageAccount: $0, device: nil))
        }
        var copied = true
        if let oldAccount {
            let m = try await retry403 { try await self.az.blobRaw("GET", Self.migratedMarker, account: account) }
            guard [200, 404].contains(m.status) else { throw AzureError.http(m.status, String(decoding: m.data, as: UTF8.self)) }
            copied = m.status == 200
        }
        if let oldAccount, let legacyAz, !copied {
            // Recorded in the marker before anything old is deleted, so the app can still ask the
            // user to re-pair these PCs after an interrupted run. Fails closed if they can't be read.
            let homeExits: [String]
            do { homeExits = try await legacyAz.listExits().map(\.name).sorted() }
            catch let AzureError.http(status, _) where status == 404 { homeExits = [] }
            try await mergePeers(from: oldAccount, into: account)
            let s = try await retry403 { try await self.az.blobRaw("GET", "config/settings.json", account: oldAccount) }
            guard [200, 404].contains(s.status) else { throw AzureError.http(s.status, String(decoding: s.data, as: UTF8.self)) }
            if s.status == 200 {
                // Only when the new deployment has none yet (412): never overwrite settings changed since.
                let w = try await az.blobRaw("PUT", "config/settings.json", body: s.data,
                                             headers: ["x-ms-blob-type": "BlockBlob", "Content-Type": "application/json",
                                                       "If-None-Match": "*"], account: account)
                guard [200, 201, 412].contains(w.status) else { throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self)) }
            }
            let old = try await readRegions(account: oldAccount).regions
            let choices = old.compactMap { r in RegionChoice.all.first { $0.code == r.code } }
            let existing = try await readRegions(account: account).regions
            try await ensureReconciler(account: account, regions: existing, adding: choices)
            for c in choices { _ = try await placeholderRegion(c, account: account) }
            let marker = try JSONSerialization.data(withJSONObject: ["from": oldAccount, "homeExits": homeExits])
            let w = try await az.blobRaw("PUT", Self.migratedMarker, body: marker,
                                         headers: ["x-ms-blob-type": "BlockBlob", "Content-Type": "application/json"],
                                         account: account)
            guard [200, 201].contains(w.status) else { throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self)) }
        }

        // Old servers go only once nobody is on them or connecting to them (an old app may still
        // be in use); until then the old reconciler keeps guarding them.
        var remaining = 0
        for g in groups where g.lowercased() != Self.legacyControlRG {
            // Under the old deployment's region lock, which an old app takes before starting or
            // building that server, so none can begin between the check and the delete.
            let code = String(g.dropFirst(Self.legacyPrefix.count + 1)).lowercased()
            let removeIfIdle = { () async throws -> Bool in
                if try await self.legacyGroupBusy(g, oldAccount: oldAccount) { return false }
                self.log("Removing \(g)")
                try await self.az.arm("DELETE", "\(self.subPath)/resourceGroups/\(g)?api-version=\(API.rg)", accept: [200, 202, 204, 404])
                return true
            }
            let removed: Bool
            do {
                if let legacyAz { removed = try await legacyAz.withRegionLock(code, wait: 60) { try await removeIfIdle() } }
                else { removed = try await removeIfIdle() }
            } catch let AzureError.http(status, _) where status == 409 {
                removed = false  // an old app holds the lock right now
            }
            if !removed { remaining += 1; log("\(g): still in use, removed later") }
        }
        if remaining == 0, groups.contains(where: { $0.lowercased() == Self.legacyControlRG }) {
            log("Removing \(Self.legacyControlRG)")
            try await az.arm("DELETE", "\(subPath)/resourceGroups/\(Self.legacyControlRG)?api-version=\(API.rg)", accept: [200, 202, 204, 404])
        }
        // A role still assigned somewhere (a group that is still being deleted) can't be removed yet.
        var rolesLeft = false
        for id in legacyRoles {
            let r = try? await az.arm("DELETE", "\(id)?api-version=\(API.auth)", accept: [200, 204, 404])
            if r == nil { rolesLeft = true }
        }
        return LegacyMigration(account: account, regions: try await readRegions(account: account).regions,
                               cleanupPending: remaining > 0 || rolesLeft)
    }

    /// Adds the old deployment's devices to the new `peers.json`, keeping any device that has
    /// registered there already (and skipping an old entry whose address it now uses).
    private func mergePeers(from old: String, into account: String) async throws {
        let src = try await retry403 { try await self.az.blobRaw("GET", "config/peers.json", account: old) }
        if src.status == 404 { return }
        guard src.status == 200 else { throw AzureError.http(src.status, String(decoding: src.data, as: UTF8.self)) }
        let oldPeers = ((try? JSONSerialization.jsonObject(with: src.data) as? [String: Any])?["peers"] as? [[String: Any]]) ?? []
        for _ in 0..<8 {
            let r = try await retry403 { try await self.az.blobRaw("GET", "config/peers.json", account: account) }
            var root = (try? JSONSerialization.jsonObject(with: r.data) as? [String: Any]) ?? [:]
            var peers = root["peers"] as? [[String: Any]] ?? []
            let keys = Set(peers.compactMap { $0["pubkey"] as? String })
            let ips = Set(peers.compactMap { $0["ip4"] as? String })
            for p in oldPeers {
                guard let k = p["pubkey"] as? String, !keys.contains(k), let ip = p["ip4"] as? String, !ips.contains(ip) else { continue }
                peers.append(p)
            }
            root["peers"] = peers
            let body = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
            let w = try await az.blobRaw("PUT", "config/peers.json", body: body,
                                         headers: (r.status == 200 ? r.etag.map { ["If-Match": $0] } : nil) ?? ["If-None-Match": "*"],
                                         account: account)
            if [200, 201].contains(w.status) { return }
            if w.status != 412 && w.status != 409 { throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self)) }
        }
        throw ProvisionError.failed("Could not copy your devices (busy).")
    }

    /// True while an old server is running, or an old app has touched its leases in the last
    /// 15 minutes (it may be about to start it).
    private func legacyGroupBusy(_ group: String, oldAccount: String?) async throws -> Bool {
        let vms = try await az.arm("GET", "\(subPath)/resourceGroups/\(group)/providers/Microsoft.Compute/virtualMachines?api-version=\(API.compute)",
                                   accept: [200, 404])
        for vm in vms["value"] as? [[String: Any]] ?? [] {
            guard let id = vm["id"] as? String else { continue }
            if try await powerState(id) != "deallocated" { return true }
        }
        guard let oldAccount else { return false }
        let code = String(group.dropFirst(Self.legacyPrefix.count + 1)).lowercased()
        let r = try await az.blobRaw("GET", "leases?restype=container&comp=list&prefix=\(code)/", account: oldAccount)
        guard r.status == 200 else { return r.status != 404 }
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        let newest = String(decoding: r.data, as: UTF8.self).components(separatedBy: "<Last-Modified>").dropFirst()
            .compactMap { $0.components(separatedBy: "</Last-Modified>").first }.compactMap { fmt.date(from: $0) }.max()
        return newest.map { Date().timeIntervalSince($0) < 900 } ?? false
    }

    private func legacyRoleIDs() async throws -> [String] {
        var ids: [String] = []
        for role in ["Stopper", "Starter"] {
            let name = "Leap" + "VPN \(role)"
            let filter = "roleName eq '\(name)'".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
            let list = try await az.arm("GET", "\(subPath)/providers/Microsoft.Authorization/roleDefinitions?$filter=\(filter)&api-version=\(API.auth)")
            ids += (list["value"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? String }
        }
        return ids
    }

    func readRegions(account: String) async throws -> (regions: [RegionConfig], etag: String?) {
        let r = try await retry403 { try await self.az.blobRaw("GET", "config/regions.json", account: account) }
        if r.status == 404 { return ([], nil) }
        guard r.status == 200 else { throw AzureError.http(r.status, String(decoding: r.data, as: UTF8.self)) }
        struct File: Codable { var regions: [RegionConfig] }
        return ((try? JSONDecoder().decode(File.self, from: r.data).regions) ?? [], r.etag)
    }

    // MARK: preflight

    func preflight(locations: [String]) async throws {
        log("Checking permissions")
        let perms = try await az.arm("GET", "\(subPath)/providers/Microsoft.Authorization/permissions?api-version=\(API.auth)")
        let canAssign = (perms["value"] as? [[String: Any]] ?? []).contains { p in
            let actions = (p["actions"] as? [String] ?? []).map { $0.lowercased() }
            let not = (p["notActions"] as? [String] ?? []).map { $0.lowercased() }
            let grants = actions.contains("*") || actions.contains("microsoft.authorization/*")
                || actions.contains("microsoft.authorization/roleassignments/write")
            let denies = not.contains("microsoft.authorization/*/write") || not.contains("microsoft.authorization/roleassignments/write")
                || not.contains("microsoft.authorization/*")
            return grants && !denies
        }
        guard canAssign else { throw ProvisionError.permission }

        log("Registering Azure services")
        try await withThrowingTaskGroup(of: Void.self) { group in
            for ns in ["Microsoft.Compute", "Microsoft.Network", "Microsoft.Storage", "Microsoft.Automation"] {
                group.addTask { try await self.register(ns) }
            }
            try await group.waitForAll()
        }

        for loc in Set(locations) {
            let usages = try await az.arm("GET", "\(subPath)/providers/Microsoft.Compute/locations/\(loc)/usages?api-version=\(API.compute)")
            for u in usages["value"] as? [[String: Any]] ?? [] {
                let name = (u["name"] as? [String: Any])?["value"] as? String ?? ""
                guard name == "cores" || name == "standardBasv2Family" else { continue }
                let used = (u["currentValue"] as? NSNumber)?.intValue ?? 0
                let limit = (u["limit"] as? NSNumber)?.intValue ?? 0
                if used + 2 > limit {
                    throw ProvisionError.quota("Not enough vCPU quota in \(loc) (\(used)/\(limit) used).")
                }
            }
        }
    }

    private func register(_ ns: String) async throws {
        let info = try await az.arm("GET", "\(subPath)/providers/\(ns)?api-version=\(API.rg)")
        if info["registrationState"] as? String == "Registered" { return }
        try await az.arm("POST", "\(subPath)/providers/\(ns)/register?api-version=\(API.rg)")
        for _ in 0..<60 {
            try await Task.sleep(for: .seconds(5))
            let s = try await az.arm("GET", "\(subPath)/providers/\(ns)?api-version=\(API.rg)")
            if s["registrationState"] as? String == "Registered" { return }
        }
        throw ProvisionError.failed("\(ns) did not finish registering.")
    }

    // MARK: control plane

    /// Storage (leases, config, exits) + the custom role, granted to the signed-in user.
    func ensureControlPlane(existing: String?) async throws -> String {
        log("Creating the control plane")
        try await ensureRG(Self.controlRG, Self.controlLocation)
        _ = try await stopperRoleID()

        var account = existing
        if account == nil {
            // Same name on every device of this subscription, so two first setups converge on one account.
            let fixed = "avenvpn" + SHA256.hash(data: Data(sub.lowercased().utf8)).prefix(8)
                .map { String(format: "%02x", $0) }.joined().prefix(16)
            let mine = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(fixed)"
            if try await az.arm("GET", "\(mine)?api-version=\(API.storage)", accept: [200, 404])["id"] != nil {
                account = fixed
            } else {
                let check = try await az.arm("POST", "\(subPath)/providers/Microsoft.Storage/checkNameAvailability?api-version=\(API.storage)",
                                             body: ["name": fixed, "type": "Microsoft.Storage/storageAccounts"])
                if check["nameAvailable"] as? Bool == true { account = fixed }
            }
        }
        if account == nil {
            for _ in 0..<5 {
                let name = "avenvpn" + String((0..<8).map { _ in "abcdefghijklmnopqrstuvwxyz0123456789".randomElement()! })
                let check = try await az.arm("POST", "\(subPath)/providers/Microsoft.Storage/checkNameAvailability?api-version=\(API.storage)",
                                             body: ["name": name, "type": "Microsoft.Storage/storageAccounts"])
                if check["nameAvailable"] as? Bool == true { account = name; break }
            }
        }
        guard let account else { throw ProvisionError.failed("No storage account name available.") }
        let acctPath = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(account)"
        let got = try await az.arm("GET", "\(acctPath)?api-version=\(API.storage)", accept: [200, 404])
        if got["id"] == nil {
            log("Creating storage \(account)")
            try await az.arm("PUT", "\(acctPath)?api-version=\(API.storage)", body: [
                "location": Self.controlLocation, "kind": "StorageV2", "sku": ["name": "Standard_LRS"],
                "tags": ["avenvpn": "1"],
                "properties": ["minimumTlsVersion": "TLS1_2", "allowBlobPublicAccess": false,
                               "allowSharedKeyAccess": false, "supportsHttpsTrafficOnly": true],
            ])
            try await waitSucceeded("\(acctPath)?api-version=\(API.storage)", what: "storage account")
        }
        for c in ["leases", "config", "exits"] {
            try await az.arm("PUT", "\(acctPath)/blobServices/default/containers/\(c)?api-version=\(API.storage)",
                             body: ["properties": ["publicAccess": "None"]])
        }
        try await assign(principal: try await me(), type: "User", role: builtin(Role.blobContributor), scope: acctPath)

        log("Waiting for storage access")
        if try await retry403({ try await self.az.blobRaw("GET", "config/peers.json", account: account) }).status == 404 {
            _ = try await az.blobRaw("PUT", "config/peers.json", body: Data(#"{"peers": []}"#.utf8),
                                     headers: ["If-None-Match": "*"], account: account)
        }
        if try await az.blobRaw("GET", "config/regions.json", account: account).status == 404 {
            _ = try await az.blobRaw("PUT", "config/regions.json", body: Data(#"{"regions": []}"#.utf8),
                                     headers: ["If-None-Match": "*"], account: account)
        }
        return account
    }

    // MARK: device

    /// Adds this Mac to `config/peers.json` (optimistic concurrency) and returns its tunnel addresses.
    /// `replacing` is this device's previous key (a restored or migrated device keeps its settings
    /// but not its this-device-only Keychain key): that entry is swapped for the new key in place.
    func registerDevice(account: String, name: String, publicKey: String, replacing old: String? = nil) async throws -> DeviceIdentity {
        for _ in 0..<8 {
            let r = try await retry403 { try await self.az.blobRaw("GET", "config/peers.json", account: account) }
            var root = (try? JSONSerialization.jsonObject(with: r.data) as? [String: Any]) ?? [:]
            var peers = root["peers"] as? [[String: Any]] ?? []
            if let p = peers.first(where: { $0["pubkey"] as? String == publicKey }),
               let ip4 = p["ip4"] as? String, let ip6 = p["ip6"] as? String {
                return DeviceIdentity(name: p["name"] as? String ?? name, ip4: ip4, ip6: ip6, publicKey: publicKey)
            }
            if let old, old != publicKey, let i = peers.firstIndex(where: { $0["pubkey"] as? String == old }),
               let ip4 = peers[i]["ip4"] as? String, let ip6 = peers[i]["ip6"] as? String {
                // Same name and addresses, so its leases and history stay this device's.
                let dev = DeviceIdentity(name: peers[i]["name"] as? String ?? name, ip4: ip4, ip6: ip6, publicKey: publicKey)
                peers[i]["pubkey"] = publicKey
                root["peers"] = peers
                let body = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
                let w = try await az.blobRaw("PUT", "config/peers.json", body: body,
                                             headers: r.etag.map { ["If-Match": $0] } ?? ["If-None-Match": "*"], account: account)
                if [200, 201].contains(w.status) { return dev }
                if w.status != 412 && w.status != 409 { throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self)) }
                continue
            }
            let names = Set(peers.compactMap { $0["name"] as? String })
            var unique = name, n = 2
            while names.contains(unique) { unique = "\(name)-\(n)"; n += 1 }
            let used = Set(peers.compactMap { ($0["ip4"] as? String)?.split(separator: ".").last.flatMap { Int($0) } })
            guard let host = (2...250).first(where: { !used.contains($0) }) else { throw ProvisionError.failed("Too many devices.") }
            let dev = DeviceIdentity(name: unique, ip4: "10.66.0.\(host)", ip6: "fd66::\(String(host, radix: 16))", publicKey: publicKey)
            peers.append(["name": dev.name, "pubkey": publicKey, "ip4": dev.ip4, "ip6": dev.ip6])
            root["peers"] = peers
            let body = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
            let w = try await az.blobRaw("PUT", "config/peers.json", body: body,
                                         headers: r.etag.map { ["If-Match": $0] } ?? ["If-None-Match": "*"], account: account)
            if [200, 201].contains(w.status) { return dev }
            if w.status != 412 && w.status != 409 { throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self)) }
        }
        throw ProvisionError.failed("Could not register this device (busy).")
    }

    // MARK: reconciler

    /// Uploads and publishes the bundled runbook, tagged with its hash.
    private func publishRunbook(_ aa: String) async throws {
        let script = try Self.resource("Reconcile-AvenVPN", "ps1")
        try await az.arm("PUT", "\(aa)/runbooks/\(Self.runbook)?api-version=\(API.automation)", body: [
            "location": Self.controlLocation,
            "properties": ["runbookType": "PowerShell", "logProgress": false, "logVerbose": false,
                           "description": "Deallocates or deletes AvenVPN servers left with no connected device."],
        ])
        let draft = try await az.armRaw("PUT", "\(aa)/runbooks/\(Self.runbook)/draft/content?api-version=\(API.automation)",
                                        body: Data(script.utf8), contentType: "text/powershell")
        guard [200, 201, 202].contains(draft.status) else {
            throw AzureError.http(draft.status, String(decoding: draft.data, as: UTF8.self))
        }
        try await az.arm("POST", "\(aa)/runbooks/\(Self.runbook)/publish?api-version=\(API.automation)")
        // Stamped last: a failed upload or publish leaves the old hash, so the next refresh retries.
        try await az.arm("PATCH", "\(aa)/runbooks/\(Self.runbook)?api-version=\(API.automation)",
                         body: ["tags": ["avenvpn-hash": SHA256Hex.of(script)]])
    }

    /// Republishes the runbook when this app ships a newer one. Returns true if it did.
    @discardableResult
    func refreshRunbook(account: String) async throws -> Bool {
        let aa = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Automation/automationAccounts/\(Self.automation)"
        let rb = try await az.arm("GET", "\(aa)/runbooks/\(Self.runbook)?api-version=\(API.automation)", accept: [200, 404])
        guard rb["id"] != nil else { return false }
        let want = SHA256Hex.of(try Self.resource("Reconcile-AvenVPN", "ps1"))
        if (rb["tags"] as? [String: String])?["avenvpn-hash"] == want { return false }
        // A newer runbook may need more on existing groups (e.g. Contributor to delete them).
        let groups = try await az.arm("GET", "\(subPath)/resourcegroups?$filter=tagName%20eq%20'avenvpn'&api-version=\(API.rg)")
        let names = ((groups["value"] as? [[String: Any]]) ?? []).compactMap { $0["name"] as? String }
            .filter { $0.hasPrefix("avenvpn-") && $0 != Self.controlRG }
        if !names.isEmpty {
            let principal = try await reconcilerPrincipal(), stopper = try await stopperRoleID()
            for g in names { try await guardGroup(g, principal: principal, stopper: stopper) }
        }
        // It takes the shared region lock, which lives in the leases container.
        let acctPath = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(account)"
        try await assign(principal: try await reconcilerPrincipal(), type: "ServicePrincipal",
                         role: builtin(Role.blobContributor), scope: Self.leasesScope(acctPath))
        try await publishRunbook(aa)
        return true
    }

    /// The hourly Automation runbook that deallocates any VM left running without a
    /// live lease — independent of the VMs and of this app.
    /// Run before any server is created: a VM that exists before the hourly reconciler can
    /// stop it would keep billing forever if setup were interrupted.
    func ensureReconciler(account: String, regions: [RegionConfig], adding new: [RegionChoice] = []) async throws {
        log("Setting up the safety net")
        let aa = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Automation/automationAccounts/\(Self.automation)"
        var info = try await az.arm("GET", "\(aa)?api-version=\(API.automation)", accept: [200, 404])
        if info["id"] == nil {
            info = try await az.arm("PUT", "\(aa)?api-version=\(API.automation)", body: [
                "location": Self.controlLocation, "identity": ["type": "SystemAssigned"],
                "tags": ["avenvpn": "1"], "properties": ["sku": ["name": "Basic"]],
            ])
        }
        guard let principal = (info["identity"] as? [String: Any])?["principalId"] as? String else {
            throw ProvisionError.failed("Automation account has no identity.")
        }
        try await publishRunbook(aa)
        let start = ISO8601DateFormatter().string(from: Date().addingTimeInterval(15 * 60))
        try await az.arm("PUT", "\(aa)/schedules/hourly?api-version=\(API.automation)", body: [
            "name": "hourly",
            "properties": ["startTime": start, "frequency": "Hour", "interval": 1, "timeZone": "UTC"],
        ], accept: [200, 201])
        let js = Self.uuid("jobschedule|\(account)")
        let existing = try await az.arm("GET", "\(aa)/jobSchedules/\(js)?api-version=\(API.automation)", accept: [200, 404])
        if existing["id"] == nil {
            try await az.arm("PUT", "\(aa)/jobSchedules/\(js)?api-version=\(API.automation)", body: [
                "properties": ["schedule": ["name": "hourly"], "runbook": ["name": Self.runbook],
                               "parameters": ["StorageAccount": account]],
            ], accept: [200, 201, 409])
        }
        let acctPath = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(account)"
        try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.blobReader), scope: acctPath)
        try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.blobContributor), scope: Self.leasesScope(acctPath))
        let stopper = try await stopperRoleID()
        for c in new { try await ensureRG("avenvpn-\(c.code)", c.location, tags: ["avenvpn": "1"]) }
        let groups = try await registerGroups(regions.map(\.resourceGroup) + new.map { "avenvpn-\($0.code)" }, account: account)
        for g in groups.sorted() {
            try await guardGroup(g, principal: principal, stopper: stopper)
        }
    }

    /// Registered before any server exists, so the reconciler also finds half-built ones.
    @discardableResult
    private func registerGroups(_ add: [String], account: String) async throws -> Set<String> {
        var groups = Set(add)
        if let old = try? JSONSerialization.jsonObject(with: try await az.blobRaw("GET", "config/groups.json", account: account).data)
            as? [String: Any], let known = old["groups"] as? [String] { groups.formUnion(known) }
        let reg = try await az.blobRaw("PUT", "config/groups.json",
                                       body: try JSONSerialization.data(withJSONObject: ["groups": groups.sorted()]),
                                       headers: ["x-ms-blob-type": "BlockBlob", "Content-Type": "application/json"],
                                       account: account)
        guard [200, 201].contains(reg.status) else { throw AzureError.http(reg.status, String(decoding: reg.data, as: UTF8.self)) }
        return groups
    }

    /// Adds one more location to an existing setup, picked from the map: its group goes
    /// under the safety net first, then it is recorded unbuilt (connect builds it).
    func enrollRegion(_ c: RegionChoice, account: String) async throws -> RegionConfig {
        let rg = "avenvpn-\(c.code)"
        try await ensureRG(rg, c.location, tags: ["avenvpn": "1"])
        try await registerGroups([rg], account: account)
        try await guardGroup(rg, principal: try await reconcilerPrincipal(), stopper: try await stopperRoleID())
        return try await placeholderRegion(c, account: account)
    }

    /// The reconciler may deallocate (Stopper) and clean up (Contributor, scoped to this one
    /// VPN group) — role assignments die with the group, so this runs again on every rebuild.
    private func guardGroup(_ g: String, principal: String, stopper: String) async throws {
        let scope = "\(subPath)/resourceGroups/\(g)"
        guard try await az.arm("GET", "\(scope)?api-version=\(API.rg)", accept: [200, 404])["id"] != nil else { return }
        try await assign(principal: principal, type: "ServicePrincipal", role: stopper, scope: scope)
        try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.contributor), scope: scope)
    }

    private func reconcilerPrincipal() async throws -> String {
        let aa = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Automation/automationAccounts/\(Self.automation)"
        let info = try await az.arm("GET", "\(aa)?api-version=\(API.automation)")
        guard let p = (info["identity"] as? [String: Any])?["principalId"] as? String else {
            throw ProvisionError.failed("Automation account has no identity.")
        }
        return p
    }

    // MARK: on-demand ("provision once") and IP release

    /// Is the region's server there at all? A deleted group (or one still being deleted) means "no".
    func groupState(_ rg: String) async throws -> String {
        let info = try await az.arm("GET", "\(subPath)/resourceGroups/\(rg)?api-version=\(API.rg)", accept: [200, 404])
        guard info["id"] != nil else { return "absent" }
        return (info["properties"] as? [String: Any])?["provisioningState"] as? String ?? "Succeeded"
    }

    /// Rebuilds a region that was deleted after its last session: wait out any running
    /// delete, put the safety net back on the new group, then deploy from scratch.
    func rebuildRegion(_ choice: RegionChoice, account: String) async throws -> RegionConfig {
        let rg = "avenvpn-\(choice.code)"
        let end = Date().addingTimeInterval(900)
        while try await groupState(rg) == "Deleting" {
            guard Date() < end else { throw ProvisionError.failed("\(choice.name) is still being removed.") }
            log("\(choice.name): waiting for the old server to be removed")
            try await Task.sleep(for: .seconds(10))
        }
        try await ensureRG(rg, choice.location, tags: ["avenvpn": "1"])
        try await guardGroup(rg, principal: try await reconcilerPrincipal(), stopper: try await stopperRoleID())
        return try await deployRegion(choice, account: account)
    }

    /// Deletes a deallocated region's whole group but keeps its record (it is rebuilt on connect).
    func deleteRegionResources(_ region: RegionConfig) async throws {
        log("\(region.name): deleting resources")
        try await az.arm("DELETE", "\(subPath)/resourceGroups/\(region.resourceGroup)?api-version=\(API.rg)",
                         accept: [200, 202, 204, 404])
    }

    private func ipPaths(_ region: RegionConfig) -> (ip: String, nic: String) {
        let net = "\(subPath)/resourceGroups/\(region.resourceGroup)/providers/Microsoft.Network"
        return ("\(net)/publicIPAddresses/\(region.vm)-ip", "\(net)/networkInterfaces/\(region.vm)-nic")
    }

    /// Detaches and deletes a stopped server's public IP so nothing is billed while idle.
    func releaseIP(_ region: RegionConfig) async throws {
        let (ip, nic) = ipPaths(region)
        var nicBody = try await az.arm("GET", "\(nic)?api-version=\(API.network)", accept: [200, 404])
        guard nicBody["id"] != nil else { return }
        if var props = nicBody["properties"] as? [String: Any], var cfgs = props["ipConfigurations"] as? [[String: Any]],
           cfgs.contains(where: { ($0["properties"] as? [String: Any])?["publicIPAddress"] != nil }) {
            for i in cfgs.indices {
                var p = cfgs[i]["properties"] as? [String: Any] ?? [:]
                p.removeValue(forKey: "publicIPAddress")
                cfgs[i]["properties"] = p
            }
            props["ipConfigurations"] = cfgs
            nicBody["properties"] = props
            log("\(region.name): releasing public IP")
            try await az.arm("PUT", "\(nic)?api-version=\(API.network)", body: nicBody)
            try await waitSucceeded("\(nic)?api-version=\(API.network)", what: "network card")
        }
        try await az.arm("DELETE", "\(ip)?api-version=\(API.network)", accept: [200, 202, 204, 404])
        // Deletion is asynchronous: attaching before it finishes would find the dying resource.
        for _ in 0..<60 {
            if try await az.arm("GET", "\(ip)?api-version=\(API.network)", accept: [200, 404])["id"] == nil { return }
            try await Task.sleep(for: .seconds(3))
        }
        throw ProvisionError.failed("\(region.name): the old public IP is still being removed.")
    }

    /// Re-creates and attaches a released public IP; returns the region with its new endpoint.
    func attachIP(_ region: RegionConfig, account: String) async throws -> RegionConfig {
        let (ip, nic) = ipPaths(region)
        var info = try await az.arm("GET", "\(ip)?api-version=\(API.network)", accept: [200, 404])
        if info["id"] == nil {
            log("\(region.name): new public IP")
            try await az.arm("PUT", "\(ip)?api-version=\(API.network)", body: [
                "location": region.location, "sku": ["name": "Standard"],
                "tags": ["avenvpn": "1", "avenvpn-region": region.code, "avenvpn-storage": account],
                "properties": ["publicIPAllocationMethod": "Static", "publicIPAddressVersion": "IPv4"],
            ])
            try await waitSucceeded("\(ip)?api-version=\(API.network)", what: "public IP")
            info = try await az.arm("GET", "\(ip)?api-version=\(API.network)")
        }
        var nicBody = try await az.arm("GET", "\(nic)?api-version=\(API.network)")
        if var props = nicBody["properties"] as? [String: Any], var cfgs = props["ipConfigurations"] as? [[String: Any]],
           !cfgs.isEmpty, (cfgs[0]["properties"] as? [String: Any])?["publicIPAddress"] == nil {
            var p = cfgs[0]["properties"] as? [String: Any] ?? [:]
            p["publicIPAddress"] = ["id": ip]
            cfgs[0]["properties"] = p
            props["ipConfigurations"] = cfgs
            nicBody["properties"] = props
            try await az.arm("PUT", "\(nic)?api-version=\(API.network)", body: nicBody)
            try await waitSucceeded("\(nic)?api-version=\(API.network)", what: "network card")
        }
        guard let address = (info["properties"] as? [String: Any])?["ipAddress"] as? String else {
            throw ProvisionError.failed("\(region.name): no public IP.")
        }
        // Another device may have rebuilt this server since `region` was cached: publish only
        // the address, on top of the stored record, so its current key is never overwritten.
        var updated = region
        if let stored = try await storedRegion(region.code, account: account), !stored.serverPublicKey.isEmpty {
            updated = stored
        }
        guard address != updated.endpoint else { return updated }
        updated.endpoint = address
        try await upsertRegion(updated, account: account)
        return updated
    }

    /// Gives a built server a new public address: the old IP is detached and deleted (so it
    /// can't keep billing) and a fresh one attached. Azure rarely hands back the same address,
    /// so that case is retried.
    func switchIP(_ region: RegionConfig, account: String) async throws -> RegionConfig {
        for _ in 0..<3 {
            try await releaseIP(region)
            let fresh: RegionConfig
            do {
                fresh = try await attachIP(region, account: account)
            } catch {
                // attachIP is idempotent: a second pass creates or attaches whatever the first left undone.
                log("\(region.name): attaching the new IP failed (\(error.localizedDescription)), retrying")
                try await Task.sleep(for: .seconds(5))
                fresh = try await attachIP(region, account: account)
            }
            if fresh.endpoint != region.endpoint { return fresh }
            log("\(region.name): got the same address back, retrying")
        }
        throw ProvisionError.failed("\(region.name): Azure kept the same address; try again later.")
    }

    /// Records a region without building it (provision-once mode builds it on first connect).
    func placeholderRegion(_ c: RegionChoice, account: String) async throws -> RegionConfig {
        if let have = try await storedRegion(c.code, account: account), !have.serverPublicKey.isEmpty { return have }
        let region = c.unbuilt(subscription: sub)
        try await upsertRegion(region, account: account)
        return region
    }

    /// Updates `config/settings.json` (read by every device and by the reconciler): `change`
    /// is applied to the latest copy, so another device's edits to other fields survive.
    func updateSettings(account: String, fallback: FleetSettings, _ change: (inout FleetSettings) -> Void) async throws {
        for _ in 0..<8 {
            let (current, etag) = try await readSettingsTagged(account: account)
            var s = current ?? fallback
            change(&s)
            let w = try await az.blobRaw("PUT", "config/settings.json", body: try JSONEncoder().encode(s),
                                         headers: etag.map { ["If-Match": $0] } ?? ["If-None-Match": "*"], account: account)
            if [200, 201].contains(w.status) { return }
            if [409, 412].contains(w.status) { continue }
            throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self))
        }
        throw ProvisionError.failed("Could not save settings (busy).")
    }

    func readSettings(account: String) async throws -> FleetSettings? {
        try await readSettingsTagged(account: account).settings
    }

    private func readSettingsTagged(account: String) async throws -> (settings: FleetSettings?, etag: String?) {
        let r = try await az.blobRaw("GET", "config/settings.json", account: account)
        if r.status == 404 { return (nil, nil) }
        guard r.status == 200 else { throw URLError(.badServerResponse) }
        return (try JSONDecoder().decode(FleetSettings.self, from: r.data), r.etag)
    }

    // MARK: regions

    /// Creates (or finishes) one region's VPN server, records it in `regions.json`, then
    /// lets the in-VM agent deallocate it.
    /// Holding a setup marker keeps the agent from deallocating mid-install; another device that
    /// finds it while holding the region lock knows this build was cut short.
    func deployRegion(_ choice: RegionChoice, account: String) async throws -> RegionConfig {
        // A failed build keeps its marker (it goes stale, so it doesn't hold the VM up): the next
        // connect then finishes the build instead of trusting a record with the old server's key.
        try await holdingMarker("leases/\(choice.code)/_setup", account: account, keepOnFailure: true) {
            try await deployRegionUnmarked(choice, account: account)
        }
    }

    private func deployRegionUnmarked(_ choice: RegionChoice, account: String) async throws -> RegionConfig {
        let code = choice.code, loc = choice.location
        let rg = "avenvpn-\(code)", vm = "avenvpn-\(code)"
        let rgPath = "\(subPath)/resourceGroups/\(rg)"
        let net = "\(rgPath)/providers/Microsoft.Network"
        let vmPath = "\(rgPath)/providers/Microsoft.Compute/virtualMachines/\(vm)"
        let tags: [String: String] = ["avenvpn": "1", "avenvpn-region": code, "avenvpn-storage": account]

        log("\(choice.name): network")
        try await ensureRG(rg, loc, tags: ["avenvpn": "1"])
        try await az.arm("PUT", "\(net)/publicIPAddresses/\(vm)-ip?api-version=\(API.network)", body: [
            "location": loc, "sku": ["name": "Standard"], "tags": tags,
            "properties": ["publicIPAllocationMethod": "Static", "publicIPAddressVersion": "IPv4"],
        ])
        try await az.arm("PUT", "\(net)/networkSecurityGroups/\(vm)-nsg?api-version=\(API.network)", body: [
            "location": loc, "tags": tags,
            "properties": ["securityRules": [
                Self.rule("wireguard", 100, "Udp", "51820"),
                Self.rule("home-exit-ssh", 110, "Tcp", "22"),
            ]],
        ])
        try await az.arm("PUT", "\(net)/virtualNetworks/\(vm)-vnet?api-version=\(API.network)", body: [
            "location": loc, "tags": tags,
            "properties": ["addressSpace": ["addressPrefixes": ["10.200.0.0/24"]],
                           "subnets": [["name": "default", "properties": ["addressPrefix": "10.200.0.0/24"]]]],
        ])
        try await waitSucceeded("\(net)/publicIPAddresses/\(vm)-ip?api-version=\(API.network)", what: "public IP")
        try await waitSucceeded("\(net)/networkSecurityGroups/\(vm)-nsg?api-version=\(API.network)", what: "firewall")
        try await waitSucceeded("\(net)/virtualNetworks/\(vm)-vnet?api-version=\(API.network)", what: "network")
        try await az.arm("PUT", "\(net)/networkInterfaces/\(vm)-nic?api-version=\(API.network)", body: [
            "location": loc, "tags": tags,
            "properties": [
                "networkSecurityGroup": ["id": "\(net)/networkSecurityGroups/\(vm)-nsg"],
                "ipConfigurations": [["name": "ipconfig1", "properties": [
                    "subnet": ["id": "\(net)/virtualNetworks/\(vm)-vnet/subnets/default"],
                    "publicIPAddress": ["id": "\(net)/publicIPAddresses/\(vm)-ip"],
                    "privateIPAllocationMethod": "Dynamic",
                ]]],
            ],
        ])
        try await waitSucceeded("\(net)/networkInterfaces/\(vm)-nic?api-version=\(API.network)", what: "network card")

        do {
        let vmInfo = try await az.arm("GET", "\(vmPath)?api-version=\(API.compute)", accept: [200, 404])
        if vmInfo["id"] == nil {
            log("\(choice.name): server")
            try await az.arm("PUT", "\(vmPath)?api-version=\(API.compute)", body: [
                "location": loc, "tags": tags, "identity": ["type": "SystemAssigned"],
                "properties": [
                    "hardwareProfile": ["vmSize": Self.vmSize],
                    "storageProfile": [
                        "imageReference": ["publisher": "Canonical", "offer": "ubuntu-24_04-lts",
                                           "sku": "server", "version": "latest"],
                        "osDisk": ["createOption": "FromImage", "diskSizeGB": 30, "deleteOption": "Delete",
                                   "managedDisk": ["storageAccountType": "StandardSSD_LRS"]],
                    ],
                    "osProfile": [
                        "computerName": vm, "adminUsername": "avenvpn",
                        "customData": Data(try Self.cloudInit().utf8).base64EncodedString(),
                        "linuxConfiguration": [
                            "disablePasswordAuthentication": true,
                            "ssh": ["publicKeys": [["path": "/home/avenvpn/.ssh/authorized_keys",
                                                    "keyData": Self.throwawaySSHKey()]]],
                        ],
                    ],
                    "networkProfile": ["networkInterfaces": [["id": "\(net)/networkInterfaces/\(vm)-nic",
                                                              "properties": ["primary": true, "deleteOption": "Delete"]]]],
                ],
            ])
        }
            return try await finishServer(choice, account: account, vmPath: vmPath, net: net)
        } catch {
            // Never leave a half-built server running: it may not yet be able to stop itself.
            // Unstructured so the cleanup still runs when setup was cancelled.
            await Task { [az] in
                // Another device may already be connected to this server; only stop it if nobody is.
                let me = await az.deviceName.map { "\(code)/\($0)<" } ?? "\u{0}"
                let list = try? await az.blobRaw("GET", "leases?restype=container&comp=list&prefix=\(code)/", account: account)
                let others = list.map { String(decoding: $0.data, as: UTF8.self)
                    .components(separatedBy: "<Name>").dropFirst()
                    .contains { !$0.hasPrefix("\(code)/_") && !$0.hasPrefix(me) } } ?? true
                if others, list?.status == 200 {
                    log("\(choice.name): setup failed; another device holds a lease, leaving it running")
                    return
                }
                log("\(choice.name): setup failed, stopping server")
                _ = try? await az.arm("POST", "\(vmPath)/deallocate?api-version=\(API.compute)", accept: [200, 202, 404])
            }.value
            throw error
        }
    }

    private func finishServer(_ choice: RegionChoice, account: String, vmPath: String, net: String) async throws -> RegionConfig {
        let code = choice.code, loc = choice.location
        let rg = "avenvpn-\(code)", vm = "avenvpn-\(code)"
        try await waitSucceeded("\(vmPath)?api-version=\(API.compute)", what: "server", timeout: 900)
        let vmInfo = try await az.arm("GET", "\(vmPath)?api-version=\(API.compute)")
        guard let vmId = vmInfo["id"] as? String,
              let principal = (vmInfo["identity"] as? [String: Any])?["principalId"] as? String else {
            throw ProvisionError.failed("\(choice.name): server has no identity.")
        }
        let acctPath = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(account)"
        try await assign(principal: principal, type: "ServicePrincipal", role: try await stopperRoleID(), scope: vmId)
        try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.blobReader), scope: acctPath)
        // Heartbeat and region lock only: write access stops at the leases container.
        try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.blobContributor), scope: Self.leasesScope(acctPath))

        if try await powerState(vmId) != "running" {
            log("\(choice.name): starting")
            try await az.arm("POST", "\(vmId)/start?api-version=\(API.compute)")
            for _ in 0..<60 where try await powerState(vmId) != "running" { try await Task.sleep(for: .seconds(5)) }
        }

        log("\(choice.name): installing WireGuard")
        let out = try await runCommand(vmId, """
            cloud-init status --wait >/dev/null 2>&1
            echo PUB=$(cat /etc/wireguard/server.pub)
            echo HOSTKEY=$(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)
            echo SVC=$(systemctl is-active wg-quick@wg0 avenvpn-agent avenvpn-deadman.timer | tr '\\n' ',')
            """)
        guard let pub = Self.field("PUB", out), pub.count == 44 else {
            throw ProvisionError.failed("\(choice.name): WireGuard did not start.\n\(out.suffix(400))")
        }
        let ip = try await az.arm("GET", "\(net)/publicIPAddresses/\(vm)-ip?api-version=\(API.network)")
        guard let address = (ip["properties"] as? [String: Any])?["ipAddress"] as? String else {
            throw ProvisionError.failed("\(choice.name): no public IP.")
        }
        let region = RegionConfig(code: code, name: choice.name, city: choice.city, flag: choice.flag,
                                  country: choice.country, location: loc, resourceGroup: rg, vm: vm, vmId: vmId,
                                  endpoint: address, size: Self.vmSize, serverPublicKey: pub,
                                  sshHostKey: Self.field("HOSTKEY", out, rest: true), agentVersion: Self.agentVersion)
        try await upsertRegion(region, account: account)
        log("\(choice.name): ready (\(Self.field("SVC", out) ?? ""))")
        return region
    }

    /// Pushes the current agent, deadman and firewall to an existing server.
    /// Updates a server's agent. Its own marker (not `_setup`) so it never reads as an interrupted build.
    func upgradeRegion(_ region: RegionConfig, account: String) async throws -> RegionConfig {
        try await holdingMarker("leases/\(region.code)/_upgrade", account: account) {
            try await upgradeRegionUnmarked(region, account: account)
        }
    }

    /// Keeps a `_`-prefixed lease blob fresh while `body` runs, then removes it before returning;
    /// the removal runs detached so a cancelled caller can't leave the marker behind.
    private func holdingMarker<T>(_ path: String, account: String, keepOnFailure: Bool = false,
                                  _ body: () async throws -> T) async throws -> T {
        let hold = Task { [az] in
            while !Task.isCancelled {
                _ = try? await az.blobRaw("PUT", path, body: Data(#"{"device":"_setup"}"#.utf8), account: account)
                try? await Task.sleep(for: .seconds(45))
            }
        }
        func clear() async {
            hold.cancel()
            await Task.detached { [az] in _ = try? await az.blobRaw("DELETE", path, account: account) }.value
        }
        do {
            let result = try await body()
            await clear()
            return result
        } catch {
            if keepOnFailure { hold.cancel(); await hold.value } else { await clear() }
            throw error
        }
    }

    private func upgradeRegionUnmarked(_ region: RegionConfig, account: String) async throws -> RegionConfig {
        // A server from before the rename runs differently named services; it is replaced, not patched.
        guard !region.resourceGroup.hasPrefix(Self.legacyPrefix) else {
            throw ProvisionError.failed("\(region.name): this server predates Aven VPN and is rebuilt on the next connect.")
        }
        log("\(region.name): updating")
        if let principal = (try await az.arm("GET", "\(region.vmId)?api-version=\(API.compute)")["identity"] as? [String: Any])?["principalId"] as? String {
            let acctPath = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(account)"
            try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.blobContributor), scope: Self.leasesScope(acctPath))
        }
        if try await powerState(region.vmId) != "running" {
            try await az.arm("POST", "\(region.vmId)/start?api-version=\(API.compute)")
            for _ in 0..<60 where try await powerState(region.vmId) != "running" { try await Task.sleep(for: .seconds(5)) }
        }
        var script = ""
        for (name, dest, mode) in Self.serverFiles {
            let b64 = Data(try Self.resource(name, nil, dir: "server").utf8).base64EncodedString()
            script += "echo \(b64) | base64 -d > \(dest).new && chmod \(mode) \(dest).new && mv \(dest).new \(dest)\n"
        }
        // Ad blocking needs dnsmasq (resolver) and conntrack (to re-route in-flight lookups
        // on a toggle); servers built before it have neither.
        script = "{ command -v dnsmasq && command -v conntrack; } >/dev/null || { apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y -qq dnsmasq-base conntrack; } >/dev/null 2>&1\n" + script
        script += """
            systemctl daemon-reload
            systemctl enable avenvpn-dns; systemctl restart avenvpn-dns
            /opt/avenvpn/firewall.sh down; /opt/avenvpn/firewall.sh up
            systemctl restart avenvpn-agent
            systemctl enable --now avenvpn-deadman.timer
            sleep 3
            echo SVC=$(systemctl is-active avenvpn-agent avenvpn-deadman.timer | tr '\\n' ',')
            echo DNS=$(command -v conntrack >/dev/null && cd /opt/avenvpn && python3 -c 'import agent; print("up" if agent.dns_ready() else "down")' || echo down)
            """
        let out = try await runCommand(region.vmId, script)
        // Recording the new version only after the resolver answers means a failed
        // install is retried on the next connect instead of leaving ad blocking dead.
        guard (Self.field("SVC", out) ?? "").hasPrefix("active,active"),
              Self.field("DNS", out) == "up" else {
            throw ProvisionError.failed("\(region.name): update failed.\n\(out.suffix(400))")
        }
        var updated = region
        updated.agentVersion = Self.agentVersion
        try await upsertRegion(updated, account: account)
        return updated
    }

    /// Deletes a region's resource group (and therefore its VM, disk, IP and network).
    func removeRegion(_ region: RegionConfig, account: String) async throws {
        log("\(region.name): removing")
        for _ in 0..<8 {
            var (regions, etag) = try await readRegions(account: account)
            regions.removeAll { $0.code == region.code }
            if try await writeRegions(regions, etag: etag, account: account) { break }
        }
        try await az.arm("DELETE", "\(subPath)/resourceGroups/\(region.resourceGroup)?api-version=\(API.rg)",
                         accept: [200, 202, 204, 404])
    }

    /// The shared record for one location, as the last device to build it wrote it.
    func storedRegion(_ code: String, account: String) async throws -> RegionConfig? {
        try await readRegions(account: account).regions.first { $0.code == code }
    }

    private func upsertRegion(_ region: RegionConfig, account: String) async throws {
        for _ in 0..<8 {
            var (regions, etag) = try await readRegions(account: account)
            regions.removeAll { $0.code == region.code }
            regions.append(region)
            regions.sort { $0.code < $1.code }
            if try await writeRegions(regions, etag: etag, account: account) { return }
        }
        throw ProvisionError.failed("Could not save \(region.name) (busy).")
    }

    private func writeRegions(_ regions: [RegionConfig], etag: String?, account: String) async throws -> Bool {
        struct File: Codable { var regions: [RegionConfig] }
        let w = try await az.blobRaw("PUT", "config/regions.json", body: try JSONEncoder.iso.encode(File(regions: regions)),
                                     headers: etag.map { ["If-Match": $0] } ?? ["If-None-Match": "*"], account: account)
        if [200, 201].contains(w.status) { return true }
        if [409, 412].contains(w.status) { return false }
        throw AzureError.http(w.status, String(decoding: w.data, as: UTF8.self))
    }

    // MARK: helpers

    static let agentVersion = 14

    private static let serverFiles: [(String, String, String)] = [
        ("agent.py", "/opt/avenvpn/agent.py", "755"),
        ("deadman.py", "/opt/avenvpn/deadman.py", "755"),
        ("firewall.sh", "/opt/avenvpn/firewall.sh", "755"),
        ("avenvpn-agent.service", "/etc/systemd/system/avenvpn-agent.service", "644"),
        ("avenvpn-deadman.service", "/etc/systemd/system/avenvpn-deadman.service", "644"),
        ("avenvpn-deadman.timer", "/etc/systemd/system/avenvpn-deadman.timer", "644"),
        ("avenvpn-dns.conf", "/opt/avenvpn/avenvpn-dns.conf", "644"),
        ("avenvpn-dns.service", "/etc/systemd/system/avenvpn-dns.service", "644"),
    ]

    /// No secrets in here: the server generates its WireGuard key itself and the app
    /// reads the public half back over ARM Run Command.
    static func cloudInit() throws -> String {
        var files = ""
        for (name, dest, mode) in serverFiles {
            let b64 = Data(try resource(name, nil, dir: "server").utf8).base64EncodedString()
            files += "  - path: \(dest)\n    encoding: b64\n    permissions: '0\(mode)'\n    content: \(b64)\n"
        }
        return """
            #cloud-config
            package_update: true
            packages: [wireguard-tools, iptables, dnsmasq-base, conntrack]
            write_files:
            \(files)  - path: /etc/sysctl.d/90-avenvpn.conf
                content: |
                  net.ipv4.ip_forward = 1
            runcmd:
              - [sh, -c, 'umask 077; [ -s /etc/wireguard/server.key ] || wg genkey > /etc/wireguard/server.key; wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub; chmod 644 /etc/wireguard/server.pub']
              - [sh, -c, 'umask 077; printf "[Interface]\\nAddress = 10.66.0.1/24, fd66::1/64\\nListenPort = 51820\\nPrivateKey = %s\\nPostUp = /opt/avenvpn/firewall.sh up\\nPostDown = /opt/avenvpn/firewall.sh down\\n" "$(cat /etc/wireguard/server.key)" > /etc/wireguard/wg0.conf']
              - sysctl --system
              - systemctl daemon-reload
              - systemctl enable --now wg-quick@wg0
              - systemctl enable --now avenvpn-agent
              - systemctl enable --now avenvpn-deadman.timer
              - systemctl enable --now avenvpn-dns

            """
    }

    static func resource(_ name: String, _ ext: String?, dir: String? = nil) throws -> String {
        guard let url = Bundle.main.url(forResource: name, withExtension: ext, subdirectory: dir),
              let text = try? String(contentsOf: url, encoding: .utf8) else {
            throw ProvisionError.failed("Missing bundled file \(name).")
        }
        return text
    }

    private static func rule(_ name: String, _ priority: Int, _ proto: String, _ port: String) -> [String: Any] {
        ["name": name, "properties": [
            "priority": priority, "direction": "Inbound", "access": "Allow", "protocol": proto,
            "sourceAddressPrefix": "*", "sourcePortRange": "*",
            "destinationAddressPrefix": "*", "destinationPortRange": port,
        ]]
    }

    /// Azure requires an admin SSH key on Linux VMs; nobody keeps the private half.
    private static func throwawaySSHKey() -> String {
        func str(_ d: Data) -> Data { withUnsafeBytes(of: UInt32(d.count).bigEndian) { Data($0) } + d }
        let pub = Curve25519.Signing.PrivateKey().publicKey.rawRepresentation
        return "ssh-ed25519 " + (str(Data("ssh-ed25519".utf8)) + str(pub)).base64EncodedString() + " avenvpn-unused"
    }

    private static func field(_ name: String, _ text: String, rest: Bool = false) -> String? {
        for line in text.components(separatedBy: "\n") where line.hasPrefix("\(name)=") {
            let v = String(line.dropFirst(name.count + 1)).trimmingCharacters(in: .whitespaces)
            if v.isEmpty { return nil }
            return rest ? v : v.components(separatedBy: " ").first
        }
        return nil
    }

    private func me() async throws -> String {
        if let userOID { return userOID }
        let oid = try await MicrosoftAuth.shared.objectID(tenant: tenant)
        userOID = oid
        return oid
    }

    private func builtin(_ id: String) -> String { "\(subPath)/providers/Microsoft.Authorization/roleDefinitions/\(id)" }

    private var stopperID: String?

    /// The Stopper custom role: read a VM and deallocate it, nothing else. A role created before
    /// the rename has the same deterministic id, so the PUT below renames it in place.
    private func stopperRoleID() async throws -> String {
        if let stopperID { return stopperID }
        let filter = "roleName eq '\(Self.stopperRole)'".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        let list = try await az.arm("GET", "\(subPath)/providers/Microsoft.Authorization/roleDefinitions?$filter=\(filter)&api-version=\(API.auth)")
        if let id = (list["value"] as? [[String: Any]])?.first?["id"] as? String {
            stopperID = id
            return id
        }
        let guid = Self.uuid("stopper|\(sub)")
        let path = "\(subPath)/providers/Microsoft.Authorization/roleDefinitions/\(guid)"
        try await az.arm("PUT", "\(path)?api-version=\(API.auth)", body: ["properties": [
            "roleName": Self.stopperRole, "type": "CustomRole",
            "description": "AvenVPN: let a server or the reconciler deallocate a VPN VM",
            "permissions": [["actions": ["Microsoft.Compute/virtualMachines/read",
                                         "Microsoft.Compute/virtualMachines/instanceView/read",
                                         "Microsoft.Compute/virtualMachines/deallocate/action"],
                             "notActions": []]],
            "assignableScopes": [subPath],
        ]])
        stopperID = path
        return path
    }

    /// Idempotent role assignment (deterministic id), retried while new identities replicate.
    private func assign(principal: String, type: String, role: String, scope: String) async throws {
        let id = Self.uuid("\(scope)|\(principal)|\(role)".lowercased())
        let path = "\(scope)/providers/Microsoft.Authorization/roleAssignments/\(id)?api-version=\(API.auth)"
        var last: Error?
        for _ in 0..<18 {
            do {
                try await az.arm("PUT", path, body: ["properties": [
                    "roleDefinitionId": role, "principalId": principal, "principalType": type,
                ]], accept: [200, 201])
                return
            } catch let e as AzureError where e.status == 409 {
                if case .http(_, let body) = e, body.contains("RoleAssignmentExists") { return }
                last = e
            } catch let e as AzureError where e.status == 400 || e.status == 404 {
                last = e  // PrincipalNotFound / RoleDefinitionDoesNotExist while replicating
            }
            try await Task.sleep(for: .seconds(10))
        }
        throw last ?? ProvisionError.failed("Role assignment failed.")
    }

    private func ensureRG(_ name: String, _ location: String, tags: [String: String] = ["avenvpn": "1"]) async throws {
        try await az.arm("PUT", "\(subPath)/resourceGroups/\(name)?api-version=\(API.rg)",
                         body: ["location": location, "tags": tags])
    }

    private func waitSucceeded(_ path: String, what: String, timeout: TimeInterval = 600) async throws {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            let info = try await az.arm("GET", path, accept: [200, 404])
            let state = (info["properties"] as? [String: Any])?["provisioningState"] as? String ?? ""
            if state == "Succeeded" { return }
            if state == "Failed" || state == "Canceled" { throw ProvisionError.failed("Creating the \(what) failed.") }
            try await Task.sleep(for: .seconds(5))
        }
        throw ProvisionError.failed("Timed out creating the \(what).")
    }

    private func powerState(_ vmId: String) async throws -> String {
        let view = try await az.arm("GET", "\(vmId)/instanceView?api-version=\(API.compute)")
        for s in view["statuses"] as? [[String: Any]] ?? [] {
            if let code = s["code"] as? String, code.hasPrefix("PowerState/") { return String(code.dropFirst(11)) }
        }
        return "unknown"
    }

    /// A run command is preempted if the VM stops underneath it; bring it back before retrying.
    private func ensureRunning(_ vmId: String) async throws {
        let state = try await powerState(vmId)
        if state == "running" || state == "starting" { return }
        NSLog("AvenVPN: VM %@ was %@ during setup; starting it again", vmId, state)
        try await az.arm("POST", "\(vmId)/start?api-version=\(API.compute)")
        let end = Date().addingTimeInterval(300)
        while Date() < end, try await powerState(vmId) != "running" {
            try await Task.sleep(for: .seconds(10))
        }
    }

    /// ARM Run Command — the trusted channel used to read the server's public keys back.
    private func runCommand(_ vmId: String, _ script: String) async throws -> String {
        let body = try JSONSerialization.data(withJSONObject: ["commandId": "RunShellScript",
                                                               "script": script.components(separatedBy: "\n")])
        var last = ""
        for attempt in 0..<5 {
            if attempt > 0 { try await ensureRunning(vmId) }
            let r = try await az.armRaw("POST", "\(vmId)/runCommand?api-version=\(API.compute)", body: body)
            if r.status == 409 { try await Task.sleep(for: .seconds(20)); continue }  // another run command in flight
            guard r.status == 202 || r.status == 200, let poll = r.headers["location"] ?? r.headers["azure-asyncoperation"] else {
                last = String(decoding: r.data, as: UTF8.self)
                try await Task.sleep(for: .seconds(10))
                continue
            }
            let end = Date().addingTimeInterval(1200)
            while Date() < end {
                try await Task.sleep(for: .seconds(10))
                let p = try await az.armRaw("GET", poll)
                if p.status == 202 { continue }
                let json = (try? JSONSerialization.jsonObject(with: p.data) as? [String: Any]) ?? [:]
                let values = (json["value"] as? [[String: Any]])
                    ?? (((json["properties"] as? [String: Any])?["output"] as? [String: Any])?["value"] as? [[String: Any]])
                if let values {
                    return values.compactMap { $0["message"] as? String }.joined(separator: "\n")
                }
                if let status = json["status"] as? String, status == "InProgress" { continue }
                last = String(decoding: p.data, as: UTF8.self)
                break
            }
        }
        throw ProvisionError.failed("Run command failed: \(last.prefix(300))")
    }

    /// Retries data-plane calls while a fresh role assignment propagates (can take minutes).
    private func retry403(_ op: @escaping () async throws -> BlobResponse) async throws -> BlobResponse {
        var r = try await op()
        for _ in 0..<36 where r.status == 403 {
            try await Task.sleep(for: .seconds(10))
            r = try await op()
        }
        if r.status == 403 { throw ProvisionError.failed("Storage access was not granted in time. Try again in a minute.") }
        return r
    }

    /// Name-based UUID so repeated runs produce the same resource ids.
    static func leasesScope(_ account: String) -> String { "\(account)/blobServices/default/containers/leases" }

    static func uuid(_ name: String) -> String {
        var b = Array(SHA256.hash(data: Data(name.utf8)).prefix(16))
        b[6] = (b[6] & 0x0F) | 0x50
        b[8] = (b[8] & 0x3F) | 0x80
        let h = b.map { String(format: "%02x", $0) }.joined()
        let c = Array(h)
        return "\(String(c[0..<8]))-\(String(c[8..<12]))-\(String(c[12..<16]))-\(String(c[16..<20]))-\(String(c[20..<32]))"
    }
}
