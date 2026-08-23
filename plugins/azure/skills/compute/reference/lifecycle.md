# Lifecycle — what gets built, and how it guarantees to die

## One resource group per job

Every job creates `rg-azc-<jobid>` holding the VM, disk, NIC, public IP, NSG and VNet,
tagged `azc=1`, `azc-job`, `azc-ttl`, `azc-profile`.

This is the single most important design decision. **Deleting a VM does not delete its
disk, IP or NIC** — they keep billing quietly forever. Deleting the *resource group*
removes everything in one call, and the tags make orphans findable later.

Teardown uses `--no-wait`, so the group shows `provisioningState: Deleting` for a few
minutes after `azc down` returns. That is normal; the VM and disk are the first things
to go, so billing stops well before the group disappears.

## What `up` does

1. `reap` — clean up anything stale from earlier runs.
2. `plan` — choose a size that fits budget, quota and region.
3. Create the resource group with tags and a TTL.
4. Generate a **per-job ed25519 keypair** in `~/.azure-compute/keys/`.
5. Create the VM: Ubuntu 22.04 (falling back to 24.04), StandardSSD, Standard public
   IP, an NSG allowing only SSH, a **system-assigned managed identity**, and cloud-init.
6. Grant that identity **Contributor on its own resource group only**.
7. Wait for SSH, then wait for `cloud-init status --wait` so no job ever starts on a
   half-built machine.

`az vm create` returning does **not** mean the machine is ready — cloud-init is still
installing. Skipping step 7 produces "ffmpeg: command not found" on a machine that will
have ffmpeg thirty seconds later.

Note: `az vm create` has `--os-disk-delete-option` and `--nic-delete-option` but **no
`--public-ip-address-delete-option`** — passing it fails the whole deployment. The
public IP is reclaimed by deleting the resource group.

## Three independent ways the machine dies

Defence in depth, because the expensive failure is a VM nobody remembers:

| # | Mechanism | Fires when | Needs |
|---|-----------|-----------|-------|
| 1 | `offload` / `down` | Job finishes or fails | The controller alive |
| 2 | **On-box watchdog** | TTL passed, idle timeout, or job marked done | Managed identity |
| 3 | **Scheduled poweroff** | TTL + 30 min | Nothing at all |

Plus `azc reap`, which runs automatically at the start of every `up` and deletes any
`azc`-tagged group whose TTL has passed — including groups this machine has forgotten
about.

### The watchdog

A systemd timer runs every 60 seconds and checks three things: has the deadline passed,
has `/var/lib/azc/done` appeared, has the heartbeat gone stale. On any of them it takes
a token from the instance metadata service and issues an async
`DELETE /resourcegroups/<rg>` against ARM, then powers off.

ARM accepts the delete (HTTP 202) and completes it **server-side**, so the operation
finishes even though the VM issuing it is destroyed halfway through. The identity only
holds Contributor on its own resource group, so the blast radius is that group.

Every `run`, `push` and `pull` touches the heartbeat. So if the laptop is closed or the
agent crashes mid-job, the machine notices the silence and deletes itself — by default
after 20 minutes.

If the role assignment fails (insufficient permission to create role assignments), `azc`
warns and carries on: mechanism 3 still stops the billing, and `reap` still cleans up.

## Tuning the timers

```bash
--ttl 120     # minutes before self-destruct (default 120)
--idle 20     # minutes of silence before self-destruct (default 20)
```

Set `--ttl` above the worst-case runtime, not the expected one — hitting it kills the
job. Long single-command renders that produce no traffic still count as "idle", so
raise `--idle` for a three-hour encode, or have the command emit progress.

## Auto-shutdown is not enough

`az vm auto-shutdown` only **deallocates**. Disks continue to bill. It is not used here;
the watchdog deletes instead.

The same applies to the subscription spending limit: when credit runs out, Azure stops
and deallocates VMs but does not delete them, and the disks keep costing. Always delete.

## Verifying nothing leaked

```bash
python3 SCRIPTS/azc.py status --all
python3 SCRIPTS/azc.py reap
az group list --tag azc=1 -o table
```

The last one is the ground truth — it asks Azure rather than the local state, so it
finds groups created by a machine you no longer have.
