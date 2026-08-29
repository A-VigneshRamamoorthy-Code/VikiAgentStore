// Background removal via Vision's foreground instance mask.
//
// The thumbnail needs real photographic subjects lifted off their backgrounds.
// Vision does this offline on-device, so no footage leaves the machine and no
// third-party service is involved.
//
//   swiftc -O -o cutout cutout.swift
//   ./cutout in.png outprefix          # writes outprefix.png (all instances)
//                                      # and outprefix_1.png ... per instance
import AppKit
import CoreImage
import Foundation
import Vision

func write(_ buf: CVPixelBuffer, _ path: String) {
    let ci = CIImage(cvPixelBuffer: buf)
    let ctx = CIContext()
    guard let data = ctx.pngRepresentation(
        of: ci, format: .RGBA8,
        colorSpace: CGColorSpaceCreateDeviceRGB()) else {
        FileHandle.standardError.write("encode failed\n".data(using: .utf8)!)
        return
    }
    try? data.write(to: URL(fileURLWithPath: path))
    print(path, Int(ci.extent.width), Int(ci.extent.height))
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    print("usage: cutout <image> <outprefix>")
    exit(2)
}
let url = URL(fileURLWithPath: args[1])
let prefix = args[2]

let handler = VNImageRequestHandler(url: url, options: [:])
let request = VNGenerateForegroundInstanceMaskRequest()
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(1)
}
guard let obs = request.results?.first else {
    FileHandle.standardError.write("no foreground found\n".data(using: .utf8)!)
    exit(1)
}

// The combined mask first, then each instance on its own -- a scatter of
// banknotes is one observation with many instances, and they are only useful
// separately.
if let all = try? obs.generateMaskedImage(ofInstances: obs.allInstances,
                                          from: handler,
                                          croppedToInstancesExtent: true) {
    write(all, "\(prefix).png")
}
for (n, i) in obs.allInstances.enumerated() {
    if let one = try? obs.generateMaskedImage(ofInstances: [i], from: handler,
                                              croppedToInstancesExtent: true) {
        write(one, "\(prefix)_\(n + 1).png")
    }
}
