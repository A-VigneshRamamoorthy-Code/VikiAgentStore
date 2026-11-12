import Foundation

struct SessionRecord: Codable, Identifiable, Hashable {
    var id = UUID()
    var region: String
    var regionName: String
    var flag: String
    var connectedAt: Date
    var disconnectedAt: Date?
    /// Last time the app saw this session's tunnel up (used to close sessions after a crash).
    var lastSeenAt: Date?
    /// When this device asked Azure to start the VM (nil if it was already running).
    var vmStartRequestedAt: Date?
    /// When the VM was seen deallocated after this session (nil if another device kept it up).
    var vmStoppedAt: Date?
    var rxBytes: Int64 = 0
    var txBytes: Int64 = 0
    var egressIP: String?
    var egressCountry: String?
    /// Home exit used for this session, if any.
    var via: String?
    var vmCost: Double = 0
    var egressCost: Double = 0
    var currency: String = "INR"
    var vmPerHour: Double = 0
    var egressPerGB: Double = 0

    var total: Double { vmCost + egressCost }
    var duration: TimeInterval { (disconnectedAt ?? Date()).timeIntervalSince(connectedAt) }
    var dataGB: Double { Double(rxBytes + txBytes) / 1_000_000_000 }

    /// Seconds of VM compute attributable to this session.
    var vmSeconds: TimeInterval {
        let from = vmStartRequestedAt ?? connectedAt
        let to = vmStoppedAt ?? disconnectedAt ?? Date()
        return max(0, to.timeIntervalSince(from))
    }
}

/// Session history in ~/Library/Application Support/VikiVPN/history.json.
@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var sessions: [SessionRecord] = []
    private let url = AppConfig.supportDir.appendingPathComponent("history.json")

    init() {
        if let data = try? Data(contentsOf: url),
           let decoded = try? JSONDecoder.iso.decode([SessionRecord].self, from: data) {
            sessions = decoded
        }
    }

    func upsert(_ record: SessionRecord) {
        if let i = sessions.firstIndex(where: { $0.id == record.id }) {
            sessions[i] = record
        } else {
            sessions.insert(record, at: 0)
        }
        save()
    }

    /// Internet egress (GB) used earlier in the same calendar month as `record`, so the free
    /// allowance is consumed in order and repricing an old session never double-counts it.
    func monthEgressGB(before record: SessionRecord) -> Double {
        let start = Calendar.current.dateInterval(of: .month, for: record.connectedAt)?.start ?? record.connectedAt
        return sessions.filter {
            $0.id != record.id && $0.connectedAt >= start
                && ($0.connectedAt, $0.id.uuidString) < (record.connectedAt, record.id.uuidString)
        }.reduce(0) { $0 + $1.dataGB }
    }

    func totals(since: Date) -> (cost: Double, hours: Double, gb: Double) {
        sessions.filter { $0.connectedAt >= since }.reduce((0, 0, 0)) {
            ($0.0 + $1.total, $0.1 + $1.vmSeconds / 3600, $0.2 + $1.dataGB)
        }
    }

    private func save() {
        try? FileManager.default.createDirectory(at: AppConfig.supportDir, withIntermediateDirectories: true)
        if let data = try? JSONEncoder.iso.encode(sessions) { try? data.write(to: url, options: .atomic) }
    }
}

enum CostModel {
    /// Estimate = VM price × attributable run time + internet egress beyond the free monthly allowance.
    static func price(_ s: inout SessionRecord, prices: Prices, monthGBBefore: Double) {
        s.vmPerHour = prices.vmPerHour
        s.egressPerGB = prices.egressPerGB
        s.currency = prices.currency
        s.vmCost = s.vmSeconds / 3600 * prices.vmPerHour
        let after = monthGBBefore + s.dataGB
        let billable = max(0, after - prices.freeEgressGB) - max(0, monthGBBefore - prices.freeEgressGB)
        s.egressCost = billable * prices.egressPerGB
    }
}

extension JSONDecoder {
    static let iso: JSONDecoder = { let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601; return d }()
}

extension JSONEncoder {
    static let iso: JSONEncoder = {
        let e = JSONEncoder()
        e.dateEncodingStrategy = .iso8601
        e.outputFormatting = [.prettyPrinted, .sortedKeys]
        return e
    }()
}

func formatMoney(_ amount: Double, _ currency: String) -> String {
    let f = NumberFormatter()
    f.numberStyle = .currency
    f.currencyCode = currency
    f.maximumFractionDigits = amount < 10 ? 2 : 0
    return f.string(from: NSNumber(value: amount)) ?? String(format: "%.2f %@", amount, currency)
}

func formatBytes(_ bytes: Int64) -> String {
    ByteCountFormatter.string(fromByteCount: bytes, countStyle: .decimal)
}

func formatDuration(_ t: TimeInterval) -> String {
    let s = Int(t)
    return s >= 3600 ? String(format: "%dh %02dm", s / 3600, (s % 3600) / 60)
                     : String(format: "%dm %02ds", s / 60, s % 60)
}
