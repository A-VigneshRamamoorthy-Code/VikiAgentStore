# azure-compute — Skill as Compute

Rents an Azure VM for the heavy part of a job and gives it back.

Any skill can hand a compute-intense task to a burst machine with one command. The
plugin sizes the VM to fit a monthly budget, installs and authenticates the Azure CLI
if needed, ships the working directory up, runs the work there, brings the results
back, and destroys the whole resource group.

```bash
copilot plugin install azure-compute@VikiAgentStore
```

## Why

Some work does not belong on a laptop. A 1080p film render pins every core for an hour
and still loses to a 16-core machine that costs 68 cents an hour.

At a ₹10,000/month budget (≈ $104) that is roughly **150 hours** of a 16-core machine —
far more than a video production needs. The real risk was never the hourly rate. It is
forgetting to switch the thing off, which is why this plugin has three independent ways
to destroy a VM and only one way to create one.

## The one command

```bash
python3 scripts/azc.py offload \
  --profile render --hours 2 \
  --push ./production \
  --cmd  "python3 scripts/render.py" \
  --pull :out --dest ./production/out
```

Create → upload → run → download → destroy. The teardown is in a `finally` block, so
the machine dies whether the job succeeds, fails, or is interrupted.

## How it guarantees to stop costing money

| Mechanism | Fires when | Depends on |
|-----------|-----------|------------|
| `offload` / `down` | Job ends | The controlling agent |
| On-box watchdog | TTL, idle timeout, or job done | Managed identity |
| Scheduled poweroff | TTL + 30 min | Nothing |
| `azc reap` | Next run | Azure tags |

Everything lives in **one resource group per job**, because deleting a VM leaves its
disk, NIC and public IP behind, still billing. Deleting the group removes all of it.

The watchdog is the interesting one: a systemd timer on the VM takes a token from the
instance metadata service and asks ARM to delete its own resource group. ARM completes
that server-side, so it works even though the machine issuing the request is destroyed
halfway through. Close the laptop mid-job and the VM notices the silence and deletes
itself.

## Budget

Asked once, on first use, defaulting to ₹10,000/month and always shown in USD too —
Azure prices everything in dollars.

Prices come live from the public Azure Retail Prices API. The planner walks an ordered
list of sizes and takes the first that clears four gates: a published price, vCPU quota
headroom, the per-job cost cap, and no subscription restriction. If the biggest machine
only fails on cost, it steps down by itself:

```
machine      Standard_F8s_v2  (8 vCPU)
skipped      Standard_F16s_v2 ($68.00 for 100h exceeds $52.25 cap)
```

Spend is tracked in a local ledger, because Azure's own cost APIs run 8–72 hours behind
real time and cannot stop a runaway machine.

## Commands

| Command | Does |
|---------|------|
| `doctor` | Install the CLI, sign in, report quota and offer limits |
| `budget` | Show or set the monthly budget |
| `plan` | Pick and price a machine, change nothing |
| `up` / `down` | Create / destroy, for multi-stage work |
| `push` / `run` / `pull` | Upload, execute, download |
| `offload` | All of the above in one call |
| `status` / `reap` | What is running; delete anything stale |

All take `--json`.

## Profiles

`render`, `render-lite`, `audio`, `batch`, `tiny` — defined as data in
`skills/azure-compute/scripts/profiles.json`. Add a profile rather than passing ad-hoc
VM sizes.

## Requirements

- An Azure subscription. Visual Studio / MSDN credit subscriptions work, with the
  caveat that **Spot VMs and GPU sizes are unavailable on them** — the plugin detects
  this and prices on-demand instead of failing five minutes into a deployment.
- `ssh` and `ssh-keygen`. `rsync` is used when present, with a `tar`-over-SSH fallback.
- Python 3. The tool uses the standard library only.

## Documentation

Detailed docs load on demand, so the skill itself stays small in the context window:

| Module | Covers |
|--------|--------|
| `reference/setup.md` | CLI install, sign-in, first-run budget, config files |
| `reference/budget.md` | Cost model, what ₹10,000 buys, the ledger, Spot eligibility |
| `reference/offload.md` | The contract other skills call, worked examples |
| `reference/lifecycle.md` | What `up` builds, the watchdog, teardown guarantees |
| `reference/troubleshooting.md` | Quota errors, SkuNotAvailable, ssh/rsync, orphans |

MIT licensed.
