import AppKit
import Foundation

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
    case welcome, signIn, subscription, locations, building, homePCs, done
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
    private var monitorTask: Task<Void, Never>?
    private var sweepTask: Task<Void, Never>?
    private var wantConnected = false
    private var prices: [String: Prices] = [:]
    /// Test aid: lets the URL hook open a sheet on the home screen.
    @Published var requestedSheet: HomeSheet?

    init() {
        let s = Setup.load()
        setup = s
        selected = UserDefaults.standard.string(forKey: "region") ?? s.regions.first?.code ?? "in"
        step = s.onboarded && s.ready && MicrosoftAuth.shared.hasSession ? .done : .welcome
        if step == .done { makeClient() }
        observeSystem()
        if step == .done { Task { await refreshAll(); startSweeper() } }
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
        exitRegions.map { ServerChoice(region: $0, exit: nil) } +
        exits.compactMap { e in regions.first { $0.code == e.region }.map { ServerChoice(region: $0, exit: e) } }
    }
    var choice: ServerChoice? { choices.first { $0.id == selected } }
    /// The Azure region that serves the current selection (a home exit's relay region).
    var region: RegionConfig? { choice?.region ?? regions.first { $0.code == selected } }

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
            $0.monthlyCreditUSD = Self.monthlyCredit(forOffer: sub.name)
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

    /// Visual Studio subscriptions carry a monthly Azure credit (USD).
    static func monthlyCredit(forOffer name: String) -> Double? {
        let n = name.lowercased()
        if n.contains("visual studio enterprise") || n.contains("msdn platforms") { return 150 }
        if n.contains("visual studio professional") { return 50 }
        if n.contains("visual studio") || n.contains("msdn") { return 50 }
        return nil
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
                Task { @MainActor in self.setupLog.append(line) }
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
                    Task { @MainActor in self.setupLog.append(line) }
                }
                var all = try await p2.readRegions(account: account).regions
                try await withThrowingTaskGroup(of: RegionConfig.self) { group in
                    for c in missing { group.addTask { try await p2.deployRegion(c, account: account) } }
                    for r in all where (r.agentVersion ?? 0) < Provisioner.agentVersion {
                        group.addTask { try await p2.upgradeRegion(r, account: account) }
                    }
                    for try await r in group {
                        all.removeAll { $0.code == r.code }
                        all.append(r)
                        let snapshot = all
                        mutate { $0.regions = snapshot.sorted { $0.code < $1.code } }
                    }
                }
                try await p2.ensureReconciler(account: account, regions: all)
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
                setupLog.append("Stopped: \(error.localizedDescription)")
                handleAuth(error)
            }
        }
    }

    func finishOnboarding() {
        mutate { $0.onboarded = true }
        step = .done
        Task { await refreshAll(); startSweeper() }
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
            if phase == .connected || phase.busy || tunnel.up { await teardown(reason: nil, waitForStop: false) }
            await MicrosoftAuth.shared.signOut()
            setup = Setup()
            setup.save()
            azure = nil
            exits = []; pendingExits = []; regionStates = [:]; spend = nil
            step = .welcome
        }
    }

    static func deviceName() -> String {
        let raw = Host.current().localizedName ?? "mac"
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
        guard let azure, let choice, !phase.busy, choice.exit?.pending != true else { return }
        let region = choice.region, exit = choice.exit
        wantConnected = true
        UserDefaults.standard.set(choice.id, forKey: "region")
        Task {
            do {
                var record = SessionRecord(region: region.code, regionName: choice.title, flag: choice.flag,
                                           connectedAt: Date())
                record.via = exit?.name
                phase = .starting("Reserving \(region.name)…")
                try await azure.putLease(region, exit: exit?.id)
                startRenewing(region, exit: exit?.id)

                var state = try await azure.powerState(region)
                while state == "deallocating" || state == "stopping" {
                    phase = .starting("Waiting for \(region.name) to finish stopping…")
                    try await Task.sleep(for: .seconds(5))
                    state = try await azure.powerState(region)
                }
                if state != "running" {
                    phase = .starting("Starting \(region.name) server…")
                    record.vmStartRequestedAt = Date()
                    try await azure.start(region)
                }
                for _ in 0..<60 where state != "running" {
                    try await Task.sleep(for: .seconds(4))
                    state = try await azure.powerState(region)
                    regionStates[region.code] = state
                }
                guard state == "running" else { throw msg("\(region.name) did not start (state: \(state))") }

                phase = .starting("Bringing up tunnel…")
                guard let device = setup.device else { throw msg("This Mac is not registered") }
                try await Tunnel.up(region, device)
                var handshake = false
                for _ in 0..<75 {
                    tunnel = await Tunnel.status()
                    if (tunnel.handshake ?? 0) > 0 { handshake = true; break }
                    try await Task.sleep(for: .seconds(2))
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
                        phase = .starting("Waiting for home exit \(exit.name)…")
                        try await Task.sleep(for: .seconds(3))
                        egress = await Egress.lookup()
                    }
                    guard onExit(egress) else {
                        throw msg("Home exit \(exit.name) isn't reachable — is the PC on, online, and set up?")
                    }
                }
                record.egressIP = egress?.ip
                record.egressCountry = egress?.country
                record.connectedAt = Date()
                current = record
                store.upsert(record)
                phase = .connected
                startMonitor()
                upgradeIfOutdated(region)
            } catch {
                handleAuth(error)
                await teardown(reason: error.localizedDescription)
            }
        }
    }

    /// Servers built by an older app get the current agent while the user is already
    /// connected, so updating never starts a VM on its own.
    private func upgradeIfOutdated(_ region: RegionConfig) {
        guard (region.agentVersion ?? 0) < Provisioner.agentVersion, let azure,
              let sub = setup.subscriptionId, let tenant = setup.tenantId,
              let account = setup.storageAccount else { return }
        Task {
            do {
                let updated = try await Provisioner(azure, subscription: sub, tenant: tenant) { NSLog("VikiVPN: %@", $0) }
                    .upgradeRegion(region, account: account)
                mutate { s in s.regions = s.regions.map { $0.code == updated.code ? updated : $0 } }
            } catch {
                NSLog("VikiVPN: upgrade of %@ failed: %@", region.code, error.localizedDescription)
            }
        }
    }

    func disconnect() {
        wantConnected = false
        Task { await teardown(reason: nil) }
    }

    /// Release this device's lease, drop the tunnel, then follow the VM to deallocation
    /// so the session's VM time is known.
    private func teardown(reason: String?, waitForStop: Bool = true) async {
        guard let azure, let region = regions.first(where: { $0.code == current?.region }) ?? self.region else { return }
        phase = .disconnecting("Disconnecting…")
        renewTask?.cancel(); renewTask = nil
        monitorTask?.cancel(); monitorTask = nil
        let final = await Tunnel.status()
        await Tunnel.down()
        tunnel = TunnelStatus(up: false)
        egress = nil
        try? await azure.deleteLease(region)

        if var record = current {
            record.disconnectedAt = Date()
            record.rxBytes = max(record.rxBytes, final.rx ?? 0)
            record.txBytes = max(record.txBytes, final.tx ?? 0)
            await price(&record)
            store.upsert(record)
            current = nil
            lastCompleted = record
            if waitForStop { Task { await self.followShutdown(record, region) } }
        }
        phase = reason.map { .failed($0) } ?? .idle
    }

    /// The VM agent deallocates ~1 minute after the last lease disappears. Record when that happens.
    private func followShutdown(_ start: SessionRecord, _ region: RegionConfig) async {
        guard let azure else { return }
        var record = start
        for _ in 0..<60 {
            try? await Task.sleep(for: .seconds(10))
            guard let state = try? await azure.powerState(region) else { continue }
            regionStates[region.code] = state
            if state == "deallocated" {
                record.vmStoppedAt = Date()
                break
            }
            if current?.region == region.code { break }  // reconnected, the VM keeps running
        }
        await price(&record)
        store.upsert(record)
        if lastCompleted?.id == record.id { lastCompleted = record }
        await refreshCosts()
    }

    private func price(_ record: inout SessionRecord) async {
        guard let azure, let region = regions.first(where: { $0.code == record.region }) else { return }
        let currency = spend?.currency ?? "INR"
        if prices[region.code] == nil {
            prices[region.code] = try? await azure.prices(for: region, currency: currency)
        }
        guard let p = prices[region.code] else { return }
        CostModel.price(&record, prices: p, monthGBBefore: store.monthEgressGB(excluding: record.id))
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
        let ws = NSWorkspace.shared.notificationCenter
        ws.addObserver(forName: NSWorkspace.willSleepNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in
                guard self.phase == .connected else { return }
                let resume = self.wantConnected
                await self.teardown(reason: nil, waitForStop: false)
                self.wantConnected = resume
            }
        }
        ws.addObserver(forName: NSWorkspace.didWakeNotification, object: nil, queue: .main) { _ in
            Task { @MainActor in
                if !self.wantConnected { await Tunnel.down() }
                if self.wantConnected {
                    try? await Task.sleep(for: .seconds(5))
                    self.connect()
                }
            }
        }
    }

    /// Called on quit: release the lease and drop the tunnel so the server can deallocate.
    func shutdownForQuit() async {
        wantConnected = false
        if phase == .connected || phase.busy || tunnel.up {
            await teardown(reason: nil, waitForStop: false)
        }
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
        guard let azure else { return }
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
    func createExitInstaller(regionCode: String) async throws -> ExitInstaller {
        guard let azure, let region = regions.first(where: { $0.code == regionCode }) else {
            throw msg("Unknown relay region")
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
        let placeholder = HomeExit(id: id, name: "New home PC", country: "XX", region: regionCode,
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

        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        let file = downloads.appendingPathComponent("LeapVPN-HomeExit-\(id).cmd")
        try Data(HomeExitSetup.clickToRun(personalized: script, invite: invite).utf8).write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        pendingExits.append(placeholder)
        watchPendingExits()
        return ExitInstaller(command: HomeExitSetup.command(installerURL: get.url), file: file, expires: put.expires)
    }

    private static func invitePath(_ id: String) -> String { "exits/_invites/\(id).ps1" }
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
        try? await azure.deleteExit(exit)
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
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(120))
                guard let self, let azure = self.azure else { continue }
                for r in self.regions where self.current?.region != r.code && !self.phase.busy {
                    guard (try? await azure.powerState(r)) == "running" else { continue }
                    guard let age = try? await azure.newestLeaseAge(r) else {
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

    /// Opt-in scripting for testing: `defaults write com.viki.vikivpn AllowURLControl -bool true`,
    /// then `open "vikivpn://connect?region=in"` / `open vikivpn://disconnect`. Only works once set up.
    func handle(url: URL) {
        guard UserDefaults.standard.bool(forKey: "AllowURLControl"), url.scheme == "vikivpn" else { return }
        if url.host == "snapshot" { snapshot(); return }
        if url.host == "history" { requestedSheet = .history; return }
        let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        if url.host == "setup", step == .locations || step == .done,
           let codes = q.first(where: { $0.name == "regions" })?.value?.split(separator: ",").map(String.init) {
            build(RegionChoice.all.filter { codes.contains($0.code) },
                  relayOnly: q.contains { $0.name == "relayOnly" }, then: step == .done ? .done : nil)
            return
        }
        if url.host == "finish", step == .homePCs { finishOnboarding(); return }
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

    /// Test aid: renders the main window into snapshot.png (needs no screen-recording permission).
    private func snapshot() {
        guard let main = NSApp.windows.first(where: { $0.canBecomeMain && $0.isVisible }),
              case let win = main.attachedSheet ?? main,
              let view = win.contentView?.superview ?? win.contentView,
              let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?
            .write(to: AppConfig.supportDir.appendingPathComponent("snapshot.png"))
    }

    private func writeStatus() {
        var out: [String: Any] = ["phase": phase.label, "connected": phase == .connected,
                                  "region": current?.region ?? selected, "at": ISO8601DateFormatter().string(from: Date())]
        if let e = egress { out["egressIP"] = e.ip; out["egressCountry"] = e.country; out["egressOrg"] = e.org ?? "" }
        out["server"] = selected
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
        NSError(domain: "VikiVPN", code: 1, userInfo: [NSLocalizedDescriptionKey: s])
    }
}
