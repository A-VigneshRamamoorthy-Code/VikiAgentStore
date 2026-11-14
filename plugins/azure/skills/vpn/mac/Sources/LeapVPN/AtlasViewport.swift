import SwiftUI
#if os(macOS)
import AppKit
#endif

/// The interactive Atlas on the home screens: drag or flick to pan (with momentum and rubber-band
/// edges), pinch / trackpad-magnify / scroll-wheel to zoom at the pointer, double-tap to zoom in,
/// tap a pin to choose it. On the Mac, hovering a pin highlights it and shows its name and flag.
struct AtlasViewport: View {
    @ObservedObject var motion: MapMotion
    let pins: [MapPin]
    let selected: String?
    let home: GeoPoint?
    let tone: MapTone
    let onSelect: (String) -> Void

    @State private var hovered: String?
    @State private var lastDrag: CGSize?
    @State private var pinchBase: CGFloat?

    var body: some View {
        GeometryReader { geo in
            let proj = MapProjection(size: geo.size, camera: motion.camera, framing: motion.framing)
            AtlasLayer(pins: pins, selected: selected, home: home, tone: tone, proj: proj, hovered: hovered, onSelect: onSelect)
                .contentShape(Rectangle())
                .gesture(taps(proj))
                .simultaneousGesture(drag.simultaneously(with: pinch))
                #if os(macOS)
                .onContinuousHover { phase in
                    switch phase {
                    case .active(let p):
                        let id = AtlasLayer.pin(at: p, pins: pins, proj: proj, reach: 22)
                        if id != hovered { hovered = id }
                        (id == nil ? NSCursor.arrow : NSCursor.pointingHand).set()
                    case .ended:
                        hovered = nil
                        NSCursor.arrow.set()
                    }
                }
                .background(MapScrollCatcher(motion: motion))
                #endif
                .onAppear { motion.layout(geo.size) }
                .onChange(of: geo.size) { _, s in motion.layout(s) }
        }
        .background(Atlas.background)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Map of locations")
        .accessibilityAction(named: "Zoom in") { motion.zoom(by: 2) }
        .accessibilityAction(named: "Zoom out") { motion.zoom(by: 0.5) }
    }

    private func taps(_ proj: MapProjection) -> some Gesture {
        SpatialTapGesture(count: 2)
            .onEnded { e in motion.zoom(by: 2, at: e.location) }
            .simultaneously(with: SpatialTapGesture(count: 1).onEnded { e in
                if let id = AtlasLayer.pin(at: e.location, pins: pins, proj: proj, reach: Platform.isPhone ? 26 : 20) {
                    onSelect(id)
                }
            })
    }

    private var drag: some Gesture {
        DragGesture(minimumDistance: Platform.isPhone ? 4 : 2)
            .onChanged { g in
                let last = lastDrag ?? .zero
                lastDrag = g.translation
                motion.pan(by: CGSize(width: g.translation.width - last.width, height: g.translation.height - last.height))
            }
            .onEnded { g in
                lastDrag = nil
                if pinchBase == nil { motion.release(velocity: g.velocity) }
            }
    }

    private var pinch: some Gesture {
        MagnifyGesture()
            .onChanged { g in
                let base = pinchBase ?? motion.camera.zoom
                if pinchBase == nil { pinchBase = base }
                motion.pinch(to: base * g.magnification, at: g.startLocation)
            }
            .onEnded { _ in
                pinchBase = nil
                if lastDrag == nil { motion.release() }
            }
    }
}

#if os(macOS)
/// Trackpad two-finger scroll pans (with our own momentum and edges); a mouse wheel, or scrolling
/// with ⌘ or ⌥ held, zooms at the pointer. SwiftUI has no scroll-wheel gesture, so this listens
/// for the window's scroll events over the map's bounds.
private struct MapScrollCatcher: NSViewRepresentable {
    let motion: MapMotion

    func makeNSView(context: Context) -> CatcherView {
        let v = CatcherView()
        v.motion = motion
        return v
    }

    func updateNSView(_ v: CatcherView, context: Context) { v.motion = motion }

    final class CatcherView: NSView {
        weak var motion: MapMotion?
        private var monitor: Any?
        private var velocity = CGSize.zero
        private var lastTime: TimeInterval = 0
        private var zooming = false

        override var isFlipped: Bool { true }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if let monitor { NSEvent.removeMonitor(monitor); self.monitor = nil }
            guard window != nil else { return }
            monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { [weak self] e in
                guard let self else { return e }
                return self.handle(e) ? nil : e
            }
        }

        deinit { if let monitor { NSEvent.removeMonitor(monitor) } }

        private func handle(_ e: NSEvent) -> Bool {
            guard let motion, let window, e.window === window, window.attachedSheet == nil else { return false }
            let p = convert(e.locationInWindow, from: nil)
            guard bounds.contains(p) else { return false }
            // Leave anything that scrolls on its own (lists in popovers, etc.) alone.
            if let hit = window.contentView?.hitTest(e.locationInWindow), hit.enclosingScrollView != nil { return false }

            let wantsZoom = !e.hasPreciseScrollingDeltas || !e.modifierFlags.intersection([.command, .option]).isEmpty
            if wantsZoom {
                if e.hasPreciseScrollingDeltas {
                    guard e.momentumPhase.isEmpty else { return true }
                    if e.phase == .began || !zooming { zooming = true; motion.beginInteraction() }
                    let f = exp(e.scrollingDeltaY * 0.012)
                    motion.pinch(to: motion.camera.zoom * f, at: p)
                    if e.phase == .ended || e.phase == .cancelled { zooming = false; motion.release() }
                } else {
                    let f = pow(1.25, max(-3, min(3, e.scrollingDeltaY)))
                    motion.zoom(by: f, at: p, response: 0.38)
                }
                return true
            }

            // Our own momentum replaces the system's, so the edges can bounce.
            guard e.momentumPhase.isEmpty else { return true }
            let d = CGSize(width: e.scrollingDeltaX, height: e.scrollingDeltaY)
            switch e.phase {
            case .began, .mayBegin:
                motion.beginInteraction()
                velocity = .zero
                lastTime = e.timestamp
            case .ended, .cancelled:
                // A pause before lifting the fingers means no flick.
                motion.release(velocity: e.timestamp - lastTime > 0.08 ? .zero : velocity)
                return true
            default:
                break
            }
            motion.pan(by: d)
            let dt = max(1.0 / 240, e.timestamp - lastTime)
            lastTime = e.timestamp
            let k = 0.35
            velocity = CGSize(width: velocity.width * (1 - k) + d.width / dt * k,
                              height: velocity.height * (1 - k) + d.height / dt * k)
            if e.phase.isEmpty { motion.release() }
            return true
        }
    }
}
#endif
