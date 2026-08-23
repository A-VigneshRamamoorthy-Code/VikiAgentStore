#!/usr/bin/env python3
"""azc — Skill as Compute.

Rent an Azure VM for the heavy part of a job, then give it back.

    azc doctor                      check/install/sign in to the Azure CLI
    azc budget --show               what the monthly budget buys
    azc plan --profile render       pick a machine, price it, change nothing
    azc up --profile render         create the machine
    azc push ./work :work           upload
    azc run  "ffmpeg …"             run there, output streamed back
    azc pull :work/out ./out        download
    azc down                        destroy everything
    azc offload …                   all of the above, as one call
    azc status / azc reap           what is running / delete anything stale

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import azc_azure as AZ                                    # noqa: E402
import azc_price as PRICE                                 # noqa: E402
import azc_remote as R                                    # noqa: E402
from azc_common import (DEFAULT_BUDGET_INR, JOBS_DIR, budget_state,  # noqa: E402
                        ensure_dirs, fail, inr_to_usd_rate, iso, load_config,
                        new_job_id, now_utc, ok, parse_iso, read_json,
                        record_spend, save_config, say, warn, write_json)

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = json.load(open(os.path.join(HERE, "profiles.json"), encoding="utf-8"))

ADMIN_USER = "azc"
REMOTE_WORKDIR = "/home/azc/work"
IMAGE_CANDIDATES = ["Ubuntu2204", "Ubuntu2404",
                    "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest"]

# Offer types Microsoft lists as eligible for Spot. MSDN / Visual Studio is
# deliberately absent — Spot deploys there fail as SkuNotAvailable.
SPOT_ELIGIBLE = ("enterpriseagreement", "payasyougo", "sponsored", "csp",
                 "msazr0003p", "internal")


# ------------------------------------------------------------------ jobs ---

def job_path(job_id: str) -> str:
    return os.path.join(JOBS_DIR, f"{job_id}.json")


def save_job(job: dict) -> None:
    write_json(job_path(job["id"]), job)


def load_job(job_id: str) -> dict | None:
    return read_json(job_path(job_id), None)


def all_jobs() -> list[dict]:
    ensure_dirs()
    out = []
    for name in sorted(os.listdir(JOBS_DIR)):
        if name.endswith(".json"):
            job = read_json(os.path.join(JOBS_DIR, name), None)
            if job:
                out.append(job)
    return out


def live_jobs() -> list[dict]:
    return [j for j in all_jobs() if j.get("state") == "running"]


def resolve_job(job_id: str | None) -> dict:
    if job_id:
        job = load_job(job_id)
        if not job:
            fail(f"no such job: {job_id}")
        return job
    live = live_jobs()
    if not live:
        fail("no running machine. Start one with:  azc up --profile <profile>")
    if len(live) > 1:
        ids = ", ".join(j["id"] for j in live)
        fail(f"several machines are running ({ids}) — pass --job <id>")
    return live[0]


# ---------------------------------------------------------------- budget ---

def cmd_budget(args) -> None:
    cfg = load_config()
    if args.set_inr is not None:
        if args.set_inr <= 0:
            fail("budget must be greater than zero")
        cfg["budgetInr"] = float(args.set_inr)
        save_config(cfg)
        ok(f"monthly budget set to ₹{args.set_inr:,.0f}")

    state = budget_state()
    if args.json:
        state["defaultInr"] = DEFAULT_BUDGET_INR
        state["needsPrompt"] = not state["configured"]
        print(json.dumps(state, indent=2))
        return

    rate = state["fxRate"]
    print(f"\n  Monthly budget   ₹{state['budgetInr']:,.0f}  ≈  "
          f"${state['budgetUsd']:,.2f}   (1 INR = ${rate:.5f}, {state['fxSource']})")
    if not state["configured"]:
        print(f"  {'':17}(not set yet — showing the ₹{DEFAULT_BUDGET_INR:,.0f} default)")
    print(f"  Spent in {state['month']}   ${state['spentUsd']:,.2f}")
    print(f"  Remaining        ${state['remainingUsd']:,.2f}  ≈  ₹{state['remainingInr']:,.0f}")
    print(f"  Cap per job      ${state['perJobCapUsd']:,.2f}\n")

    region = cfg.get("region") or PROFILES["defaultRegions"][0]
    try:
        prices = PRICE.region_prices(region)
    except Exception:
        return
    print(f"  What that buys in {region} (on-demand Linux):\n")
    print(f"    {'size':28} {'$/hour':>9} {'hours left':>11}")
    seen = []
    for prof in PROFILES["profiles"].values():
        for size in prof["sizes"]:
            if size not in seen:
                seen.append(size)
    for size in seen:
        hourly = (prices.get(size) or {}).get("ondemand")
        if not hourly:
            continue
        hours = state["remainingUsd"] / hourly if hourly else 0
        print(f"    {PRICE.describe(size):28} {hourly:>9.3f} {hours:>11.0f}")
    print()


# ---------------------------------------------------------------- doctor ---

def spot_eligible(quota_id: str) -> bool:
    q = (quota_id or "").lower()
    return any(q.startswith(p) for p in SPOT_ELIGIBLE)


def cmd_doctor(args) -> None:
    ensure_dirs()
    report = {"ok": True, "checks": []}

    def check(name, good, detail=""):
        report["checks"].append({"name": name, "ok": bool(good), "detail": detail})
        if not good:
            report["ok"] = False
        if not args.json:
            mark = "✓" if good else "✗"
            print(f"  {mark} {name:26} {detail}")

    if not args.json:
        print("\n  azc doctor\n")

    AZ.ensure_cli(auto=not args.no_install)
    check("azure cli", bool(AZ.az_path()), AZ.az_path() or "missing")

    for tool in ("ssh", "ssh-keygen", "rsync"):
        import shutil as _sh
        check(tool, bool(_sh.which(tool)), _sh.which(tool) or "missing")

    acct = AZ.ensure_login(interactive=not args.no_login)
    check("signed in", bool(acct), acct.get("user", {}).get("name", ""))

    sub_id = acct["id"]
    check("subscription", True, f"{acct.get('name')} ({sub_id[:8]}…)")

    pol = AZ.subscription_policies(sub_id)
    quota_id = pol.get("quotaId", "")
    limit = pol.get("spendingLimit", "")
    check("offer type", True, quota_id)
    check("spending limit", True,
          f"{limit}" + (" — Azure hard-stops at credit exhaustion"
                        if limit == "On" else ""))

    spot = spot_eligible(quota_id)
    check("spot vms", True,
          "available" if spot else
          f"NOT available on {quota_id} — using on-demand pricing")

    cfg = load_config()
    region = args.region or cfg.get("region") or PROFILES["defaultRegions"][0]
    usage = AZ.quota(region)
    total = usage.get("cores") or usage.get("Total Regional vCPUs") or (0, 0)
    check(f"quota {region}", total[1] > 0,
          f"{total[0]}/{total[1]} regional vCPUs used")

    cfg.update({"subscription": sub_id, "region": region,
                "quotaId": quota_id, "spotEligible": spot,
                "spendingLimit": limit})
    save_config(cfg)

    state = budget_state()
    if not state["configured"] and not args.json:
        print(f"\n  ! No monthly budget set. Default is ₹{DEFAULT_BUDGET_INR:,.0f} "
              f"(≈ ${DEFAULT_BUDGET_INR * state['fxRate']:,.2f}).")
        print("    Set it with:  azc budget --set-inr <amount>\n")

    if args.json:
        report["subscription"] = sub_id
        report["quotaId"] = quota_id
        report["spotEligible"] = spot
        report["region"] = region
        report["budget"] = state
        print(json.dumps(report, indent=2))
    else:
        print()
    if not report["ok"]:
        sys.exit(1)


# ------------------------------------------------------------------ plan ---

def _quota_headroom(usage: dict, size: str) -> tuple[bool, str]:
    need = PRICE.VCPU.get(size, 0)
    fam = PRICE.FAMILY.get(size)
    total = usage.get("cores")
    if total and total[1] - total[0] < need:
        return False, f"regional vCPU quota {total[0]}/{total[1]}, needs {need}"
    if fam and fam in usage:
        cur, lim = usage[fam]
        if lim - cur < need:
            return False, f"{fam} quota {cur}/{lim}, needs {need}"
    return True, ""


def plan(profile_name: str, hours: float, region: str | None = None,
         want_spot: bool | None = None, max_cost: float | None = None) -> dict:
    prof = PROFILES["profiles"].get(profile_name)
    if not prof:
        fail(f"unknown profile '{profile_name}'. Known: " +
             ", ".join(PROFILES["profiles"]))

    cfg = load_config()
    region = region or cfg.get("region") or PROFILES["defaultRegions"][0]
    state = budget_state()

    spot_ok = cfg.get("spotEligible")
    if spot_ok is None:
        spot_ok = spot_eligible(cfg.get("quotaId", ""))
    use_spot = spot_ok if want_spot is None else (want_spot and spot_ok)
    spot_note = ("" if spot_ok else
                 f"spot unavailable on offer {cfg.get('quotaId', '?')} — on-demand pricing")

    prices = PRICE.region_prices(region)
    usage = AZ.quota(region) if AZ.az_path() and AZ.current_account() else {}

    ceiling = max_cost if max_cost is not None else state["perJobCapUsd"]
    rejected, chosen = [], None

    for size in prof["sizes"]:
        hourly = (prices.get(size) or {}).get("spot" if use_spot else "ondemand")
        if not hourly:
            rejected.append((size, "no published price in this region"))
            continue
        if usage:
            fits, why = _quota_headroom(usage, size)
            if not fits:
                rejected.append((size, why))
                continue
        est = hourly * hours
        if ceiling and est > ceiling:
            rejected.append((size, f"${est:.2f} for {hours:g}h exceeds ${ceiling:.2f} cap"))
            continue
        chosen = {"size": size, "hourly": hourly, "estimate": est}
        break

    rate = state["fxRate"]
    result = {
        "profile": profile_name,
        "summary": prof["summary"],
        "region": region,
        "spot": bool(use_spot),
        "spotNote": spot_note,
        "hours": hours,
        "budget": state,
        "rejected": [{"size": s, "reason": r} for s, r in rejected],
        "diskGB": prof.get("diskGB", 64),
    }
    if not chosen:
        result["affordable"] = False
        result["reason"] = ("no machine in this profile fits the budget, the quota "
                            "or this region")
        return result

    result.update({
        "affordable": True,
        "size": chosen["size"],
        "vcpu": PRICE.VCPU.get(chosen["size"]),
        "usdPerHour": round(chosen["hourly"], 4),
        "inrPerHour": round(chosen["hourly"] / rate, 2) if rate else None,
        "estimateUsd": round(chosen["estimate"], 2),
        "estimateInr": round(chosen["estimate"] / rate, 2) if rate else None,
        "maxHoursRemaining": round(state["remainingUsd"] / chosen["hourly"], 1),
    })
    return result


def print_plan(p: dict, out=sys.stdout) -> None:
    def w(line=""):
        print(line, file=out, flush=True)

    w()
    if not p.get("affordable"):
        w(f"  ✗ {p['reason']}")
        for r in p["rejected"]:
            w(f"      {r['size']:22} {r['reason']}")
        w()
        return
    b = p["budget"]
    w(f"  profile      {p['profile']} — {p['summary']}")
    w(f"  machine      {p['size']}  ({p['vcpu']} vCPU, {p['diskGB']} GB disk)")
    w(f"  region       {p['region']}")
    w(f"  pricing      ${p['usdPerHour']}/hour  ≈ ₹{p['inrPerHour']}/hour"
      f"   ({'spot' if p['spot'] else 'on-demand'})")
    if p.get("spotNote"):
        w(f"               {p['spotNote']}")
    w(f"  estimate     ${p['estimateUsd']} for {p['hours']:g}h "
      f"≈ ₹{p['estimateInr']}")
    w(f"  budget left  ${b['remainingUsd']} of ${b['budgetUsd']} "
      f"→ {p['maxHoursRemaining']}h at this rate")
    if p["rejected"]:
        w("  skipped      " + "; ".join(f"{r['size']} ({r['reason']})"
                                        for r in p["rejected"][:3]))
    w()


def cmd_plan(args) -> None:
    p = plan(args.profile, args.hours, args.region, args.spot, args.max_cost)
    print(json.dumps(p, indent=2)) if args.json else print_plan(p)
    if not p.get("affordable"):
        sys.exit(2)


# -------------------------------------------------------------------- up ---

def cmd_up(args) -> dict:
    ensure_dirs()
    AZ.ensure_cli()
    acct = AZ.ensure_login()
    sub_id = acct["id"]

    reap(quiet=True)

    p = plan(args.profile, args.hours, args.region, args.spot, args.max_cost)
    if not p.get("affordable"):
        print_plan(p, out=sys.stderr)
        fail("nothing affordable to launch — raise the budget or pick a smaller profile")
    if not args.json:
        print_plan(p, out=sys.stderr)

    job_id = new_job_id()
    rg = f"rg-azc-{job_id}"
    vm = f"vm-{job_id}"
    region = p["region"]
    size = p["size"]
    prof = PROFILES["profiles"][args.profile]

    ttl_minutes = int(args.ttl)
    idle_minutes = int(args.idle)
    started = now_utc()
    deadline = started + timedelta(minutes=ttl_minutes)

    _, pub = R.make_key(job_id)
    with open(pub, encoding="utf-8") as fh:
        pub_key = fh.read().strip()

    say(f"creating resource group {rg} in {region}")
    AZ.az(["group", "create", "--name", rg, "--location", region,
           "--tags", "azc=1", f"azc-job={job_id}", f"azc-ttl={iso(deadline)}",
           f"azc-profile={args.profile}"], parse=False)

    ci = AZ.cloud_init(prof, sub_id, rg, int(deadline.timestamp()),
                       idle_minutes * 60, ttl_minutes + 30)
    ci_path = os.path.join(JOBS_DIR, f"{job_id}.cloud-init.yaml")
    with open(ci_path, "w", encoding="utf-8") as fh:
        fh.write(ci)

    base = ["vm", "create", "--resource-group", rg, "--name", vm,
            "--size", size, "--admin-username", ADMIN_USER,
            "--ssh-key-values", pub_key,
            "--public-ip-sku", "Standard", "--nsg-rule", "SSH",
            "--storage-sku", "StandardSSD_LRS",
            "--os-disk-size-gb", str(p["diskGB"]),
            # There is no --public-ip-address-delete-option on `az vm create`;
            # the public IP is freed because we delete the whole resource group.
            "--os-disk-delete-option", "Delete",
            "--nic-delete-option", "Delete",
            "--assign-identity", "[system]",
            "--custom-data", ci_path,
            "--tags", "azc=1", f"azc-job={job_id}",
            "--only-show-errors"]
    if p["spot"]:
        base += ["--priority", "Spot", "--eviction-policy", "Delete",
                 "--max-price", "-1"]

    created = None
    for image in IMAGE_CANDIDATES:
        say(f"creating {size} from {image} — this takes a couple of minutes")
        created = AZ.az(base + ["--image", image], check=False, timeout=1800)
        if created:
            break
        warn(f"image {image} was rejected, trying the next one")
    if not created:
        AZ.delete_rg(rg)
        fail("could not create the VM — see the errors above. "
             "Run `azc plan` to check quota and region.")

    ip = created.get("publicIpAddress")
    principal = (created.get("identity") or {}).get("systemAssignedIdentity") \
        or (created.get("identity") or {}).get("principalId")
    if not ip:
        ip = AZ.az(["vm", "show", "-d", "-g", rg, "-n", vm,
                    "--query", "publicIps", "-o", "tsv"], parse=False)
        ip = (ip.stdout or "").strip() if hasattr(ip, "stdout") else ip
    if not ip:
        AZ.delete_rg(rg)
        fail("VM created without a public IP — torn down")

    job = {
        "id": job_id, "rg": rg, "vm": vm, "ip": ip, "user": ADMIN_USER,
        "size": size, "region": region, "profile": args.profile,
        "usdPerHour": p["usdPerHour"], "spot": p["spot"],
        "subscription": sub_id, "workdir": REMOTE_WORKDIR,
        "createdAt": iso(started), "deadline": iso(deadline),
        "ttlMinutes": ttl_minutes, "idleMinutes": idle_minutes,
        "state": "running",
    }
    save_job(job)
    ok(f"machine {job_id} up at {ip}")

    # Let the box delete its own resource group when the job ends or stalls.
    if principal:
        res = AZ.az(["role", "assignment", "create",
                     "--assignee-object-id", principal,
                     "--assignee-principal-type", "ServicePrincipal",
                     "--role", "Contributor",
                     "--scope", f"/subscriptions/{sub_id}/resourceGroups/{rg}"],
                    check=False, timeout=300)
        if res:
            ok("self-destruct watchdog armed")
        else:
            warn("could not grant the VM permission to delete itself — it will "
                 "still power off at TTL, and `azc reap` cleans up the rest")
    else:
        warn("no managed identity on the VM — relying on TTL poweroff and `azc reap`")

    R.wait_for_ssh(job)
    R.wait_for_cloud_init(job)
    R.run(job, f"mkdir -p {REMOTE_WORKDIR}", stream=False)

    say(f"deadline {iso(deadline)} ({ttl_minutes} min), idle timeout {idle_minutes} min")
    if args.json:
        print(json.dumps({"job": job, "plan": p}, indent=2))
    return job


# ---------------------------------------------------- run / push / pull ----

def _remote(path: str) -> str:
    return REMOTE_WORKDIR + "/" + path[1:].lstrip("/") if path.startswith(":") else path


def cmd_run(args) -> None:
    job = resolve_job(args.job)
    code = R.run(job, args.command)
    if code != 0:
        fail(f"remote command exited {code}", code)


def cmd_push(args) -> None:
    R.push(resolve_job(args.job), args.local, _remote(args.remote))


def cmd_pull(args) -> None:
    R.pull(resolve_job(args.job), _remote(args.remote), args.local)


# ------------------------------------------------------- status / down -----

def _elapsed_hours(job: dict) -> float:
    """Billable hours. Frozen once the machine is gone."""
    if job.get("state") != "running" and job.get("hours") is not None:
        return float(job["hours"])
    return max(0.0, (now_utc() - parse_iso(job["createdAt"])).total_seconds() / 3600.0)


def cmd_status(args) -> None:
    jobs = all_jobs() if args.all else live_jobs()
    state = budget_state()
    if args.json:
        for j in jobs:
            j["elapsedHours"] = round(_elapsed_hours(j), 3)
            j["costSoFarUsd"] = round(_elapsed_hours(j) * j.get("usdPerHour", 0), 3)
        print(json.dumps({"jobs": jobs, "budget": state}, indent=2))
        return

    print()
    if not jobs:
        print("  no machines running")
    for j in jobs:
        hrs = _elapsed_hours(j)
        cost = j.get("costUsd") if j.get("state") != "running" else hrs * j.get("usdPerHour", 0)
        cost = cost or 0.0
        if j.get("state") == "running":
            mins = int((parse_iso(j["deadline"]) - now_utc()).total_seconds() // 60)
            when = f"TTL {mins}m" if mins > 0 else "PAST TTL"
            where = j.get("ip", "-")
        else:
            when = j.get("deletedAt", "")[:16].replace("T", " ")
            where = "-"
        print(f"  {j['id']}  {j['state']:8} {j['size']:20} {j['region']:14} "
              f"{where:15} {hrs:5.2f}h  ${cost:6.2f}  {when}")
    print(f"\n  budget: ${state['spentUsd']} spent of ${state['budgetUsd']} "
          f"this month, ${state['remainingUsd']} left\n")


def teardown(job: dict, reason: str = "done") -> None:
    if job.get("state") != "running":
        return
    hrs = _elapsed_hours(job)
    cost = hrs * job.get("usdPerHour", 0.0)
    say(f"deleting resource group {job['rg']} ({reason})")
    AZ.delete_rg(job["rg"], wait=False)
    job["state"] = "deleted"
    job["deletedAt"] = iso(now_utc())
    job["hours"] = round(hrs, 3)
    job["costUsd"] = round(cost, 4)
    save_job(job)
    record_spend(job["id"], cost, {"size": job["size"], "region": job["region"],
                                   "hours": round(hrs, 3), "profile": job.get("profile")})
    R.drop_key(job["id"])
    rate, _ = inr_to_usd_rate()
    ok(f"{job['id']} destroyed — ran {hrs:.2f}h, cost ${cost:.2f} "
       f"(≈ ₹{cost / rate:,.0f})" if rate else f"{job['id']} destroyed")


def cmd_down(args) -> None:
    if args.all:
        jobs = live_jobs()
        if not jobs:
            say("nothing running")
        for job in jobs:
            teardown(job, "down --all")
        return
    teardown(resolve_job(args.job))


def reap(quiet: bool = False) -> int:
    """Delete anything tagged azc whose TTL has passed, plus stale local jobs."""
    killed = 0
    for job in live_jobs():
        if now_utc() > parse_iso(job["deadline"]):
            teardown(job, "past TTL")
            killed += 1

    if not (AZ.az_path() and AZ.current_account()):
        return killed
    known = {j["rg"] for j in all_jobs()}
    for grp in AZ.list_azc_groups():
        name = grp.get("name", "")
        tags = grp.get("tags") or {}
        ttl = tags.get("azc-ttl")
        if name in known and any(j["rg"] == name and j["state"] == "running"
                                 for j in all_jobs()):
            continue
        stale = True
        if ttl:
            try:
                stale = now_utc() > parse_iso(ttl)
            except ValueError:
                stale = True
        if stale:
            if not quiet:
                say(f"reaping orphaned resource group {name}")
            AZ.delete_rg(name, wait=False)
            killed += 1
    return killed


def cmd_reap(args) -> None:
    AZ.ensure_cli()
    AZ.ensure_login()
    n = reap(quiet=False)
    ok(f"reaped {n} resource group(s)" if n else "nothing to reap")


# --------------------------------------------------------------- offload ---

def cmd_offload(args) -> None:
    """up → push → run → pull → down. The VM always dies, pass or fail."""
    job = None
    failure = None
    try:
        job = cmd_up(args)
        if args.push:
            R.push(job, args.push, _remote(args.push_to or ":"))
        for cmd in args.cmd:
            say(f"running: {cmd}")
            code = R.run(job, cmd)
            if code != 0:
                failure = f"remote command exited {code}: {cmd}"
                break
        if not failure and args.pull:
            R.pull(job, _remote(args.pull), args.dest or "./azc-output")
    except SystemExit:
        failure = failure or "aborted"
        raise
    except Exception as exc:                                  # noqa: BLE001
        failure = f"{type(exc).__name__}: {exc}"
    finally:
        if job:
            if args.keep and not failure:
                warn(f"--keep set: machine {job['id']} is STILL RUNNING and still "
                     f"costing money. Destroy it with:  azc down --job {job['id']}")
            else:
                R.mark_done(job)
                teardown(job, "offload complete")
    if failure:
        fail(failure)
    ok("offload complete")


# ------------------------------------------------------------------ main ---

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="azc", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="check/install/sign in")
    d.add_argument("--json", action="store_true")
    d.add_argument("--region")
    d.add_argument("--no-install", action="store_true")
    d.add_argument("--no-login", action="store_true")
    d.set_defaults(fn=cmd_doctor)

    b = sub.add_parser("budget", help="show or set the monthly budget")
    b.add_argument("--set-inr", type=float)
    b.add_argument("--json", action="store_true")
    b.set_defaults(fn=cmd_budget)

    def add_launch_args(p):
        p.add_argument("--profile", default="render")
        p.add_argument("--hours", type=float, default=1.0,
                       help="expected runtime, used to price the job")
        p.add_argument("--region")
        p.add_argument("--spot", action="store_true", default=None,
                       help="prefer spot (ignored on ineligible offers)")
        p.add_argument("--max-cost", type=float,
                       help="hard ceiling in USD for this job")

    pl = sub.add_parser("plan", help="pick and price a machine, change nothing")
    add_launch_args(pl)
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(fn=cmd_plan)

    u = sub.add_parser("up", help="create the machine")
    add_launch_args(u)
    u.add_argument("--ttl", type=int, default=120, help="minutes before self-destruct")
    u.add_argument("--idle", type=int, default=20,
                   help="minutes of silence before self-destruct")
    u.add_argument("--json", action="store_true")
    u.set_defaults(fn=cmd_up)

    r = sub.add_parser("run", help="run a command on the machine")
    r.add_argument("command")
    r.add_argument("--job")
    r.set_defaults(fn=cmd_run)

    ps = sub.add_parser("push", help="upload (':' prefixes the remote workdir)")
    ps.add_argument("local")
    ps.add_argument("remote", nargs="?", default=":")
    ps.add_argument("--job")
    ps.set_defaults(fn=cmd_push)

    pu = sub.add_parser("pull", help="download")
    pu.add_argument("remote")
    pu.add_argument("local")
    pu.add_argument("--job")
    pu.set_defaults(fn=cmd_pull)

    st = sub.add_parser("status", help="what is running and what it has cost")
    st.add_argument("--all", action="store_true")
    st.add_argument("--json", action="store_true")
    st.set_defaults(fn=cmd_status)

    dn = sub.add_parser("down", help="destroy the machine")
    dn.add_argument("--job")
    dn.add_argument("--all", action="store_true")
    dn.set_defaults(fn=cmd_down)

    rp = sub.add_parser("reap", help="delete anything stale left behind")
    rp.set_defaults(fn=cmd_reap)

    of = sub.add_parser("offload", help="up, push, run, pull, down — one call")
    add_launch_args(of)
    of.add_argument("--ttl", type=int, default=120)
    of.add_argument("--idle", type=int, default=20)
    of.add_argument("--push")
    of.add_argument("--push-to")
    of.add_argument("--cmd", action="append", default=[], required=True)
    of.add_argument("--pull")
    of.add_argument("--dest")
    of.add_argument("--keep", action="store_true",
                    help="leave the machine running (it still self-destructs at TTL)")
    of.add_argument("--json", action="store_true")
    of.set_defaults(fn=cmd_offload)

    return ap


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.fn(args)
    except KeyboardInterrupt:
        warn("interrupted — run `azc status` to check for a running machine")
        sys.exit(130)


if __name__ == "__main__":
    main()
