// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "VikiVPN",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "VikiVPN",
            path: "Sources/VikiVPN"
        )
    ]
)
