# 1. Project setup — build a macOS app without Xcode

Target environment: **Apple Silicon, Command Line Tools only (no Xcode)**. So:
build with **SwiftPM**, **hand-assemble** the `.app`, and **ad-hoc codesign**.

## Verify the toolchain first
```bash
swift --version                 # need the Swift toolchain
xcrun --show-sdk-path            # CLT SDK; AppKit + QuartzCore live here
# Confirm frameworks exist:
SDK=$(xcrun --show-sdk-path); ls "$SDK/System/Library/Frameworks/AppKit.framework"
```
`xcodebuild` will error ("requires Xcode") — that's expected and fine. `swift build`
links AppKit/QuartzCore/CoreGraphics from the CLT SDK.

## Package.swift — split pure core from the AppKit shell
```swift
// swift-tools-version:5.9
import PackageDescription
let package = Package(
    name: "App",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "App", targets: ["App"]),
        .library(name: "AppCore", targets: ["AppCore"]),
    ],
    targets: [
        .target(name: "AppCore"),                                  // PURE: no AppKit
        .executableTarget(name: "App", dependencies: ["AppCore"]), // AppKit shell
        // Command Line Tools ship NO XCTest → use a plain executable test harness:
        .executableTarget(name: "app-selftest", dependencies: ["AppCore"]),
    ]
)
```
Rules of thumb:
- `AppCore` imports only `Foundation` / `CoreGraphics`. Everything testable and
  every pixel of drawing lives here so it runs headless.
- The `App` target is the only place that imports `AppKit` / `QuartzCore`.

## scripts/build_app.sh — assemble the `.app`
SwiftPM emits a bare executable; macOS needs a bundle. Key moves:
```bash
swift build -c release --product App
BIN="$(swift build -c release --product App --show-bin-path)/App"
APP=build/App.app
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/App"
# Info.plist (see below) → "$APP/Contents/Info.plist"
codesign --force --sign - --timestamp=none "$APP"   # ad-hoc signature
```

### Info.plist essentials
```xml
<key>CFBundleExecutable</key>      <string>App</string>
<key>CFBundleIdentifier</key>      <string>com.example.App</string>
<key>CFBundlePackageType</key>     <string>APPL</string>
<key>LSMinimumSystemVersion</key>  <string>14.0</string>
<key>NSPrincipalClass</key>        <string>NSApplication</string>
<key>NSHighResolutionCapable</key> <true/>
<key>LSUIElement</key>             <true/>   <!-- agent app: NO Dock icon, NO app menu -->
<key>CFBundleIconFile</key>        <string>AppIcon</string>  <!-- if you ship an icon -->
```
`LSUIElement=true` is half of "no Dock icon"; the other half is
`NSApp.setActivationPolicy(.accessory)` at runtime (set both).

## main.swift — entry + hidden headless modes
```swift
import AppKit
let app = NSApplication.shared
// Hidden offscreen render modes for visual verification (no window server needed):
if let i = CommandLine.arguments.firstIndex(of: "--render"),
   CommandLine.arguments.indices.contains(i+1) { Preview.render(to: CommandLine.arguments[i+1]); exit(0) }
// ...also --contact (animation grid), --icons, --appicon ...
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)   // no Dock icon
app.run()
```

## Build & run
```bash
swift build                       # quick compile check
./scripts/build_app.sh release    # → build/App.app
open build/App.app                # launch (or run the binary directly to see NSLog)
./build/App.app/Contents/MacOS/App   # foreground, prints NSLog to terminal
```

## Why this split pays off
- The pure core compiles in ~1s and runs headless → fast TDD-style iteration.
- All art is drawn by the core, so you can render PNG previews from the CLI and
  *see* your changes without a GUI session or Screen-Recording permission.
- See also: [testing-and-verification.md](testing-and-verification.md),
  [distribution.md](distribution.md).
