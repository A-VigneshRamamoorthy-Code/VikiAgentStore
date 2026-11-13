import QuartzCore
import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// Where the map is looking: the centre in map units (0…1 across the world window) and the zoom,
/// where zoom 1 is the screen's natural framing (see `MapFraming`).
struct MapCamera: Equatable {
    var u: CGFloat
    var v: CGFloat
    var zoom: CGFloat

    static let world = MapCamera(u: 0.5, v: 0.5, zoom: 1)

    static func centre(on g: GeoPoint, zoom: CGFloat) -> MapCamera {
        MapCamera(u: MapProjection.u(g.lon), v: MapProjection.v(g.lat), zoom: zoom)
    }
}

/// How a screen frames the world at zoom 1, and which parts of it are covered by chrome.
struct MapFraming: Equatable {
    enum Fit: Equatable {
        /// The whole world fits (Mac window).
        case whole
        /// The world is this fraction of the screen's height and pans sideways (iPhone).
        case height(CGFloat)
    }
    var fit: Fit
    /// Points at the top covered by the toolbar / status bar.
    var topInset: CGFloat
    /// Fraction of the height at the bottom covered by the connect panel.
    var bottomFraction: CGFloat
    var maxZoom: CGFloat

    static let desktop = MapFraming(fit: .whole, topInset: 64, bottomFraction: 0, maxZoom: 6)
    static let phone = MapFraming(fit: .height(0.78), topInset: 110, bottomFraction: 0.3, maxZoom: 5)
}

/// Drives the camera with real physics: rubber-band edges, momentum after a fling, springs for
/// fly-to and zoom, all on the display link so gestures stay at the screen's frame rate.
/// Only the map view observes it, so a moving camera never re-renders the rest of the screen.
final class MapMotion: NSObject, ObservableObject {
    @Published private(set) var camera: MapCamera
    @Published private(set) var isMoving = false
    let framing: MapFraming
    private(set) var size: CGSize = .zero

    /// Content velocity in points per second while coasting.
    private var velocity = CGVector.zero
    private var zoomVelocity: CGFloat = 0
    private var zoomAnchor: CGPoint?
    private var target: MapCamera?
    private var targetVelocity = (u: CGFloat(0), v: CGFloat(0), z: CGFloat(0))
    private var omega: CGFloat = 7
    private var zeta: CGFloat = 1
    private var link: CADisplayLink?
    private var lastTick: CFTimeInterval = 0
    private var interacting = false

    init(framing: MapFraming, camera: MapCamera = .world) {
        self.framing = framing
        self.camera = camera
    }

    var projection: MapProjection { MapProjection(size: size, camera: camera, framing: framing) }

    // MARK: layout

    func layout(_ newSize: CGSize) {
        guard newSize.width > 0, newSize.height > 0, newSize != size else { return }
        size = newSize
        if let t = target { target = clamped(t) }
        camera = clamped(camera)
    }

    // MARK: programmatic moves

    /// Moves to a camera, either at once or on a spring (`response` in seconds; damping 1 = no overshoot).
    func show(_ cam: MapCamera, animated: Bool, response: CGFloat = 0.9, damping: CGFloat = 1) {
        let next = size == .zero ? cam : clamped(cam)
        guard animated, size != .zero else {
            stop()
            camera = next
            return
        }
        velocity = .zero
        zoomVelocity = 0
        if target == nil { targetVelocity = (0, 0, 0) }
        target = next
        omega = 2 * .pi / max(0.1, response)
        zeta = damping
        startLink()
    }

    func focus(on g: GeoPoint, zoom: CGFloat, animated: Bool, response: CGFloat = 0.9) {
        show(.centre(on: g, zoom: zoom), animated: animated, response: response)
    }

    /// Zooms by a factor about a screen point, on a bouncy spring (double-click, wheel, +/-).
    func zoom(by factor: CGFloat, at anchor: CGPoint? = nil, response: CGFloat = 0.45) {
        guard size != .zero else { return }
        let base = target ?? camera
        let range = zoomRange
        let z = min(range.upperBound, max(range.lowerBound, base.zoom * factor))
        show(zoomed(base, to: z, at: anchor ?? centrePoint), animated: true, response: response, damping: 0.82)
    }

    // MARK: gestures

    func beginInteraction() {
        interacting = true
        stop()
    }

    /// Moves the content by a screen delta, with resistance past the edges.
    func pan(by d: CGSize) {
        guard size != .zero else { return }
        if !interacting { beginInteraction() }
        let p = projection, m = p.mapSize, b = bounds(for: camera.zoom)
        var c = camera
        c.u -= resisted(d.width, value: c.u, range: b.u, scale: m.width) / m.width
        c.v -= resisted(d.height, value: c.v, range: b.v, scale: m.height) / m.height
        camera = c
    }

    /// Sets the zoom while a pinch is in progress, keeping `anchor` fixed; elastic past the limits.
    func pinch(to rawZoom: CGFloat, at anchor: CGPoint) {
        guard size != .zero else { return }
        if !interacting { beginInteraction() }
        let r = zoomRange
        var z = rawZoom
        if z > r.upperBound { z = r.upperBound * pow(z / r.upperBound, 0.3) }
        if z < r.lowerBound { z = r.lowerBound / pow(r.lowerBound / z, 0.3) }
        zoomAnchor = anchor
        camera = zoomed(camera, to: z, at: anchor)
    }

    /// Lets go: coasts with the given content velocity, then settles back inside the edges.
    func release(velocity v: CGSize = .zero) {
        interacting = false
        let cap: CGFloat = 5000
        velocity = CGVector(dx: max(-cap, min(cap, v.width)), dy: max(-cap, min(cap, v.height)))
        startLink()
    }

    // MARK: geometry

    var zoomRange: ClosedRange<CGFloat> {
        let p = MapProjection(size: size, camera: .world, framing: framing)
        let fitWhole = min(1, p.wholeWorldZoom)
        return fitWhole...framing.maxZoom
    }

    private var centrePoint: CGPoint { projection.centre }

    func bounds(for zoom: CGFloat) -> (u: ClosedRange<CGFloat>, v: ClosedRange<CGFloat>) {
        var c = camera
        c.zoom = zoom
        let p = MapProjection(size: size, camera: c, framing: framing)
        let m = p.mapSize, ctr = p.centre
        let pad: CGFloat = 28
        var uLo = (ctr.x - pad) / m.width, uHi = 1 - (size.width - ctr.x - pad) / m.width
        if uLo > uHi { uLo = 0.5; uHi = 0.5 }
        let bandBottom = size.height * (1 - framing.bottomFraction)
        var vLo = (ctr.y - framing.topInset - pad) / m.height
        var vHi = 1 - (bandBottom - ctr.y - pad) / m.height
        if vLo > vHi { vLo = 0.5; vHi = 0.5 }
        return (uLo...uHi, vLo...vHi)
    }

    func clamped(_ c: MapCamera) -> MapCamera {
        guard size != .zero else { return c }
        let r = zoomRange
        var n = c
        n.zoom = min(r.upperBound, max(r.lowerBound, c.zoom))
        let b = bounds(for: n.zoom)
        n.u = min(b.u.upperBound, max(b.u.lowerBound, n.u))
        n.v = min(b.v.upperBound, max(b.v.lowerBound, n.v))
        return n
    }

    /// The camera at zoom `z` that keeps the map point under `anchor` where it is.
    func zoomed(_ c: MapCamera, to z: CGFloat, at anchor: CGPoint) -> MapCamera {
        let p0 = MapProjection(size: size, camera: c, framing: framing)
        let m = p0.mapUnits(at: anchor)
        var n = c
        n.zoom = z
        let p1 = MapProjection(size: size, camera: n, framing: framing)
        let s = p1.mapSize, ctr = p1.centre
        n.u = m.u - (anchor.x - ctr.x) / s.width
        n.v = m.v - (anchor.y - ctr.y) / s.height
        return n
    }

    /// Past an edge each point of finger travel moves the map less and less, like a scroll view.
    private func resisted(_ d: CGFloat, value: CGFloat, range: ClosedRange<CGFloat>, scale: CGFloat) -> CGFloat {
        let next = value - d / scale
        let outward = (next < range.lowerBound && d > 0) || (next > range.upperBound && d < 0)
        guard outward else { return d }
        let over = max(range.lowerBound - value, value - range.upperBound, 0) * scale
        let k = 1 / (1 + over / 110)
        return d * 0.55 * k * k
    }

    // MARK: animation

    private func stop() {
        target = nil
        velocity = .zero
        zoomVelocity = 0
        link?.invalidate()
        link = nil
        if isMoving { isMoving = false }
    }

    private func startLink() {
        if !isMoving { isMoving = true }
        guard link == nil else { return }
        #if os(macOS)
        guard let screen = NSScreen.main ?? NSScreen.screens.first else { settleNow(); return }
        let l = screen.displayLink(target: self, selector: #selector(tick(_:)))
        #else
        let l = CADisplayLink(target: self, selector: #selector(tick(_:)))
        l.preferredFrameRateRange = CAFrameRateRange(minimum: 60, maximum: 120, preferred: 120)
        #endif
        lastTick = 0
        l.add(to: .main, forMode: .common)
        link = l
    }

    private func settleNow() {
        camera = clamped(target ?? camera)
        target = nil
        velocity = .zero
        isMoving = false
    }

    @objc private func tick(_ l: CADisplayLink) {
        let now = l.timestamp
        let dt = lastTick == 0 ? 1.0 / 60 : min(1.0 / 20, max(1.0 / 480, now - lastTick))
        lastTick = now
        guard size != .zero else { settleNow(); stop(); return }
        var remaining = CGFloat(dt)
        var done = false
        while remaining > 0, !done {
            let h = min(remaining, 1.0 / 240)
            remaining -= h
            done = target != nil ? stepTarget(h) : stepCoast(h)
        }
        if done { stop() }
    }

    /// Spring towards `target`, zooming in log space so a zoom feels even at every scale.
    private func stepTarget(_ h: CGFloat) -> Bool {
        guard let t = target else { return true }
        let k = omega * omega, c = 2 * zeta * omega
        var cam = camera
        func spring(_ x: inout CGFloat, _ v: inout CGFloat, _ goal: CGFloat) {
            v += (-k * (x - goal) - c * v) * h
            x += v * h
        }
        spring(&cam.u, &targetVelocity.u, t.u)
        spring(&cam.v, &targetVelocity.v, t.v)
        var lz = log(cam.zoom)
        spring(&lz, &targetVelocity.z, log(t.zoom))
        cam.zoom = exp(lz)
        let m = MapProjection(size: size, camera: cam, framing: framing).mapSize
        let close = abs(cam.u - t.u) * m.width < 0.25 && abs(cam.v - t.v) * m.height < 0.25
            && abs(lz - log(t.zoom)) < 0.0008
        let slow = abs(targetVelocity.u) * m.width < 4 && abs(targetVelocity.v) * m.height < 4
            && abs(targetVelocity.z) < 0.01
        if close && slow {
            camera = t
            target = nil
            targetVelocity = (0, 0, 0)
            return true
        }
        camera = cam
        return false
    }

    /// Momentum with friction inside the edges, and a slightly bouncy spring outside them.
    private func stepCoast(_ h: CGFloat) -> Bool {
        var cam = camera
        // Zoom first: spring back inside the limits around the last pinch point.
        let r = zoomRange
        var zoomSettled = true
        if cam.zoom > r.upperBound + 0.0001 || cam.zoom < r.lowerBound - 0.0001 || abs(zoomVelocity) > 0.01 {
            let goal = log(min(r.upperBound, max(r.lowerBound, cam.zoom)))
            let w: CGFloat = 2 * .pi / 0.38, z: CGFloat = 0.9
            var lz = log(cam.zoom)
            zoomVelocity += (-w * w * (lz - goal) - 2 * z * w * zoomVelocity) * h
            lz += zoomVelocity * h
            cam = zoomed(cam, to: exp(lz), at: zoomAnchor ?? centrePoint)
            zoomSettled = abs(lz - goal) < 0.0008 && abs(zoomVelocity) < 0.01
            if zoomSettled { cam = zoomed(cam, to: exp(goal), at: zoomAnchor ?? centrePoint); zoomVelocity = 0 }
        }

        let m = MapProjection(size: size, camera: cam, framing: framing).mapSize
        let b = bounds(for: cam.zoom)
        // Work in points of content offset: content moving right means u decreasing.
        var pu = -cam.u * m.width, pv = -cam.v * m.height
        let lu = (-b.u.upperBound * m.width)...(-b.u.lowerBound * m.width)
        let lv = (-b.v.upperBound * m.height)...(-b.v.lowerBound * m.height)
        let settledU = coast(&pu, &velocity.dx, lu, h)
        let settledV = coast(&pv, &velocity.dy, lv, h)
        cam.u = -pu / m.width
        cam.v = -pv / m.height
        camera = cam
        return zoomSettled && settledU && settledV
    }

    private func coast(_ x: inout CGFloat, _ v: inout CGFloat, _ range: ClosedRange<CGFloat>, _ h: CGFloat) -> Bool {
        let edge = min(range.upperBound, max(range.lowerBound, x))
        if x != edge {
            let w: CGFloat = 2 * .pi / 0.42, z: CGFloat = 0.78
            v += (-w * w * (x - edge) - 2 * z * w * v) * h
            x += v * h
            if abs(x - edge) < 0.3 && abs(v) < 6 { x = edge; v = 0 }
            return x == edge && v == 0
        }
        x += v * h
        v *= exp(-4.2 * h)
        if abs(v) < 6 { v = 0 }
        return v == 0 && range.contains(x)
    }
}
