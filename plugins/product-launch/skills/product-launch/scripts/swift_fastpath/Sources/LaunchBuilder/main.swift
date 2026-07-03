import AppKit
import AVFoundation
import Foundation
import QuartzCore

struct LaunchBuilderError: Error, CustomStringConvertible {
    let description: String
}

final class LaunchBuilder {
    private let configURL: URL
    private let config: LaunchConfig
    private let configDirectory: URL
    private let assets: RenderAssets

    init(arguments: [String]) throws {
        guard let idx = arguments.firstIndex(of: "--config"), arguments.indices.contains(idx + 1) else {
            throw LaunchBuilderError(description: "Usage: LaunchBuilder --config <path>")
        }
        let raw = arguments[idx + 1]
        let url = URL(fileURLWithPath: NSString(string: raw).expandingTildeInPath)
        self.configURL = url.path.hasPrefix("/") ? url : URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(raw)
        self.configDirectory = self.configURL.deletingLastPathComponent()
        self.config = try LaunchConfig.load(from: self.configURL)
        self.assets = RenderAssets(config: config, configDirectory: configDirectory)
    }

    func run() async throws {
        let inputURL = resolve(config.input)
        let outputURL = resolve(config.output)
        try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: outputURL.path) { try FileManager.default.removeItem(at: outputURL) }

        let sourceAsset = AVURLAsset(url: inputURL)
        let sourceDuration = try await sourceAsset.load(.duration)
        let videoTracks = try await sourceAsset.loadTracks(withMediaType: .video)
        guard let sourceVideo = videoTracks.first else { throw LaunchBuilderError(description: "Input has no video track: \(inputURL.path)") }
        let naturalSize = try await sourceVideo.load(.naturalSize)

        let composition = AVMutableComposition()
        guard let compVideo = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw LaunchBuilderError(description: "Could not create composition video track")
        }

        let fps = max(1, config.fps)
        let frame = CMTime(value: 1, timescale: CMTimeScale(fps))
        let introDuration = config.intro.enabled ? CMTime(seconds: max(0, config.intro.duration), preferredTimescale: 600) : .zero
        let outroDuration = config.outro.enabled ? CMTime(seconds: max(0, config.outro.duration), preferredTimescale: 600) : .zero
        var cursor = CMTime.zero
        var cutTimes: [CMTime] = []

        if introDuration > .zero {
            try insertHold(sourceVideo, into: compVideo, sourceStart: .zero, frame: frame, at: cursor, duration: introDuration)
            cursor = cursor + introDuration
            cutTimes.append(cursor)
        }

        let segments = normalizedSegments(sourceDuration: sourceDuration)
        for (index, segment) in segments.enumerated() {
            let start = CMTime(seconds: segment.start, preferredTimescale: 600)
            let end = CMTime(seconds: segment.end, preferredTimescale: 600)
            let range = CMTimeRange(start: start, duration: maxTime(end - start, frame))
            try compVideo.insertTimeRange(range, of: sourceVideo, at: cursor)
            cursor = cursor + range.duration
            if index < segments.count - 1 { cutTimes.append(cursor) }
        }

        if outroDuration > .zero {
            let lastStartSeconds = max(0, CMTimeGetSeconds(sourceDuration) - CMTimeGetSeconds(frame) * 2.0)
            try insertHold(sourceVideo, into: compVideo, sourceStart: CMTime(seconds: lastStartSeconds, preferredTimescale: 600), frame: frame, at: cursor, duration: outroDuration)
            cursor = cursor + outroDuration
        }

        let videoDuration = snap(cursor, fps: fps)
        let instruction = AVMutableVideoCompositionInstruction()
        instruction.timeRange = CMTimeRange(start: .zero, duration: videoDuration)
        let layerInstruction = AVMutableVideoCompositionLayerInstruction(assetTrack: compVideo)
        let srcWidth = max(1.0, abs(naturalSize.width))
        let scale = CGFloat(config.renderWidth) / srcWidth
        layerInstruction.setTransform(CGAffineTransform(scaleX: scale, y: scale), at: .zero)
        instruction.layerInstructions = [layerInstruction]

        let videoComposition = AVMutableVideoComposition()
        videoComposition.renderSize = CGSize(width: config.renderWidth, height: config.renderHeight)
        videoComposition.frameDuration = frame
        videoComposition.instructions = [instruction]
        videoComposition.animationTool = makeAnimationTool(total: videoDuration, cutTimes: cutTimes)

        let audioURL = outputURL.deletingLastPathComponent().appendingPathComponent(".launchbuilder_audio.wav")
        if FileManager.default.fileExists(atPath: audioURL.path) { try FileManager.default.removeItem(at: audioURL) }
        _ = try AudioSynth(config: config, duration: videoDuration, outputURL: audioURL).writeWAV()
        try await addAudio(from: audioURL, to: composition, duration: videoDuration)

        try await export(composition: composition, videoComposition: videoComposition, outputURL: outputURL)
        try? FileManager.default.removeItem(at: audioURL)
        print("Wrote \(outputURL.path)")
    }

    private func resolve(_ path: String) -> URL {
        let url = URL(fileURLWithPath: NSString(string: path).expandingTildeInPath)
        return url.path.hasPrefix("/") ? url : configDirectory.appendingPathComponent(path)
    }

    private func normalizedSegments(sourceDuration: CMTime) -> [Segment] {
        let total = CMTimeGetSeconds(sourceDuration)
        let raw = config.segments.isEmpty ? [Segment(start: 0, end: total)] : config.segments
        return raw.compactMap { segment in
            let start = max(0, min(total, segment.start))
            let end = max(start, min(total, segment.end))
            return end > start ? Segment(start: start, end: end) : nil
        }
    }

    private func insertHold(_ source: AVAssetTrack, into track: AVMutableCompositionTrack, sourceStart: CMTime, frame: CMTime, at cursor: CMTime, duration: CMTime) throws {
        let range = CMTimeRange(start: sourceStart, duration: frame)
        try track.insertTimeRange(range, of: source, at: cursor)
        track.scaleTimeRange(CMTimeRange(start: cursor, duration: frame), toDuration: duration)
    }

    private func maxTime(_ a: CMTime, _ b: CMTime) -> CMTime { CMTimeCompare(a, b) >= 0 ? a : b }

    private func snap(_ time: CMTime, fps: Int) -> CMTime {
        let seconds = CMTimeGetSeconds(time)
        let frames = ceil(seconds * Double(fps))
        return CMTime(value: CMTimeValue(frames), timescale: CMTimeScale(fps))
    }

    private func makeAnimationTool(total: CMTime, cutTimes: [CMTime]) -> AVVideoCompositionCoreAnimationTool {
        let renderW = CGFloat(config.renderWidth)
        let renderH = CGFloat(config.renderHeight)
        let totalSeconds = max(0.001, CMTimeGetSeconds(total))
        let parent = CALayer()
        parent.frame = CGRect(x: 0, y: 0, width: renderW, height: renderH)
        parent.masksToBounds = true
        let videoLayer = CALayer()
        videoLayer.frame = parent.bounds
        parent.addSublayer(videoLayer)

        addIntro(to: parent, total: totalSeconds)
        addCaptions(to: parent, total: totalSeconds)
        addTransitions(to: parent, cutTimes: cutTimes, total: totalSeconds)
        addLogoBug(to: parent, total: totalSeconds)
        addOutro(to: parent, total: totalSeconds)

        return AVVideoCompositionCoreAnimationTool(postProcessingAsVideoLayer: videoLayer, in: parent)
    }

    private func imageLayer(_ image: CGImage, frame: CGRect) -> CALayer {
        let layer = CALayer()
        layer.frame = frame
        layer.contents = image
        layer.contentsGravity = .resizeAspect
        return layer
    }

    private func addIntro(to parent: CALayer, total: Double) {
        guard config.intro.enabled, config.intro.duration > 0 else { return }
        let layer = imageLayer(assets.introCard(), frame: parent.bounds)
        layer.opacity = 0
        let fade = CAKeyframeAnimation(keyPath: "opacity")
        fade.beginTime = AVCoreAnimationBeginTimeAtZero
        fade.duration = total
        fade.keyTimes = [0, normalized(0.15, total: total), normalized(max(0.2, config.intro.duration - 0.35), total: total), normalized(config.intro.duration, total: total), 1]
        fade.values = [0, 1, 1, 0, 0]
        persist(fade)
        layer.add(fade, forKey: "introOpacity")
        parent.addSublayer(layer)
    }

    private func addCaptions(to parent: CALayer, total: Double) {
        let motion = MotionSpec.forPersonality(config.personality)
        for caption in config.captions where caption.end > caption.start {
            let image = assets.captionPill(text: caption.text)
            let w = CGFloat(image.width)
            let h = CGFloat(image.height)
            let layer = imageLayer(image, frame: CGRect(x: (parent.bounds.width - w) / 2, y: 82, width: w, height: h))
            layer.opacity = 0
            let enterEnd = min(caption.end, caption.start + motion.enter)
            let exitStart = max(caption.start, caption.end - motion.exit)
            let opacity = CAKeyframeAnimation(keyPath: "opacity")
            opacity.beginTime = AVCoreAnimationBeginTimeAtZero
            opacity.duration = total
            opacity.keyTimes = [0, normalized(caption.start, total: total), normalized(enterEnd, total: total), normalized(exitStart, total: total), normalized(caption.end, total: total), 1]
            opacity.values = [0, 0, 1, 1, 0, 0]
            persist(opacity)
            layer.add(opacity, forKey: "opacity")

            let scale = CAKeyframeAnimation(keyPath: "transform.scale")
            scale.beginTime = AVCoreAnimationBeginTimeAtZero
            scale.duration = total
            scale.keyTimes = opacity.keyTimes
            scale.values = [0.92, 0.92, motion.popScale, 1.0, 0.96, 0.96]
            scale.timingFunctions = [motion.easing, motion.easing, motion.easing, CAMediaTimingFunction(name: .easeInEaseOut), CAMediaTimingFunction(name: .linear)]
            persist(scale)
            layer.add(scale, forKey: "scale")
            parent.addSublayer(layer)
        }
    }

    private func addTransitions(to parent: CALayer, cutTimes: [CMTime], total: Double) {
        guard config.transitions != .cut else { return }
        for cut in cutTimes {
            let t = CMTimeGetSeconds(cut)
            let layer = CALayer()
            layer.backgroundColor = assets.primary.withAlphaComponent(config.transitions == .dissolve ? 0.28 : 0.82).cgColor
            layer.frame = CGRect(x: -parent.bounds.width, y: 0, width: parent.bounds.width, height: parent.bounds.height)
            let anim = CAKeyframeAnimation(keyPath: "position.x")
            anim.beginTime = AVCoreAnimationBeginTimeAtZero
            anim.duration = total
            anim.keyTimes = [0, normalized(max(0, t - 0.18), total: total), normalized(t + 0.18, total: total), 1]
            anim.values = [-parent.bounds.width / 2, -parent.bounds.width / 2, parent.bounds.width * 1.5, parent.bounds.width * 1.5]
            persist(anim)
            layer.add(anim, forKey: "wipe")
            parent.addSublayer(layer)
        }
    }

    private func addLogoBug(to parent: CALayer, total: Double) {
        guard config.logoBug else { return }
        let introEnd = config.intro.enabled ? config.intro.duration : 0
        let outroStart = max(introEnd, total - (config.outro.enabled ? config.outro.duration : 0))
        let image = assets.logoBug()
        let w = CGFloat(image.width)
        let h = CGFloat(image.height)
        let layer = imageLayer(image, frame: CGRect(x: parent.bounds.width - w - 34, y: parent.bounds.height - h - 34, width: w, height: h))
        layer.opacity = 0
        let fade = CAKeyframeAnimation(keyPath: "opacity")
        fade.beginTime = AVCoreAnimationBeginTimeAtZero
        fade.duration = total
        fade.keyTimes = [0, normalized(introEnd + 0.2, total: total), normalized(introEnd + 0.5, total: total), normalized(outroStart - 0.3, total: total), normalized(outroStart, total: total), 1]
        fade.values = [0, 0, 0.92, 0.92, 0, 0]
        persist(fade)
        layer.add(fade, forKey: "opacity")
        parent.addSublayer(layer)
    }

    private func addOutro(to parent: CALayer, total: Double) {
        guard config.outro.enabled, config.outro.duration > 0 else { return }
        let start = max(0, total - config.outro.duration)
        let outro = imageLayer(assets.outroCard(), frame: parent.bounds)
        outro.opacity = 0
        let fade = CAKeyframeAnimation(keyPath: "opacity")
        fade.beginTime = AVCoreAnimationBeginTimeAtZero
        fade.duration = total
        fade.keyTimes = [0, normalized(start, total: total), normalized(start + 0.45, total: total), normalized(total, total: total)]
        fade.values = [0, 0, 1, 1]
        persist(fade)
        outro.add(fade, forKey: "outroOpacity")
        parent.addSublayer(outro)

        if config.outro.endCard {
            let endStart = max(start, total - min(2.0, config.outro.duration * 0.45))
            let end = imageLayer(assets.endCard(), frame: parent.bounds)
            end.opacity = 0
            let endFade = CAKeyframeAnimation(keyPath: "opacity")
            endFade.beginTime = AVCoreAnimationBeginTimeAtZero
            endFade.duration = total
            endFade.keyTimes = [0, normalized(endStart, total: total), normalized(endStart + 0.35, total: total), 1]
            endFade.values = [0, 0, 1, 1]
            persist(endFade)
            end.add(endFade, forKey: "endCardOpacity")
            parent.addSublayer(end)
        }
    }

    private func persist(_ animation: CAAnimation) {
        animation.fillMode = .both
        animation.isRemovedOnCompletion = false
    }

    private func addAudio(from audioURL: URL, to composition: AVMutableComposition, duration: CMTime) async throws {
        let audioAsset = AVURLAsset(url: audioURL)
        let tracks = try await audioAsset.loadTracks(withMediaType: .audio)
        guard let sourceAudio = tracks.first else { throw LaunchBuilderError(description: "Synthesized audio could not be loaded") }
        guard let compAudio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw LaunchBuilderError(description: "Could not create composition audio track")
        }
        try compAudio.insertTimeRange(CMTimeRange(start: .zero, duration: duration), of: sourceAudio, at: .zero)
    }

    private func export(composition: AVMutableComposition, videoComposition: AVMutableVideoComposition, outputURL: URL) async throws {
        guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else {
            throw LaunchBuilderError(description: "Could not create AVAssetExportSession")
        }
        session.outputURL = outputURL
        session.outputFileType = .mp4
        session.videoComposition = videoComposition
        session.shouldOptimizeForNetworkUse = true
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            session.exportAsynchronously { continuation.resume() }
        }
        if session.status != .completed {
            let message = session.error?.localizedDescription ?? "Unknown export failure"
            throw LaunchBuilderError(description: "Export failed: \(message)")
        }
    }
}

let semaphore = DispatchSemaphore(value: 0)
var exitCode: Int32 = 0
Task {
    do {
        try await LaunchBuilder(arguments: CommandLine.arguments).run()
    } catch {
        fputs("LaunchBuilder error: \(error)\n", stderr)
        exitCode = 1
    }
    semaphore.signal()
}
semaphore.wait()
Foundation.exit(exitCode)
