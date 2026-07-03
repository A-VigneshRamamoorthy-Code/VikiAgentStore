import AppKit
import CoreGraphics
import Foundation
import ImageIO
import QuartzCore

struct RenderAssets {
    let config: LaunchConfig
    let configDirectory: URL
    let width: Int
    let height: Int
    let primary: NSColor
    let gradient: [NSColor]
    let regularFontName: String?
    let boldFontName: String?
    let logo: CGImage?

    init(config: LaunchConfig, configDirectory: URL) {
        self.config = config
        self.configDirectory = configDirectory
        self.width = config.renderWidth
        self.height = config.renderHeight
        self.primary = NSColor(hex: config.brand.primary) ?? NSColor(calibratedRed: 0.36, green: 0.55, blue: 0.94, alpha: 1)
        let colors = config.brand.bgGradient.compactMap { NSColor(hex: $0) }
        self.gradient = colors.isEmpty ? [NSColor(calibratedRed: 0.08, green: 0.09, blue: 0.17, alpha: 1), NSColor(calibratedRed: 0.06, green: 0.07, blue: 0.15, alpha: 1)] : colors
        self.regularFontName = RenderAssets.registerFont(config.font, base: configDirectory)
        self.boldFontName = RenderAssets.registerFont(config.fontBold, base: configDirectory)
        self.logo = RenderAssets.loadLogo(config.brand.logo, base: configDirectory)
    }

    static func registerFont(_ path: String?, base: URL) -> String? {
        guard let path else { return nil }
        let url = resolve(path, base: base)
        var error: Unmanaged<CFError>?
        CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error)
        guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [[CFString: Any]],
              let first = descriptors.first,
              let name = first[kCTFontNameAttribute] as? String else { return nil }
        return name
    }

    static func resolve(_ path: String, base: URL) -> URL {
        let url = URL(fileURLWithPath: NSString(string: path).expandingTildeInPath)
        return url.path.hasPrefix("/") ? url : base.appendingPathComponent(path)
    }

    static func loadLogo(_ path: String?, base: URL) -> CGImage? {
        guard let path, !path.isEmpty else { return nil }
        let url = resolve(path, base: base)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }

    func font(size: CGFloat, bold: Bool = false) -> NSFont {
        if bold, let boldFontName, let font = NSFont(name: boldFontName, size: size) { return font }
        if !bold, let regularFontName, let font = NSFont(name: regularFontName, size: size) { return font }
        return bold ? NSFont.boldSystemFont(ofSize: size) : NSFont.systemFont(ofSize: size, weight: .regular)
    }

    func introCard() -> CGImage { cardImage(title: config.resolvedText(config.intro.title), subtitle: config.resolvedText(config.intro.subtitle), mode: .intro) }
    func outroCard() -> CGImage { cardImage(title: config.outro.headline.isEmpty ? config.brand.name : config.outro.headline, subtitle: [config.outro.ctaText, config.outro.link, config.outro.footnote].compactMap { $0 }.joined(separator: "  •  "), mode: .outro) }
    func endCard() -> CGImage { cardImage(title: config.brand.name, subtitle: config.brand.tagline, mode: .endCard) }

    enum CardMode { case intro, outro, endCard }

    func cardImage(title: String, subtitle: String, mode: CardMode) -> CGImage {
        drawImage(size: CGSize(width: width, height: height)) { context, rect in
            drawGradient(context, rect: rect)
            let mark = logo ?? generatedMark(size: 280)
            let markSize: CGFloat = mode == .endCard ? 210 : 150
            drawLogo(mark, in: CGRect(x: (rect.width - markSize) / 2, y: rect.height * 0.57, width: markSize, height: markSize), context: context)
            drawCentered(title, y: rect.height * 0.45, maxWidth: rect.width * 0.78, size: mode == .endCard ? 78 : 86, bold: true, color: .white)
            if !subtitle.isEmpty {
                drawCentered(subtitle, y: rect.height * 0.34, maxWidth: rect.width * 0.72, size: 34, bold: false, color: NSColor.white.withAlphaComponent(0.82))
            }
            let accentRect = CGRect(x: rect.width * 0.42, y: rect.height * 0.29, width: rect.width * 0.16, height: 8)
            context.setFillColor(primary.cgColor)
            context.fillEllipse(in: accentRect)
        }
    }

    func captionPill(text: String) -> CGImage {
        let maxW = CGFloat(width) * 0.70
        let attrs: [NSAttributedString.Key: Any] = [.font: font(size: 34, bold: true), .foregroundColor: NSColor.white]
        let measured = (text as NSString).boundingRect(with: CGSize(width: maxW - 96, height: 400), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attrs)
        let pillW = min(maxW, max(420, ceil(measured.width) + 120))
        let pillH = max(92, ceil(measured.height) + 44)
        return drawImage(size: CGSize(width: pillW, height: pillH)) { context, rect in
            let path = CGPath(roundedRect: rect.insetBy(dx: 2, dy: 2), cornerWidth: pillH / 2, cornerHeight: pillH / 2, transform: nil)
            context.setShadow(offset: CGSize(width: 0, height: -12), blur: 22, color: NSColor.black.withAlphaComponent(0.25).cgColor)
            context.setFillColor(NSColor.black.withAlphaComponent(0.72).cgColor)
            context.addPath(path)
            context.fillPath()
            context.setFillColor(primary.cgColor)
            context.fillEllipse(in: CGRect(x: 28, y: (pillH - 22) / 2, width: 22, height: 22))
            let textRect = CGRect(x: 68, y: (pillH - measured.height) / 2 - 3, width: pillW - 100, height: measured.height + 10)
            (text as NSString).draw(with: textRect, options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attrs)
        }
    }

    func logoBug() -> CGImage {
        let size = CGSize(width: 240, height: 72)
        return drawImage(size: size) { context, rect in
            let path = CGPath(roundedRect: rect, cornerWidth: 28, cornerHeight: 28, transform: nil)
            context.setFillColor(NSColor.black.withAlphaComponent(0.42).cgColor)
            context.addPath(path)
            context.fillPath()
            let mark = logo ?? generatedMark(size: 48)
            drawLogo(mark, in: CGRect(x: 16, y: 12, width: 48, height: 48), context: context)
            let attrs: [NSAttributedString.Key: Any] = [.font: font(size: 22, bold: true), .foregroundColor: NSColor.white]
            (config.brand.name as NSString).draw(in: CGRect(x: 76, y: 23, width: 148, height: 30), withAttributes: attrs)
        }
    }

    func generatedMark(size: CGFloat) -> CGImage {
        drawImage(size: CGSize(width: size, height: size)) { context, rect in
            context.setFillColor(primary.cgColor)
            context.fillEllipse(in: rect.insetBy(dx: 4, dy: 4))
            context.setFillColor(NSColor.white.withAlphaComponent(0.95).cgColor)
            let letter = String(config.brand.name.prefix(1)).uppercased() as NSString
            let attrs: [NSAttributedString.Key: Any] = [.font: font(size: size * 0.48, bold: true), .foregroundColor: NSColor.white]
            let bounds = letter.size(withAttributes: attrs)
            letter.draw(at: CGPoint(x: (size - bounds.width) / 2, y: (size - bounds.height) / 2 - size * 0.03), withAttributes: attrs)
        }
    }

    private func drawGradient(_ context: CGContext, rect: CGRect) {
        let cgColors = gradient.map { $0.cgColor } as CFArray
        let locations = gradient.enumerated().map { CGFloat($0.offset) / CGFloat(max(1, gradient.count - 1)) }
        if let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: cgColors, locations: locations) {
            context.drawLinearGradient(gradient, start: CGPoint(x: 0, y: rect.height), end: CGPoint(x: rect.width, y: 0), options: [])
        }
        context.setFillColor(primary.withAlphaComponent(0.16).cgColor)
        context.fillEllipse(in: CGRect(x: rect.width * 0.65, y: rect.height * 0.55, width: rect.width * 0.42, height: rect.width * 0.42))
        context.fillEllipse(in: CGRect(x: -rect.width * 0.14, y: -rect.height * 0.18, width: rect.width * 0.36, height: rect.width * 0.36))
    }

    private func drawCentered(_ string: String, y: CGFloat, maxWidth: CGFloat, size: CGFloat, bold: Bool, color: NSColor) {
        let attrs: [NSAttributedString.Key: Any] = [.font: font(size: size, bold: bold), .foregroundColor: color]
        let rect = (string as NSString).boundingRect(with: CGSize(width: maxWidth, height: 260), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attrs)
        (string as NSString).draw(with: CGRect(x: (CGFloat(width) - maxWidth) / 2, y: y - rect.height / 2, width: maxWidth, height: rect.height + 12), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: attrs)
    }

    private func drawLogo(_ image: CGImage, in rect: CGRect, context: CGContext) {
        context.saveGState()
        context.setShadow(offset: CGSize(width: 0, height: -12), blur: 22, color: NSColor.black.withAlphaComponent(0.24).cgColor)
        context.draw(image, in: rect)
        context.restoreGState()
    }
}

func drawImage(size: CGSize, drawing: (CGContext, CGRect) -> Void) -> CGImage {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width), pixelsHigh: Int(size.height), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    let nsContext = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.current = nsContext
    let context = nsContext.cgContext
    context.clear(CGRect(origin: .zero, size: size))
    drawing(context, CGRect(origin: .zero, size: size))
    NSGraphicsContext.restoreGraphicsState()
    return rep.cgImage!
}

extension NSColor {
    convenience init?(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") { s.removeFirst() }
        guard s.count == 6, let value = Int(s, radix: 16) else { return nil }
        self.init(calibratedRed: CGFloat((value >> 16) & 0xff) / 255.0, green: CGFloat((value >> 8) & 0xff) / 255.0, blue: CGFloat(value & 0xff) / 255.0, alpha: 1)
    }
}
