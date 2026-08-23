# Budget — what the money buys and how it is guarded

## The short version

At **₹10,000/month (≈ $104)** the constraint is not whether you can afford to run a
job. It is whether you remember to switch the machine off.

A 16-core render box costs about **$0.68/hour**. The monthly budget is therefore
roughly **150 hours** of it — and a film-crew render is minutes, not hours. One
forgotten VM left running for a fortnight, however, spends the entire month.

That is why every path in this skill deletes the machine, and why the machine can
delete itself.

## What ₹10,000 buys

```bash
python3 SCRIPTS/azc.py budget
```

Live example, Central India, on-demand Linux:

| Size | vCPU | $/hour | Hours in ₹10,000 |
|------|-----:|-------:|-----------------:|
| `Standard_D4as_v5` | 4 | 0.111 | ~940 |
| `Standard_F4s_v2` | 4 | 0.170 | ~615 |
| `Standard_D8as_v5` | 8 | 0.222 | ~470 |
| `Standard_F8s_v2` | 8 | 0.340 | ~307 |
| `Standard_D16as_v5` | 16 | 0.444 | ~235 |
| `Standard_F16s_v2` | 16 | 0.680 | ~154 |

Prices come from the **Azure Retail Prices API**
(`https://prices.azure.com/api/retail/prices`), which is public and needs no
authentication — so planning and pricing work before the user has even signed in.
Results are cached for 24 hours per region.

Two traps that the price parser handles for you:

- The same `armSkuName` is published for **Windows and Linux**; the Windows rows carry
  an OS licence and cost roughly double. Rows whose `productName` contains `Windows`
  are discarded.
- Spot rows appear as a separate `skuName` containing `Spot` (older meters say
  `Low Priority`), not as a separate size.

## Spot is often not available

Spot VMs are 70–80% cheaper, but Microsoft restricts them to specific offer types:
Enterprise Agreement, pay-as-you-go, Sponsored and CSP.

**Visual Studio / MSDN subscriptions are not eligible.** A Spot deployment there fails
with a misleading `SkuNotAvailable` / `InvalidTemplateDeployment` error that mentions
capacity rather than eligibility.

`azc` reads the subscription's `quotaId` in `doctor` and decides for you. On an
ineligible offer it silently prices on-demand and says so in the plan:

```
spot unavailable on offer MSDN_2014-09-01 — on-demand pricing
```

Passing `--spot` on an ineligible subscription is ignored rather than obeyed, because
obeying it produces a deployment failure several minutes later.

## How the guard works

`azc plan` walks the profile's ordered size list and takes the **first** size that
clears all four gates:

1. A published price exists for that size in that region.
2. Regional and per-family **vCPU quota** has headroom.
3. `hourly × --hours` is within the **per-job cap** (half the monthly budget by
   default, and never more than what is left).
4. Not restricted for this subscription.

If the biggest machine fails only the cost gate, it steps down automatically:

```
machine      Standard_F8s_v2  (8 vCPU)
skipped      Standard_F16s_v2 ($68.00 for 100h exceeds $52.25 cap)
```

Override the cap for a single job with `--max-cost 5`.

## The ledger is authoritative, not Azure

Azure's own cost APIs are **8–72 hours behind real time**. They cannot stop a runaway
VM and must not be used as a real-time guard.

So `azc` keeps its own ledger. At teardown it records `elapsed hours × known hourly
price` into `~/.azure-compute/ledger.json`, and `budget` sums the current month. This
is accurate to the second and available instantly.

Consequences worth knowing:

- A VM deleted outside `azc` (portal, `az group delete`) never gets a ledger entry, so
  its cost is invisible to the guard. Prefer `azc down`.
- The ledger counts VM compute only. Disks, IPs and egress are pennies for short jobs
  but are not tracked.
- Reconcile against the real bill occasionally in the portal, or with
  `az costmanagement query`.

Related: `Microsoft.Consumption/credits/balanceSummary` — the endpoint that would give
a true remaining-credit figure — is **Microsoft Customer Agreement only** and returns
404 for Visual Studio subscriptions. There is no API for "rupees of credit left" on
this kind of subscription.

## The backstop you already have

Visual Studio subscriptions run with **spending limit `On`**. When the credit is gone,
Azure disables the subscription for the rest of the billing period: VMs are **stopped
and deallocated**, not deleted, and the subscription re-enables next month.

That prevents a surprise invoice, but it is a blunt instrument — it stops everything
mid-job, and **deallocated disks keep billing**. Treat it as the last line of defence,
never the plan. Deleting the resource group is the plan.
