import SwiftUI
#if canImport(UIKit)
import UIKit
typealias FlagImage = UIImage
#else
import AppKit
typealias FlagImage = NSImage
#endif

/// A flat, circular country flag that fills its circle, used on the map, in the connect panel
/// and in lists. `country` is an ISO 3166 alpha-2 code (any case); nil or unknown draws a globe.
/// Artwork: HatScripts/circle-flags (MIT), bundled as `Flags/<CC>.png` by build.sh / project.yml.
struct FlagBadge: View {
    let country: String?
    var size: CGFloat = 28
    @Environment(\.displayScale) private var scale

    var body: some View {
        Group {
            if let image = FlagArt.image(country) {
                #if canImport(UIKit)
                Image(uiImage: image).resizable().interpolation(.high)
                #else
                Image(nsImage: image).resizable().interpolation(.high)
                #endif
            } else {
                Circle().fill(.quaternary)
                    .overlay(Image(systemName: "globe").font(.system(size: size * 0.55, weight: .medium))
                        .foregroundStyle(.secondary))
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .overlay(Circle().strokeBorder(Color.primary.opacity(0.14), lineWidth: 1 / max(scale, 1)))
        .accessibilityHidden(true)
    }
}

/// Loads and caches the bundled flag PNGs.
enum FlagArt {
    @MainActor private static var cache: [String: FlagImage] = [:]
    @MainActor private static var missing: Set<String> = []

    @MainActor static func image(_ country: String?) -> FlagImage? {
        guard let code = country?.uppercased(), code.count == 2, !missing.contains(code) else { return nil }
        if let hit = cache[code] { return hit }
        guard let url = url(code), let image = FlagImage(contentsOfFile: url.path) else {
            missing.insert(code)
            return nil
        }
        cache[code] = image
        return image
    }

    private static func url(_ code: String) -> URL? {
        if let url = Bundle.main.url(forResource: code, withExtension: "png", subdirectory: "Flags") { return url }
        #if DEBUG
        // `swift build` runs have no app bundle: read straight from the source tree.
        let dev = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("../../Assets/Flags/\(code).png").standardized
        if FileManager.default.fileExists(atPath: dev.path) { return dev }
        #endif
        return nil
    }
}

/// The ISO alpha-2 code behind a flag emoji ("🇮🇳" → "IN"), for records stored before flags
/// became images. nil when the string isn't a pair of regional indicator symbols.
func countryCode(fromFlagEmoji emoji: String) -> String? {
    let scalars = Array(emoji.unicodeScalars)
    guard scalars.count == 2 else { return nil }
    let letters = scalars.compactMap { s -> Character? in
        guard (0x1F1E6...0x1F1FF).contains(s.value) else { return nil }
        return Character(UnicodeScalar(s.value - 0x1F1E6 + 65)!)
    }
    return letters.count == 2 ? String(letters) : nil
}
