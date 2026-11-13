#if os(macOS)
import AppKit
#endif
import Charts
import SwiftUI

struct SheetHeader: View {
    let icon: String
    let title: String
    var tint: Color = Atlas.blue
    var trailing: AnyView? = nil
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon).font(.system(size: 16, weight: .semibold)).foregroundStyle(.white)
                .frame(width: 34, height: 34).background(Circle().fill(tint.gradient))
            Text(title).font(.title2.weight(.semibold))
            Spacer()
            trailing
            CircleButton(icon: "xmark", help: "Close") { dismiss() }.keyboardShortcut(.cancelAction)
        }
    }
}

struct Card<Content: View>: View {
    var title: String? = nil
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let title { Text(title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.secondary).tracking(0.6) }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(.primary.opacity(0.045)))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(.primary.opacity(0.07), lineWidth: 0.5))
    }
}

// MARK: usage

extension VPNController {
    var usageCurrency: String { store.sessions.first?.currency ?? spend?.currency ?? "USD" }
}
