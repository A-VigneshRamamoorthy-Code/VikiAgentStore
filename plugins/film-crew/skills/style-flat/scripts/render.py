#!/usr/bin/env python3
"""Render a storyboard in the mid-century flat-vector style.

    python3 render.py storyboard.json -o film.mp4
    python3 render.py storyboard.json --sheet          # contact sheet
    python3 render.py storyboard.json --frame 12.5     # one frame

Everything about *timing, staging, camera, motion and sound* is the shared
engine in `style-paper/scripts`. This module changes only what the frame
looks like, by re-pointing three functions before that engine is asked to
draw anything:

    collage.sticker   -> look.flat_sticker   (no torn border, no shadow)
    paper.add_grain   -> look.no_grain       (no texture)
    paper.parchment   -> look.colour_field   (a saturated field, not a sheet)

Doing it this way is a deliberate trade. Writing a second renderer would have
meant re-drawing forty-odd illustrations to get a second look; patching the
look layer means every drawing the paper style has ever had renders flat for
free, and any illustration added later arrives in both styles at once.

The cost is that this style cannot express anything the shared element model
cannot — it gets no per-shape gradients and no outline weights of its own.
For flat vector that is very nearly free, because the style's own rule is
that shapes are untextured, unoutlined and unshaded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
#: The shared engine. Kept as a sibling skill rather than vendored, so a fix
#: to staging or scoring reaches both styles instead of one.
ENGINE = os.path.normpath(
    os.path.join(HERE, "..", "..", "style-paper", "scripts"))
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import look  # noqa: E402


def _engine():
    """Import the paper engine's renderer by path, never by name.

    This module is also called `render.py`, so a plain ``import render``
    resolves to whichever directory happens to be first on `sys.path` — and
    since this file's own directory is prepended automatically when it is run
    as a script, that is *this* file. The first version of this wrapper did
    exactly that and silently loaded itself, which is why the look patches
    appeared to do nothing: they were applied to one pair of module objects
    while a second copy of the engine drew the frames.
    """
    import importlib.util
    path = os.path.join(ENGINE, "render.py")
    spec = importlib.util.spec_from_file_location("paper_render", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["paper_render"] = mod
    spec.loader.exec_module(mod)
    return mod


def install(palette):
    """Swap the paper look for the flat one, before anything is drawn.

    Order matters. `illustrations` does ``from paper import PALETTE`` at
    import time and binds `add_grain` by attribute at call time, so the
    module-level table has to be *mutated in place* rather than rebound — a
    reassignment here would leave the already-imported name pointing at the
    old dict and the film would come out in paper colours with flat edges.
    """
    import collage
    import illustrations
    import paper

    before = dict(paper.PALETTE)

    collage.sticker = look.flat_sticker
    paper.add_grain = look.no_grain
    illustrations.paper.add_grain = look.no_grain

    field, field2 = palette["field"], palette["field2"]

    def parchment(w, h, seed=7, light=None, deep=None, blotches=9):
        # Two different things call this: the *field* — frame-sized, and the
        # one surface whose colour this style owns — and small surfaces like
        # caption chips, note cards and labels, which name a stock colour
        # because they mean it.
        #
        # Ignoring `light` for both made every caption card the same
        # near-black as the field behind it. Honouring it for both put the
        # paper stock back as the film's background. Size is what tells them
        # apart: nothing but the board is frame-sized.
        if light is not None and max(w, h) < 1200:
            return look.colour_field(w, h, light, deep or light, seed=seed)
        return look.colour_field(w, h, field, field2, seed=seed)

    paper.parchment = parchment

    # Captions are the one element that must survive any field colour, so
    # they get an explicit high-contrast pair rather than inheriting the
    # scenery ink — which in a dark palette is near-black on near-black.
    chip_bg = look._rgb(palette["papers"][1])
    chip_fg = look._rgb(palette["field"])
    _label_chip = collage.label_chip

    def label_chip(text, *a, **kw):
        kw.setdefault("fg", chip_fg)
        kw["bg"] = chip_bg
        kw["torn"] = False
        return _label_chip(text, *a, **kw)

    collage.label_chip = label_chip

    # Shape internals — cards, tape, the fallback ink — follow the palette
    # too. Left alone they stay beige, which is precisely the bug that made
    # every paper film brown no matter which palette it chose.
    flat = {
        "paper_light": look._rgb(field), "paper_mid": look._rgb(field2),
        "paper_deep": look._rgb(field2), "paper_shadow": look._rgb(field2),
        "ink": look._rgb(palette["ink"]),
        "ink_soft": look._rgb(palette["papers"][0]),
        "accent": look._rgb(palette["papers"][0]),
        "accent_deep": look._rgb(palette["papers"][-1]),
        "card": look._rgb(field), "tape": look._rgb(palette["papers"][1]),
        "night": look._rgb(field),
    }
    paper.PALETTE.update(flat)
    illustrations.PALETTE.update(flat)
    illustrations.INK = look._rgb(palette["ink"])
    _retint_defaults(before, flat, collage, illustrations, paper)


def _retint_defaults(before, after, *modules):
    """Rewrite palette colours captured in function *default arguments*.

    Many drawing helpers are declared as ``def marker_rect(..., color=
    PALETTE["accent"])``. A default is evaluated once, when the module is
    imported, so it holds the *value* — mutating `PALETTE` afterwards does
    nothing for them. That is why the first flat render came back with a
    white note card on a near-black field: the field had been repainted and
    the card had not.

    Rather than chase each one, every module-level function is scanned and
    any default that matches a colour the palette used to hold is swapped for
    the colour it holds now.
    """
    swap = {}
    for key, old in before.items():
        new = after.get(key)
        if new is None or tuple(old) == tuple(new):
            continue
        swap[tuple(old)] = tuple(new)
        swap[tuple(old) + (255,)] = tuple(new) + (255,)
    if not swap:
        return 0

    def _sub(v):
        if isinstance(v, tuple) and v in swap:
            return swap[v]
        return v

    n = 0
    for mod in modules:
        for fn in vars(mod).values():
            if not isinstance(fn, types.FunctionType):
                continue
            if fn.__defaults__:
                new = tuple(_sub(v) for v in fn.__defaults__)
                if new != fn.__defaults__:
                    fn.__defaults__ = new
                    n += 1
            if fn.__kwdefaults__:
                new = {k: _sub(v) for k, v in fn.__kwdefaults__.items()}
                if new != fn.__kwdefaults__:
                    fn.__kwdefaults__ = new
                    n += 1
    return n


def restyle(sb, palette):
    """Rewrite a storyboard's colours for this style.

    A board compiled for paper carries paper colours: a stock, an ink and a
    per-element sheet drawn from a muted set. Those are re-mapped onto the
    flat palette here rather than at compile time, so **the same storyboard
    renders in either style** and any difference between the two films is
    genuinely the look and not a different edit.
    """
    st = sb.setdefault("style", {})
    st["paper_light"] = list(look._rgb(palette["field"]))
    st["paper_deep"] = list(look._rgb(palette["field2"]))
    st["ink"] = palette["ink"]
    st["accent"] = palette["papers"][0]
    st["texture"] = "none"
    # Board-level medium effects. Every one of these exists to sell paper —
    # fibre noise, ink bleed, a ghosted print showing through the sheet. In a
    # style whose whole claim is that there is no sheet they are not just
    # unnecessary, they are the thing that keeps it looking like paper.
    st["grain"] = 0
    st["blotches"] = 0
    st["ghost_print"] = False
    st["map_underlay"] = False
    st["vignette"] = 0.12

    papers = palette["papers"]
    # Map each distinct paper ink onto a flat sheet, keeping the *grouping*:
    # things that were the same colour stay the same colour, so the board's
    # own colour logic survives the translation.
    seen = {}
    for el in sb.get("elements", []):
        ink = el.get("ink")
        if not ink:
            continue
        if ink not in seen:
            seen[ink] = papers[len(seen) % len(papers)]
        el["ink"] = seen[ink]
    return sb


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="render.py",
        description="Storyboard -> mid-century flat-vector film.")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--palette", default=None,
                    help="one of: %s" % ", ".join(sorted(look.PALETTES)))
    args, rest = ap.parse_known_args(argv)

    with open(args.storyboard, encoding="utf-8") as fh:
        sb = json.load(fh)

    name, palette = look.choose(
        paper_name=(sb.get("style") or {}).get("palette"),
        mood=args.palette or (sb.get("music") or {}).get("mood"))
    if args.palette in look.PALETTES:
        name, palette = args.palette, dict(look.PALETTES[args.palette])

    install(palette)
    sb = restyle(sb, palette)

    out_sb = os.path.join(
        os.path.dirname(os.path.abspath(args.storyboard)),
        "_flat_" + os.path.basename(args.storyboard))
    with open(out_sb, "w", encoding="utf-8") as fh:
        json.dump(sb, fh, indent=1)

    print("flat: palette %r — %s" % (name, palette["note"]), file=sys.stderr)

    engine = _engine()
    argv2 = [out_sb] + rest
    if args.out:
        argv2 += ["-o", args.out]
    # The engine's `main()` parses `sys.argv` itself rather than taking an
    # argument list, so the flags are handed over that way. `_engine()` must
    # be called *after* `install()`, so the renderer binds the patched
    # modules as it imports them.
    sys.argv = ["render.py"] + argv2
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
