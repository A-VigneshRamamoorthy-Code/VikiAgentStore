// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ProductLaunchSwiftFastPath",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "LaunchBuilder", targets: ["LaunchBuilder"])
    ],
    targets: [
        .executableTarget(
            name: "LaunchBuilder",
            linkerSettings: [
                .linkedFramework("AVFoundation"),
                .linkedFramework("AppKit"),
                .linkedFramework("QuartzCore"),
                .linkedFramework("ImageIO")
            ]
        )
    ]
)
