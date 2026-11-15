// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "AvenVPN",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "AvenVPN",
            path: "Sources/AvenVPN"
        )
    ]
)
