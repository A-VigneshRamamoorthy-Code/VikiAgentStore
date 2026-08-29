#!/usr/bin/env python3
"""Resolve where this style's art comes from.

    python3 asset_library.py --check          # print the resolved root, exit 0/1
    python3 asset_library.py --set /path      # remember a root for next time
    python3 asset_library.py --forget         # go back to the bundled art
    python3 asset_library.py --prompt         # emit the first-run question
    python3 asset_library.py --find characters/emma   # search every root in order

Most art a film needs is already committed under `assets/packs/`. This module
exists for the art that cannot be: commercial character kits, EPS/AI packs
bought from a stock site, a studio's own library. That material is usable in a
film and **not** redistributable inside an MIT-licensed skill, so it lives
outside the skill entirely and is pointed at rather than copied in.

Resolution order, first hit wins:

  1. ``$FILM_CREW_ASSETS``            -- an absolute path, or a colon-separated
                                        list of them, highest priority first
  2. ``~/.config/film-crew/assets``   -- whatever ``--set`` last wrote
  3. ``<skill>/assets/local``         -- the bundled, gitignored scratch dir
  4. ``<skill>/assets/packs``         -- the committed CC0 packs

Rules 3 and 4 always exist, so **a missing or skipped external library is not
an error**. Everything degrades to the art that ships with the skill, which is
why the first-run prompt is allowed to be declined.

Nothing here downloads anything. `fetch_assets.py` owns the network and its
licence gate; this owns "where do I look", and the two do not overlap.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
BUNDLED_LOCAL = os.path.join(SKILL_DIR, "assets", "local")
BUNDLED_PACKS = os.path.join(SKILL_DIR, "assets", "packs")

ENV_VAR = "FILM_CREW_ASSETS"

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "film-crew")
CONFIG_PATH = os.path.join(CONFIG_DIR, "assets.json")

# The question to ask once, on first use, and never again. Phrased so that
# "no" is a complete and correct answer -- a user who has no such library, or
# who does not want the skill reading outside its own directory, must not be
# left thinking the skill is now broken.
PROMPT = f"""\
Point this style at your own art library?

Commercial character kits and stock packs cannot be committed inside the
skill, so if you have one, tell me where it is and I will read from it.

  Set it for this shell only:   export {ENV_VAR}=/path/to/your/assets
  Remember it for next time:    python3 scripts/asset_library.py --set /path/to/your/assets

Skip this and the film uses the CC0 art bundled with the skill, plus anything
you drop into assets/local/. That is a complete, working setup -- skipping
costs you nothing but the extra art.\
"""


def _split(value):
    """Absolute, existing directories from a PATH-style string, in order."""
    out = []
    for chunk in (value or "").split(os.pathsep):
        chunk = os.path.expanduser(chunk.strip())
        if not chunk:
            continue
        chunk = os.path.abspath(chunk)
        if os.path.isdir(chunk) and chunk not in out:
            out.append(chunk)
    return out


def configured():
    """The root recorded by ``--set``, or None. A broken config is not fatal."""
    try:
        with open(CONFIG_PATH) as fh:
            return _split(json.load(fh).get("root", ""))
    except (OSError, ValueError):
        return []


def roots(include_bundled=True):
    """Every directory to search, highest priority first.

    The env var wins over the config file so a single render can be pointed
    somewhere else without editing anything -- which is what makes this usable
    from a batch job or a rented render box.
    """
    found = list(_split(os.environ.get(ENV_VAR)))
    for path in configured():
        if path not in found:
            found.append(path)
    if include_bundled:
        for path in (BUNDLED_LOCAL, BUNDLED_PACKS):
            if os.path.isdir(path) and path not in found:
                found.append(path)
    return found


def external():
    """Only the user's own roots -- what the first-run prompt is asking about."""
    return roots(include_bundled=False)


def find(relpath, required=False):
    """First existing match for *relpath* across the roots, or None.

    Pass ``required=True`` to raise instead. Prefer that anywhere a missing
    asset means the shot is wrong: a silent None becomes a figure with no head
    several hundred frames later, at which point nothing points back to here.
    """
    for root in roots():
        candidate = os.path.join(root, relpath)
        if os.path.exists(candidate):
            return candidate
    if required:
        raise FileNotFoundError(
            f"{relpath!r} is in none of: {', '.join(roots()) or '(no roots)'}. "
            f"Set ${ENV_VAR} to your art library, or drop the file into "
            f"{BUNDLED_LOCAL}.")
    return None


def remember(path):
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        raise NotADirectoryError(path)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as fh:
        json.dump({"root": path}, fh, indent=2)
        fh.write("\n")
    return path


def forget():
    try:
        os.remove(CONFIG_PATH)
        return True
    except OSError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="print resolved roots; exit 1 if no external library")
    ap.add_argument("--set", metavar="DIR", help="remember DIR for next time")
    ap.add_argument("--forget", action="store_true", help="drop the saved root")
    ap.add_argument("--prompt", action="store_true",
                    help="print the first-run question")
    ap.add_argument("--find", metavar="RELPATH", help="resolve one asset path")
    args = ap.parse_args(argv)

    if args.set:
        try:
            print(f"remembered: {remember(args.set)}")
        except NotADirectoryError as exc:
            print(f"not a directory: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.forget:
        print("forgotten" if forget() else "nothing saved")
        return 0

    if args.prompt:
        # Already answered, one way or another -- do not ask twice.
        if external() or os.path.exists(CONFIG_PATH):
            print(f"asset library already configured: "
                  f"{', '.join(external()) or '(none, previously declined)'}")
            return 0
        print(PROMPT)
        return 0

    if args.find:
        hit = find(args.find)
        print(hit or "")
        return 0 if hit else 1

    ext = external()
    print(f"${ENV_VAR}={os.environ.get(ENV_VAR) or '(unset)'}")
    print(f"config      {CONFIG_PATH if os.path.exists(CONFIG_PATH) else '(none)'}")
    for i, root in enumerate(roots(), 1):
        tag = "external" if root in ext else "bundled"
        print(f"  {i}. [{tag}] {root}")
    if args.check and not ext:
        print("no external library configured -- using bundled art only")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
