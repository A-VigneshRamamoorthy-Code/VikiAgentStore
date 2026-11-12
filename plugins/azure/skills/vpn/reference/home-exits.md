# Home exits and streaming

## What streaming services do with Azure IPs (measured, India server)

| Service | Catalogue over Azure India IP | Playback |
|---------|-------------------------------|----------|
| Netflix | `/in/`, `requestCountry` IN / ALLOW, ₹ plans, Indian Top 10 | Played (user test, signed in) |
| Prime Video | Indian home page ("#1 in India", regional titles, U/A ratings) | Played an India-locked title. Signed-in Prime shows a "travelling" banner and the **account's home-marketplace** catalogue — that is tied to the Amazon account, not the IP |

An earlier test on a different Azure India IP got Prime's "Video Unavailable"
(`GU85HKX66NVFNQ9Y`, VPN/proxy block). Datacenter IPs can be blocked at any time; a
residential home exit is the dependable route.

## Home PC as an exit

A Windows PC on a home connection becomes an exit: devices still connect to the Azure VM
(fast WireGuard), and the VM forwards their traffic out through the PC.

```
Mac ──WireGuard──▶ Azure VM ──vx<port> tun → tun2socks → 127.0.0.1:<port>
                                  ▲ ssh -R (outbound from the PC, no inbound ports at home)
                          Windows PC (Indian ISP) ──▶ internet
```

- **Add**: Atlas "+" → home PC → the app creates a one-time invite (user-delegation SAS,
  create-only on `exits/_enroll/<id>.json`, 48 h) and a `LeapVPN-HomeExit-<id>.cmd`.
- **On the PC**: run the `.cmd` as a normal user (no admin; works under Constrained
  Language Mode). `Install-VikiVPNExit.ps1` makes an SSH key, posts the enrollment, and
  registers a per-user scheduled task that keeps `ssh -R` up with keepalives.
- **Approve**: the app's next refresh moves the enrollment to `exits/<region>/<id>.json`.
  The agent authorises the key (`restrict,port-forwarding,permitlisten=127.0.0.1:<port>`,
  no shell) and starts a tun2socks unit for it.
- **Use**: pick the home pin on the map. The lease carries `x-ms-meta-exit`; the agent adds
  `ip rule from <deviceIP> lookup <port>` (DNS stays on the VM). If the exit is down,
  the device is blackholed rather than silently leaking out of Azure, and the app reports it.
- Home exits **never keep a VM running** — only leases do. The PC's tunnel just retries
  until the VM is next started.

- **Remove**: the trash button in the home-PC list deletes the exit plus any leftover `_enroll`/`_pending` blob,
  otherwise the next refresh would re-approve it.

Validated (Nov 2026) on an Azure Windows Server 2022 VM standing in for a home PC: the
in-app one-liner installed as a standard user, the app connected through it, and the
egress IP equalled the Windows VM's public IP. The relay deallocated ~50 s after disconnect.

Users can run any mix: Azure regions only, home PCs only (the relay VM still starts on
demand), or both.

Respect each service's terms of use; this is for reaching your own home connection.
