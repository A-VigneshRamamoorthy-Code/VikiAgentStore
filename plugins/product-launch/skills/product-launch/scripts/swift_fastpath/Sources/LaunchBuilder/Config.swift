import Foundation

struct LaunchConfig: Decodable {
    var input: String
    var output: String
    var fps: Int
    var resolution: [Int]
    var fit: String
    var personality: Personality
    var brand: Brand
    var intro: Intro
    var segments: [Segment]
    var transitions: TransitionStyle
    var captions: [Caption]
    var logoBug: Bool
    var outro: Outro
    var music: Music
    var sfx: Bool
    var font: String?
    var fontBold: String?

    enum CodingKeys: String, CodingKey {
        case input, output, fps, resolution, fit, personality, brand, intro, segments, transitions, captions, outro, music, sfx, font
        case logoBug = "logo_bug"
        case fontBold = "font_bold"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        input = try c.decode(String.self, forKey: .input)
        output = try c.decodeIfPresent(String.self, forKey: .output) ?? "launch.mp4"
        fps = try c.decodeIfPresent(Int.self, forKey: .fps) ?? 30
        resolution = try c.decodeIfPresent([Int].self, forKey: .resolution) ?? [1920, 1080]
        fit = try c.decodeIfPresent(String.self, forKey: .fit) ?? "height"
        personality = try c.decodeIfPresent(Personality.self, forKey: .personality) ?? .playful
        brand = try c.decode(Brand.self, forKey: .brand)
        intro = try c.decodeIfPresent(Intro.self, forKey: .intro) ?? Intro()
        segments = try c.decodeIfPresent([Segment].self, forKey: .segments) ?? []
        transitions = try c.decodeIfPresent(TransitionStyle.self, forKey: .transitions) ?? .wipe
        captions = try c.decodeIfPresent([Caption].self, forKey: .captions) ?? []
        logoBug = try c.decodeIfPresent(Bool.self, forKey: .logoBug) ?? true
        outro = try c.decodeIfPresent(Outro.self, forKey: .outro) ?? Outro()
        music = try c.decodeIfPresent(Music.self, forKey: .music) ?? Music()
        sfx = try c.decodeIfPresent(Bool.self, forKey: .sfx) ?? true
        font = try c.decodeIfPresent(String.self, forKey: .font)
        fontBold = try c.decodeIfPresent(String.self, forKey: .fontBold)
    }

    var renderWidth: Int { max(2, resolution.first ?? 1920) }
    var renderHeight: Int { max(2, resolution.dropFirst().first ?? 1080) }
}

struct Brand: Decodable {
    var name: String
    var tagline: String
    var primary: String
    var bgGradient: [String]
    var logo: String?

    enum CodingKeys: String, CodingKey { case name, tagline, primary, logo; case bgGradient = "bg_gradient" }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        tagline = try c.decodeIfPresent(String.self, forKey: .tagline) ?? ""
        primary = try c.decodeIfPresent(String.self, forKey: .primary) ?? "#5B8DEF"
        bgGradient = try c.decodeIfPresent([String].self, forKey: .bgGradient) ?? ["#14172B", "#1E2348", "#101326"]
        logo = try c.decodeIfPresent(String.self, forKey: .logo)
    }
}

struct Intro: Decodable {
    var enabled = true
    var duration = 2.8
    var title = "{brand.name}"
    var subtitle = "{brand.tagline}"

    enum CodingKeys: String, CodingKey { case enabled, duration, title, subtitle }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try c.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        duration = try c.decodeIfPresent(Double.self, forKey: .duration) ?? 2.8
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? "{brand.name}"
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle) ?? "{brand.tagline}"
    }
}

struct Segment: Decodable {
    var start: Double
    var end: Double
}

struct Caption: Decodable {
    var text: String
    var start: Double
    var end: Double
}

struct Outro: Decodable {
    var enabled = true
    var headline = ""
    var ctaText: String?
    var link: String?
    var footnote: String?
    var duration = 6.0
    var endCard = true

    enum CodingKeys: String, CodingKey { case enabled, headline, link, footnote, duration; case ctaText = "cta_text"; case endCard = "end_card" }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try c.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        headline = try c.decodeIfPresent(String.self, forKey: .headline) ?? ""
        ctaText = try c.decodeIfPresent(String.self, forKey: .ctaText)
        link = try c.decodeIfPresent(String.self, forKey: .link)
        footnote = try c.decodeIfPresent(String.self, forKey: .footnote)
        duration = try c.decodeIfPresent(Double.self, forKey: .duration) ?? 6.0
        endCard = try c.decodeIfPresent(Bool.self, forKey: .endCard) ?? true
    }
}

struct Music: Decodable {
    var enabled = true
    var vibe = "modern-playful"
    var bpm = 120.0
    var gain = 0.9

    enum CodingKeys: String, CodingKey { case enabled, vibe, bpm, gain }

    init() {}

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try c.decodeIfPresent(Bool.self, forKey: .enabled) ?? true
        vibe = try c.decodeIfPresent(String.self, forKey: .vibe) ?? "modern-playful"
        bpm = try c.decodeIfPresent(Double.self, forKey: .bpm) ?? 120
        gain = try c.decodeIfPresent(Double.self, forKey: .gain) ?? 0.9
    }
}

enum Personality: String, Decodable {
    case playful, premium, corporate, energetic
}

enum TransitionStyle: String, Decodable {
    case wipe, dissolve, cut
}

extension LaunchConfig {
    func resolvedText(_ text: String?) -> String {
        (text ?? "")
            .replacingOccurrences(of: "{brand.name}", with: brand.name)
            .replacingOccurrences(of: "{brand.tagline}", with: brand.tagline)
    }

    static func load(from url: URL) throws -> LaunchConfig {
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(LaunchConfig.self, from: data)
    }
}
