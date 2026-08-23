# Troubleshooting

**First rule: if you are confused, tear down before you debug.**

```bash
python3 SCRIPTS/azc.py down --all && python3 SCRIPTS/azc.py reap
```

A running VM plus an uncertain agent is the only way this skill costs real money.

## Deployment failures

### `SkuNotAvailable` / `InvalidTemplateDeployment`

Three different causes wear this one error message.

1. **Spot on an ineligible subscription.** Spot is limited to Enterprise Agreement,
   pay-as-you-go, Sponsored and CSP offers. Visual Studio / MSDN subscriptions are
   excluded, and the refusal arrives as a capacity error rather than an eligibility
   one. `azc doctor` detects this from the `quotaId` and prices on-demand instead.
2. **Genuine regional capacity shortage.** Try another region: `--region southindia`.
3. **The size is restricted for your subscription.** `azc plan` checks this via
   `az vm list-skus` and reports `not available for this subscription in this region`.

Diagnostic: if the same size deploys with Spot turned off, it was cause 1.

### `QuotaExceeded` / `OperationNotAllowed`

You asked for more vCPUs than the region allows. Check headroom:

```bash
az vm list-usage --location centralindia -o table | grep -i "Total Regional"
```

Visual Studio subscriptions typically get 20 vCPU per family. Note the quota counts
**existing** VMs too — an idle 4-core VM elsewhere leaves only 16.

Fixes: pick a lighter profile, use another region, delete something, or request a quota
increase in the portal.

### GPU sizes never work

N-series, ND, NV and H-series have a default quota of zero on Visual Studio
subscriptions and increase requests are routinely refused. No profile offers them.
For ffmpeg this matters less than it sounds — x264 on 16 cores is close to NVENC
throughput at meaningfully better quality per bit.

### The VM is created but has no public IP

`azc` tears it down and says so. Almost always a subscription policy blocking public
IPs. You would need to reach the machine over a VNet/bastion instead, which this skill
does not do.

## Connection failures

### `ssh never came up`

Boot plus provisioning is two to four minutes; `azc` waits up to seven. If it still
fails:

- A corporate network blocking outbound port 22 is the usual cause. Test with
  `nc -vz <ip> 22`.
- Confirm the NSG has the SSH rule: `az network nsg rule list -g rg-azc-<id> -o table`.

### `rsync: unrecognized option '--info=...'`

macOS ships **openrsync**, not GNU rsync. Its first line is
`openrsync: protocol version 29`, so naive version-sniffing reads "29" as the rsync
version and enables GNU-only flags. `azc` therefore uses only `-az` and `--delete`,
which both implementations support, and falls back to `tar` over SSH when rsync is
absent entirely.

### Pulled results land one directory too deep

rsync copies a directory *into* the destination unless the source ends in `/`. `azc`
probes whether the remote path is a directory and appends the slash. If you call rsync
yourself, remember the trailing slash.

## Cost and budget

### `nothing affordable to launch`

The cheapest size in the profile still exceeds the per-job cap (half the monthly budget
by default). Either:

```bash
--max-cost 20                 # raise the ceiling for this job
--hours 1                     # a shorter job costs less
--profile render-lite         # a smaller machine
python3 SCRIPTS/azc.py budget --set-inr 15000
```

### The ledger disagrees with the Azure portal

Expected, in both directions:

- Azure's cost APIs lag **8–72 hours**. The portal will be *behind* the ledger.
- The ledger counts VM compute only — not disks, IP, or egress. It will be slightly
  *under* the real bill.
- A VM deleted outside `azc` never gets a ledger entry at all.

The ledger exists to be instant and roughly right, because the accurate source is far
too slow to stop a runaway machine.

### Where has my credit gone?

There is no API for remaining credit on a Visual Studio subscription —
`Consumption/credits/balanceSummary` is Microsoft Customer Agreement only and returns
404. Read it in the portal under **Cost Management + Billing → Credits**.

## Cleanup

### A resource group survived

```bash
az group list --tag azc=1 -o table
python3 SCRIPTS/azc.py reap
az group delete --name rg-azc-<id> --yes --no-wait     # last resort
```

### `azc status` shows a machine that no longer exists

Local state drifted, usually because the group was deleted in the portal. `reap`
reconciles it. The cost of such a job is missing from the ledger.

### A group is stuck `Deleting`

Normal for a few minutes. If it persists, something in it has a **resource lock**, or
a disk is still attached to a VM in another group. Check with:

```bash
az lock list -g rg-azc-<id> -o table
```
