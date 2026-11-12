# Operations

## Build and install the Mac app

```bash
cd plugins/azure/skills/vpn/mac
./build.sh          # swift build, assemble app + tunnel appex, sign (team via provisioning profile), install
open "/Applications/Leap VPN.app"
```

- Needs a paid Apple Developer team with the **Network Extension (packet-tunnel)**
  capability; `tools/provision.py` creates/refreshes the App IDs and macOS
  profiles (development signing, this Mac registered) via the App Store Connect API. The tunnel ships as an app extension, so no admin password is needed.
- Bundle ID stays `com.viki.vikivpn` (executable `VikiVPN`, scheme `vikivpn`) so existing
  installs keep their sign-in and VPN profile; the display name is **Leap VPN**.
- Single-window app: Window ▸ Leap VPN (⌘0) reopens it; closing the window keeps the
  menu-bar item and any tunnel alive.

## First run (no developer credentials involved)

Splash with sample cost → Microsoft sign-in → choose subscription → choose regions (map)
→ optional home PCs. Setup is idempotent: re-running it resumes a failed build and
upgrades outdated servers.

## Upgrading servers

Change files in `server/`, bump `Provisioner.agentVersion`, rebuild. A region is upgraded
in the background the next time someone connects to it (holds a `_setup` lease, pushes
files by Run Command, restarts the agent). Nothing starts a VM just to upgrade it.

## Test hooks (off by default)

```bash
defaults write com.viki.vikivpn AllowURLControl -bool true
open "vikivpn://connect?region=in"     # or ?server=exit:<id>
open "vikivpn://disconnect"
open "vikivpn://history"                # open the usage sheet
open "vikivpn://snapshot"               # → ~/Library/Application Support/VikiVPN/snapshot.png
```

## Validation checklist

1. Connect each region; `curl ipinfo.io/json` shows the right country.
2. Disconnect; `az vm get-instance-view -g vikivpn-<code> -n vikivpn-<code>` reaches
   `PowerState/deallocated` within ~1 min.
3. Force-kill the app while connected; VM deallocates within ~5 min, and the Mac's
   internet returns once the tunnel watchdog fires (~4–6 min).
4. Usage sheet shows the sessions with non-zero costs.

Measured (Nov 2026): connect 89–96 s from deallocated, deallocated 44–56 s after
disconnect in all four regions; crash path deallocated at +223 s.

## Gotchas

- The guest clock jumps forward by the time spent deallocated; never compare file mtimes
  with wall time right after boot (the deadman uses the agent's monotonic heartbeat).
- Blob listings start with a UTF-8 BOM; PowerShell's `.Content` mis-decodes it and `[xml]`
  throws. The runbook parses `RawContentStream` instead. Runbook jobs report `Completed`
  even when every region errored — read the job **output**, not just its status.
- `time.monotonic()` is ~0 at boot — initialise "last run" timestamps to `-inf`.
- Run Command can be preempted if the VM is deallocated mid-call; `Provisioner.runCommand`
  restarts the VM and retries.
- Subscription quotas: 20 vCPU per region on MSDN offers; `southindia`/`westindia`
  rejected the Ubuntu images — use `centralindia`.
- `scripts/vpnctl.py` is the legacy CLI (Azure CLI + Keychain secrets) from before in-app
  provisioning. Use it only for diagnostics (`status`, `verify-idle`).
