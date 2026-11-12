# Architecture

## Resources (all tagged `vikivpn=1`, in the user's subscription)

| Resource group | Contents |
|----------------|----------|
| `vikivpn-ctl` (centralindia) | Storage account: containers `config` (`regions.json`, `peers.json`), `leases`, `exits`. Automation account `vikivpn-reconciler` with the hourly runbook. Custom role **VikiVPN Stopper** (read + deallocate VMs) |
| `vikivpn-<code>` | Ubuntu 24.04 VM `Standard_B2ats_v2`, 30 GB StandardSSD, Standard static public IP, NSG (UDP 51820 + SSH for home exits), VNet. System-assigned identity holding the Stopper role on its own RG and blob access to the control storage |

## Leases — the only thing that keeps a VM alive

A lease is a blob `leases/<region>/<deviceId>`. Its server-side Last-Modified time is the
heartbeat. The app writes it **before** starting the VM and rewrites it every 45 s.

The agent (`server/agent.py`, every 15 s) counts a lease as active when:

- it is younger than `LEASE_TTL` (180 s), **and**
- the device's WireGuard handshake is recent (`HANDSHAKE_MAX` 300 s), **or** the lease is
  younger than `CONNECT_GRACE` (300 s) — covers the boot + first handshake window.
- `_`-prefixed leases (`_setup`, used while provisioning/upgrading) always count.

No active lease for `IDLE_DEBOUNCE` (45 s) → the VM deallocates **itself** through its
managed identity (`IMDS` token → ARM `deallocate`). Multiple devices simply mean multiple
leases; the VM stops only when the last one goes.

## Three independent stop mechanisms

| Mechanism | Fires when | Survives |
|-----------|-----------|----------|
| Agent self-deallocate | No live lease for 45 s | App crash, laptop sleep/lid close, network loss (lease expires in ≤180 s) |
| `deadman.py` (systemd timer, every 2 min) | Agent's `status.json` older than 600 s | Agent hang or crash. Age is clamped by uptime because the guest clock jumps hours after resume from deallocation |
| Reconciler runbook (hourly, Azure Automation, managed identity) | A VPN VM is running with no live lease (and not started in the last 15 min), or is `stopped` but still allocated | VM-side failure of both of the above |

Measured: disconnect → deallocated in 44–56 s; app force-killed → deallocated in ~4 min.

## Connect flow (`VPNController.connect`)

1. Put lease (with `exit` metadata when a home exit was chosen) and start renewing.
2. ARM `start` if the VM isn't running; wait for `PowerState/running`.
3. `Tunnel.up` — installs/updates the `NETunnelProviderManager` and starts the packet
   tunnel. Peers are synced by the agent immediately at boot.
4. Wait for a handshake (≤150 s), then verify egress country via ipinfo.
5. `upgradeIfOutdated` — background agent upgrade when `regions.json` has an older
   `agentVersion` than the app.

Disconnect: drop tunnel → delete lease → follow the VM to `deallocated` to time the session.
Sleep: tear down before sleep, reconnect on wake if the user wanted it.

## Crash handling

- **Server side**: the lease expires; the VM deallocates (above).
- **Client side**: the packet tunnel's watchdog cancels itself after 200 s without a
  handshake, so a dead server never leaves the Mac without DNS/internet. On the next launch
  the app drops any orphaned tunnel and closes orphaned sessions using the real deallocation
  time from the ARM activity log.

## Porting to iOS / Android

Everything a client needs is the same three calls: write/renew/delete a lease blob, ARM
`start` + `instanceView`, and a WireGuard tunnel with the peer from `peers.json`. iOS can
reuse `Auth.swift`, `Azure.swift`, `Sessions.swift` and the tunnel extension unchanged;
Android needs MSAL (or the same PKCE flow) plus `GoBackend` from wireguard-android.
