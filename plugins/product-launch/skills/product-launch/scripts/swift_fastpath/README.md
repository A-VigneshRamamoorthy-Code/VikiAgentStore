# Swift fast path

Native macOS renderer for the `product-launch` skill. It uses SwiftPM + AVFoundation/AppKit/QuartzCore/ImageIO only; no ffmpeg, Python, Homebrew, or Xcode project is required.

```bash
cd scripts/swift_fastpath
swift run LaunchBuilder --config ../../config.json
```

Release build:

```bash
swift build -c release
.build/release/LaunchBuilder --config ../../config.json
```

The command consumes the same `config.json` schema as the cross-platform engine and writes `config.output`.
