import SwiftUI

struct PhoneHome: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var sheet = Box<HomeSheet?>(nil)
    @StateObject private var cam = Box(MapCamera(u: 0.55, v: 0.4, zoom: 1))
    @StateObject private var gestureStart = Box<MapCamera?>(nil)
    @StateObject private var pinchStart = Box<MapCamera?>(nil)
    @Namespace private var glassNS

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Atlas.background.ignoresSafeArea()
                CameraMap(camera: cam.v, viewport: geo.size, pins: vpn.mapPins, selected: vpn.choice?.id,
                          home: vpn.home, tone: vpn.phase.tone) { id in
                    guard vpn.phase == .idle || isFailed else { return }
                    vpn.select(id)
                }
                .contentShape(Rectangle())
                .gesture(pan(geo.size).simultaneously(with: pinch(geo.size)))
                .accessibilityLabel("Map of locations")

                VStack(spacing: 0) {
                    HStack(alignment: .center) {
                        StatusCapsule(ns: glassNS)
                        Spacer(minLength: 8)
                        GlassGroup(spacing: 10) {
                            HStack(spacing: 10) {
                                CircleButton(icon: "chart.bar.xaxis", help: "Usage") { sheet.v = .history }
                                CircleButton(icon: "gearshape", help: "Settings") { sheet.v = .settings }
                                CircleButton(icon: "plus", help: "Add a home PC", prominent: true) { sheet.v = .addPC }
                                    .disabled(vpn.working)
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    Spacer()
                    ConnectCard().padding(.horizontal, 12).padding(.bottom, 8)
                }
            }
            .onAppear { focusSelection(geo.size, zoom: 1, animated: false) }
            .onChange(of: vpn.phase) { _, p in
                switch p {
                case .idle: focusSelection(geo.size, zoom: 1.2, animated: true)
                default: if p.busy || p == .connected { focusSelection(geo.size, zoom: 2.6, animated: true) }
                }
            }
            .onChange(of: vpn.choice?.id) { _, _ in
                if !vpn.phase.busy { focusSelection(geo.size, zoom: max(cam.v.zoom, 1), animated: true) }
            }
        }
        .sheet(item: $sheet.v) { s in
            NavigationStack {
                Group {
                    switch s {
                    case .history: HistorySheet()
                    case .settings: SettingsSheet()
                    case .addPC: AddHomeExitSheet()
                    }
                }
                .toolbar(.hidden, for: .navigationBar)
            }
            .presentationDetents([.large])
            .environmentObject(vpn)
        }
        .onReceive(vpn.$requestedSheet.compactMap { $0 }) { s in
            sheet.v = s
            vpn.requestedSheet = nil
        }
        .onReceive(vpn.$sheetDismissals.dropFirst()) { _ in sheet.v = nil }
        .animation(.spring(duration: 0.4), value: vpn.phase)
    }

    private var isFailed: Bool { if case .failed = vpn.phase { return true }; return false }

    /// Flies the camera to the chosen location (or home), e.g. a smooth zoom-in on Connect.
    private func focusSelection(_ viewport: CGSize, zoom: CGFloat, animated: Bool) {
        let target = vpn.mapPins.first { $0.id == vpn.choice?.id }?.point ?? vpn.home
        guard let target else { return }
        let next = MapCamera.centre(on: target, zoom: zoom).clamped(viewport)
        if animated { withAnimation(.smooth(duration: 1.1)) { cam.v = next } } else { cam.v = next }
    }

    private func pan(_ viewport: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 6)
            .onChanged { g in
                let start = gestureStart.v ?? cam.v
                if gestureStart.v == nil { gestureStart.v = start }
                let s = start.mapSize(viewport)
                cam.v = MapCamera(u: start.u - g.translation.width / s.width,
                                  v: start.v - g.translation.height / s.height, zoom: cam.v.zoom).clamped(viewport)
            }
            .onEnded { _ in gestureStart.v = nil }
    }

    private func pinch(_ viewport: CGSize) -> some Gesture {
        MagnifyGesture()
            .onChanged { g in
                let start = pinchStart.v ?? cam.v
                if pinchStart.v == nil { pinchStart.v = start }
                let z = min(MapCamera.maxZoom, max(MapCamera.minZoom, start.zoom * g.magnification))
                cam.v = MapCamera(u: cam.v.u, v: cam.v.v, zoom: z).clamped(viewport)
            }
            .onEnded { _ in pinchStart.v = nil }
    }
}
