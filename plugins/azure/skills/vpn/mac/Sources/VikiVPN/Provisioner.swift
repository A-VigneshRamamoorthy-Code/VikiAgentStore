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
        Keychain.set(key.rawRepresentation.base64EncodedString(), account: account, label: "VikiVPN WireGuard key")
        return key.publicKey.rawRepresentation.base64EncodedString()
    }

    static func reset() { Keychain.delete(account: account) }
}

/// Builds and maintains the user's VPN in their own subscription with their own
/// delegated ARM/Storage tokens — the same steps `scripts/vpnctl.py` performs with
/// the Azure CLI. Every step is idempotent, so a failed or interrupted setup is
/// resumed by running it again.
///
/// Layout (all tagged `vikivpn=1`):
///   vikivpn-ctl      storage account (leases / config / exits) + Automation reconciler
///   vikivpn-<code>   one WireGuard VM per region, deallocated whenever unused
actor Provisioner {
    static let controlRG = "vikivpn-ctl"
    static let controlLocation = "centralindia"
    static let vmSize = "Standard_B2ats_v2"
    static let automation = "vikivpn-reconciler"
    static let runbook = "Reconcile-VikiVPN"
    static let stopperRole = "VikiVPN Stopper"

    private let az: AzureClient
    private let sub: String
    private let tenant: String
    private let log: @Sendable (String) -> Void
    private var userOID: String?

    private enum Role {
        static let blobContributor = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"
        static let blobReader = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
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

    /// Finds an existing VikiVPN deployment in the subscription (set up from another device).
    func discover() async throws -> (account: String, regions: [RegionConfig])? {
        let list = try await az.arm("GET", "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts?api-version=\(API.storage)",
                                    accept: [200, 404])
        let accounts = (list["value"] as? [[String: Any]] ?? []).compactMap { a -> String? in
            guard let name = a["name"] as? String, name.hasPrefix("vikivpn") else { return nil }
            return name
        }
        guard let account = accounts.first else { return nil }
        return (account, try await readRegions(account: account).regions)
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
            for _ in 0..<5 {
                let name = "vikivpn" + String((0..<8).map { _ in "abcdefghijklmnopqrstuvwxyz0123456789".randomElement()! })
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
                "tags": ["vikivpn": "1"],
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
    func registerDevice(account: String, name: String, publicKey: String) async throws -> DeviceIdentity {
        for _ in 0..<8 {
            let r = try await retry403 { try await self.az.blobRaw("GET", "config/peers.json", account: account) }
            var root = (try? JSONSerialization.jsonObject(with: r.data) as? [String: Any]) ?? [:]
            var peers = root["peers"] as? [[String: Any]] ?? []
            if let p = peers.first(where: { $0["pubkey"] as? String == publicKey }),
               let ip4 = p["ip4"] as? String, let ip6 = p["ip6"] as? String {
                return DeviceIdentity(name: p["name"] as? String ?? name, ip4: ip4, ip6: ip6, publicKey: publicKey)
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
                "tags": ["vikivpn": "1"], "properties": ["sku": ["name": "Basic"]],
            ])
        }
        guard let principal = (info["identity"] as? [String: Any])?["principalId"] as? String else {
            throw ProvisionError.failed("Automation account has no identity.")
        }
        let script = try Self.resource("Reconcile-VikiVPN", "ps1")
        try await az.arm("PUT", "\(aa)/runbooks/\(Self.runbook)?api-version=\(API.automation)", body: [
            "location": Self.controlLocation,
            "properties": ["runbookType": "PowerShell", "logProgress": false, "logVerbose": false,
                           "description": "Deallocates VikiVPN servers left running with no connected device."],
        ])
        let draft = try await az.armRaw("PUT", "\(aa)/runbooks/\(Self.runbook)/draft/content?api-version=\(API.automation)",
                                        body: Data(script.utf8), contentType: "text/powershell")
        guard [200, 201, 202].contains(draft.status) else {
            throw AzureError.http(draft.status, String(decoding: draft.data, as: UTF8.self))
        }
        try await az.arm("POST", "\(aa)/runbooks/\(Self.runbook)/publish?api-version=\(API.automation)")
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
        let stopper = try await stopperRoleID()
        for c in new { try await ensureRG("vikivpn-\(c.code)", c.location, tags: ["vikivpn": "1"]) }
        let groups = Set(regions.map(\.resourceGroup) + new.map { "vikivpn-\($0.code)" })
        for g in groups.sorted() {
            try await assign(principal: principal, type: "ServicePrincipal", role: stopper,
                             scope: "\(subPath)/resourceGroups/\(g)")
        }
    }

    // MARK: regions

    /// Creates (or finishes) one region's VPN server, records it in `regions.json`, then
    /// lets the in-VM agent deallocate it.
    func deployRegion(_ choice: RegionChoice, account: String) async throws -> RegionConfig {
        let code = choice.code, loc = choice.location
        let rg = "vikivpn-\(code)", vm = "vikivpn-\(code)"
        let rgPath = "\(subPath)/resourceGroups/\(rg)"
        let net = "\(rgPath)/providers/Microsoft.Network"
        let vmPath = "\(rgPath)/providers/Microsoft.Compute/virtualMachines/\(vm)"
        let tags: [String: String] = ["vikivpn": "1", "vikivpn-region": code, "vikivpn-storage": account]

        // Holding a setup lease keeps the agent from deallocating mid-install.
        let hold = Task { [az] in
            while !Task.isCancelled {
                _ = try? await az.blobRaw("PUT", "leases/\(code)/_setup",
                                          body: Data(#"{"device":"_setup"}"#.utf8), account: account)
                try? await Task.sleep(for: .seconds(45))
            }
        }
        defer {
            hold.cancel()
            Task { [az] in _ = try? await az.blobRaw("DELETE", "leases/\(code)/_setup", account: account) }
        }

        log("\(choice.name): network")
        try await ensureRG(rg, loc, tags: ["vikivpn": "1"])
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

        var vmInfo = try await az.arm("GET", "\(vmPath)?api-version=\(API.compute)", accept: [200, 404])
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
                        "computerName": vm, "adminUsername": "vikivpn",
                        "customData": Data(try Self.cloudInit().utf8).base64EncodedString(),
                        "linuxConfiguration": [
                            "disablePasswordAuthentication": true,
                            "ssh": ["publicKeys": [["path": "/home/vikivpn/.ssh/authorized_keys",
                                                    "keyData": Self.throwawaySSHKey()]]],
                        ],
                    ],
                    "networkProfile": ["networkInterfaces": [["id": "\(net)/networkInterfaces/\(vm)-nic",
                                                              "properties": ["primary": true, "deleteOption": "Delete"]]]],
                ],
            ])
        }
        do {
            return try await finishServer(choice, account: account, vmPath: vmPath, net: net)
        } catch {
            // Never leave a half-built server running: it may not yet be able to stop itself.
            log("\(choice.name): setup failed, stopping server")
            _ = try? await az.arm("POST", "\(vmPath)/deallocate?api-version=\(API.compute)", accept: [200, 202, 404])
            throw error
        }
    }

    private func finishServer(_ choice: RegionChoice, account: String, vmPath: String, net: String) async throws -> RegionConfig {
        let code = choice.code, loc = choice.location
        let rg = "vikivpn-\(code)", vm = "vikivpn-\(code)"
        try await waitSucceeded("\(vmPath)?api-version=\(API.compute)", what: "server", timeout: 900)
        let vmInfo = try await az.arm("GET", "\(vmPath)?api-version=\(API.compute)")
        guard let vmId = vmInfo["id"] as? String,
              let principal = (vmInfo["identity"] as? [String: Any])?["principalId"] as? String else {
            throw ProvisionError.failed("\(choice.name): server has no identity.")
        }
        let acctPath = "\(subPath)/resourceGroups/\(Self.controlRG)/providers/Microsoft.Storage/storageAccounts/\(account)"
        try await assign(principal: principal, type: "ServicePrincipal", role: try await stopperRoleID(), scope: vmId)
        try await assign(principal: principal, type: "ServicePrincipal", role: builtin(Role.blobReader), scope: acctPath)

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
            echo SVC=$(systemctl is-active wg-quick@wg0 vikivpn-agent vikivpn-deadman.timer | tr '\\n' ',')
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
    func upgradeRegion(_ region: RegionConfig, account: String) async throws -> RegionConfig {
        let hold = Task { [az] in
            while !Task.isCancelled {
                _ = try? await az.blobRaw("PUT", "leases/\(region.code)/_setup",
                                          body: Data(#"{"device":"_setup"}"#.utf8), account: account)
                try? await Task.sleep(for: .seconds(45))
            }
        }
        defer {
            hold.cancel()
            Task { [az] in _ = try? await az.blobRaw("DELETE", "leases/\(region.code)/_setup", account: account) }
        }
        log("\(region.name): updating")
        if try await powerState(region.vmId) != "running" {
            try await az.arm("POST", "\(region.vmId)/start?api-version=\(API.compute)")
            for _ in 0..<60 where try await powerState(region.vmId) != "running" { try await Task.sleep(for: .seconds(5)) }
        }
        var script = ""
        for (name, dest, mode) in Self.serverFiles {
            let b64 = Data(try Self.resource(name, nil, dir: "server").utf8).base64EncodedString()
            script += "echo \(b64) | base64 -d > \(dest).new && chmod \(mode) \(dest).new && mv \(dest).new \(dest)\n"
        }
        script += """
            systemctl daemon-reload
            /opt/vikivpn/firewall.sh down; /opt/vikivpn/firewall.sh up
            systemctl restart vikivpn-agent
            systemctl enable --now vikivpn-deadman.timer
            sleep 3
            echo SVC=$(systemctl is-active vikivpn-agent vikivpn-deadman.timer | tr '\\n' ',')
            """
        let out = try await runCommand(region.vmId, script)
        guard (Self.field("SVC", out) ?? "").hasPrefix("active,active") else {
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

    static let agentVersion = 5

    private static let serverFiles: [(String, String, String)] = [
        ("agent.py", "/opt/vikivpn/agent.py", "755"),
        ("deadman.py", "/opt/vikivpn/deadman.py", "755"),
        ("firewall.sh", "/opt/vikivpn/firewall.sh", "755"),
        ("vikivpn-agent.service", "/etc/systemd/system/vikivpn-agent.service", "644"),
        ("vikivpn-deadman.service", "/etc/systemd/system/vikivpn-deadman.service", "644"),
        ("vikivpn-deadman.timer", "/etc/systemd/system/vikivpn-deadman.timer", "644"),
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
            packages: [wireguard-tools, iptables]
            write_files:
            \(files)  - path: /etc/sysctl.d/90-vikivpn.conf
                content: |
                  net.ipv4.ip_forward = 1
            runcmd:
              - [sh, -c, 'umask 077; [ -s /etc/wireguard/server.key ] || wg genkey > /etc/wireguard/server.key; wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub; chmod 644 /etc/wireguard/server.pub']
              - [sh, -c, 'umask 077; printf "[Interface]\\nAddress = 10.66.0.1/24, fd66::1/64\\nListenPort = 51820\\nPrivateKey = %s\\nPostUp = /opt/vikivpn/firewall.sh up\\nPostDown = /opt/vikivpn/firewall.sh down\\n" "$(cat /etc/wireguard/server.key)" > /etc/wireguard/wg0.conf']
              - sysctl --system
              - systemctl daemon-reload
              - systemctl enable --now wg-quick@wg0
              - systemctl enable --now vikivpn-agent
              - systemctl enable --now vikivpn-deadman.timer

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
        return "ssh-ed25519 " + (str(Data("ssh-ed25519".utf8)) + str(pub)).base64EncodedString() + " vikivpn-unused"
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

    /// The "VikiVPN Stopper" custom role: read a VM and deallocate it, nothing else.
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
            "description": "VikiVPN: let a server or the reconciler deallocate a VPN VM",
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

    private func ensureRG(_ name: String, _ location: String, tags: [String: String] = ["vikivpn": "1"]) async throws {
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
        NSLog("VikiVPN: VM %@ was %@ during setup; starting it again", vmId, state)
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
    static func uuid(_ name: String) -> String {
        var b = Array(SHA256.hash(data: Data(name.utf8)).prefix(16))
        b[6] = (b[6] & 0x0F) | 0x50
        b[8] = (b[8] & 0x3F) | 0x80
        let h = b.map { String(format: "%02x", $0) }.joined()
        let c = Array(h)
        return "\(String(c[0..<8]))-\(String(c[8..<12]))-\(String(c[12..<16]))-\(String(c[16..<20]))-\(String(c[20..<32]))"
    }
}
