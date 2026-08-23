# Setup — CLI, sign-in and the first-run budget

`azc doctor` is the only setup step. It installs what is missing, signs in, records the
subscription, and prints the limits that will shape every later decision.

```bash
python3 SCRIPTS/azc.py doctor
python3 SCRIPTS/azc.py doctor --json     # same, machine-readable
```

## What it checks

| Check | Why it matters |
|-------|----------------|
| `azure cli` | Installed automatically if absent |
| `ssh`, `ssh-keygen`, `rsync` | Transport to the VM (rsync is optional — see below) |
| `signed in` | Device-code sign-in if there is no session |
| `subscription` | Recorded in config; everything is created here |
| `offer type` | Decides whether Spot pricing is even possible |
| `spending limit` | `On` means Azure hard-stops when credit runs out |
| `spot vms` | Availability, derived from the offer type |
| `quota <region>` | Regional vCPU headroom — caps how big a machine can be |

## Installing the Azure CLI

`azc` installs it for you. If you would rather do it by hand:

| Platform | Command |
|----------|---------|
| macOS | `brew update && brew install azure-cli` |
| Debian/Ubuntu | `curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash` |
| RHEL/Fedora | `curl -sL https://aka.ms/InstallAzureCli \| sudo bash` |
| Windows | `winget install -e --id Microsoft.AzureCLI` |

On macOS the install needs Homebrew. If it is missing, `azc` stops and says so rather
than trying to bootstrap a package manager.

## Signing in

Three routes, tried in this order:

1. **Existing session** — `az account show` succeeds, nothing to do.
2. **Service principal** — if `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` and
   `AZURE_TENANT_ID` are all set, it logs in non-interactively. This is the right
   choice for CI.
3. **Device code** — `az login --use-device-code`.

The device code and its URL are printed **on stderr** and the process blocks until the
user finishes in a browser. When running as an agent, surface that code to the user
immediately — they cannot see your subprocess.

To fail instead of prompting (CI): `azc doctor --no-login --json`.

`azc` sets `AZURE_CORE_ONLY_SHOW_ERRORS`, `AZURE_CORE_NO_COLOR`,
`AZURE_CORE_DISABLE_CONFIRM_PROMPT`, `AZURE_CORE_LOGIN_EXPERIENCE_V2=false` and
`AZURE_CORE_SURVEY_MESSAGE=no` on every call, so the CLI never blocks on a prompt or
writes a survey banner into output that gets parsed.

## The first-run budget prompt

`azc` will not silently invent a spending limit. On first use:

```bash
python3 SCRIPTS/azc.py budget --json     # -> "needsPrompt": true
```

Ask the user, defaulting to **₹10,000/month**, and always show the USD equivalent —
Azure bills and prices everything in USD, so rupees alone are not actionable.

```bash
python3 SCRIPTS/azc.py budget --set-inr 10000
```

The rate is fetched live from `api.frankfurter.dev`, falling back to
`open.er-api.com`, then to a cached value, then to a pinned constant. It is cached for
24 hours. The source is always shown, so a stale or pinned rate is visible rather than
silent.

## Where state lives

Everything is under `~/.azure-compute/` (override with `AZC_HOME`):

```
config.json      budget, region, subscription, offer type, cached FX rate
ledger.json      one entry per finished job — the month-to-date spend
jobs/<id>.json   live and historical job records
keys/<id>        per-job ed25519 keypair, deleted at teardown
cache/           Azure retail price cache, 24h
```

Nothing here is secret beyond the SSH keys, which are per-job, unencrypted only on
disk with `0600`, and destroyed with the machine. No Azure credentials are stored by
`azc` — it borrows the Azure CLI's own session.

## Choosing a region

Defaults to `centralindia`, then `southindia`, `southeastasia`, `eastus`. Override per
command with `--region`, or permanently:

```bash
python3 SCRIPTS/azc.py doctor --region southeastasia
```

Pick a region near the data, not near the user — upload time usually dominates a short
job.
