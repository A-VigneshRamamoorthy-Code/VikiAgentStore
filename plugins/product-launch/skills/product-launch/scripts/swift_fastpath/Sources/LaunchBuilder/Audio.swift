import AVFoundation
import Foundation

struct AudioSynth {
    let config: LaunchConfig
    let duration: CMTime
    let outputURL: URL

    func writeWAV() throws -> URL {
        let sampleRate = 44_100
        let channels = 2
        let seconds = max(0.1, CMTimeGetSeconds(duration))
        let frames = Int(ceil(seconds * Double(sampleRate))) + sampleRate / 10
        var pcm = [Int16]()
        pcm.reserveCapacity(frames * channels)

        let bpm = max(60.0, config.music.bpm)
        let beat = 60.0 / bpm
        let gain = max(0.0, min(1.5, config.music.gain))
        let vibe = config.music.vibe

        for i in 0..<frames {
            let t = Double(i) / Double(sampleRate)
            var sample = 0.0
            if config.music.enabled {
                let introFade = min(1.0, t / 1.2)
                let outroFade = min(1.0, max(0.0, (seconds - t) / 1.4))
                let env = introFade * outroFade
                let root = rootFrequency(vibe: vibe)
                let chord = chordTone(t: t, beat: beat, root: root, vibe: vibe)
                let pad = 0.18 * sin(2.0 * .pi * chord * t) + 0.08 * sin(2.0 * .pi * chord * 2.0 * t)
                let pulsePhase = t.truncatingRemainder(dividingBy: beat)
                let kick = exp(-pulsePhase * 18.0) * sin(2.0 * .pi * (58.0 + 24.0 * exp(-pulsePhase * 20.0)) * t)
                let hatPhase = t.truncatingRemainder(dividingBy: beat / 2.0)
                let hat = exp(-hatPhase * 55.0) * (noise(i) * 2.0 - 1.0)
                let drop = t > max(0.5, config.intro.enabled ? config.intro.duration : 0.5) ? 1.0 : 0.32
                sample += (pad + 0.24 * kick * drop + 0.035 * hat * drop) * env
            }
            if config.sfx {
                sample += sfxSample(t: t, introEnd: config.intro.enabled ? config.intro.duration : 0.0, total: seconds)
                for caption in config.captions {
                    if t >= caption.start && t < caption.start + 0.18 { sample += pop(t - caption.start) * 0.28 }
                }
            }
            let clamped = max(-1.0, min(1.0, sample * gain))
            let intSample = Int16(clamped * Double(Int16.max))
            pcm.append(intSample)
            pcm.append(intSample)
        }

        let dataBytes = pcm.count * MemoryLayout<Int16>.size
        var data = Data()
        data.appendString("RIFF")
        data.appendUInt32LE(UInt32(36 + dataBytes))
        data.appendString("WAVE")
        data.appendString("fmt ")
        data.appendUInt32LE(16)
        data.appendUInt16LE(1)
        data.appendUInt16LE(UInt16(channels))
        data.appendUInt32LE(UInt32(sampleRate))
        data.appendUInt32LE(UInt32(sampleRate * channels * 2))
        data.appendUInt16LE(UInt16(channels * 2))
        data.appendUInt16LE(16)
        data.appendString("data")
        data.appendUInt32LE(UInt32(dataBytes))
        for sample in pcm { data.appendInt16LE(sample) }
        try data.write(to: outputURL, options: .atomic)
        return outputURL
    }

    private func rootFrequency(vibe: String) -> Double {
        switch vibe {
        case "calm": return 196.0
        case "corporate": return 174.61
        case "energetic": return 220.0
        default: return 207.65
        }
    }

    private func chordTone(t: Double, beat: Double, root: Double, vibe: String) -> Double {
        let bar = Int(floor(t / (beat * 4.0))) % 4
        let ratios: [Double]
        switch vibe {
        case "corporate": ratios = [1.0, 1.25, 1.5, 1.333]
        case "calm": ratios = [1.0, 1.2, 1.5, 1.125]
        case "energetic": ratios = [1.0, 1.5, 1.25, 1.777]
        default: ratios = [1.0, 1.25, 1.5, 1.667]
        }
        return root * ratios[bar]
    }

    private func sfxSample(t: Double, introEnd: Double, total: Double) -> Double {
        var v = 0.0
        if t >= introEnd && t < introEnd + 0.65 { v += whoosh(t - introEnd) * 0.20 }
        let endStart = max(0.0, total - max(2.5, config.outro.duration))
        if config.outro.enabled && t >= endStart && t < endStart + 0.5 { v += sparkle(t - endStart) * 0.20 }
        return v
    }

    private func pop(_ x: Double) -> Double {
        exp(-x * 28.0) * sin(2.0 * .pi * (620.0 + 180.0 * x) * x)
    }

    private func whoosh(_ x: Double) -> Double {
        let env = min(1.0, x / 0.2) * max(0.0, 1.0 - x / 0.65)
        return env * (noise(Int(x * 44100.0)) * 2.0 - 1.0)
    }

    private func sparkle(_ x: Double) -> Double {
        let env = exp(-x * 5.0)
        return env * (sin(2.0 * .pi * 1200.0 * x) + 0.5 * sin(2.0 * .pi * 1800.0 * x))
    }

    private func noise(_ i: Int) -> Double {
        let n = (i &* 1103515245 &+ 12345) & 0x7fffffff
        return Double(n % 10_000) / 10_000.0
    }
}

extension Data {
    mutating func appendString(_ string: String) { append(string.data(using: .ascii)!) }
    mutating func appendUInt16LE(_ value: UInt16) { var v = value.littleEndian; append(Data(bytes: &v, count: 2)) }
    mutating func appendUInt32LE(_ value: UInt32) { var v = value.littleEndian; append(Data(bytes: &v, count: 4)) }
    mutating func appendInt16LE(_ value: Int16) { var v = value.littleEndian; append(Data(bytes: &v, count: 2)) }
}
