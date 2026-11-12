import CryptoKit
import Foundation

enum AzureError: LocalizedError {
    case http(Int, String)
    case notConfigured
    var errorDescription: String? {
        switch self {
        case .http(let code, let body): return "Azure HTTP \(code): \(Self.message(body))"
        case .notConfigured: return "Finish setup first."
        }
    }
    static func message(_ body: String) -> String {
        if let data = body.data(using: .utf8),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let err = json["error"] as? [String: Any], let msg = err["message"] as? String { return String(msg.prefix(300)) }
        return String(body.prefix(300))
    }
    var status: Int { if case .http(let c, _) = self { return c }; return 0 }
}

struct Money: Codable, Hashable {
    var amount: Double
    var currency: String
}

struct Prices: Codable {
    var vmPerHour: Double
    var egressPerGB: Double      // first paid tier, after the monthly free allowance
    var freeEgressGB: Double
    var currency: String
}

/// Where the app is working: the signed-in user's directory and subscription.
struct AzureContext: Hashable {
    var tenantId: String
    var subscriptionId: String
    var storageAccount: String?
    var device: String?
}

struct BlobResponse {
    var status: Int
    var data: Data
    var etag: String?
}

/// Azure control-plane calls the app needs, made with the signed-in user's own
/// delegated tokens. Plain REST so the same calls port directly to iOS and Android.
actor AzureClient {
    private(set) var ctx: AzureContext
    private let auth: MicrosoftAuth
    private let session: URLSession
    private let api = "2024-07-01"

    init(_ ctx: AzureContext, auth: MicrosoftAuth = .shared) {
        self.ctx = ctx
        self.auth = auth
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 30
        session = URLSession(configuration: cfg)
    }

    func update(_ ctx: AzureContext) { self.ctx = ctx }

    private var storageAccount: String { get throws { guard let a = ctx.storageAccount else { throw AzureError.notConfigured }; return a } }
    private var device: String { get throws { guard let d = ctx.device else { throw AzureError.notConfigured }; return d } }

    /// URLSession with retries for transient network failures (Azure calls are idempotent).
    private func fetch(_ req: URLRequest) async throws -> (Data, URLResponse) {
        try await URLSession.retrying(req, on: session)
    }

    @discardableResult
    private func send(_ req: URLRequest, accept: Set<Int> = [200, 201, 202, 204]) async throws -> [String: Any] {
        let (data, resp) = try await fetch(req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard accept.contains(code) else { throw AzureError.http(code, String(decoding: data, as: UTF8.self)) }
        if data.isEmpty { return [:] }
        return (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    /// ARM call. `path` is either a full URL or a path below management.azure.com.
    @discardableResult
    func arm(_ method: String, _ path: String, body: [String: Any]? = nil,
             accept: Set<Int> = [200, 201, 202, 204]) async throws -> [String: Any] {
        let url = path.hasPrefix("https://") ? path : "https://management.azure.com\(path)"
        var req = URLRequest(url: URL(string: url)!)
        req.httpMethod = method
        req.setValue("Bearer \(try await auth.token(MicrosoftAuth.arm, tenant: ctx.tenantId))", forHTTPHeaderField: "Authorization")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        } else if method == "POST" {
            req.httpBody = Data()
        }
        return try await send(req, accept: accept)
    }

    /// ARM call returning headers too (for long-running operations).
    func armRaw(_ method: String, _ path: String, body: Data? = nil, contentType: String = "application/json")
        async throws -> (status: Int, data: Data, headers: [String: String]) {
        let url = path.hasPrefix("https://") ? path : "https://management.azure.com\(path)"
        var req = URLRequest(url: URL(string: url)!)
        req.httpMethod = method
        req.setValue("Bearer \(try await auth.token(MicrosoftAuth.arm, tenant: ctx.tenantId))", forHTTPHeaderField: "Authorization")
        if let body { req.setValue(contentType, forHTTPHeaderField: "Content-Type"); req.httpBody = body }
        else if method == "POST" { req.httpBody = Data() }
        let (data, resp) = try await fetch(req)
        let http = resp as? HTTPURLResponse
        var headers: [String: String] = [:]
        for (k, v) in http?.allHeaderFields ?? [:] { headers[String(describing: k).lowercased()] = String(describing: v) }
        return (http?.statusCode ?? 0, data, headers)
    }

    /// Raw blob call on the deployment storage account (or `account`).
    func blobRaw(_ method: String, _ path: String, body: Data? = nil, headers: [String: String] = [:],
                 account: String? = nil) async throws -> BlobResponse {
        let acct = try account ?? storageAccount
        var req = URLRequest(url: URL(string: "https://\(acct).blob.core.windows.net/\(path)")!)
        req.httpMethod = method
        req.setValue("Bearer \(try await auth.token(MicrosoftAuth.storage, tenant: ctx.tenantId))", forHTTPHeaderField: "Authorization")
        req.setValue("2021-08-06", forHTTPHeaderField: "x-ms-version")
        if method == "PUT" {
            req.setValue("BlockBlob", forHTTPHeaderField: "x-ms-blob-type")
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = body ?? Data()
        }
        for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        let (data, resp) = try await fetch(req)
        let http = resp as? HTTPURLResponse
        return BlobResponse(status: http?.statusCode ?? 0, data: data,
                            etag: http?.value(forHTTPHeaderField: "ETag"))
    }

    @discardableResult
    private func blob(_ method: String, _ path: String, body: Data? = nil,
                      headers: [String: String] = [:]) async throws -> Data {
        let r = try await blobRaw(method, path, body: body, headers: headers)
        guard [200, 201, 202, 404].contains(r.status) else {
            throw AzureError.http(r.status, String(decoding: r.data, as: UTF8.self))
        }
        return r.status == 404 ? Data() : r.data
    }

    // MARK: VM

    /// "running", "starting", "stopping", "stopped", "deallocating", "deallocated"
    func powerState(_ region: RegionConfig) async throws -> String {
        let view = try await arm("GET", "\(region.vmId)/instanceView?api-version=\(api)")
        let statuses = view["statuses"] as? [[String: Any]] ?? []
        for s in statuses {
            if let code = s["code"] as? String, code.hasPrefix("PowerState/") {
                return String(code.dropFirst("PowerState/".count))
            }
        }
        return "unknown"
    }

    func start(_ region: RegionConfig) async throws {
        try await arm("POST", "\(region.vmId)/start?api-version=\(api)")
    }

    // MARK: leases

    func deallocate(_ region: RegionConfig) async throws {
        try await arm("POST", "\(region.vmId)/deallocate?api-version=\(api)")
    }

    /// Seconds since the freshest lease on a region was renewed (nil: no lease at all).
    func newestLeaseAge(_ region: RegionConfig) async throws -> TimeInterval? {
        let r = try await blobRaw("GET", "leases?restype=container&comp=list&prefix=\(region.code)/")
        guard r.status == 200 else { throw AzureError.http(r.status, String(decoding: r.data, as: UTF8.self)) }
        let xml = String(decoding: r.data, as: UTF8.self)
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        let dates = xml.components(separatedBy: "<Last-Modified>").dropFirst()
            .compactMap { $0.components(separatedBy: "</Last-Modified>").first }.compactMap { fmt.date(from: $0) }
        return dates.max().map { Date().timeIntervalSince($0) }
    }

    /// `exit` asks the relay VM to send this device's traffic through that home exit.
    func putLease(_ region: RegionConfig, exit: String? = nil) async throws {
        let body = try JSONSerialization.data(withJSONObject: [
            "device": try device, "at": ISO8601DateFormatter().string(from: Date())])
        try await blob("PUT", "leases/\(region.code)/\(try device)", body: body,
                       headers: exit.map { ["x-ms-meta-exit": $0] } ?? [:])
    }

    // MARK: home exits

    private func list(_ prefix: String) async throws -> [String] {
        let enc = prefix.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? prefix
        let xml = String(decoding: try await blob("GET", "exits?restype=container&comp=list&prefix=\(enc)"), as: UTF8.self)
        return xml.components(separatedBy: "<Name>").dropFirst()
            .compactMap { $0.components(separatedBy: "</Name>").first }
            .filter { $0.hasSuffix(".json") }
    }

    private func readExits(_ names: [String]) async throws -> [HomeExit] {
        var out: [HomeExit] = []
        for name in names {
            let data = try await blob("GET", "exits/\(name)")
            if let exit = try? JSONDecoder.iso.decode(HomeExit.self, from: data) { out.append(exit) }
        }
        return out.sorted { $0.createdAt < $1.createdAt }
    }

    /// Approved exits (what the relays use).
    func listExits() async throws -> [HomeExit] {
        try await readExits(try await list("").filter { !$0.hasPrefix("_") })
    }

    /// Slots reserved by this user that no PC has claimed yet.
    func listPendingExits() async throws -> [HomeExit] {
        try await readExits(try await list("_pending/"))
    }

    func putExit(_ exit: HomeExit) async throws {
        try await blob("PUT", "exits/\(exit.region)/\(exit.id).json", body: try JSONEncoder.iso.encode(exit))
    }

    func putPendingExit(_ exit: HomeExit) async throws {
        try await blob("PUT", "exits/_pending/\(exit.id).json", body: try JSONEncoder.iso.encode(exit))
    }

    /// Promotes every enrollment that matches a reserved slot; drops the rest.
    /// Returns the newly approved exits.
    func approveEnrollments() async throws -> [HomeExit] {
        let pending = Dictionary(try await listPendingExits().map { ($0.id, $0) }) { a, _ in a }
        var approved: [HomeExit] = []
        for name in try await list("_enroll/") {
            let id = String(name.dropFirst("_enroll/".count).dropLast(".json".count))
            let data = try await blob("GET", "exits/\(name)")
            defer { Task { try? await self.deleteBlob("exits/\(name)") } }
            guard let slot = pending[id], let pc = try? JSONDecoder.iso.decode(HomeExit.self, from: data),
                  let key = pc.sshPublicKey, key.hasPrefix("ssh-ed25519 "), key.count < 200 else { continue }
            var exit = slot
            exit.sshPublicKey = key
            exit.name = String(pc.name.prefix(40))
            exit.country = String(pc.country.prefix(2)).uppercased()
            exit.city = pc.city.map { String($0.prefix(60)) }
            exit.isp = pc.isp.map { String($0.prefix(80)) }
            exit.host = pc.host.map { String($0.prefix(40)) }
            exit.loc = pc.loc.flatMap { GeoPoint($0) != nil ? $0 : nil }
            try await putExit(exit)
            try? await deleteBlob("exits/_pending/\(id).json")
            approved.append(exit)
        }
        return approved
    }

    /// A SAS URL for one blob, signed with a user-delegation key (the storage account
    /// has shared keys disabled). `cw` lets a home PC register itself and `r` lets it
    /// fetch its installer, without any Azure credential of its own.
    func blobSASURL(_ path: String, permissions sp: String, validFor: TimeInterval) async throws -> (url: String, expires: Date) {
        let fmt = ISO8601DateFormatter()
        let start = Date().addingTimeInterval(-300), expiry = Date().addingTimeInterval(validFor)
        let account = try storageAccount
        var req = URLRequest(url: URL(string: "https://\(account).blob.core.windows.net/?restype=service&comp=userdelegationkey")!)
        req.httpMethod = "POST"
        req.setValue("Bearer \(try await auth.token(MicrosoftAuth.storage, tenant: ctx.tenantId))", forHTTPHeaderField: "Authorization")
        req.setValue("2022-11-02", forHTTPHeaderField: "x-ms-version")
        req.setValue("application/xml", forHTTPHeaderField: "Content-Type")
        req.httpBody = Data("<?xml version=\"1.0\" encoding=\"utf-8\"?><KeyInfo><Start>\(fmt.string(from: start))</Start><Expiry>\(fmt.string(from: expiry))</Expiry></KeyInfo>".utf8)
        let (data, resp) = try await fetch(req)
        let xml = String(decoding: data, as: UTF8.self)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
            throw AzureError.http((resp as? HTTPURLResponse)?.statusCode ?? 0,
                                  "user delegation key: \(xml)")
        }
        func tag(_ t: String) -> String {
            xml.components(separatedBy: "<\(t)>").dropFirst().first?.components(separatedBy: "</\(t)>").first ?? ""
        }
        guard let key = Data(base64Encoded: tag("Value")) else { throw AzureError.http(0, "bad delegation key") }
        let sv = "2022-11-02", st = fmt.string(from: start), se = fmt.string(from: expiry)
        let (oid, tid, skt, ske, sks, skv) = (tag("SignedOid"), tag("SignedTid"), tag("SignedStart"),
                                              tag("SignedExpiry"), tag("SignedService"), tag("SignedVersion"))
        let toSign = [sp, st, se, "/blob/\(account)/\(path)", oid, tid, skt, ske, sks, skv,
                      "", "", "", "", "https", sv, "b", "", "", "", "", "", "", ""].joined(separator: "\n")
        let sig = Data(HMAC<SHA256>.authenticationCode(for: Data(toSign.utf8), using: SymmetricKey(data: key)))
            .base64EncodedString()
        let enc: (String) -> String = {
            $0.addingPercentEncoding(withAllowedCharacters: CharacterSet(charactersIn:
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")) ?? $0
        }
        let query = [("sv", sv), ("sr", "b"), ("sp", sp), ("st", st), ("se", se), ("skoid", oid),
                     ("sktid", tid), ("skt", skt), ("ske", ske), ("sks", sks), ("skv", skv),
                     ("spr", "https"), ("sig", sig)].map { "\($0.0)=\(enc($0.1))" }.joined(separator: "&")
        return ("https://\(account).blob.core.windows.net/\(path)?\(query)", expiry)
    }

    func putText(_ path: String, _ text: String) async throws {
        try await blob("PUT", path, body: Data(text.utf8), headers: ["Content-Type": "text/plain; charset=utf-8"])
    }

    func deleteBlob(_ path: String) async throws {
        try await blob("DELETE", path)
    }

    func deleteExit(_ exit: HomeExit) async throws {
        try await blob("DELETE", "exits/\(exit.region)/\(exit.id).json")
        try await blob("DELETE", "exits/_pending/\(exit.id).json")
        try await blob("DELETE", "exits/_enroll/\(exit.id).json")
    }

    func deleteLease(_ region: RegionConfig) async throws {
        try await blob("DELETE", "leases/\(region.code)/\(try device)")
    }

    // MARK: cost

    private func costQuery(grouping: [[String: String]]? = nil, timeframe: String = "BillingMonthToDate",
                           granularity: String = "None") async throws -> (columns: [String], rows: [[Any]]) {
        var dataset: [String: Any] = [
            "granularity": granularity,
            "aggregation": ["totalCost": ["name": "Cost", "function": "Sum"]],
        ]
        if let grouping { dataset["grouping"] = grouping }
        let json = try await arm("POST",
            "/subscriptions/\(ctx.subscriptionId)/providers/Microsoft.CostManagement/query?api-version=2023-11-01",
            body: ["type": "ActualCost", "timeframe": timeframe, "dataset": dataset])
        let props = json["properties"] as? [String: Any] ?? [:]
        let cols = (props["columns"] as? [[String: Any]] ?? []).compactMap { $0["name"] as? String }
        return (cols, props["rows"] as? [[Any]] ?? [])
    }

    /// Billing-period-to-date spend across the whole subscription.
    func periodToDateSpend() async throws -> Money {
        let (_, rows) = try await costQuery()
        let amount = (rows.first?.first as? Double) ?? 0
        let currency = (rows.first?.last as? String) ?? "INR"
        return Money(amount: amount, currency: currency)
    }

    /// Billing-period-to-date actual cost per VikiVPN resource group (lags several hours).
    func vpnCostByRegion() async throws -> [String: Double] {
        let (cols, rows) = try await costQuery(grouping: [["type": "Dimension", "name": "ResourceGroupName"]])
        guard let ci = cols.firstIndex(of: "Cost"), let gi = cols.firstIndex(of: "ResourceGroupName") else { return [:] }
        var out: [String: Double] = [:]
        for row in rows {
            guard let rg = (row[gi] as? String)?.lowercased(), rg.hasPrefix("vikivpn") else { continue }
            out[rg, default: 0] += (row[ci] as? Double) ?? 0
        }
        return out
    }

    /// Public retail prices (no auth) for the VM size and internet egress in a region.
    /// First successful deallocation of the region's VM after `after`, from the ARM activity log.
    func deallocatedAt(_ region: RegionConfig, after: Date) async throws -> Date? {
        let sub = region.vmId.components(separatedBy: "/").prefix(3).joined(separator: "/")
        let iso = ISO8601DateFormatter()
        let filter = "eventTimestamp ge '\(iso.string(from: after))' and resourceUri eq '\(region.vmId)'"
        var c = URLComponents(string: "https://management.azure.com\(sub)/providers/Microsoft.Insights/eventtypes/management/values")!
        c.queryItems = [URLQueryItem(name: "api-version", value: "2015-04-01"),
                        URLQueryItem(name: "$filter", value: filter),
                        URLQueryItem(name: "$select", value: "eventTimestamp,operationName,status")]
        let json = try await arm("GET", c.url!.absoluteString)
        let frac = ISO8601DateFormatter(); frac.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return (json["value"] as? [[String: Any]] ?? []).compactMap { e -> Date? in
            guard (e["operationName"] as? [String: Any])?["value"] as? String == "Microsoft.Compute/virtualMachines/deallocate/action",
                  (e["status"] as? [String: Any])?["value"] as? String == "Succeeded",
                  let t = e["eventTimestamp"] as? String else { return nil }
            return frac.date(from: t) ?? iso.date(from: t)
        }.min()
    }

    func prices(for region: RegionConfig, currency: String) async throws -> Prices {
        func items(_ filter: String) async throws -> [[String: Any]] {
            var comps = URLComponents(string: "https://prices.azure.com/api/retail/prices")!
            comps.queryItems = [.init(name: "currencyCode", value: currency), .init(name: "$filter", value: filter)]
            let json = try await send(URLRequest(url: comps.url!))
            return json["Items"] as? [[String: Any]] ?? []
        }
        let vmItems = try await items("serviceName eq 'Virtual Machines' and armRegionName eq '\(region.location)' and armSkuName eq '\(region.size)' and priceType eq 'Consumption'")
        let vm = vmItems.first {
            let product = $0["productName"] as? String ?? ""
            let sku = $0["skuName"] as? String ?? ""
            return !product.contains("Windows") && !product.contains("Cloud Services")
                && !sku.contains("Spot") && !sku.contains("Low Priority")
        }
        let bw = try await items("serviceName eq 'Bandwidth' and armRegionName eq '\(region.location)' and meterName eq 'Standard Data Transfer Out' and priceType eq 'Consumption'")
            .filter { ($0["productName"] as? String ?? "").contains("MGN") }
            .sorted { ($0["tierMinimumUnits"] as? Double ?? 0) < ($1["tierMinimumUnits"] as? Double ?? 0) }
        let paid = bw.first { ($0["retailPrice"] as? Double ?? 0) > 0 }
        return Prices(vmPerHour: vm?["retailPrice"] as? Double ?? 0,
                      egressPerGB: paid?["retailPrice"] as? Double ?? 0,
                      freeEgressGB: paid?["tierMinimumUnits"] as? Double ?? 100,
                      currency: currency)
    }

    /// USD → billing currency, for showing the Visual Studio credit ($150/month) in local currency.
    func usdRate(to currency: String) async -> Double? {
        if currency == "USD" { return 1 }
        guard let json = try? await send(URLRequest(url: URL(string: "https://open.er-api.com/v6/latest/USD")!)),
              let rates = json["rates"] as? [String: Any] else { return nil }
        return rates[currency] as? Double
    }
}

extension URLSession {
    static let transient: Set<URLError.Code> = [.timedOut, .networkConnectionLost, .cannotConnectToHost,
                                                 .notConnectedToInternet, .dnsLookupFailed, .cannotFindHost]

    /// `data(for:)` with backoff retries for transient network failures.
    static func retrying(_ req: URLRequest, on session: URLSession, attempts: Int = 4) async throws -> (Data, URLResponse) {
        var delay: UInt64 = 1
        var attempt = 1
        while true {
            do { return try await session.data(for: req) }
            catch let e as URLError where transient.contains(e.code) && attempt < attempts {
                NSLog("VikiVPN: %@ %@ failed (%@), retry %d", req.httpMethod ?? "GET",
                      req.url?.host ?? "", e.localizedDescription, attempt)
                try await Task.sleep(nanoseconds: delay * 1_000_000_000)
                delay *= 2
                attempt += 1
            }
        }
    }
}
