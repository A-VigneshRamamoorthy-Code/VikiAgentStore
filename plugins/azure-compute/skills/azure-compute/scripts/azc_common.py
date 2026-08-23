"""Shared state for azc: paths, config, FX, budget ledger, logging.

Standard library only. No third-party imports anywhere in this tool.
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import time
import urllib.request
from datetime import datetime, timezone

HOME = os.path.expanduser(os.environ.get("AZC_HOME", "~/.azure-compute"))
CONFIG_PATH = os.path.join(HOME, "config.json")
LEDGER_PATH = os.path.join(HOME, "ledger.json")
JOBS_DIR = os.path.join(HOME, "jobs")
KEYS_DIR = os.path.join(HOME, "keys")
CACHE_DIR = os.path.join(HOME, "cache")

DEFAULT_BUDGET_INR = 10000.0
FALLBACK_INR_USD = 0.0105          # only used if every FX endpoint is unreachable
FX_TTL_SECONDS = 24 * 3600
PRICE_TTL_SECONDS = 24 * 3600

# ---------------------------------------------------------------- output ----

_QUIET = os.environ.get("AZC_QUIET") == "1"


def _c(code: str, text: str) -> str:
    if not sys.stderr.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def say(msg: str) -> None:
    if not _QUIET:
        print(_c("36", "azc") + " " + msg, file=sys.stderr, flush=True)


def warn(msg: str) -> None:
    print(_c("33", "azc warning") + " " + msg, file=sys.stderr, flush=True)


def fail(msg: str, code: int = 1):
    print(_c("31", "azc error") + " " + msg, file=sys.stderr, flush=True)
    sys.exit(code)


def ok(msg: str) -> None:
    if not _QUIET:
        print(_c("32", "azc ok") + "   " + msg, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ util ----

def ensure_dirs() -> None:
    for d in (HOME, JOBS_DIR, KEYS_DIR, CACHE_DIR):
        os.makedirs(d, mode=0o700, exist_ok=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def parse_iso(text: str) -> datetime:
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def new_job_id() -> str:
    stamp = now_utc().strftime("%m%d%H%M")
    tail = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{stamp}{tail}"


def read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: str, data) -> None:
    ensure_dirs()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def http_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": "azc/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


# ---------------------------------------------------------------- config ----

def load_config() -> dict:
    return read_json(CONFIG_PATH, {})


def save_config(cfg: dict) -> None:
    write_json(CONFIG_PATH, cfg)


def is_configured() -> bool:
    return bool(load_config().get("budgetInr"))


# -------------------------------------------------------------------- fx ----

FX_ENDPOINTS = [
    ("https://api.frankfurter.dev/v1/latest?base=INR&symbols=USD",
     lambda d: float(d["rates"]["USD"])),
    ("https://open.er-api.com/v6/latest/INR",
     lambda d: float(d["rates"]["USD"])),
]


def inr_to_usd_rate(force: bool = False) -> tuple[float, str]:
    """Return (rate, source). Cached for a day; falls back to a pinned rate."""
    cfg = load_config()
    cached = cfg.get("fx") or {}
    if not force and cached.get("rate") and time.time() - cached.get("at", 0) < FX_TTL_SECONDS:
        return float(cached["rate"]), cached.get("source", "cache")

    for url, pick in FX_ENDPOINTS:
        try:
            rate = pick(http_json(url, timeout=12))
            if 0.001 < rate < 1:
                host = url.split("/")[2]
                cfg["fx"] = {"rate": rate, "at": time.time(), "source": host}
                save_config(cfg)
                return rate, host
        except Exception:
            continue

    if cached.get("rate"):
        return float(cached["rate"]), cached.get("source", "stale cache")
    warn(f"no FX endpoint reachable — using pinned fallback {FALLBACK_INR_USD} INR/USD")
    return FALLBACK_INR_USD, "fallback"


def inr(usd: float, rate: float) -> float:
    return usd / rate if rate else 0.0


# ---------------------------------------------------------------- ledger ----

def _month_key(dt: datetime | None = None) -> str:
    return (dt or now_utc()).strftime("%Y-%m")


def load_ledger() -> dict:
    return read_json(LEDGER_PATH, {"entries": []})


def record_spend(job_id: str, usd: float, detail: dict) -> None:
    led = load_ledger()
    led["entries"].append({
        "job": job_id,
        "month": _month_key(),
        "usd": round(usd, 4),
        "at": iso(now_utc()),
        **detail,
    })
    write_json(LEDGER_PATH, led)


def month_spend_usd(month: str | None = None) -> float:
    month = month or _month_key()
    return sum(e.get("usd", 0.0) for e in load_ledger().get("entries", [])
               if e.get("month") == month)


def budget_state() -> dict:
    """Everything the planner and the agent need to talk about money."""
    cfg = load_config()
    rate, source = inr_to_usd_rate()
    budget_inr = float(cfg.get("budgetInr") or DEFAULT_BUDGET_INR)
    budget_usd = budget_inr * rate
    spent = month_spend_usd()
    remaining = max(0.0, budget_usd - spent)
    return {
        "configured": bool(cfg.get("budgetInr")),
        "budgetInr": budget_inr,
        "budgetUsd": round(budget_usd, 2),
        "fxRate": rate,
        "fxSource": source,
        "month": _month_key(),
        "spentUsd": round(spent, 4),
        "remainingUsd": round(remaining, 2),
        "remainingInr": round(inr(remaining, rate), 2),
        # Leave headroom so a single job can never eat the whole month.
        "perJobCapUsd": round(min(remaining, budget_usd * float(cfg.get("perJobFraction", 0.5))), 2),
        "region": cfg.get("region"),
        "subscription": cfg.get("subscription"),
    }
