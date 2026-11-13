import SwiftUI

/// Where the iPhone map is looking: the centre in map units (0…1 across the visible world
/// window) and how far it is zoomed in. Animatable, so a zoom re-projects every frame and stays crisp.
struct MapCamera: Equatable {
    var u: CGFloat
    var v: CGFloat
    var zoom: CGFloat

    static let minZoom: CGFloat = 1, maxZoom: CGFloat = 4

    static func centre(on g: GeoPoint, zoom: CGFloat) -> MapCamera {
        let lon = MapProjection.lonSpan, lat = MapProjection.latSpan
        return MapCamera(u: CGFloat((g.lon - lon.0) / (lon.1 - lon.0)),
                         v: CGFloat((lat.0 - g.lat) / (lat.0 - lat.1)), zoom: zoom)
    }

    /// The whole map's size at this zoom: as tall as the screen, so the world pans sideways.
    func mapSize(_ viewport: CGSize) -> CGSize {
        let lon = MapProjection.lonSpan, lat = MapProjection.latSpan
        let aspect = CGFloat((lon.1 - lon.0) / (lat.0 - lat.1))
        let h = viewport.height * 0.78 * zoom
        return CGSize(width: h * aspect, height: h)
    }

    /// Keeps the map covering the screen where it can.
    func clamped(_ viewport: CGSize) -> MapCamera {
        let s = mapSize(viewport)
        func clamp(_ x: CGFloat, _ view: CGFloat, _ map: CGFloat) -> CGFloat {
            let half = view / 2 / map
            return half >= 0.5 ? 0.5 : min(max(x, half), 1 - half)
        }
        return MapCamera(u: clamp(u, viewport.width, s.width), v: clamp(v, viewport.height * 0.8, s.height), zoom: zoom)
    }
}

/// Renders `AtlasMap` at the camera's size and position. Being `Animatable`, a change of camera
/// inside `withAnimation` interpolates zoom and centre together: a smooth fly-to.
struct CameraMap: View, Animatable {
    var camera: MapCamera
    let viewport: CGSize
    let pins: [MapPin]
    let selected: String?
    let home: GeoPoint?
    let tone: MapTone
    let onSelect: (String) -> Void

    var animatableData: AnimatablePair<AnimatablePair<CGFloat, CGFloat>, CGFloat> {
        get { AnimatablePair(AnimatablePair(camera.u, camera.v), camera.zoom) }
        set { camera = MapCamera(u: newValue.first.first, v: newValue.first.second, zoom: newValue.second) }
    }

    var body: some View {
        let s = camera.mapSize(viewport)
        AtlasMap(pins: pins, selected: selected, home: home, tone: tone, onSelect: onSelect)
            .frame(width: s.width, height: s.height)
            .position(x: viewport.width / 2 - (camera.u - 0.5) * s.width,
                      y: viewport.height * 0.4 - (camera.v - 0.5) * s.height)
    }
}
