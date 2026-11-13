#if os(macOS)
import AppKit
#endif
import SwiftUI

enum HomeSheet: String, Identifiable { case history, settings, addPC; var id: String { rawValue } }

struct AtlasHome: View {
    @EnvironmentObject var vpn: VPNController
    @StateObject private var sheet = Box<HomeSheet?>(nil)
    /// Held, not observed: only the map re-renders as the camera moves.
    @State private var motion = MapMotion(framing: .desktop)
    @Namespace private var glassNS

    var body: some View {
        ZStack {
            AtlasViewport(motion: motion, pins: vpn.mapPins, selected: vpn.choice?.id, home: vpn.home,
                          tone: vpn.phase.tone) { id in
                guard vpn.phase == .idle || isFailed else { return }
                vpn.select(id)
            }
            .ignoresSafeArea()

            VStack {
                HStack(alignment: .center) {
                    StatusCapsule(ns: glassNS)
                    Spacer(minLength: 12)
                    GlassGroup(spacing: 10) {
                        HStack(spacing: 10) {
                            CircleButton(icon: "chart.bar.xaxis", help: "Usage") { sheet.v = .history }
                            CircleButton(icon: "gearshape", help: "Settings") { sheet.v = .settings }
                            CircleButton(icon: "plus", help: "Add a home PC", prominent: true) {
                                sheet.v = .addPC
                            }
                            .disabled(vpn.working)
                        }
                    }
                }
                Spacer()
                    .allowsHitTesting(false)
                ConnectCard().frame(maxWidth: 400)
            }
            .padding(18)
        }
        .onChange(of: vpn.phase) { old, p in
            // Connecting zooms gently to the exit so its ripple is in view; back out when idle.
            guard let g = selectedPoint else { return }
            if (p.busy || p == .connected) && !(old.busy || old == .connected) {
                motion.focus(on: g, zoom: max(motion.camera.zoom, 1.6), animated: true, response: 1.1)
            }
        }
        .sheet(item: $sheet.v) { s in
            Group {
                switch s {
                case .history: HistorySheet()
                case .settings: SettingsSheet()
                case .addPC: AddHomeExitSheet()
                }
            }
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

    private var selectedPoint: GeoPoint? { vpn.mapPins.first { $0.id == vpn.choice?.id }?.point }
}
