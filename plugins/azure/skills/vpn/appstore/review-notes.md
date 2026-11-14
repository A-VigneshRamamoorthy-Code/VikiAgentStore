# App Review notes — Leap VPN (iOS and macOS, one app record 6834297538)

Paste into App Review Information → Notes (4000-char limit; this is ~2,600). The same text works for both platforms, and the platform-specific lines are marked.

---

Leap VPN is not a VPN service. The developer runs no VPN servers, has no user accounts and never sees, routes or stores user traffic. The app is a client and provisioner for infrastructure that the user owns.

HOW IT WORKS
1. The user signs in with their own Microsoft account (Microsoft identity platform, OAuth with PKCE). The app calls Azure Resource Manager directly from the device and creates WireGuard servers in the user's own Azure subscription, in regions the user picks.
2. WireGuard keys are generated on the device. The private key stays in the device Keychain, and the server's key stays on the server inside the user's subscription.
3. When the user connects, the app starts that server. When they disconnect, it stops (deallocates) it, so nothing runs or bills while the VPN is off. A watchdog on the server stops it by itself if no device has connected for a few minutes.
4. Azure bills the user directly. We receive no money from Azure usage and have no access to the user's subscription after the app's own on-device session.

WHY GUIDELINE 5.4 IS SATISFIED
We read 5.4 as being about apps that offer a VPN service: they route users' traffic through infrastructure the developer controls, and so they must come from an organization that is accountable for that traffic. Leap VPN offers no such service. It is closer to an SSH or WireGuard client combined with a cloud-console app. Every server belongs to the user, sits in the user's cloud account and is administered by the user. The developer cannot reach the servers or the traffic, and collects no data (App Privacy: Data Not Collected).
- The app uses NEPacketTunnelProvider only to bring up the tunnel to the user's own server.
- It does not sell or share user data, and it does not route traffic through third parties.
- The optional DNS ad and tracker filter runs on the user's own server. Queries are not logged.

SUBSCRIPTION
Leap VPN Plus ($0.99/month or $9.99/year, one subscription group shared by iPhone and Mac) starts with a 2-week free trial (App Store introductory offer). Signing in and setting up servers are free; connecting the VPN requires an active subscription or trial. Tapping Connect without one opens the subscription screen, which is also reachable from the Upgrade button in the top-left corner of the home screen (iOS) or the main window (macOS). Sandbox: start the free trial on that screen, then connect.
It shows the terms, restore, and the Terms of Use and Privacy links.

HOW TO REVIEW
[OPTION A — fill in only if you provide a demo account: Microsoft account email / password for a demo Azure subscription with credit. Sign in → pick India → Continue → start the free trial when asked. The first build takes about 2 minutes, after which the VPN connects and the IP becomes Indian. Disconnect, and the server stops.]

[OPTION B — no Azure account available] Using the app requires the reviewer's own Microsoft Azure subscription, because the app creates resources in it. Steps:
- Free Azure trial: https://azure.microsoft.com/free
- Sign in with that account → pick any location → Continue → tap Connect → start the free trial (sandbox) → the VPN connects.
- A screen recording of the full flow is attached for convenience.

Face ID / Touch ID protects the app. Tap the lock and authenticate, or use the device passcode.

Contact: [name] · [phone] · [email]
