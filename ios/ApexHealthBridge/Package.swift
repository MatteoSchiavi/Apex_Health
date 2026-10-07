// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ApexHealthBridge",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [.library(name: "ApexHealthBridgeCore", targets: ["ApexHealthBridgeCore"])],
    targets: [
        .target(name: "ApexHealthBridgeCore", path: "Sources/Core"),
        .testTarget(name: "ApexHealthBridgeCoreTests", dependencies: ["ApexHealthBridgeCore"], path: "Tests/CoreTests")
    ]
)
