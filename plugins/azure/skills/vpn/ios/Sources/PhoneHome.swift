import SwiftUI

struct PhoneHome: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var sheet = Box<HomeSheet?>(nil)
    /// Held, not observed: only the map re-renders as the camera moves.
    @State private var motion = MapMotion(framing: .phone)
    @Namespace private var glassNS

    /// Resting zoom when idle: close enough that nearby locations are named.
    private static let idleZoom: CGFloat = 1.2
    private static let connectZoom: CGFloat = 2.6

    var body: some View {
        ZStack {
            AtlasViewport(motion: motion, pins: vpn.mapPins, selected: vpn.choice?.id, home: vpn.home,
                          tone: vpn.phase.tone) { id in
                guard vpn.phase == .idle || isFailed else { return }
                vpn.select(id)
            }
            .ignoresSafeArea()

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
                Spacer(minLength: 0)
                    .allowsHitTesting(false)
                // Docked: flush with the screen's bottom and sides, following its corner radius.
                // Its glass runs under the home indicator; the controls stay inside the safe area.
                ConnectCard(docked: true)
            }
        }
        .onAppear { focusSelection(zoom: Self.idleZoom, animated: false) }
        .onChange(of: vpn.phase) { old, p in
            let wasActive = old.busy || old == .connected
            if p.busy || p == .connected {
                if !wasActive { focusSelection(zoom: Self.connectZoom, animated: true, response: 1.1) }
            } else if p == .idle {
                focusSelection(zoom: Self.idleZoom, animated: true, response: 0.9)
            }
        }
        .onChange(of: vpn.choice?.id) { _, _ in
            if !vpn.phase.busy { focusSelection(zoom: max(motion.camera.zoom, Self.idleZoom), animated: true, response: 0.7) }
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
            .presentationDetents(s == .addPC ? [.medium, .large] : [.large])
            .presentationDragIndicator(.visible)
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
    /// With nothing to show, frames the world so the map is never stuck at an unpannable zoom.
    private func focusSelection(zoom: CGFloat, animated: Bool, response: CGFloat = 0.9) {
        let target = vpn.mapPins.first { $0.id == vpn.choice?.id }?.point ?? vpn.home
        let cam = target.map { MapCamera.centre(on: $0, zoom: zoom) } ?? MapCamera(u: 0.55, v: 0.4, zoom: zoom)
        motion.show(cam, animated: animated, response: response)
    }
}
