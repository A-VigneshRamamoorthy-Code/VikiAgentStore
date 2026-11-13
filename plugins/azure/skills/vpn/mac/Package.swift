// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "LeapVPN",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "LeapVPN",
            path: "Sources/LeapVPN"
        )
    ]
)
