---
name: compute
description: >
  Skill as Compute — offloads compute-intense work to a temporary Azure VM and destroys it
  afterwards. Sizes the machine to fit a monthly budget (default ₹10,000), installs and
  authenticates the Azure CLI if missing, ships the working directory up, runs the job there,
  brings the results back, and deletes the whole resource group. A watchdog on the machine
  deletes it even if the controlling agent dies, so nothing is left billing. This is the
  standard way for ANY other skill to borrow compute: video rendering and ffmpeg encodes,
  TTS and audio mixing, batch image work, long builds and test suites. Use when a task would
  take too long, overheat the laptop, or needs more cores than the local machine has.
license: MIT
metadata:
  author: Vignesh Ramamoorthy
  version: "1.0.0"
---

# Skill as Compute

Rent a machine for the heavy part of a job. Give it back the moment it is done.

All of it runs through one tool. `SCRIPTS` below means
`plugins/azure/skills/compute/scripts`.

```bash
python3 SCRIPTS/azc.py <command>
```

## The two rules

1. **Never leave a machine running.** Prefer `offload`, which always tears down —
   including when the job fails. Only use `up`/`down` when you must keep a machine
   across several steps, and pair every `up` with a `down`.
2. **Never invent prices or sizes.** Run `azc plan` and report what it says. Live
   prices come from Azure's public API; the affordable list is computed, not guessed.

## First run — ask for the budget

If `azc budget --json` reports `"needsPrompt": true`, ask the user for their monthly
budget **before launching anything**, using the `ask_user` tool. Offer the default and
show it in USD as well as rupees:

> Monthly Azure budget for offloaded compute? Default **₹10,000** (≈ **$104**/month —
> about 150 hours of a 16-core machine).

Then store it and carry on:

```bash
python3 SCRIPTS/azc.py budget --set-inr 10000
```

Ask **once, ever**. The answer is saved in `~/.azure-compute/config.json`.

## The one command

`offload` does everything: create → upload → run → download → destroy.

```bash
python3 SCRIPTS/azc.py offload \
  --profile render \
  --hours 2 \
  --push ./project \
  --cmd  "bash render.sh" \
  --pull :out \
  --dest ./output
```

`--cmd` may be repeated to run steps in order. Paths starting with `:` are relative to
the remote working directory. The VM is destroyed in a `finally` block, so it dies even
if the command fails or you interrupt it.

## Keeping a machine between steps

Only when several separate stages must share state:

```bash
python3 SCRIPTS/azc.py up --profile render --ttl 120   # ttl = self-destruct minutes
python3 SCRIPTS/azc.py push ./project :
python3 SCRIPTS/azc.py run "ffmpeg -i in.mp4 …"
python3 SCRIPTS/azc.py pull :out ./output
python3 SCRIPTS/azc.py down                            # never skip this
```

## Profiles

| Profile | For |
|---------|-----|
| `render` | Video encode & compositing — ffmpeg, Pillow, numpy |
| `render-lite` | Shorter renders, single clips |
| `audio` | TTS, mixing, loudness normalisation |
| `batch` | General parallel work, long builds |
| `tiny` | Smoke test |

Profiles are data, in `scripts/profiles.json`. Add one rather than passing ad-hoc sizes.

## Before you report cost or capability

```bash
python3 SCRIPTS/azc.py doctor    # installs the CLI, signs in, shows quota + offer limits
python3 SCRIPTS/azc.py plan --profile render --hours 2   # picks and prices a machine
python3 SCRIPTS/azc.py status    # what is running, and what it has cost so far
python3 SCRIPTS/azc.py reap      # delete anything stale left behind
```

Every command takes `--json` for parsing.

## Modules

Load only the one you need:

| Module | Covers |
|--------|--------|
| [reference/setup.md](reference/setup.md) | Azure CLI install, sign-in, first-run budget, config files |
| [reference/budget.md](reference/budget.md) | How cost is computed, what ₹10,000 buys, the ledger, why Spot may be unavailable |
| [reference/offload.md](reference/offload.md) | The contract other skills use, worked film-crew examples |
| [reference/lifecycle.md](reference/lifecycle.md) | What `up` builds, the self-destruct watchdog, teardown guarantees |
| [reference/troubleshooting.md](reference/troubleshooting.md) | Quota errors, SkuNotAvailable, ssh/rsync problems, orphan cleanup |

## If something goes wrong

Tear down first, diagnose after. A confused agent plus a running VM is the only way
this skill costs real money:

```bash
python3 SCRIPTS/azc.py down --all && python3 SCRIPTS/azc.py reap
```
