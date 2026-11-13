import SwiftUI

/// A country flag cropped to a circle, used on the map, in the connect panel and in lists.
/// `country` is an ISO 3166 alpha-2 code; nil or unknown draws a globe.
struct FlagBadge: View {
    let country: String?
    var size: CGFloat = 28

    var body: some View {
        ZStack {
            if let c = country, c.count == 2 {
                Text(flag(c))
                    .font(.system(size: size * 1.5))
                    .fixedSize()
                    .frame(width: size, height: size)
            } else {
                Image(systemName: "globe").font(.system(size: size * 0.6, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: size, height: size)
            }
        }
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(.white.opacity(0.35), lineWidth: max(1, size / 22)))
        .shadow(color: .black.opacity(0.18), radius: size / 10, y: size / 20)
        .accessibilityHidden(true)
    }
}
