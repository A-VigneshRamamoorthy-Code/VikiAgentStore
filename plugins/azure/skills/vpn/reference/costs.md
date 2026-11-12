# Costs

## What bills, and when

| Item | While connected | While idle (deallocated) |
|------|-----------------|--------------------------|
| VM `Standard_B2ats_v2` | ≈ ₹0.6–0.9 / h depending on region (live retail price) | **₹0** — deallocated VMs bill no compute |
| OS disk 30 GB StandardSSD | — | ≈ $2.4 / month per region; **₹0 with provision once** |
| Standard public IP | — | Static IP on: ≈ $3.65 / month per region. Off (default): released on disconnect, ₹0 |
| Internet egress | First 100 GB / month free, then per-GB retail | ₹0 |
| Storage account, Automation (≤500 job-min free) | cents | cents |

## Per-location options (map card and Settings)

| Option | Default | Idle cost | Connect time |
|--------|---------|-----------|--------------|
| Provision once (delete on disconnect) | **on** | ₹0 — group deleted ~3 min after disconnect | ≈ 2–2.5 min (rebuild) |
| Off, static IP off | | disk ≈ $2.4 / month | ≈ 40 s–2 min (start + new IP) |
| Off, static IP on | | disk + IP ≈ $6 / month | ≈ 40 s, same IP every time |

The card shows both toggles every time a location is about to connect. Settings holds the
defaults and a per-location override. Relay regions for home PCs are never deleted while a
home PC uses them.

Typical heavy month: 2 h/day connected ≈ 60 h ≈ ₹50 compute + residual.

## Per-session estimate (`Sessions.swift` → `CostModel`)

```
vmCost     = vmSeconds / 3600 × VM retail price (region, Consumption, non-Spot)
egressCost = data beyond the month's free 100 GB × "Standard Data Transfer Out" price
vmSeconds  = from vmStartRequestedAt (or connect) to vmStoppedAt (or disconnect)
```

Prices come from the public Azure Retail Prices API in the subscription's billing
currency. The app follows the VM after disconnect to record the real deallocation time, so
the ~1 minute shutdown tail is charged to the session. If the app was killed mid-session,
the next launch closes the record with the deallocation time from the ARM activity log.
The app persists byte counters about once a minute so a crash keeps most of the data total.

## Credits and billed totals

- **Credit left (est.)** — Visual Studio / MSDN offers have no public balance API, so the
  app uses the offer's monthly credit minus
  billing-period-to-date spend from Cost Management. Labelled as an estimate. The offer is
  identified by the subscription's `quotaId` (`MSDN_*`); the tier (Enterprise $150, otherwise
  $50) comes from its display name, which the user can rename.
- **Free egress allowance** is applied in session order within the month, so repricing an
  old session never consumes allowance used by later ones.
- **VPN billed** — Cost Management `ActualCost` for `vikivpn-*` resource groups. Lags the
  session estimates by several hours.
- History: `~/Library/Application Support/VikiVPN/history.json` (region, start/end,
  duration, data, cost split, egress IP/country).
