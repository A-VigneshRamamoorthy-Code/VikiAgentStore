"""Azure retail pricing + VM size selection.

The retail price API is public and unauthenticated, so planning costs nothing
and works before the user has even signed in.
"""
from __future__ import annotations

import os
import time
import urllib.parse

from azc_common import (CACHE_DIR, PRICE_TTL_SECONDS, http_json, read_json,
                        say, warn, write_json)

RETAIL = "https://prices.azure.com/api/retail/prices"

# vCPU counts for the sizes we offer. Used for quota checks and for reporting;
# we never need the whole Azure catalogue.
VCPU = {
    "Standard_B2s": 2, "Standard_B2ms": 2,
    "Standard_D2as_v5": 2, "Standard_D4as_v5": 4, "Standard_D8as_v5": 8,
    "Standard_D16as_v5": 16,
    "Standard_F4s_v2": 4, "Standard_F8s_v2": 8, "Standard_F16s_v2": 16,
    "Standard_F32s_v2": 32,
    "Standard_E4s_v5": 4, "Standard_E8s_v5": 8,
}

# Quota meter family that each size draws from, as reported by `az vm list-usage`.
FAMILY = {
    "Standard_B2s": "standardBSFamily", "Standard_B2ms": "standardBSFamily",
    "Standard_D2as_v5": "standardDASv5Family",
    "Standard_D4as_v5": "standardDASv5Family",
    "Standard_D8as_v5": "standardDASv5Family",
    "Standard_D16as_v5": "standardDASv5Family",
    "Standard_F4s_v2": "standardFSv2Family",
    "Standard_F8s_v2": "standardFSv2Family",
    "Standard_F16s_v2": "standardFSv2Family",
    "Standard_F32s_v2": "standardFSv2Family",
    "Standard_E4s_v5": "standardESv5Family",
    "Standard_E8s_v5": "standardESv5Family",
}


def _cache_path(region: str) -> str:
    return os.path.join(CACHE_DIR, f"prices-{region}.json")


def _fetch_region(region: str) -> list:
    flt = ("serviceName eq 'Virtual Machines' and armRegionName eq '%s' "
           "and priceType eq 'Consumption'" % region)
    url = RETAIL + "?$filter=" + urllib.parse.quote(flt)
    items, pages = [], 0
    while url and pages < 20:
        data = http_json(url, timeout=40)
        items.extend(data.get("Items", []))
        url = data.get("NextPageLink")
        pages += 1
    return items


def region_prices(region: str, refresh: bool = False) -> dict:
    """{size: {'ondemand': usd_per_hour, 'spot': usd_per_hour}} for Linux."""
    path = _cache_path(region)
    cached = read_json(path, {})
    if not refresh and cached.get("at", 0) and time.time() - cached["at"] < PRICE_TTL_SECONDS:
        return cached.get("sizes", {})

    say(f"fetching Azure retail prices for {region} …")
    try:
        items = _fetch_region(region)
    except Exception as exc:
        if cached.get("sizes"):
            warn(f"price API unreachable ({exc}); using cached prices")
            return cached["sizes"]
        raise

    sizes: dict[str, dict] = {}
    for row in items:
        size = row.get("armSkuName")
        if not size:
            continue
        product = row.get("productName", "")
        sku = row.get("skuName", "")
        # The same armSkuName is published for Windows and Linux; Windows rows
        # carry the OS licence and are not what we run.
        if "Windows" in product:
            continue
        if row.get("unitOfMeasure") != "1 Hour":
            continue
        price = row.get("retailPrice")
        if not price or price <= 0:
            continue
        kind = "spot" if ("Spot" in sku or "Low Priority" in sku) else "ondemand"
        slot = sizes.setdefault(size, {})
        if kind not in slot or price < slot[kind]:
            slot[kind] = price

    write_json(path, {"at": time.time(), "region": region, "sizes": sizes})
    return sizes


def price_for(region: str, size: str, spot: bool) -> float | None:
    entry = region_prices(region).get(size)
    if not entry:
        return None
    if spot:
        return entry.get("spot") or entry.get("ondemand")
    return entry.get("ondemand")


def describe(size: str) -> str:
    return f"{size} ({VCPU.get(size, '?')} vCPU)"
