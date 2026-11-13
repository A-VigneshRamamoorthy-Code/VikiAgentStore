---
name: vpn
description: >
  Leap VPN — a personal on-demand WireGuard VPN that runs in the user's own Azure
  subscription and costs nothing in compute while nobody is connected. A native macOS app
  (SwiftUI + NetworkExtension) signs the user in with their Microsoft account (work, school
  or personal), shows every Azure region that can host the server on an Atlas map, builds or
  starts only the region the user picks, and deallocates (or, with "provision once", deletes)
  it as soon as no device holds a session lease. Home Windows PCs can be added as residential exit nodes for streaming.
  Shows Azure credits, per-session cost and usage history. Use when building, operating,
  debugging or extending Leap VPN (LeapVPN), adding regions, or porting it to iOS/Android.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Leap VPN — on-demand VPN on your own Azure subscription

The guarantee: **a region's VM is deallocated whenever no device is connected to it.**
With **provision once** (the default, per location) the whole `leapvpn-<code>` group is
deleted instead, so the region costs nothing idle; otherwise only its disk (and a static IP,
if that location keeps one) bills while idle.

```
Mac app ──ARM (user token)──▶ start VM ─┐
   │  lease blob leases/<region>/<device> (renew 45 s, TTL 180 s)
   └──WireGuard (NetworkExtension)──────▶ VM agent ──no live lease 45 s──▶ deallocates itself
                                              │  (managed identity, no secrets)
                                    deadman timer + hourly reconciler = backstops
```

| Region | Azure location | Code |
|--------|---------------|------|
| 🇮🇳 India | centralindia | `in` |
| 🇳🇱 Netherlands | westeurope | `nl` |
| 🇺🇸 United States | eastus | `us` |
| 🇨🇦 Canada | canadacentral | `ca` |
| … ~40 in total | `RegionChoice.all` in `Config.swift` | e.g. `uk` = uksouth |

Any region in `RegionChoice.all` appears on the map and is enrolled the first time it is
connected; the four above were the original set.

## Layout

| Path | What |
|------|------|
| `mac/` | SwiftUI app + `Tunnel/` packet-tunnel extension (WireGuardKit). `./build.sh` builds, signs and installs `/Applications/Leap VPN.app` |
| `server/` | Files pushed into every VM: `agent.py` (leases, peers, self-deallocate, home-exit routing), `deadman.py` + timer, `firewall.sh` |
| `homeexit/Install-LeapVPNExit.ps1` | No-admin Windows installer that turns a home PC into an exit node |
| `reconciler/Reconcile-LeapVPN.ps1` | Hourly Azure Automation runbook that deallocates any VM left running without a lease |
| `scripts/vpnctl.py` | **Legacy** dev CLI from before in-app provisioning (uses `az`). Kept for diagnostics only |
| `reference/` | Deeper docs — load only what you need |

## Reference modules

- [architecture.md](reference/architecture.md) — leases, the agent, the three stop mechanisms, connect/teardown flow, crash handling
- [sign-in.md](reference/sign-in.md) — Microsoft sign-in, personal accounts, tenants and consent, what is stored where
- [costs.md](reference/costs.md) — session cost model, credits, idle residual cost
- [home-exits.md](reference/home-exits.md) — home PCs as exits, and what streaming services do with Azure IPs
- [operations.md](reference/operations.md) — building, upgrading servers, test hooks, validation checklist, gotchas

## Rules when changing it

1. **Never add a path that can leave a VM running.** Any new "keep alive" reason must be a
   lease with a TTL, never a flag.
2. **No credentials in the app or repo.** Everything comes from the signed-in user's token;
   servers use their managed identity. The public client ID is the only embedded identifier.
3. Bump `Provisioner.agentVersion` whenever `server/` changes; the app upgrades a region the
   next time it is connected.
4. Re-validate: connect → correct egress country → disconnect → `deallocated` within ~1 min
   (provision once: resource group gone within ~3 min).
