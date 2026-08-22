#!/usr/bin/env python3
"""The last check before an upload that cannot be taken back.

Publishing is the only irreversible act in this pipeline. A wrong frame can be
re-rendered; a wrong claim that has been live for an hour has been screenshotted.
This stage exists so that the question "are we allowed to publish this, and does
it say what we can defend?" is asked once, deliberately, and written down.

It checks three things and refuses on any of them:

* **Every asset has a licence on record.** A film assembled from images with no
  provenance is a takedown waiting to happen, and the moment to notice is
  before the upload, not after the strike.
* **The metadata's claims are the ledger's claims.** A title is where
  overreach happens, because it is written last, by whoever wants the click.
  Numbers and superlatives in the title or description are checked back against
  the researched ledger.
* **Attribution that a licence requires is actually present.** CC-BY is not
  free; it is free *if you credit*. An uncredited CC-BY asset is simply
  unlicensed.

    python3 clearance.py --assets assets.json --meta youtube_metadata.json \\
        --ledger ledger.json -o clearance.json
"""

import argparse
import datetime
import json
import os
import re
import sys

# Licences that carry an attribution condition. Holding an asset under one of
# these without a credit string is the same as holding it under none.
NEEDS_CREDIT = {"cc-by", "cc-by-sa", "cc-by-nd", "cc-by-nc", "cc-by-nc-sa",
                "cc-by-nc-nd"}
# Licences that impose no condition we can breach by publishing.
UNCONDITIONAL = {"cc0", "public-domain", "publicdomain", "owned", "original",
                 "generated", "licensed", "fair-dealing", "fair-use"}

SUPERLATIVE = re.compile(
    r"\b(first|only|largest|biggest|worst|deadliest|greatest|most|never|"
    r"always|every|all|no one|nobody|unprecedented|record)\b", re.I)
NUMBER = re.compile(r"\b\d[\d,.]*\b")


def die(msg, code=2):
    print("clearance: %s" % msg, file=sys.stderr)
    raise SystemExit(code)


def load(path, what):
    if not os.path.exists(path):
        die("no such %s: %s" % (what, path))
    try:
        with open(path) as fh:
            return json.load(fh)
    except json.JSONDecodeError as e:
        die("%s is not valid JSON: %s" % (path, e))


def norm_number(s):
    """`40,000` and `40000` are the same claim written two ways."""
    return s.replace(",", "").rstrip(".").lstrip("0") or "0"


def ledger_text(ledger):
    """Everything the researcher established, as one searchable blob."""
    claims = ledger.get("claims") if isinstance(ledger, dict) else ledger
    if not isinstance(claims, list):
        return "", []
    bits, listed = [], []
    for c in claims:
        if isinstance(c, str):
            bits.append(c)
            listed.append(c)
            continue
        for k in ("text", "claim", "statement", "value", "quote"):
            v = c.get(k)
            if isinstance(v, str):
                bits.append(v)
        listed.append(c.get("text") or c.get("claim") or "")
    return " \n".join(bits), listed


def check_assets(assets):
    problems, cleared = [], 0
    items = assets.get("assets") if isinstance(assets, dict) else assets
    if not isinstance(items, list):
        die("the asset register must be a list, or an object with an "
            "`assets` list")
    if not items:
        problems.append("the asset register is empty. A film with no assets "
                        "on record has not been checked, it has been skipped.")
    for i, a in enumerate(items, 1):
        name = a.get("file") or a.get("id") or "asset %d" % i
        lic = (a.get("license") or a.get("licence") or "").strip().lower()
        if not lic:
            problems.append("%s: no licence recorded" % name)
            continue
        if lic in NEEDS_CREDIT and not (a.get("credit") or
                                        a.get("attribution")):
            problems.append("%s: %s requires attribution, and none is "
                            "recorded" % (name, lic))
            continue
        if lic not in NEEDS_CREDIT and lic not in UNCONDITIONAL:
            problems.append("%s: licence %r is not one this stage knows how "
                            "to clear. Record it as one of: %s"
                            % (name, lic,
                               ", ".join(sorted(UNCONDITIONAL | NEEDS_CREDIT))))
            continue
        cleared += 1
    return problems, cleared, len(items)


def check_claims(meta, ledger):
    """Numbers and superlatives in the packaging must exist in the ledger."""
    blob, _ = ledger_text(ledger)
    if not blob.strip():
        return ["the ledger carries no claims, so nothing in the metadata can "
                "be checked against it"]
    low = blob.lower()
    nums = {norm_number(n) for n in NUMBER.findall(blob)}

    problems = []
    for field in ("title", "description"):
        text = meta.get(field) or ""
        if not text:
            continue
        for n in NUMBER.findall(text):
            if norm_number(n) not in nums:
                problems.append("%s: the figure %r does not appear in the "
                                "ledger" % (field, n))
        for m in SUPERLATIVE.finditer(text):
            w = m.group(0).lower()
            if w not in low:
                problems.append("%s: %r is a claim of its own and the ledger "
                                "does not support it" % (field, m.group(0)))
    return problems


def main():
    ap = argparse.ArgumentParser(
        description="Clear a deliverable for publication, or refuse.")
    ap.add_argument("--assets", required=True,
                    help="asset register: file, license, credit")
    ap.add_argument("--meta", required=True, help="youtube_metadata.json")
    ap.add_argument("--ledger", required=True, help="the researcher's ledger")
    ap.add_argument("-o", "--out", required=True, help="clearance.json")
    ap.add_argument("--allow", action="append", default=[], metavar="REASON",
                    help="record a deliberate, reasoned exception; repeatable")
    a = ap.parse_args()

    assets = load(a.assets, "asset register")
    meta = load(a.meta, "metadata")
    ledger = load(a.ledger, "ledger")

    asset_problems, cleared, total = check_assets(assets)
    claim_problems = check_claims(meta, ledger)
    problems = asset_problems + claim_problems

    ok = not problems or bool(a.allow)
    rec = {
        "cleared": ok,
        "checked_utc": datetime.datetime.now(
            datetime.timezone.utc).replace(microsecond=0).isoformat(),
        "assets_total": total,
        "assets_cleared": cleared,
        "problems": problems,
        "exceptions": a.allow,
        "title": meta.get("title"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(rec, fh, indent=2)

    print("clearance: %d/%d assets cleared" % (cleared, total))
    for p in problems:
        print("clearance: %s" % p, file=sys.stderr)

    if problems and not a.allow:
        print("clearance: REFUSED -- %d problem(s). Fix them, or re-run with "
              "--allow \"<why this is acceptable>\" to record a deliberate "
              "exception." % len(problems), file=sys.stderr)
        return 1
    if problems:
        print("clearance: cleared with %d recorded exception(s) over %d "
              "problem(s)" % (len(a.allow), len(problems)))
    else:
        print("clearance: cleared -- licences accounted for, metadata claims "
              "match the ledger")
    return 0


if __name__ == "__main__":
    sys.exit(main())
