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
import math
import os
import re
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


# Below this redmean distance a sheet stops reading as a shape against the
# background and becomes a silhouette. The worst offender across the whole
# palette set measured 39.6; the next worst cleared 99.
GROUND_CONTRAST = 70.0


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
    #
    # The obvious way to do that — hand out sheets in first-seen order — is
    # wrong, and produced the "invisible chair". A paper board carries more
    # distinct inks than this palette has sheets (nine against six on the
    # validation film), so a plain `papers[n % len(papers)]` *wraps*, and the
    # two inks that land on the same sheet are chosen by nothing but the order
    # they happened to appear in. On that film a bench cut from #2e5f8a and
    # the hill it stood on, cut from #7c543f, both came out #41C7B9: the same
    # flat colour, one drawn straight on top of the other, separated only by
    # its border. Four of the nine inks collapsed that way.
    #
    # So the collapse is made deliberate instead of accidental. Two inks
    # *conflict* when something carrying one is drawn on top of something
    # carrying the other, and conflicting inks are never given the same sheet
    # if it can be avoided — and where a sheet must be reused, the pair chosen
    # is the pair that never share a frame.
    conflicts = _ink_conflicts(sb)
    order, seen = [], {}
    for el in sb.get("elements", []):
        ink = el.get("ink")
        if ink and ink not in seen:
            seen[ink] = None
            order.append(ink)

    # A sheet also has to be distinguishable from the ground it is drawn on.
    # The conflict graph below separates inks from *each other* and never
    # looked at the background, so on the `voyage` palette the sheet #2E5F8A
    # was handed out freely — 39.6 redmean from that palette's own #1F6E82
    # field, against a worst case of 99 anywhere else in the set. A trawler
    # cut from it stopped reading as a boat and became a dark hole in the sky,
    # which is precisely the "everything is grey" the flat style exists to
    # avoid. The field colours are therefore permanent neighbours: a sheet
    # close to them scores badly and is chosen last, not never.
    ground = (palette["field"], palette["field2"])

    for ink in order:
        taken = {seen[o] for o in conflicts.get(ink, ()) if seen.get(o)}
        # Prefer a sheet no conflicting ink is using; among those, the one
        # furthest from every neighbour, so the separation is visible and not
        # merely nominal. Unused sheets win ties, to keep the film's spread.
        used = {v for v in seen.values() if v}
        best, best_key = papers[0], None
        for cand in papers:
            gap = min([_redmean(cand, t) for t in taken] or [999.0])
            gap = min(gap, *(_redmean(cand, g) for g in ground))
            key = (cand not in taken, gap, cand not in used)
            if best_key is None or key > best_key:
                best, best_key = cand, key
        if best in taken:
            # Every sheet is spoken for by something this ink touches. The
            # greedy picked the least-bad one; say so rather than shipping a
            # frame where two shapes silently merge.
            print("flat: warning — %s has no free sheet against %d "
                  "neighbour(s); reusing %s" % (ink, len(taken), best),
                  file=sys.stderr)
        if min(_redmean(best, g) for g in ground) < GROUND_CONTRAST:
            print("flat: warning — sheet %s reads against this palette's "
                  "background; %s will show as a silhouette"
                  % (best, ink), file=sys.stderr)
        seen[ink] = best

    for el in sb.get("elements", []):
        if el.get("ink"):
            el["ink"] = seen[el["ink"]]
    return sb


def _redmean(a, b):
    """Perceptual distance between two hex colours, 0..~765.

    The low-cost "redmean" approximation. Plain RGB distance is not good
    enough here: it rates a teal against a blue of the same lightness as a
    wide gap, when on screen they read as one shape.
    """
    r1, g1, b1 = look._rgb(a)
    r2, g2, b2 = look._rgb(b)
    rm = (r1 + r2) / 2.0
    dr, dg, db = r1 - r2, g1 - g2, b1 - b2
    return math.sqrt((2 + rm / 256.0) * dr * dr + 4.0 * dg * dg
                     + (2 + (255 - rm) / 256.0) * db * db)


def _ink_conflicts(sb):
    """Which inks are drawn on top of which, as an undirected graph.

    Two elements conflict when their boxes overlap *and* they are on screen
    at the same time. After the paper compile has resolved staging, the pairs
    that survive that test are exactly the ones that matter: a subject and
    the ground it stands on, and the members of a single beat composed
    together on purpose. Those are precisely the pairs a viewer needs to be
    able to tell apart.
    """
    line = {c.get("id"): i for i, c in enumerate(sb.get("narration") or [])}

    def when(tok, default):
        if not isinstance(tok, str):
            return default
        m = re.match(r"([A-Za-z0-9]+)([+-][\d.]+)?$", tok)
        if not m or m.group(1) not in line:
            return default
        return line[m.group(1)] * 4.0 + float(m.group(2) or 0)

    live = []
    for el in sb.get("elements") or []:
        if el.get("type") != "art" or not el.get("ink") or not el.get("fit"):
            continue
        x, y = (el.get("at") or [0, 0])[:2]
        w, h = (el.get("fit") or [0, 0])[:2]
        live.append((el["ink"],
                     (x - w / 2, y - h / 2, x + w / 2, y + h / 2),
                     (when((el.get("in") or {}).get("t"), 0.0),
                      when((el.get("out") or {}).get("t"), 1e9))))

    graph = {}
    for i, (ink_a, ba, ta) in enumerate(live):
        for ink_b, bb, tb in live[i + 1:]:
            if ink_a == ink_b:
                continue
            if not (ta[0] < tb[1] - 0.25 and tb[0] < ta[1] - 0.25):
                continue
            if not (ba[0] < bb[2] and bb[0] < ba[2]
                    and ba[1] < bb[3] and bb[1] < ba[3]):
                continue
            graph.setdefault(ink_a, set()).add(ink_b)
            graph.setdefault(ink_b, set()).add(ink_a)
    return graph


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
