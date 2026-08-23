#!/usr/bin/env python3
"""Compile a beat plan for the flat style.

There is nothing style-specific to do here. The flat style shares its
compiler with `style-paper` — same scene grammar, same staging, same motion
tiers, same score — and differs only in how the result is drawn. Compiling
through this file rather than pointing straight at the paper compiler exists
for two reasons:

* the style contract requires every entrypoint to be a script under the style
  folder, so that a style is a self-describing unit rather than a set of
  paths into a sibling; and
* it is the one place to put a style-specific compile step later, without
  changing the contract or anything that calls it.

Because the two styles compile *identically*, a board built by either one
renders in both. That is what makes an A/B honest: the edit, the timings and
the staging are the same file, and the only variable is the look.
"""

from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.normpath(
    os.path.join(HERE, "..", "..", "style-paper", "scripts"))
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)


def main():
    # Loaded by path, not by name: this file is also called `compile.py` and
    # its own directory is first on `sys.path`, so `import compile` would
    # import itself.
    path = os.path.join(ENGINE, "compile.py")
    spec = importlib.util.spec_from_file_location("paper_compile", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["paper_compile"] = mod
    spec.loader.exec_module(mod)
    return mod.main()


if __name__ == "__main__":
    raise SystemExit(main())
