import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif
import Foundation
import os

enum Phase: Equatable {
    case idle
    case starting(String)
    case connected
    case disconnecting(String)
    case failed(String)

    var label: String {
        switch self {
        case .idle: return "Disconnected"
        case .starting(let s), .disconnecting(let s): return s
        case .connected: return "Connected"
        case .failed(let e): return e
        }
    }
    var busy: Bool {
        if case .starting = self { return true }
        if case .disconnecting = self { return true }
        return false
    }
    var tone: MapTone {
        switch self {
        case .idle: return .exposed
        case .starting, .disconnecting: return .connecting
        case .connected: return .secure
        case .failed: return .failed
        }
    }
}

/// Where the first-run flow is.
enum OnboardingStep: Equatable {
    case welcome, signIn, subscription, locations, building, homePCs, directPC, done
}

@MainActor
final class VPNController: ObservableObject {
    @Published var phase: Phase = .idle { didSet { writeStatus() } }
    @Published var selected: String
    @Published var regionStates: [String: String] = [:]
    @Published var tunnel = TunnelStatus(up: false)
    @Published var egress: EgressInfo? { didSet { writeStatus() } }
    @Published var home: GeoPoint?
    @Published var current: SessionRecord?
    @Published var lastCompleted: SessionRecord? { didSet { writeStatus() } }
    @Published var spend: Money?
    @Published var vpnBilled: [String: Double] = [:]
    @Published var usdRate: Double?
    @Published var exits: [HomeExit] = []
    @Published var pendingExits: [HomeExit] = []

    // onboarding / setup
    @Published private(set) var setup: Setup
    @Published var step: OnboardingStep
    @Published var subscriptions: [AzureSubscription] = []
    @Published var setupLog: [String] = []
    @Published var setupError: String?
    @Published var working = false
    @Published var needsSignIn = false
    @Published var email = ""
    @Published var directory = ""
    @Published var askDirectory = false

    let store = SessionStore()
    private(set) var azure: AzureClient?
    private var renewTask: Task<Void, Never>?
    static let log = Logger(subsystem: "com.sololeap.leapvpn", category: "app")
    private var connectTask: Task<Void, Never>?
    private var sleepTeardown: Task<Void, Never>?
    private var stopTask: Task<Void, Never>?
    private var quickStop = false
    private var monitorTask: Task<Void, Never>?
    private var sweepTask: Task<Void, Never>?
    private var wantConnected = false
    private var prices: [String: Prices] = [:]
    /// Test aid: lets the URL hook open a sheet on the home screen.
    @Published var requestedSheet: HomeSheet?
    @Published var sheetDismissals = 0

    init() {
        let s = Setup.load()
        setup = s
        selected = UserDefaults.standard.string(forKey: "region") ?? s.regions.first?.code ?? "in"
        // Home-PC-only users never sign in to Microsoft; everyone else needs a live session.
        let azureOK = s.subscriptionId == nil || (s.ready && MicrosoftAuth.shared.hasSession)
        step = s.onboarded && azureOK ? .done : .welcome
        if step == .done { makeClient() }
        observeSystem()
        if step == .done { Task { await refreshAll(); if azure != nil { startSweeper() } } }
        else if MicrosoftAuth.shared.hasSession && s.user != nil { resumeSession() }
    }

    private func makeClient() {
        guard let t = setup.tenantId, let sub = setup.subscriptionId else { azure = nil; return }
        azure = AzureClient(AzureContext(tenantId: t, subscriptionId: sub,
                                         storageAccount: setup.storageAccount, device: setup.device?.name))
    }

    private func mutate(_ f: (inout Setup) -> Void) {
        f(&setup)
        setup.save()
    }

    /// Azure servers offered as exits (relay-only regions stay off the map).
    var regions: [RegionConfig] { setup.regions }
    var exitRegions: [RegionConfig] { setup.regions.filter { !setup.relayOnly.contains($0.code) } }
    var choices: [ServerChoice] {
        exitRegions.map { ServerChoice(region: $0) } +
        exits.compactMap { e in regions.first { $0.code == e.region }.map { ServerChoice(region: $0, exit: e) } } +
        setup.direct.map { ServerChoice(region: nil, direct: $0) } +
        unbuiltChoices
    }
    /// Every other Azure location, offered on the map once the control plane exists.
    var unbuiltChoices: [ServerChoice] {
        guard let sub = setup.subscriptionId, setup.storageAccount != nil else { return [] }
        let have = Set(exitRegions.map(\.code))
        return RegionChoice.all.filter { !have.contains($0.code) }.map { c in
            ServerChoice(region: setup.regions.first { $0.code == c.code } ?? c.unbuilt(subscription: sub), unbuilt: true)
        }
    }
    /// The selection, falling back to the first location so one is always chosen.
    var choice: ServerChoice? { choices.first { $0.id == selected } ?? choices.first }
    /// The Azure region that serves the current selection (a home exit's relay region).
    var region: RegionConfig? { choice?.region }
    var hasAzure: Bool { setup.subscriptionId != nil }
    /// Defaults for locations without their own setting.
    var ephemeral: Bool { setup.ephemeral }
    var staticIP: Bool { setup.staticIP }
    func ephemeral(_ code: String) -> Bool { setup.ephemeral(for: code) }
    func staticIP(_ code: String) -> Bool { setup.staticIP(for: code) }
    func hasOwnPrefs(_ code: String) -> Bool { setup.regionPrefs?[code] != nil }

    /// Regions that relay a home PC keep their server and IP: the PC pins both.
    var relayRegions: Set<String> {
        Set((exits + pendingExits).map(\.region)).union(setup.relayOnly).union(building)
    }
    /// Relays being built for a new home PC, before their slot exists.
    private var building = Set<String>()

    // MARK: onboarding

    /// With a valid session: pick up where onboarding (or the app) left off.
    private func afterSignIn() async throws {
        subscriptions = try await MicrosoftAuth.shared.subscriptions()
        if setup.onboarded, let id = setup.subscriptionId, subscriptions.contains(where: { $0.id == id }) {
            makeClient()
            step = .done
            await refreshAll()
            startSweeper()
            return
        }
        if subscriptions.isEmpty {
            setupError = "No Azure subscription on this account."
            step = .signIn
        } else if subscriptions.count == 1 {
            await choose(subscriptions[0])
        } else {
            step = .subscription
        }
    }

    /// Relaunch mid-onboarding with a stored session: resume without asking again.
    private func resumeSession() {
        working = true
        Task {
            defer { working = false }
            do {
                email = setup.user?.username ?? ""
                _ = try await MicrosoftAuth.shared.token(MicrosoftAuth.storage, tenant: MicrosoftAuth.authority)
                try await afterSignIn()
                if step == .subscription,
                   let id = setup.subscriptionId, let sub = subscriptions.first(where: { $0.id == id }) {
                    await choose(sub)
                }
            } catch {
                step = .welcome
            }
        }
    }

    var signedIn: Bool { hasAzure && setup.user != nil && !needsSignIn }

    /// Re-run setup while already signed in: skip the browser and go straight to locations.
    func continueSignedIn() {
        guard !working else { return }
        working = true
        setupError = nil
        Task {
            defer { working = false }
            do {
                subscriptions = try await MicrosoftAuth.shared.subscriptions()
                if subscriptions.count == 1 {
                    await choose(subscriptions[0])
                } else if subscriptions.isEmpty {
                    setupError = "No Azure subscription on this account."
                } else {
                    step = .subscription
                }
            } catch { setupError = error.localizedDescription; step = .signIn }
        }
    }

    func signIn() {
        guard !working else { return }
        working = true
        setupError = nil
        Task {
            defer { working = false }
            do {
                let user = try await MicrosoftAuth.shared.signIn(directory: askDirectory ? directory : nil)
                email = user.username
                mutate { $0.user = user }
                needsSignIn = false
                try await afterSignIn()
            } catch AuthError.cancelled {
                step = .signIn
            } catch AuthError.needsDirectory {
                askDirectory = true
                step = .signIn
            } catch {
                setupError = error.localizedDescription
                step = .signIn
            }
        }
    }

    /// Picks the subscription, then adopts an existing deployment if there is one.
    func choose(_ sub: AzureSubscription) async {
        working = true
        defer { working = false }
        mutate {
            $0.tenantId = sub.tenantId
            $0.subscriptionId = sub.id
            $0.subscriptionName = sub.name
            $0.quotaId = sub.quotaId
            $0.monthlyCreditUSD = Self.monthlyCredit(quotaId: sub.quotaId, name: sub.name)
        }
        makeClient()
        guard let azure else { return }
        let p = Provisioner(azure, subscription: sub.id, tenant: sub.tenantId) { _ in }
        if let found = try? await p.discover() {
            mutate { $0.storageAccount = found.account; $0.regions = found.regions }
            makeClient()
        }
        step = .locations
    }

    /// Visual Studio (MSDN) subscriptions carry a monthly Azure credit (USD). The offer is
    /// identified by `quotaId`; the user-editable name only picks the tier, and an unknown
    /// tier gets the lower amount so the estimate never overstates the balance.
    static func monthlyCredit(quotaId: String?, name: String) -> Double? {
        let offer = quotaId?.components(separatedBy: "_").first?.uppercased()
        guard offer == "MSDN" || offer == "BIZSPARK" else { return nil }
        let n = name.lowercased()
        return n.contains("enterprise") || offer == "BIZSPARK" ? 150 : 50
    }

    /// Builds the control plane, this device's identity, the chosen regions and the
    /// reconciler — or resumes any of those that a previous attempt left unfinished.
    func build(_ chosen: [RegionChoice], relayOnly: Bool = false, then next: OnboardingStep? = nil) {
        guard !working, let azure, let sub = setup.subscriptionId, let tenant = setup.tenantId else { return }
        working = true
        setupError = nil
        setupLog = []
        if step != .done { step = .building }
        Task {
            defer { working = false }
            let p = Provisioner(azure, subscription: sub, tenant: tenant) { line in
                Self.log.notice("setup: \(line, privacy: .public)"); Task { @MainActor in self.setupLog.append(line) }
            }
            do {
                let missing = chosen.filter { c in !setup.regions.contains { $0.code == c.code } }
                try await p.preflight(locations: [Provisioner.controlLocation] + missing.map(\.location))
                let account = try await p.ensureControlPlane(existing: setup.storageAccount)
                mutate { $0.storageAccount = account }
                await azure.update(AzureContext(tenantId: tenant, subscriptionId: sub, storageAccount: account,
                                                device: setup.device?.name))
                let device = try await p.registerDevice(account: account, name: Self.deviceName(),
                                                        publicKey: DeviceKey.publicKey())
                mutate { $0.device = device }
                makeClient()
                guard let azure = self.azure else { return }
                let p2 = Provisioner(azure, subscription: sub, tenant: tenant) { line in
                    Self.log.notice("setup: \(line, privacy: .public)"); Task { @MainActor in self.setupLog.append(line) }
                }
                var all = try await p2.readRegions(account: account).regions
                try await p2.ensureReconciler(account: account, regions: all, adding: missing)
                try await withThrowingTaskGroup(of: RegionConfig.self) { group in
                    // Provision once: just record the region; its server is built on first connect.
                    for c in missing {
                        let lazy = self.setup.ephemeral(for: c.code) && !relayOnly
                        group.addTask { lazy ? try await p2.placeholderRegion(c, account: account) : try await p2.deployRegion(c, account: account) }
                    }
                    for r in all where (r.agentVersion ?? 0) < Provisioner.agentVersion && !r.serverPublicKey.isEmpty {
                        group.addTask {
                            // An old agent still works; retry next time rather than abort the others.
                            do { return try await p2.upgradeRegion(r, account: account) } catch {
                                if error is CancellationError { throw error }
                                Self.log.error("upgrade \(r.code, privacy: .public): \(String(describing: error), privacy: .public)")
                                return r
                            }
                        }
                    }
                    for try await r in group {
                        all.removeAll { $0.code == r.code }
                        all.append(r)
                        let snapshot = all
                        mutate { $0.regions = snapshot.sorted { $0.code < $1.code } }
                    }
                }
                mutate {
                    $0.regions = all.sorted { $0.code < $1.code }
                    if relayOnly { for c in missing { $0.relayOnly.insert(c.code) } }
                    else { for c in chosen { $0.relayOnly.remove(c.code) } }
                }
                setupLog.append("Done")
                if let first = chosen.first, !relayOnly { selected = first.code }
                if let next { step = next } else if step == .building { step = .homePCs }
                await refreshStates()
                startSweeper()
            } catch AuthError.signInRequired where !setup.onboarded {
                setupLog.removeAll()
                step = .welcome
            } catch {
                setupError = error.localizedDescription
                Self.log.error("setup failed: \(String(describing: error), privacy: .public)")
                setupLog.append("Stopped: \(error.localizedDescription)")
                handleAuth(error)
            }
        }
    }

    /// Settings › "Run setup again": back to the first-run screens, keeping everything already set up.
    func rerunOnboarding() {
        guard !phase.busy, phase != .connected, !working else { return }
        setupError = nil
        setupLog.removeAll()
        step = .welcome
    }

    /// Leaves a re-run of the setup screens without changing anything.
    func closeOnboarding() {
        guard setup.onboarded, !working else { return }
        setupError = nil
        step = .done
    }

    func finishOnboarding() {
        mutate { $0.onboarded = true }
        step = .done
        Task { await refreshAll(); if azure != nil { startSweeper() } }
    }

    // MARK: fleet settings

    /// `code == nil` changes the default; a location's own value always wins over it.
    func setEphemeral(_ on: Bool, for code: String? = nil) {
        localEdits += 1
        if let code { dirtyCodes.insert(code) } else { dirtyDefaults = true }
        mutate { s in
            guard let code else { s.ephemeralPref = on; return }
            var all = s.regionPrefs ?? [:]
            all[code, default: RegionPrefs()].ephemeral = on
            s.regionPrefs = all
        }
        pushSettings()
    }
    func setStaticIP(_ on: Bool, for code: String? = nil) {
        localEdits += 1
        if let code { dirtyCodes.insert(code) } else { dirtyDefaults = true }
        mutate { s in
            guard let code else { s.staticIPPref = on; return }
            var all = s.regionPrefs ?? [:]
            all[code, default: RegionPrefs()].staticIP = on
            s.regionPrefs = all
        }
        pushSettings()
    }
    /// Back to the defaults for one location.
    func resetPrefs(_ code: String) {
        localEdits += 1
        dirtyCodes.insert(code)
        mutate { $0.regionPrefs?[code] = nil }
        pushSettings()
    }
    /// Bumped by every local toggle, so a read that raced a write never reverts it.
    private var localEdits = 0
    /// What this device changed since its last write: only these overwrite the shared file.
    private var dirtyDefaults = false
    private var dirtyCodes = Set<String>()
    /// A toggle made before the Azure client existed: publish it rather than adopt the remote copy.
    private var unpushed = false
    private var pushTask: Task<Void, Never>?

    /// Shared with other devices and the reconciler through `config/settings.json`.
    private func pushSettings() {
        guard let azure, let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount else { unpushed = true; return }
        unpushed = false
        // Writes run one at a time and read the values when they run, so the last toggle always wins.
        let previous = pushTask
        pendingPushes += 1
        pushTask = Task {
            await previous?.value
            defer { pendingPushes -= 1 }
            let defaults = dirtyDefaults, codes = dirtyCodes
            dirtyDefaults = false; dirtyCodes = []
            let local = setup.regionPrefs ?? [:], eph = ephemeral, fixed = staticIP, relays = relayRegions.sorted()
            let fallback = FleetSettings(ephemeral: eph, staticIP: fixed, relays: relays, regions: local.isEmpty ? nil : local)
            let p = Provisioner(azure, subscription: sub, tenant: tenant) { _ in }
            do {
                try await p.updateSettings(account: account, fallback: fallback) { s in
                    if defaults { s.ephemeral = eph; s.staticIP = fixed }
                    var r = s.regions ?? [:]
                    for c in codes { r[c] = local[c] }
                    s.regions = r.isEmpty ? nil : r
                    s.relays = relays
                }
            } catch {
                // keep the local choice; the next sync retries instead of adopting the old file
                dirtyDefaults = dirtyDefaults || defaults; dirtyCodes.formUnion(codes)
                unpushed = true
                Self.trace("settings: \(error.localizedDescription)")
            }
            localEdits += 1  // reads that overlapped the write saw the old file
            // Static IP turned back on: idle servers get their address back now, not at next connect.
            for r in regions where staticIP(r.code) && !ephemeral(r.code) && !r.serverPublicKey.isEmpty && current?.region != r.code {
                if (try? await azure.powerState(r)) == "deallocated", let u = try? await p.attachIP(r, account: account), u != r {
                    mutate { st in st.regions = st.regions.map { $0.code == u.code ? u : $0 } }
                }
            }
        }
    }

    private var runbookChecked = false
    private var pendingPushes = 0

    func syncSettings() async {
        guard let azure, let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount else { return }
        let p = Provisioner(azure, subscription: sub, tenant: tenant) { _ in }
        // A missing file means defaults: publish them so the reconciler enforces the same rules.
        if !runbookChecked {
            do {
                if try await p.refreshRunbook() { Self.trace("reconciler runbook republished") }
                runbookChecked = true
            } catch { Self.trace("runbook refresh: \(error)") }
        }
        // A queued write would land after this read and then publish whatever the read adopted.
        await pushTask?.value
        guard pendingPushes == 0 else { return }
        let edits = localEdits
        let read: FleetSettings?
        do { read = try await p.readSettings(account: account) } catch { Self.trace("settings read: \(error)"); return }
        guard edits == localEdits, pendingPushes == 0 else { return }
        guard let s = read, !unpushed else { pushSettings(); return }
        let remote = s.regions?.isEmpty == false ? s.regions : nil
        let local = setup.regionPrefs?.isEmpty == false ? setup.regionPrefs : nil
        if s.ephemeral != ephemeral || s.staticIP != staticIP || remote != local {
            mutate { $0.ephemeralPref = s.ephemeral; $0.staticIPPref = s.staticIP; $0.regionPrefs = remote }
        }
        if (s.relays ?? []) != relayRegions.sorted() { pushSettings() }
    }

    // MARK: home PCs without Azure

    /// Home-PC-only setup: no Microsoft account, this Mac pairs with each PC directly.
    func skipSignIn() {
        _ = DeviceKey.publicKey()
        step = .directPC
    }

    static let directScriptURL =
        "https://raw.githubusercontent.com/A-VigneshRamamoorthy-Code/VikiAgentStore/\(directScriptRef)/plugins/azure/skills/vpn/homeexit/Install-LeapDirect.ps1"
    static let directScriptRef = "6f64bd8257440ebb84628904ee56bbcf0f6923c1"

    /// The one line to paste into PowerShell on the PC: it carries only this Mac's public key.
    func directCommand(name: String) -> String {
        let n = name.replacingOccurrences(of: "'", with: "").prefix(30)
        return "$env:LEAP_MAC='\(DeviceKey.publicKey())'; $env:LEAP_NAME='\(n)'; irm \(Self.directScriptURL) | iex"
    }

    /// Adds a PC from the link its installer printed. Returns false if the link isn't valid.
    @discardableResult
    func pair(link: String) -> Bool {
        guard let pc = DirectPC(link: link.trimmingCharacters(in: .whitespacesAndNewlines)) else { return false }
        mutate { s in
            var list = s.directPCs ?? []
            list.removeAll { $0.id == pc.id }
            list.append(pc)
            s.directPCs = list
        }
        if current == nil, !phase.busy {
            selected = "pc:\(pc.id)"
            UserDefaults.standard.set(selected, forKey: "region")
        }
        Self.trace("paired \(pc.id) \(pc.endpoint)")
        return true
    }

    func removeDirect(_ pc: DirectPC) {
        guard current?.region != "pc:\(pc.id)" else { return }
        mutate { $0.directPCs?.removeAll { $0.id == pc.id } }
    }

    func removeRegion(_ region: RegionConfig) {
        guard let azure, let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount, current?.region != region.code else { return }
        working = true
        Task {
            defer { working = false }
            let p = Provisioner(azure, subscription: sub, tenant: tenant) { _ in }
            do {
                try await p.removeRegion(region, account: account)
                mutate { $0.regions.removeAll { $0.code == region.code }; $0.relayOnly.remove(region.code) }
                if selected == region.code { selected = exitRegions.first?.code ?? "" }
            } catch { setupError = error.localizedDescription }
        }
    }

    /// Stops using the account on this Mac: no lease renewal, no tunnel, no tokens.
    /// Azure resources stay (deallocated) for the next sign-in or other devices.
    func signOut() {
        Task {
            wantConnected = false
            sweepTask?.cancel(); sweepTask = nil
            await stop(waitForStop: false).value
            await MicrosoftAuth.shared.signOut()
            setup = Setup()
            setup.save()
            azure = nil
            exits = []; pendingExits = []; regionStates = [:]; spend = nil
            step = .welcome
        }
    }

    static func deviceName() -> String {
        #if os(macOS)
        let raw = Host.current().localizedName ?? "mac"
        #else
        let raw = UIDevice.current.model
        #endif
        let slug = raw.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "-" }
            .reduce(into: "") { s, c in if !(c == "-" && s.hasSuffix("-")) { s.append(c) } }
            .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return String((slug.isEmpty ? "mac" : slug).prefix(30))
    }

    private func handleAuth(_ error: Error) {
        if case AuthError.signInRequired = error { needsSignIn = true }
    }

    // MARK: connect / disconnect

    func connect() {
        guard stopTask == nil else { return }
        guard let choice, !phase.busy, choice.exit?.pending != true else { return }
        if choice.direct == nil, azure == nil { return }
        selected = choice.id
        wantConnected = true
        UserDefaults.standard.set(choice.id, forKey: "region")
        connectTask = Task {
            defer { connectTask = nil }
            do {
                if let pc = choice.direct { try await connectDirect(pc, choice); return }
                guard let azure, var region = choice.region else { return }
                if choice.unbuilt { region = try await enroll(region) }
                let exit = choice.exit
                var record = SessionRecord(region: region.code, regionName: choice.title, flag: choice.flag,
                                           connectedAt: Date())
                record.via = exit?.name
                phase = .starting("Reserving \(region.name)…")
                // A new blob (not an overwrite) resets the server's connect grace after a crash.
                try await azure.deleteLease(region)
                try await azure.putLease(region, exit: exit?.id)
                startRenewing(region, exit: exit?.id)

                guard let device = setup.device else { throw msg("This Mac is not registered") }
                region = try await prepareServer(region, &record)
                var handshake = false
                // Two attempts: the server may have decided to deallocate just before our lease landed.
                for attempt in 0..<2 where !handshake {
                    var state = try await azure.powerState(region)
                    while state == "deallocating" || state == "stopping" {
                        phase = .starting("Waiting for \(region.name) to finish stopping…")
                        try await Task.sleep(for: .seconds(5))
                        state = try await azure.powerState(region)
                    }
                    if state != "running" {
                        phase = .starting("Starting \(region.name)…")
                        if record.vmStartRequestedAt == nil { record.vmStartRequestedAt = Date() }
                        try await azure.start(region)
                    }
                    for _ in 0..<60 where state != "running" {
                        try await Task.sleep(for: .seconds(4))
                        state = try await azure.powerState(region)
                        regionStates[region.code] = state
                    }
                    guard state == "running" else { throw msg("\(region.name) did not start (state: \(state))") }

                    phase = .starting("Securing tunnel…")
                    try await Tunnel.up(region, device)
                    for _ in 0..<75 {
                        tunnel = await Tunnel.status()
                        if (tunnel.handshake ?? 0) > 0 { handshake = true; break }
                        try await Task.sleep(for: .seconds(2))
                        if attempt == 0, (try? await azure.powerState(region)).map({ $0 != "running" }) == true { break }
                    }
                }
                guard handshake else { throw msg("No WireGuard handshake from \(region.name)") }

                phase = .starting("Checking exit location…")
                egress = await Egress.lookup()
                if let exit {
                    // The relay switches this device to the home exit within one agent cycle (~15 s);
                    // until then traffic still leaves from the relay's own address.
                    let relayIP = region.endpoint.components(separatedBy: ":")[0]
                    func onExit(_ e: EgressInfo?) -> Bool { e.map { $0.ip != relayIP } ?? false }
                    for _ in 0..<20 where !onExit(egress) {
                        phase = .starting("Waiting for \(exit.name)…")
                        try await Task.sleep(for: .seconds(3))
                        egress = await Egress.lookup()
                    }
                    guard onExit(egress) else {
                        throw msg("\(exit.name) isn't reachable — is the PC on and online?")
                    }
                }
                record.egressIP = egress?.ip
                record.egressCountry = egress?.country
                try Task.checkCancellation()
                record.connectedAt = Date()
                current = record
                store.upsert(record)
                phase = .connected
                startMonitor()
                upgradeIfOutdated(region)
            } catch {
                if Task.isCancelled { await teardown(reason: nil, waitForStop: !quickStop); return }  // stopped mid-connect
                handleAuth(error)
                await teardown(reason: error.localizedDescription)
            }
        }
    }

    /// A location picked from the map: recorded and put under the safety net; connect builds it.
    private func enroll(_ region: RegionConfig) async throws -> RegionConfig {
        if let known = setup.regions.first(where: { $0.code == region.code }) {
            if setup.relayOnly.contains(region.code) { mutate { _ = $0.relayOnly.remove(region.code) } }
            return known
        }
        guard let azure, let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount,
              let c = RegionChoice.all.first(where: { $0.code == region.code }) else { throw msg("\(region.name) can't be added") }
        let p = Provisioner(azure, subscription: sub, tenant: tenant) { line in Self.log.notice("enroll: \(line, privacy: .public)") }
        phase = .starting("Adding \(c.name)…")
        try await p.preflight(locations: [c.location])
        let added = try await p.enrollRegion(c, account: account)
        mutate { s in
            s.regions.removeAll { $0.code == added.code }
            s.regions.append(added)
            s.regions.sort { $0.code < $1.code }
        }
        Self.trace("enrolled \(added.code)")
        return added
    }

    /// Makes sure the region's server exists and has a public IP: provision-once mode
    /// deleted it after the last session, and dynamic-IP mode released its address.
    private func prepareServer(_ region: RegionConfig, _ record: inout SessionRecord) async throws -> RegionConfig {
        guard let azure, let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount else { return region }
        let p = Provisioner(azure, subscription: sub, tenant: tenant) { line in
            Self.log.notice("prepare: \(line, privacy: .public)")
        }
        // Another device may be building or deleting this server: wait for it, then use what it left.
        phase = .starting("Preparing \(region.name)…")
        var buildStart: Date?
        let updated: RegionConfig = try await azure.withRegionLock(region.code) {
            var base = region
            if let stored = try await p.storedRegion(region.code, account: account),
               !stored.serverPublicKey.isEmpty, stored.serverPublicKey != region.serverPublicKey {
                base = stored
            }
            let state = try await azure.powerState(base)
            let group = try await p.groupState(base.resourceGroup)
            if state == "deleted" || group != "Succeeded" {
                guard let c = RegionChoice.all.first(where: { $0.code == region.code }) else {
                    throw msg("\(region.name) can't be rebuilt")
                }
                phase = .starting("Building \(region.name) · ~2 min")
                regionStates[region.code] = "building"
                buildStart = Date()
                return try await p.rebuildRegion(c, account: account)
            }
            return try await p.attachIP(base, account: account)
        }
        if let buildStart { record.vmStartRequestedAt = buildStart }
        if updated != region { mutate { s in s.regions = s.regions.map { $0.code == updated.code ? updated : $0 } } }
        return updated
    }

    /// A home PC paired directly: no Azure, no lease, nothing billed.
    private func connectDirect(_ pc: DirectPC, _ choice: ServerChoice) async throws {
        var record = SessionRecord(region: choice.id, regionName: pc.name, flag: pc.flag, connectedAt: Date())
        record.via = pc.name
        record.currency = spend?.currency ?? lastCompleted?.currency ?? "USD"
        _ = DeviceKey.publicKey()
        phase = .starting("Reaching \(pc.name)…")
        try await Tunnel.up(pc)
        var handshake = false
        for _ in 0..<20 {
            tunnel = await Tunnel.status()
            if (tunnel.handshake ?? 0) > 0 { handshake = true; break }
            try await Task.sleep(for: .seconds(1.5))
        }
        guard handshake else {
            throw msg("\(pc.name) didn't answer — is it on, and is UDP \(pc.endpoint.split(separator: ":").last ?? "") forwarded?")
        }
        phase = .starting("Checking exit location…")
        egress = await Egress.lookup()
        record.egressIP = egress?.ip
        record.egressCountry = egress?.country
        try Task.checkCancellation()
        record.connectedAt = Date()
        current = record
        store.upsert(record)
        phase = .connected
        startMonitor()
    }

    /// Servers built by an older app get the current agent while the user is already
    /// connected, so updating never starts a VM on its own.
    private func upgradeIfOutdated(_ region: RegionConfig) {
        guard (region.agentVersion ?? 0) < Provisioner.agentVersion, let azure,
              let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount else { return }
        Task {
            do {
                let updated = try await Provisioner(azure, subscription: sub, tenant: tenant) { NSLog("LeapVPN: %@", $0) }
                    .upgradeRegion(region, account: account)
                mutate { s in s.regions = s.regions.map { $0.code == updated.code ? updated : $0 } }
            } catch {
                NSLog("LeapVPN: upgrade of %@ failed: %@", region.code, error.localizedDescription)
            }
        }
    }

    func disconnect() {
        wantConnected = false
        stop(waitForStop: true)
    }

    /// The one way a session ends (disconnect, sleep, sign-out, quit). A pending connect is
    /// cancelled and awaited — its catch tears down — so cleanup never has two owners.
    @discardableResult
    private func stop(waitForStop: Bool) -> Task<Void, Never> {
        if let stopTask { return stopTask }
        let t = Task {
            if let connecting = connectTask {
                quickStop = !waitForStop
                connecting.cancel()
                await connecting.value
                quickStop = false
            } else if phase == .connected || phase.busy || tunnel.up {
                await teardown(reason: nil, waitForStop: waitForStop)
            }
            stopTask = nil
        }
        stopTask = t
        return t
    }

    /// Release this device's lease, drop the tunnel, then follow the VM to deallocation
    /// (and deletion or IP release) so the session's VM time is known.
    private func teardown(reason: String?, waitForStop: Bool = true) async {
        let code = current?.region ?? choice?.id ?? ""
        let region = regions.first { $0.code == code } ?? (code.hasPrefix("pc:") ? nil : self.region)
        phase = .disconnecting("Disconnecting…")
        let renewing = renewTask
        renewTask = nil
        renewing?.cancel()
        await renewing?.value
        monitorTask?.cancel(); monitorTask = nil
        let final = await Tunnel.status()
        await Tunnel.down()
        tunnel = TunnelStatus(up: false)
        egress = nil
        if let region, let azure { try? await azure.deleteLease(region) }

        if var record = current {
            record.disconnectedAt = Date()
            record.rxBytes = max(record.rxBytes, final.rx ?? 0)
            record.txBytes = max(record.txBytes, final.tx ?? 0)
            if region == nil { record.vmStoppedAt = record.disconnectedAt }
            await price(&record)
            store.upsert(record)
            current = nil
            lastCompleted = record
            if waitForStop, let region { Task { await self.followShutdown(record, region) } }
        } else if waitForStop, let region, reason != nil {
            // A failed connect (perhaps mid-build) still must not leave anything behind.
            Task { await self.followShutdown(nil, region) }
        }
        phase = reason.map { .failed($0) } ?? .idle
    }

    /// The VM agent deallocates ~1 minute after the last lease disappears. Record when that
    /// happens, then delete the region (provision once) or release its IP (dynamic IP).
    private func followShutdown(_ start: SessionRecord?, _ region: RegionConfig) async {
        guard let azure else { return }
        var record = start
        var stopped = false
        for _ in 0..<60 {
            try? await Task.sleep(for: .seconds(10))
            guard let state = try? await azure.powerState(region) else { continue }
            regionStates[region.code] = state
            if state == "deallocated" || state == "deleted" {
                record?.vmStoppedAt = Date()
                stopped = true
                break
            }
            if current?.region == region.code { break }  // reconnected, the VM keeps running
        }
        if stopped { await cleanUp(region) }
        guard var record else { return }
        await price(&record)
        store.upsert(record)
        if lastCompleted?.id == record.id { lastCompleted = record }
        await refreshCosts()
    }

    /// Nothing left running *or* held: only for a stopped server nobody has a live lease on.
    private func cleanUp(_ region: RegionConfig) async {
        guard let azure, current?.region != region.code, !(phase.busy && self.region?.code == region.code),
              !relayRegions.contains(region.code), ephemeral(region.code) || !staticIP(region.code),
              let sub = setup.subscriptionId, let tenant = setup.tenantId else { return }
        guard (try? await azure.powerState(region)) == "deallocated" else { return }
        guard let age = try? await azure.newestLeaseAge(region) ?? .infinity, age > Double(Setup.leaseTTL) else { return }
        guard current?.region != region.code, !(phase.busy && self.region?.code == region.code),
              !relayRegions.contains(region.code) else { return }
        let p = Provisioner(azure, subscription: sub, tenant: tenant) { line in Self.log.notice("cleanup: \(line, privacy: .public)") }
        do {
            // Under the region lock a joining device either already holds a lease (seen below)
            // or is waiting for the lock and will rebuild after this delete.
            let done: Bool = try await azure.withRegionLock(region.code, wait: 60) {
                guard (try await azure.powerState(region)) == "deallocated",
                      (try await azure.newestLeaseAge(region) ?? .infinity) > Double(Setup.leaseTTL),
                      current?.region != region.code, !(phase.busy && self.region?.code == region.code),
                      !relayRegions.contains(region.code) else { return false }
                if ephemeral(region.code) {
                    try await p.deleteRegionResources(region)
                    regionStates[region.code] = "deleted"
                } else {
                    try await p.releaseIP(region)
                }
                return true
            }
            guard done else { return }
            Self.trace("cleanup \(region.code) ephemeral=\(ephemeral(region.code)) staticIP=\(staticIP(region.code))")
        } catch {
            Self.trace("cleanup \(region.code) failed: \(error)")
        }
    }

    private func price(_ record: inout SessionRecord) async {
        guard let azure, let region = regions.first(where: { $0.code == record.region }) else { return }
        guard region.endpoint.isEmpty == false || record.vmStartRequestedAt != nil else { return }
        let currency = spend?.currency ?? "INR"
        if prices[region.code] == nil {
            prices[region.code] = try? await azure.prices(for: region, currency: currency)
        }
        guard let p = prices[region.code] else { return }
        CostModel.price(&record, prices: p, monthGBBefore: store.monthEgressGB(before: record))
    }

    private func startRenewing(_ region: RegionConfig, exit: String?) {
        renewTask?.cancel()
        let every = Double(Setup.renewEvery)
        renewTask = Task { [azure] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(every))
                if Task.isCancelled { break }
                try? await azure?.putLease(region, exit: exit)
            }
        }
    }

    private func startMonitor() {
        monitorTask?.cancel()
        monitorTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                let s = await Tunnel.status()
                tunnel = s
                if var r = current {
                    r.rxBytes = s.rx ?? r.rxBytes
                    r.txBytes = s.tx ?? r.txBytes
                    r.lastSeenAt = Date()
                    current = r
                    // Persist about once a minute so a crash still leaves usable numbers behind.
                    if Int(Date().timeIntervalSince1970) % 60 < 5 { store.upsert(r) }
                }
                if !s.up, phase == .connected {
                    await teardown(reason: "Tunnel went down")
                }
            }
        }
    }

    // MARK: system events

    private func observeSystem() {
        #if os(iOS)
        // iOS keeps the tunnel up in the background by itself; no sleep teardown is needed.
        return
        #else
        let ws = NSWorkspace.shared.notificationCenter
        ws.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in
                guard self.phase == .connected || self.phase.busy else { return }
                let resume = self.wantConnected
                self.sleepTeardown = self.stop(waitForStop: false)
                await self.sleepTeardown?.value
                self.wantConnected = resume
            }
        }
        ws.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in
                await self.sleepTeardown?.value
                await self.stopTask?.value
                self.sleepTeardown = nil
                guard self.wantConnected else { await Tunnel.down(); return }
                try? await Task.sleep(for: .seconds(3))  // let the network come back
                for _ in 0..<60 where self.phase.busy { try? await Task.sleep(for: .seconds(2)) }
                if self.wantConnected, self.phase != .connected { self.connect() }
            }
        }
        #endif
    }

    /// Called on quit: release the lease and drop the tunnel so the server can deallocate.
    func shutdownForQuit() async {
        wantConnected = false
        await stop(waitForStop: false).value
    }

    // MARK: refresh

    func refreshAll() async {
        if home == nil, !tunnel.up, let e = await Egress.lookup() { home = GeoPoint(e.loc) }
        await refreshExits()
        await refreshStates()
        tunnel = await Tunnel.status()
        if tunnel.up && current == nil && !phase.busy {
            await Tunnel.down()  // orphaned from a previous run: it holds no lease, so the server is going away
            tunnel = TunnelStatus(up: false)
        }
        await finalizeOrphans()
        await refreshCosts()
    }

    /// Sessions left open by a crash or force-quit: end them at the last time the app saw
    /// the tunnel, and take the VM's real deallocation time from the Azure activity log.
    private func finalizeOrphans() async {
        guard let azure else {
            for var r in store.sessions where r.disconnectedAt == nil && r.id != current?.id {
                r.disconnectedAt = r.lastSeenAt ?? r.connectedAt
                store.upsert(r)
            }
            return
        }
        for var r in store.sessions where r.disconnectedAt == nil && r.id != current?.id && r.region.hasPrefix("pc:") {
            r.disconnectedAt = r.lastSeenAt ?? r.connectedAt
            store.upsert(r)
        }
        for var r in store.sessions where r.disconnectedAt == nil && r.id != current?.id {
            guard let region = regions.first(where: { $0.code == r.region }) else { continue }
            let stopped = try? await azure.deallocatedAt(region, after: r.connectedAt)
            if stopped == nil, Date().timeIntervalSince(r.connectedAt) < 3600 { continue }  // log may lag; retry later
            r.disconnectedAt = r.lastSeenAt ?? stopped ?? r.connectedAt
            r.vmStoppedAt = stopped
            await price(&r)
            store.upsert(r)
        }
    }

    func refreshStates() async {
        guard let azure else { return }
        await withTaskGroup(of: (String, String).self) { group in
            for r in regions {
                group.addTask { (r.code, (try? await azure.powerState(r)) ?? "unknown") }
            }
            for await (code, state) in group { regionStates[code] = state }
        }
    }

    func refreshExits() async {
        guard let azure else { return }
        if let approved = try? await azure.approveEnrollments(), !approved.isEmpty {
            for e in approved { try? await azure.deleteBlob(Self.invitePath(e.id)) }
        }
        if let list = try? await azure.listExits() { exits = list }
        if let list = try? await azure.listPendingExits() {
            let cutoff = Date().addingTimeInterval(-48 * 3600)
            for e in list where e.createdAt < cutoff {
                try? await azure.deleteExit(e)
                try? await azure.deleteBlob(Self.invitePath(e.id))
            }
            pendingExits = list.filter { $0.createdAt >= cutoff }
        }
        if !pendingExits.isEmpty { watchPendingExits() }
    }

    struct ExitInstaller {
        let command: String
        let file: URL
        let expires: Date
    }

    /// Reserve a home-exit slot on a relay and produce its Windows installer: a one-line
    /// PowerShell command (primary) plus a .cmd in ~/Downloads. The PC generates its own
    /// SSH key and registers itself (country, ISP, key) through a write-only link; both
    /// links expire in 48 hours.
    func createExitInstaller(regionCode: String, name: String? = nil, country: String? = nil) async throws -> ExitInstaller {
        guard let azure, var region = regions.first(where: { $0.code == regionCode }) else {
            throw msg("Unknown relay region")
        }
        if let sub = setup.subscriptionId, let tenant = setup.tenantId, let account = setup.storageAccount,
           let c = RegionChoice.all.first(where: { $0.code == regionCode }) {
            let p = Provisioner(azure, subscription: sub, tenant: tenant) { line in Self.log.notice("relay: \(line, privacy: .public)") }
            let power = try await azure.powerState(region)
            let group = try await p.groupState(region.resourceGroup)
            if region.serverPublicKey.isEmpty || power == "deleted" || group != "Succeeded" {
                // Keep the sweeper off it while it builds; it is a relay once the slot is reserved below.
                building.insert(regionCode)
                defer { building.remove(regionCode) }
                let current = region
                region = try await azure.withRegionLock(regionCode) {
                    if let stored = try await p.storedRegion(regionCode, account: account), !stored.serverPublicKey.isEmpty,
                       stored.serverPublicKey != current.serverPublicKey,
                       (try await p.groupState(stored.resourceGroup)) == "Succeeded",
                       (try await azure.powerState(stored)) != "deleted" { return stored }
                    return try await p.rebuildRegion(c, account: account)
                }
                let built = region
                mutate { s in s.regions = s.regions.map { $0.code == built.code ? built : $0 } }
            }
        }
        guard let hostKey = region.sshHostKey else {
            throw msg("No SSH host key for \(region.name) — run `vpnctl.py upgrade` and `install-mac` again")
        }
        let installer = try HomeExitSetup.installerSource()
        await refreshExits()
        let used = Set((exits + pendingExits).filter { $0.region == regionCode }.map(\.port))
        guard let port = HomeExitSetup.ports.first(where: { !used.contains($0) }) else {
            throw msg("No free exit ports on \(region.name)")
        }
        let id = HomeExitSetup.makeID("pc")
        let placeholder = HomeExit(id: id, name: name.map { String($0.prefix(40)) } ?? "New home PC",
                                   country: country?.uppercased() ?? "XX", region: regionCode,
                                   port: port, sshPublicKey: nil, createdAt: Date())
        try await azure.putPendingExit(placeholder)
        let ttl: TimeInterval = 48 * 3600
        // Create-only: the PC can write its enrollment once and cannot overwrite or read anything.
        let put = try await azure.blobSASURL("exits/_enroll/\(id).json", permissions: "c", validFor: ttl)
        let invite = HomeExitSetup.Invite(id: id, region: regionCode, regionName: region.name,
                                          relay: region.endpoint, hostKey: hostKey, port: port, put: put.url,
                                          expires: ISO8601DateFormatter().string(from: put.expires))
        let script = try HomeExitSetup.personalized(invite: invite, installer: installer)
        try await azure.putText(Self.invitePath(id), script)
        let get = try await azure.blobSASURL(Self.invitePath(id), permissions: "r", validFor: ttl)

        #if os(macOS)
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        #else
        let downloads = FileManager.default.temporaryDirectory
        #endif
        let file = downloads.appendingPathComponent("LeapVPN-HomeExit-\(id).cmd")
        try Data(HomeExitSetup.clickToRun(personalized: script, invite: invite).utf8).write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        pendingExits.append(placeholder)
        watchPendingExits()
        return ExitInstaller(command: HomeExitSetup.command(installerURL: get.url), file: file, expires: put.expires)
    }

    private static func invitePath(_ id: String) -> String { "exits/_invites/\(id).ps1" }

    /// Test-only trace for URL-driven runs (AllowURLControl); appends to trace.log.
    static func trace(_ line: String) {
        guard UserDefaults.standard.bool(forKey: "AllowURLControl") else { return }
        let url = AppConfig.supportDir.appendingPathComponent("trace.log")
        let entry = Data("\(ISO8601DateFormatter().string(from: Date())) \(line)\n".utf8)
        if let h = try? FileHandle(forWritingTo: url) { h.seekToEndOfFile(); h.write(entry); try? h.close() }
        else { try? entry.write(to: url) }
    }
    private var cleanedInvites: Set<String> = []

    private var exitWatcher: Task<Void, Never>?

    /// Poll while an installer is outstanding so the PC shows up as soon as it registers.
    func watchPendingExits() {
        guard exitWatcher == nil else { return }
        exitWatcher = Task { [weak self] in
            while let self, !self.pendingExits.isEmpty, !Task.isCancelled {
                try? await Task.sleep(for: .seconds(20))
                await self.refreshExits()
            }
            self?.exitWatcher = nil
        }
    }

    func removeExit(_ exit: HomeExit) async {
        guard let azure else { return }
        do { try await azure.deleteExit(exit); Self.trace("deleted \(exit.id)") } catch { Self.trace("deleteExit \(exit.id): \(error)") }
        try? await azure.deleteBlob(Self.invitePath(exit.id))
        exits.removeAll { $0.id == exit.id }
        pendingExits.removeAll { $0.id == exit.id }
        if selected == "exit:\(exit.id)" { selected = exit.region }
    }

    func refreshCosts() async {
        guard let azure else { return }
        if let s = try? await azure.periodToDateSpend() { spend = s }
        if let b = try? await azure.vpnCostByRegion() { vpnBilled = b }
        if usdRate == nil, let cur = spend?.currency { usdRate = await azure.usdRate(to: cur) }
    }

    /// Estimated monthly credit in billing currency (from the subscription offer).
    var monthlyCredit: Double? {
        guard let usd = setup.monthlyCreditUSD else { return nil }
        if spend?.currency == "USD" { return usd }
        guard let rate = usdRate else { return nil }
        return usd * rate
    }

    // MARK: sweeper

    /// While the app is open it also guards against VMs left running with nobody on them
    /// (another device that crashed, a failed setup). The VM's own agent and deadman timer
    /// and the hourly reconciler do the same without the app.
    func startSweeper() {
        guard sweepTask == nil else { return }
        sweepTask = Task { [weak self] in
            var first = true
            while !Task.isCancelled {
                if !first { try? await Task.sleep(for: .seconds(120)) }
                first = false
                guard let self, let azure = self.azure else { continue }
                await self.syncSettings()
                for r in self.regions where self.current?.region != r.code && !self.phase.busy && !self.building.contains(r.code) {
                    let state = try? await azure.powerState(r)
                    if state == "deallocated" { await self.cleanUp(r); continue }
                    guard state == "running" else { continue }
                    let newest: TimeInterval?
                    do { newest = try await azure.newestLeaseAge(r) } catch { continue }  // unknown is not "nobody"
                    guard let age = newest else {
                        // no lease at all; give a booting VM a chance to be claimed first
                        if self.idleSince[r.code] == nil { self.idleSince[r.code] = Date() }
                        if Date().timeIntervalSince(self.idleSince[r.code]!) > 300 {
                            try? await azure.deallocate(r); self.idleSince[r.code] = nil
                        }
                        continue
                    }
                    if age > 300 { try? await azure.deallocate(r) } else { self.idleSince[r.code] = nil }
                }
            }
        }
    }
    private var idleSince: [String: Date] = [:]

    /// Opt-in scripting for testing: `defaults write com.sololeap.leapvpn AllowURLControl -bool true`,
    /// then `open "leapvpn://connect?region=in"` / `open leapvpn://disconnect`. Only works once set up.
    struct PendingPair: Identifiable { let link: String, name: String, endpoint: String; var id: String { link } }
    /// iPhone: a pair link waiting for the user's confirmation (an alert in the UI).
    @Published var pendingPair: PendingPair?

    func confirmPair(_ link: String) {
        pendingPair = nil
        if pair(link: link), step != .done { finishOnboarding() }
        #if os(macOS)
        NSApp.activate(ignoringOtherApps: true)
        #endif
    }

    func handle(url: URL) {
        // leapvpn://pair links come from the user's own PC; they add a location but never connect.
        if url.scheme == "leapvpn", url.host == "pair" {
            guard let pc = DirectPC(link: url.absoluteString) else { return }
            #if os(macOS)
            NSApp.activate(ignoringOtherApps: true)
            let a = NSAlert()
            a.messageText = "Add \(pc.name)?"
            a.informativeText = "Only add a PC you set up yourself. Traffic will go to \(pc.endpoint)."
            a.addButton(withTitle: "Add"); a.addButton(withTitle: "Cancel")
            guard a.runModal() == .alertFirstButtonReturn else { return }
            confirmPair(url.absoluteString)
            #else
            pendingPair = PendingPair(link: url.absoluteString, name: pc.name, endpoint: pc.endpoint)
            #endif
            return
        }
        guard UserDefaults.standard.bool(forKey: "AllowURLControl"), url.scheme == "leapvpn" else { return }
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        if url.host == "settings" {
            let code = items.first(where: { $0.name == "region" })?.value
            if let v = items.first(where: { $0.name == "ephemeral" })?.value { setEphemeral(v == "1", for: code) }
            if let v = items.first(where: { $0.name == "staticIP" })?.value { setStaticIP(v == "1", for: code) }
            return
        }
        if url.host == "skip" { skipSignIn(); return }
        if url.host == "settingsSheet" { requestedSheet = .settings; return }
        #if os(macOS)
        if url.host == "menubar" { snapshotMenuBar(); return }
        if url.host == "snapshot" {
            snapshot(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first { $0.name == "name" }?.value)
            return
        }
        #endif
        if url.host == "addpc" { requestedSheet = .addPC; return }
        if url.host == "rerun" { rerunOnboarding(); return }
        if url.host == "preview", !phase.busy, phase != .connected,
           let v = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "step" })?.value {
            switch v {
            case "welcome": step = .welcome
            case "locations": step = .locations
            case "homepcs": step = .homePCs
            case "directpc": step = .directPC
            case "signin": step = .welcome; signIn()
            default: if setup.onboarded { step = .done }
            }
            return
        }
        if url.host == "closesheet" { sheetDismissals += 1; return }
        if url.host == "history" { requestedSheet = .history; return }
        let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        if url.host == "setup", step == .locations || step == .done,
           let codes = q.first(where: { $0.name == "regions" })?.value?.split(separator: ",").map(String.init) {
            build(RegionChoice.all.filter { codes.contains($0.code) },
                  relayOnly: q.contains { $0.name == "relayOnly" }, then: step == .done ? .done : nil)
            return
        }
        if url.host == "finish", step == .homePCs || step == .directPC { finishOnboarding(); return }
        guard step == .done else { return }
        let server = URLComponents(url: url, resolvingAgainstBaseURL: false)?
            .queryItems?.first { $0.name == "region" || $0.name == "server" }?.value
        switch url.host {
        case "connect":
            Task {
                if let server, server.hasPrefix("exit:") { await refreshExits() }
                if let server, choices.contains(where: { $0.id == server }) { selected = server }
                connect()
            }
        case "disconnect":
            disconnect()
        case "removeexit":
            Task {
                await refreshExits()
                let match = (exits + pendingExits).first { "exit:\($0.id)" == server || $0.id == server }
                Self.trace("removeexit \(server ?? "-") -> \(match?.id ?? "no match") exits=\(exits.map(\.id)) pending=\(pendingExits.map(\.id))")
                if let match { await removeExit(match) }
            }
        case "invite":
            Task {
                do {
                    let inst = try await createExitInstaller(regionCode: server ?? "in")
                    try? Data("\(inst.file.path)\n\(inst.command)\n".utf8)
                        .write(to: AppConfig.supportDir.appendingPathComponent("invite.txt"))
                } catch {
                    try? Data("error: \(error.localizedDescription)".utf8)
                        .write(to: AppConfig.supportDir.appendingPathComponent("invite.txt"))
                }
            }
        default: break
        }
    }

    #if os(macOS)
    /// Test aid: writes the main window (plus any sheet) to snapshot[-name].png. Captures the app's own
    /// windows from the window server so Liquid Glass renders; falls back to cacheDisplay.
    /// Testing only: shows the menu-bar popover content in a borderless panel and saves it,
    /// plus the status icon (outlined/filled) as `snapshot-menubar-<appearance>.png`.
    private func snapshotMenuBar() {
        Self.trace("snapshot menubar")
        let dark = NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        StatusBar.shared?.show()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            typealias CreateImage = @convention(c) (CGRect, UInt32, UInt32, UInt32) -> Unmanaged<CGImage>?
            let tag = dark ? "dark" : "light"
            if let sym = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGWindowListCreateImage"),
               let win = StatusBar.shared?.popover.contentViewController?.view.window,
               let img = unsafeBitCast(sym, to: CreateImage.self)(.null, 1 << 3, UInt32(win.windowNumber), (1 << 0) | (1 << 3))?.takeRetainedValue() {
                try? NSBitmapImageRep(cgImage: img).representation(using: .png, properties: [:])?
                    .write(to: AppConfig.supportDir.appendingPathComponent("snapshot-menubar-\(tag).png"))
            }
            for filled in [false, true] {
                let big = NSImage(size: NSSize(width: 72, height: 72), flipped: false) { r in
                    (dark ? NSColor.white : NSColor.black).set()
                    let i = LensIcon.image(filled: filled).copy() as! NSImage
                    i.isTemplate = false
                    i.draw(in: r)
                    r.fill(using: .sourceAtop)
                    return true
                }
                if let t = big.tiffRepresentation, let b = NSBitmapImageRep(data: t) {
                    try? b.representation(using: .png, properties: [:])?
                        .write(to: AppConfig.supportDir.appendingPathComponent("snapshot-icon-\(filled ? "filled" : "outline")-\(tag).png"))
                }
            }
            StatusBar.shared?.close()
        }
    }

    private func snapshot(_ name: String? = nil) {
        guard let main = NSApp.windows.first(where: { $0.canBecomeMain && $0.isVisible }) else { return }
        if !CGPreflightScreenCaptureAccess() { CGRequestScreenCaptureAccess() }
        let file = AppConfig.supportDir.appendingPathComponent(name.map { "snapshot-\($0).png" } ?? "snapshot.png")
        typealias CreateImage = @convention(c) (CGRect, UInt32, UInt32, UInt32) -> Unmanaged<CGImage>?
        func grab(_ w: NSWindow) -> CGImage? {
            guard let sym = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGWindowListCreateImage") else { return nil }
            let f = unsafeBitCast(sym, to: CreateImage.self)
            // optionIncludingWindow = 1 << 3; boundsIgnoreFraming = 1 << 0, bestResolution = 1 << 3
            return f(.null, 1 << 3, UInt32(w.windowNumber), (1 << 0) | (1 << 3))?.takeRetainedValue()
        }
        if !(name?.hasSuffix("-cache") ?? false), let base = grab(main) {
            let scale = CGFloat(base.width) / main.frame.width
            let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: base.width, pixelsHigh: base.height,
                                       bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                       colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
            let ctx = NSGraphicsContext.current!.cgContext
            ctx.draw(base, in: CGRect(x: 0, y: 0, width: base.width, height: base.height))
            if let sheet = main.attachedSheet, let img = grab(sheet) {
                let r = sheet.frame
                let x = (r.minX - main.frame.minX) * scale, y = (r.minY - main.frame.minY) * scale
                ctx.draw(img, in: CGRect(x: x, y: y, width: CGFloat(img.width), height: CGFloat(img.height)))
            }
            NSGraphicsContext.restoreGraphicsState()
            try? rep.representation(using: .png, properties: [:])?.write(to: file)
            return
        }
        let win = main.attachedSheet ?? main
        guard let view = win.contentView?.superview ?? win.contentView,
              let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: file)
    }
    #endif

    private func writeStatus() {
        var out: [String: Any] = ["phase": phase.label, "connected": phase == .connected,
                                  "region": current?.region ?? selected, "at": ISO8601DateFormatter().string(from: Date())]
        if let e = egress { out["egressIP"] = e.ip; out["egressCountry"] = e.country; out["egressOrg"] = e.org ?? "" }
        out["server"] = choice?.id ?? selected
        out["ephemeral"] = ephemeral
        out["staticIP"] = staticIP
        out["regionPrefs"] = Dictionary(uniqueKeysWithValues: regions.map { ($0.code, ["ephemeral": ephemeral($0.code), "staticIP": staticIP($0.code)]) })
        out["regionStates"] = regionStates
        out["via"] = current?.via ?? ""
        if let l = lastCompleted {
            out["lastSession"] = ["region": l.region, "cost": l.total, "currency": l.currency,
                                  "vmSeconds": l.vmSeconds, "bytes": l.rxBytes + l.txBytes,
                                  "deallocated": l.vmStoppedAt != nil]
        }
        if let data = try? JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: AppConfig.supportDir.appendingPathComponent("status.json"), options: .atomic)
        }
    }

    private func msg(_ s: String) -> NSError {
        NSError(domain: "LeapVPN", code: 1, userInfo: [NSLocalizedDescriptionKey: s])
    }
}
