#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

struct HistorySheet: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SheetHeader(icon: "chart.bar.xaxis", title: "Usage", tint: Atlas.green, trailing: AnyView(
                CircleButton(icon: "arrow.clockwise", help: "Refresh") { Task { await vpn.refreshCosts() } }))
            ScrollView {
                VStack(spacing: 14) {
                    StatTiles()
                    #if os(iOS)
                    Card(title: "Last 14 days") { DailyChart() }
                    Card(title: "By location") { LocationBreakdown() }
                    #else
                    HStack(alignment: .top, spacing: 14) {
                        Card(title: "Last 14 days") { DailyChart() }
                        Card(title: "By location") { LocationBreakdown() }.frame(width: 230)
                    }
                    #endif
                    Card(title: "Sessions") { SessionList() }
                    Text("Estimates from Azure retail prices. Billed totals lag a few hours.")
                        .font(.caption2).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(22)
        .macFrame(width: 680, height: 600)
    }
}

struct StatTiles: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let month = Calendar.current.dateInterval(of: .month, for: Date())?.start ?? Date()
        let t = vpn.store.totals(since: month)
        let cur = vpn.usageCurrency
        #if os(iOS)
        Grid(horizontalSpacing: 10, verticalSpacing: 10) {
            GridRow {
                if let spend = vpn.spend, let credit = vpn.monthlyCredit {
                    tile("creditcard", "Credit left", formatMoney(max(0, credit - spend.amount), spend.currency),
                         "of \(compactMoney(credit, spend.currency))", Atlas.green)
                }
                tile("calendar", "This month", formatMoney(t.cost, cur), "\(sessionsThisMonth(month)) sessions", Atlas.blue)
            }
            GridRow {
                tile("clock", "Server time", String(format: "%.1f h", t.hours), "billed compute", Atlas.amber)
                tile("arrow.up.arrow.down", "Data", String(format: "%.2f GB", t.gb), "through the VPN", .purple)
            }
        }
        #else
        HStack(spacing: 10) {
            if let spend = vpn.spend, let credit = vpn.monthlyCredit {
                tile("creditcard", "Credit left", formatMoney(max(0, credit - spend.amount), spend.currency),
                     "of \(compactMoney(credit, spend.currency))", Atlas.green)
            }
            tile("calendar", "This month", formatMoney(t.cost, cur), "\(sessionsThisMonth(month)) sessions", Atlas.blue)
            tile("clock", "Server time", String(format: "%.1f h", t.hours), "billed compute", Atlas.amber)
            tile("arrow.up.arrow.down", "Data", String(format: "%.2f GB", t.gb), "through the VPN", .purple)
        }
        #endif
    }

    private func sessionsThisMonth(_ since: Date) -> Int { vpn.store.sessions.filter { $0.connectedAt >= since }.count }

    private func tile(_ icon: String, _ title: String, _ value: String, _ caption: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(title, systemImage: icon).font(.caption).foregroundStyle(tint)
            Text(value).font(.title3.weight(.bold)).monospacedDigit().lineLimit(1).minimumScaleFactor(0.7)
            Text(caption).font(.caption2).foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(tint.opacity(0.09)))
    }
}

struct DailyChart: View {
    @EnvironmentObject var vpn: VPNController

    struct Day: Identifiable { let id: Date; let cost: Double }

    var body: some View {
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        let days: [Day] = (0..<14).reversed().compactMap { i in
            guard let d = cal.date(byAdding: .day, value: -i, to: today) else { return nil }
            let cost = vpn.store.sessions.filter { cal.isDate($0.connectedAt, inSameDayAs: d) }.map(\.total).reduce(0, +)
            return Day(id: d, cost: cost)
        }
        Chart(days) { d in
            BarMark(x: .value("Day", d.id, unit: .day), y: .value("Cost", d.cost))
                .foregroundStyle(Atlas.green.gradient).cornerRadius(4)
        }
        .chartXAxis { AxisMarks(values: .stride(by: .day, count: 3)) { _ in AxisValueLabel(format: .dateTime.day().month(.abbreviated)) } }
        .chartYAxis { AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { v in
            AxisGridLine()
            AxisValueLabel { if let n = v.as(Double.self) { Text(formatMoney(n, vpn.usageCurrency)) } }
        } }
        .frame(height: 150)
    }
}

struct LocationBreakdown: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        let groups = Dictionary(grouping: vpn.store.sessions) { "\($0.flag) \($0.regionName)" }
            .map { (name: $0.key, cost: $0.value.map(\.total).reduce(0, +), count: $0.value.count) }
            .sorted { $0.cost > $1.cost }
        let top = groups.first?.cost ?? 0
        VStack(alignment: .leading, spacing: 10) {
            ForEach(groups.prefix(6), id: \.name) { g in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(g.name).font(.caption).lineLimit(1)
                        Spacer()
                        Text(formatMoney(g.cost, vpn.usageCurrency)).font(.caption.weight(.semibold)).monospacedDigit()
                    }
                    GeometryReader { geo in
                        Capsule().fill(.primary.opacity(0.07))
                            .overlay(alignment: .leading) {
                                Capsule().fill(Atlas.blue.gradient).frame(width: max(4, geo.size.width * (top > 0 ? g.cost / top : 0)))
                            }
                    }
                    .frame(height: 6)
                }
            }
            if groups.isEmpty { Text("No sessions yet").font(.caption).foregroundStyle(.tertiary) }
        }
    }
}

struct SessionList: View {
    @EnvironmentObject var vpn: VPNController

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(vpn.store.sessions.prefix(40).enumerated()), id: \.element.id) { i, s in
                if i > 0 { Divider().opacity(0.5) }
                HStack(spacing: 12) {
                    Text(s.flag).font(.title3)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(s.regionName).font(.callout.weight(.medium))
                        Text(s.connectedAt.formatted(.dateTime.day().month(.abbreviated).hour().minute()))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Chip(icon: "timer", text: formatDuration(s.duration), width: 92)
                    Chip(icon: "arrow.up.arrow.down", text: s.rxBytes + s.txBytes > 0 ? formatBytes(s.rxBytes + s.txBytes) : "—", width: 96)
                    Text(formatMoney(s.total, s.currency)).font(.callout.weight(.semibold)).monospacedDigit()
                        .frame(width: 70, alignment: .trailing)
                        .help("server \(formatMoney(s.vmCost, s.currency)) + data \(formatMoney(s.egressCost, s.currency))")
                }
                .padding(.vertical, 8)
            }
            if vpn.store.sessions.isEmpty { Text("No sessions yet").font(.caption).foregroundStyle(.tertiary) }
        }
    }
}

// MARK: settings
