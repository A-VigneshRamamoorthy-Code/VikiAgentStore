# macOS native Swift/AVFoundation fast path

The macOS fast path is an optional renderer for users who want a native launch-video render without ffmpeg, Python, Homebrew, or Xcode. It consumes the same `config.json` schema as the cross-platform engine, so a config authored for `scripts/launch_video.py` is interchangeable.

## Requirements

- macOS 13 or newer
- Swift toolchain from Apple Command Line Tools

Check:

```bash
swift --version
```

Xcode is not required.

## Run

From the skill directory:

```bash
cd scripts/swift_fastpath
swift run LaunchBuilder --config ../../config.json
```

For a release build:

```bash
cd scripts/swift_fastpath
swift build -c release
.build/release/LaunchBuilder --config ../../config.json
```

The renderer writes `config.output` as an H.264 `.mp4` at `config.resolution` and `config.fps`, with a branded intro, tightened demo, synced feature captions, transition accents, logo bug, outro CTA, final logo+name end-card, and original synthesized music/SFX.

## Pipeline

1. Parse the same generic `config.json` used by the cross-platform engine.
2. Load the demo with `AVURLAsset`, using async AVFoundation loading (`load(.duration)`, `loadTracks(withMediaType:)`).
3. Build an `AVMutableComposition` with one video track:
   - Insert a short source range at the beginning and scale it to the intro duration, giving the intro card room on the timeline.
   - Insert each configured `segments` source range sequentially. If no segments are provided, the whole input is used.
   - Insert a short source range near the end and scale it to the outro duration, giving the outro/end-card room.
4. Build an `AVMutableVideoComposition`:
   - `renderSize` comes from `resolution`.
   - `frameDuration` is `1 / fps`.
   - A single instruction covers the full composition duration.
   - A layer instruction scales the source to fill the output width and keeps translation at `(0, 0)`, preserving top-of-screen UI while cropping extra height at the bottom.
5. Add overlays with `AVVideoCompositionCoreAnimationTool(postProcessingAsVideoLayer:in:)`:
   - Intro card, lower-third caption pills, wipe accents, logo bug, ambient accents, outro CTA, and end-card are CALayers.
   - Text and graphics are prerendered to CGImages with `NSBitmapImageRep` for reliable text, emoji, shadows, and gradients.
   - Animations use `beginTime = AVCoreAnimationBeginTimeAtZero`, `fillMode = .both`, and `isRemovedOnCompletion = false`.
   - Keyframe animations span the full timeline with normalized `keyTimes`, so every exported frame has deterministic overlay state.
6. Synthesize an original WAV music bed and SFX track as raw PCM, load it with `AVURLAsset`, and insert it as the composition audio.
7. Export with `AVAssetExportSession` using `AVAssetExportPresetHighestQuality`, `videoComposition`, `.mp4`, and async continuation-based export.

## Important learned gotchas

- **Audio/video duration must match.** Capture `comp.duration` after the video track is built. Use that same frame-snapped duration for the video composition instruction and for the audio insert. If the instruction or audio does not cover the full timeline, AVFoundation export can fail with `-11841 Operation Stopped / The video could not be composed.`
- **Overlay coordinates are y-up.** CALayers used by the Core Animation video tool have origin at bottom-left: larger `y` values are higher on screen.
- **Top-aligned scale preserves screen UI.** Scaling the source by `renderWidth / sourceWidth` with translation `(0, 0)` keeps the top menu/action area visible and crops from the bottom when heights differ.
- **Prerendered images render upright.** Drawing text/graphics into an `NSBitmapImageRep` and assigning the resulting `CGImage` to `layer.contents` avoids upside-down text and inconsistent font rendering.

## Config mapping

- `input` / `output`: source demo and output MP4 path. Relative paths resolve from the config file directory.
- `fps`, `resolution`: video composition frame duration and render size.
- `fit`: accepted for schema compatibility; the native fast path uses the proven width-fill, top-aligned transform.
- `personality`: selects easing curves and animation timing.
- `brand.name`, `brand.tagline`, `brand.primary`, `brand.bg_gradient`, `brand.logo`: intro/outro/end-card text, colors, and logo; if no logo is supplied, a generated mark is used.
- `intro`: controls the opening card and hold duration.
- `segments`: source time ranges to keep; empty means the whole recording.
- `transitions`: enables wipe/dissolve/cut-style accent treatment between kept ranges.
- `captions`: lower-third callouts using output-time `start`/`end` windows.
- `logo_bug`: toggles the persistent small brand mark during the demo.
- `outro`: closing headline, optional CTA/link/footnote, duration, and end-card.
- `music` / `sfx`: controls the original synthesized bed and short UI sound effects.
- `font`, `font_bold`: optional font paths; system fonts are used when omitted.
