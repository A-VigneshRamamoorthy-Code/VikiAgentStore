import SwiftUI

@main
struct LeapVPNApp: App {
    @StateObject private var vpn = VPNController()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(vpn)
                .onOpenURL { vpn.handle(url: $0) }
                #if DEBUG
                // Test aid: `-LeapOpenURL leapvpn://…` runs a hook at launch, skipping the system's "Open in" prompt.
                .task {
                    guard let s = UserDefaults.standard.string(forKey: "LeapOpenURL"), let u = URL(string: s) else { return }
                    try? await Task.sleep(for: .seconds(1.5))
                    vpn.handle(url: u)
                }
                #endif
                .alert(item: $vpn.pendingPair) { p in
                    Alert(title: Text("Add \(p.name)?"),
                          message: Text("Only add a PC you set up yourself. Traffic will go to \(p.endpoint)."),
                          primaryButton: .default(Text("Add")) { vpn.confirmPair(p.link) },
                          secondaryButton: .cancel { vpn.pendingPair = nil })
                }
        }
    }
}
