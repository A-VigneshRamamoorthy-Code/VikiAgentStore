#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

struct HistorySheet: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var refreshing = Box(false)

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SheetHeader(icon: "chart.bar.xaxis", title: "Usage", tint: SheetTheme.accent, trailing: AnyView(refresh),
                        subtitle: Date().formatted(.dateTime.month(.wide).year()))
            ScrollView {
                VStack(spacing: 18) {
                    StatTiles()
                    #if os(iOS)
                    Card(title: "Last 14 days", trailing: DailyChart.total(vpn)) { DailyChart() }
                    Card(title: "By location") { LocationBreakdown() }
                    #else
                    HStack(alignment: .top, spacing: 14) {
                        Card(title: "Last 14 days", trailing: DailyChart.total(vpn)) { DailyChart() }
                        Card(title: "By location") { LocationBreakdown() }.frame(width: 250)
                    }
                    #endif
                    Card(title: "Sessions", padding: 6) { SessionList() }
                    Label("Estimates from Azure retail prices. Billed totals lag a few hours.", systemImage: "info.circle")
                        .font(.caption2).foregroundStyle(.tertiary).frame(maxWidth: .infinity)
                }
                .padding(.bottom, 20)
            }
            .scrollIndicators(.hidden)
        }
        .sheetChrome(width: 720, height: 640)
    }

    private var refresh: some View {
        CircleButton(icon: "arrow.clockwise", help: "Refresh") {
            guard !refreshing.v else { return }
            refreshing.v = true
            Task { await vpn.refreshCosts(); refreshing.v = false }
        }
        .opacity(refreshing.v ? 0.5 : 1)
        .disabled(!vpn.hasAzure || refreshing.v)
    }
}

/// This month at a glance: spend (with the remaining credit as a ring) and three small tiles.
struct StatTiles: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let month = Calendar.current.dateInterval(of: .month, for: Date())?.start ?? Date()
        let t = vpn.store.totals(since: month)
        let count = vpn.store.sessions.filter { $0.connectedAt >= month }.count
        VStack(spacing: 10) {
            hero(t.cost)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 98), spacing: 10)], spacing: 10) {
                tile("clock.fill", "Server time", t.hours < 10 ? String(format: "%.1f h", t.hours) : "\(Int(t.hours)) h", Atlas.amber)
                tile("arrow.up.arrow.down", "Data", formatBytes(Int64(t.gb * 1_000_000_000)), Atlas.blue)
                tile("bolt.horizontal.fill", "Sessions", "\(count)", .purple)
            }
        }
    }

    private func hero(_ cost: Double) -> some View {
        HStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("This month").font(.subheadline.weight(.medium)).foregroundStyle(.secondary)
                Text(formatMoney(cost, vpn.usageCurrency))
                    .font(.system(size: 34, weight: .bold, design: .rounded)).monospacedDigit()
                    .lineLimit(1).minimumScaleFactor(0.6)
                    .contentTransition(.numericText())
                if let spend = vpn.spend {
                    Text("Azure billed \(formatMoney(spend.amount, spend.currency))")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            if let spend = vpn.spend, let credit = vpn.monthlyCredit, credit > 0 {
                let left = max(0, credit - spend.amount)
                UsageCreditRing(fraction: left / credit, label: compact(left, spend.currency))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheetSurface(22, tint: SheetTheme.mint)
    }

    private func tile(_ icon: String, _ title: String, _ value: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: icon).font(.system(size: 12, weight: .semibold)).foregroundStyle(tint)
                .frame(width: 26, height: 26).background(Circle().fill(tint.opacity(0.14)))
            VStack(alignment: .leading, spacing: 1) {
                Text(value).font(.system(.title3, design: .rounded).weight(.bold)).monospacedDigit()
                    .lineLimit(1).minimumScaleFactor(0.6)
                Text(title).font(.caption).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .sheetSurface(18)
    }

    private func compact(_ amount: Double, _ currency: String) -> String {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = currency
        f.maximumFractionDigits = 0
        if amount >= 10_000 { return (f.string(from: NSNumber(value: amount / 1000)) ?? "") + "k" }
        return f.string(from: NSNumber(value: amount)) ?? ""
    }
}

/// Credit left this month as a ring.
struct UsageCreditRing: View {
    let fraction: Double
    let label: String

    var body: some View {
        ZStack {
            Circle().stroke(SheetTheme.mint.opacity(0.15), lineWidth: 7)
            Circle().trim(from: 0, to: max(0.02, min(1, fraction)))
                .stroke(AngularGradient(colors: [SheetTheme.accent, SheetTheme.mint], center: .center),
                        style: StrokeStyle(lineWidth: 7, lineCap: .round))
                .rotationEffect(.degrees(-90))
            VStack(spacing: 0) {
                Text(label).font(.system(size: 13, weight: .bold, design: .rounded)).monospacedDigit()
                    .lineLimit(1).minimumScaleFactor(0.5)
                Text("left").font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary)
            }
            .padding(10)
        }
        .frame(width: 76, height: 76)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Credit left \(label)")
    }
}

struct DailyChart: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var picked = Box<Date?>(nil)

    struct Day: Identifiable { let id: Date; let cost: Double }

    static func days(_ vpn: VPNController) -> [Day] {
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        return (0..<14).reversed().compactMap { i in
            guard let d = cal.date(byAdding: .day, value: -i, to: today) else { return nil }
            let cost = vpn.store.sessions.filter { cal.isDate($0.connectedAt, inSameDayAs: d) }.map(\.total).reduce(0, +)
            return Day(id: d, cost: cost)
        }
    }

    static func total(_ vpn: VPNController) -> String {
        formatMoney(days(vpn).map(\.cost).reduce(0, +), vpn.usageCurrency)
    }

    var body: some View {
        let days = Self.days(vpn)
        let sel = picked.v.flatMap { p in days.first { Calendar.current.isDate($0.id, inSameDayAs: p) } }
        Chart(days) { d in
            BarMark(x: .value("Day", d.id, unit: .day), y: .value("Cost", d.cost), width: .ratio(0.62))
                .foregroundStyle(LinearGradient(colors: [SheetTheme.mint, SheetTheme.accent], startPoint: .top, endPoint: .bottom))
                .cornerRadius(5)
                .opacity(sel == nil || sel?.id == d.id ? 1 : 0.35)
            if let sel, sel.id == d.id {
                RuleMark(x: .value("Day", d.id, unit: .day))
                    .foregroundStyle(.secondary.opacity(0.25))
                    .annotation(position: .top, overflowResolution: .init(x: .fit(to: .chart), y: .disabled)) {
                        VStack(spacing: 1) {
                            Text(formatMoney(d.cost, vpn.usageCurrency)).font(.caption.weight(.bold)).monospacedDigit()
                            Text(d.id.formatted(.dateTime.day().month(.abbreviated))).font(.caption2).foregroundStyle(.secondary)
                        }
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .glass(10)
                    }
            }
        }
        .chartXSelection(value: Binding(get: { picked.v }, set: { picked.v = $0 }))
        .chartXAxis {
            AxisMarks(values: .stride(by: .day, count: Self.labelEvery)) { _ in
                AxisValueLabel(format: .dateTime.day().month(.abbreviated), centered: true)
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { v in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [3, 3])).foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel { if let n = v.as(Double.self) { Text(formatMoney(n, vpn.usageCurrency)).font(.caption2) } }
            }
        }
        .frame(height: Self.height)
        .overlay {
            if days.allSatisfy({ $0.cost == 0 }) {
                Text("No usage in the last 14 days").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    #if os(iOS)
    static let labelEvery = 4
    static let height: CGFloat = 150
    #else
    static let labelEvery = 3
    static let height: CGFloat = 170
    #endif
}

struct LocationBreakdown: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let groups = Dictionary(grouping: vpn.store.sessions) { $0.region }
            .compactMap { code, list -> (code: String, name: String, country: String?, cost: Double, count: Int)? in
                guard let s = list.first else { return nil }
                return (code, s.regionName, vpn.sessionCountry(s), list.map(\.total).reduce(0, +), list.count)
            }
            .sorted { $0.cost > $1.cost }
        let top = groups.first?.cost ?? 0
        VStack(alignment: .leading, spacing: 12) {
            ForEach(groups.prefix(6), id: \.code) { g in
                HStack(spacing: 10) {
                    FlagBadge(country: g.country, size: 26)
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(g.name).font(.callout.weight(.medium)).lineLimit(1)
                            Spacer(minLength: 6)
                            Text(formatMoney(g.cost, vpn.usageCurrency)).font(.callout.weight(.semibold)).monospacedDigit()
                        }
                        GeometryReader { geo in
                            Capsule().fill(SheetTheme.mint.opacity(0.12))
                                .overlay(alignment: .leading) {
                                    Capsule().fill(LinearGradient(colors: [SheetTheme.accent, SheetTheme.mint], startPoint: .leading, endPoint: .trailing))
                                        .frame(width: max(5, geo.size.width * (top > 0 ? g.cost / top : 0)))
                                }
                        }
                        .frame(height: 5)
                    }
                }
            }
            if groups.isEmpty {
                Label("No sessions yet", systemImage: "globe").font(.callout).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 60)
            }
        }
    }
}

extension VPNController {
    /// ISO country for a session's flag: its location's country, else where traffic left from.
    func sessionCountry(_ s: SessionRecord) -> String? {
        if let c = regions.first(where: { $0.code == s.region })?.country { return c }
        if let c = s.egressCountry, c.count == 2 { return c }
        return Countries.all.first { flag($0.code) == s.flag }?.code
    }
}

/// Sessions grouped by day, newest first.
struct SessionList: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let cal = Calendar.current
        let recent = Array(vpn.store.sessions.prefix(40))
        let days = Dictionary(grouping: recent) { cal.startOfDay(for: $0.connectedAt) }.sorted { $0.key > $1.key }
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(days.enumerated()), id: \.element.key) { i, day in
                HStack {
                    Text(dayTitle(day.key)).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Spacer()
                    Text(dayTotal(day.value))
                        .font(.caption.weight(.medium)).foregroundStyle(.tertiary).monospacedDigit()
                }
                .padding(.horizontal, 10).padding(.top, i == 0 ? 8 : 16).padding(.bottom, 4)
                ForEach(day.value) { s in row(s) }
            }
            if recent.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "clock.arrow.circlepath").font(.title2).foregroundStyle(SheetTheme.accent)
                    Text("No sessions yet").font(.callout.weight(.medium))
                    Text("Connect once and it shows up here.").font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 24)
            }
        }
    }

    /// Sums per currency, so a day mixing billing currencies never shows one under the other's symbol.
    private func dayTotal(_ sessions: [SessionRecord]) -> String {
        let byCurrency = Dictionary(grouping: sessions, by: \.currency)
        return byCurrency.keys.sorted().map { code in
            formatMoney(byCurrency[code]!.map(\.total).reduce(0, +), code)
        }.joined(separator: " + ")
    }

    private func row(_ s: SessionRecord) -> some View {
        let data = s.rxBytes + s.txBytes
        return HStack(spacing: 12) {
            FlagBadge(country: vpn.sessionCountry(s), size: 32)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 5) {
                    Text(s.regionName).font(.callout.weight(.medium)).lineLimit(1)
                    if s.via != nil { Image(systemName: "house.fill").font(.caption2).foregroundStyle(Atlas.home) }
                    if s.disconnectedAt == nil {
                        Circle().fill(SheetTheme.mint).frame(width: 6, height: 6).accessibilityLabel("Live")
                    }
                }
                Text([s.connectedAt.formatted(date: .omitted, time: .shortened), formatDuration(s.duration),
                      data > 0 ? formatBytes(data) : nil].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption).foregroundStyle(.secondary).monospacedDigit().lineLimit(1).minimumScaleFactor(0.85)
            }
            Spacer(minLength: 8)
            Text(formatMoney(s.total, s.currency)).font(.callout.weight(.semibold)).monospacedDigit()
                .help("server \(formatMoney(s.vmCost, s.currency)) + data \(formatMoney(s.egressCost, s.currency))")
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .contentShape(Rectangle())
    }

    private func dayTitle(_ d: Date) -> String {
        let cal = Calendar.current
        if cal.isDateInToday(d) { return "Today" }
        if cal.isDateInYesterday(d) { return "Yesterday" }
        return d.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated))
    }
}
