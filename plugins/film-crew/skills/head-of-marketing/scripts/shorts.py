"""Render vertical YouTube Shorts from a finished 16:9 video.

Driven by `meta/shorts_spec.json` in a publish project, so the renderer is
reusable for any channel, any film. Three design decisions matter:

1. **No crop.** A centre crop to 9:16 throws away whatever is not in the
   middle third of the frame. Archive-paper documentaries like this one lay
   text and annotations across the *whole* 16:9 frame, so a crop would
   destroy the shot rather than reframe it. Instead the source is scaled to
   the canvas width (1080) at its native aspect ratio and set into a fixed
   "window", full width, with paper above and below -- nothing is thrown away.
2. **The surround is a baked PNG, not `drawtext`.** `drawtext`'s own font
   handling cannot do a multi-line, auto-shrinking, precisely positioned
   layout reliably, and its behaviour varies by ffmpeg build. Pillow builds
   the exact layout once per Short as a still image; ffmpeg's job is then
   only to scale the clip and overlay it into the transparent window --  a
   single robust `overlay`, not a pile of `drawtext` filters.
3. **The window is centred a little above the vertical middle (52%).** That
   leaves a bigger band above the video for the hook -- the one thing that
   has to be read in the first second -- than below it, where the wordmark
   and CTA are much shorter.

Usage:

    python3 shorts.py <project>                 # meta/shorts_spec.json -> out/
    python3 shorts.py <project> --only s2        # render a single entry
    python3 shorts.py <project> --from-cuts      # short*/short.json -> the spec
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_kit as bk  # noqa: E402

# ---- canvas ---------------------------------------------------------------
W, H = 1080, 1920
FPS = 30
MAX_SECONDS = 60  # YouTube's own cutoff for what counts as a Short at all.

# The source is 1920x1080; scaled to fill the canvas width, its height is
# W * 1080 / 1920 = 607.5, rounded to the nearest even number for a clean
# yuv420p encode.
WIN_W = W
WIN_H = int(round(W * 1080 / 1920 / 2)) * 2
WINDOW_CENTER_FRAC = 0.52  # a little below centre -> more room above than below

MARGIN_X = 80              # left/right text margin, matches the hook's max width
RULE_W, RULE_H = 180, 6
RULE_GAP = 46              # rule centre sits this far above the window top
FRAME_HAIRLINE = 2         # ink line framing the window top and bottom edges

# Heavy condensed sans, in order of preference. Index picks the specific face
# out of a .ttc collection (probed once, offline, against this machine's
# fonts -- see the SKILL's font stack notes).
HOOK_FONTS = [
    ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8),    # Heavy
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 4),      # Condensed ExtraBold
    ("/System/Library/Fonts/HelveticaNeue.ttc", 4),            # Condensed Bold
    ("/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf", 0),
    ("/System/Library/Fonts/Supplemental/Impact.ttf", 0),
    ("/Library/Fonts/Arial Bold.ttf", 0),
]
LABEL_FONTS = HOOK_FONTS  # wordmark: same heavy condensed family, smaller
CTA_FONTS = [
    ("/System/Library/Fonts/Avenir Next Condensed.ttc", 2),    # Demi Bold
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),            # Regular
    ("/System/Library/Fonts/Supplemental/Futura.ttc", 0),      # Medium
    ("/Library/Fonts/Arial.ttf", 0),
]

HOOK_MAX_SIZE, HOOK_MIN_SIZE = 92, 54
WORDMARK_MAX_SIZE, WORDMARK_MIN_SIZE = 50, 28
WORDMARK_TRACKING = 9
CTA_SIZE, CTA_MIN_SIZE = 30, 20


def _load_font(path, index, size):
    return ImageFont.truetype(path, size, index=index)


def _font_stack(candidates, size):
    """First candidate that actually loads on this machine, at `size`.

    Never raises: a missing font face is common (a `.ttc` index that exists
    on one macOS version and not another, a font moved to `/Library/Fonts`),
    and losing an entire render over it would be worse than a plainer font.
    """
    for path, index in candidates:
        try:
            return _load_font(path, index, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow: load_default() takes no size
        return ImageFont.load_default()


def _mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _tracked_width(draw, text, font, tracking):
    if not text:
        return 0.0
    widths = [draw.textlength(ch, font=font) for ch in text]
    return sum(widths) + tracking * (len(text) - 1)


def _draw_tracked(draw, cx, cy, text, font, fill, tracking):
    """Draw a single line with manual letter-spacing.

    Pillow's `ImageFont` has no kerning/tracking control, unlike the CoreText
    path used elsewhere in this skill -- so each glyph is placed by hand.
    """
    if not text:
        return
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, cy), ch, font=font, fill=fill, anchor="lm")
        x += w + tracking


def _fit_tracked(draw, text, candidates, max_w, start, minimum, tracking=0):
    """Shrink font size until `text` (with tracking) fits `max_w`."""
    size = start
    while size > minimum:
        font = _font_stack(candidates, size)
        if _tracked_width(draw, text, font, tracking) <= max_w:
            return font
        size -= 2
    return _font_stack(candidates, minimum)


def _fit_hook(draw, hook, max_w, max_h, start=HOOK_MAX_SIZE, minimum=HOOK_MIN_SIZE):
    """Shrink the (explicit-`\\n`) hook until every line fits `max_w` and the
    whole block fits `max_h`. Lines are never rewrapped -- only the authored
    breaks are honoured."""
    lines = [ln.strip() for ln in hook.split("\n") if ln.strip()]
    size = start
    while size > minimum:
        font = _font_stack(HOOK_FONTS, size)
        widths = [draw.textlength(ln, font=font) for ln in lines]
        ascent, descent = font.getmetrics()
        line_h = (ascent + descent) * 1.16
        if max(widths, default=0) <= max_w and line_h * len(lines) <= max_h:
            return font, lines, line_h
        size -= 2
    font = _font_stack(HOOK_FONTS, minimum)
    ascent, descent = font.getmetrics()
    return font, lines, (ascent + descent) * 1.16


def window_geometry():
    cy = round(H * WINDOW_CENTER_FRAC)
    top = cy - WIN_H // 2
    return {"w": WIN_W, "h": WIN_H, "top": top, "bottom": top + WIN_H}


def build_card(pub, hook, cta, geometry, out_path):
    """Paint the 1080x1920 paper surround, with a transparent video window.

    Everything opaque is painted first; the window is punched fully
    transparent as the very last step so nothing -- grain, vignette, a rule
    drawn a pixel too long -- can leak into where the film shows through.
    """
    ink = pub.rgb("ink")
    crimson = pub.rgb("crimson")
    paper = pub.rgb("paper")
    wordmark = (pub.get("brand", "wordmark", default="") or "").upper()

    base = Image.new("RGB", (W, H), paper)
    base = bk.vignette(base, strength=0.28)
    base = bk.texture(base, amount=5)
    img = base.convert("RGBA")
    draw = ImageDraw.Draw(img)

    top, bottom = geometry["top"], geometry["bottom"]
    max_text_w = W - 2 * MARGIN_X

    # ---- hook, top band -----------------------------------------------
    rule_cy = top - RULE_GAP
    hook_bottom = rule_cy - RULE_H / 2 - 26
    hook_top = 72
    font, lines, line_h = _fit_hook(draw, hook, max_text_w, hook_bottom - hook_top)
    block_h = line_h * len(lines)
    y = hook_top + (hook_bottom - hook_top - block_h) / 2 + line_h / 2
    for ln in lines:
        draw.text((W / 2, y), ln, font=font, fill=ink, anchor="mm", align="center")
        y += line_h

    # ---- red rule between hook and window ------------------------------
    bk.rounded_bar(draw, W / 2 - RULE_W / 2, rule_cy - RULE_H / 2, RULE_W, RULE_H,
                    crimson, r=RULE_H / 2)

    # ---- ink hairline framing the window --------------------------------
    # Only top and bottom: the window is the full canvas width, so a
    # left/right hairline would sit on the very edge pixels the video
    # overlay covers -- invisible by construction, not a missing feature.
    draw.rectangle([0, top - FRAME_HAIRLINE, W, top - 1], fill=ink)
    draw.rectangle([0, bottom, W, bottom + FRAME_HAIRLINE - 1], fill=ink)

    # ---- wordmark + cta, bottom band ------------------------------------
    band_top = bottom + FRAME_HAIRLINE
    band_h = H - band_top
    wm_cy = band_top + band_h * 0.40
    cta_cy = band_top + band_h * 0.66

    if wordmark:
        wfont = _fit_tracked(draw, wordmark, LABEL_FONTS, max_text_w,
                              WORDMARK_MAX_SIZE, WORDMARK_MIN_SIZE,
                              tracking=WORDMARK_TRACKING)
        _draw_tracked(draw, W / 2, wm_cy, wordmark, wfont, ink, WORDMARK_TRACKING)

    if cta:
        cfont = _fit_tracked(draw, cta, CTA_FONTS, max_text_w, CTA_SIZE, CTA_MIN_SIZE)
        muted = _mix(ink, paper, 0.45)
        draw.text((W / 2, cta_cy), cta, font=cfont, fill=muted, anchor="mm")

    # ---- punch the window transparent, last -----------------------------
    draw.rectangle([0, top, W, bottom - 1], fill=(0, 0, 0, 0))

    img.save(out_path)
    return out_path


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float((out.stdout or "").strip())
    except ValueError:
        return 0.0


def compose(src, card_path, start, dur, dest, geometry, accurate=False):
    """Trim `src` to [start, start+dur) and overlay it into the card's window.

    Two trimming tiers, tried in order by the caller:

    - fast (`accurate=False`): `-ss`/`-t` as *input* options. ffmpeg's default
      "accurate seek" decodes and discards up to `start` rather than snapping
      to the nearest keyframe, so this is normally frame-exact and is much
      cheaper than decoding from the start of a 12-minute file.
    - accurate (`accurate=True`): the same trim as *output* options instead,
      forcing a full decode of the source from its own beginning. Slower, but
      immune to any keyframe-placement edge case the fast path might hit.
    """
    win_w, win_h, top = geometry["w"], geometry["h"], geometry["top"]
    filt = (f"[1:v]scale={win_w}:{win_h}:flags=lanczos,setsar=1[vid];"
            f"[0:v][vid]overlay=0:{top}:shortest=1,format=yuv420p[vout]")

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-loop", "1", "-framerate", str(FPS), "-i", card_path]

    tail = []
    if accurate:
        cmd += ["-i", src]
        tail = ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}"]
    else:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", src]

    cmd += ["-filter_complex", filt, "-map", "[vout]", "-map", "1:a?",
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            *tail, "-shortest", "-movflags", "+faststart", dest]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {os.path.basename(dest)}: "
                            f"{r.stderr[-800:]}")


def render_short(pub, spec_entry, geometry, say):
    sid = spec_entry["id"]
    start, end = float(spec_entry["start"]), float(spec_entry["end"])
    dur = end - start

    card_path = pub.p("out", f"short_{sid}_card.png")
    dest = pub.p("out", f"short_{sid}.mp4")
    build_card(pub, spec_entry.get("hook", ""), spec_entry.get("cta", ""),
               geometry, card_path)

    # A cut names the film it was taken from; only fall back to the project's
    # own video when it does not. Rendering every short from `publish.json`'s
    # video slices episode one at episode two's timestamps without a word.
    src = spec_entry.get("source")
    src = os.path.join(pub.root, src) if src else pub.video
    if not os.path.exists(src):
        raise SystemExit(f"{sid}: missing source video {src}")
    compose(src, card_path, start, dur, dest, geometry, accurate=False)
    actual = _probe_duration(dest)
    if abs(actual - dur) > 0.15:
        say(f"  {sid}: fast trim gave {actual:.2f}s (wanted {dur:.2f}s) -- "
            f"retrying with output-side trimming")
        compose(src, card_path, start, dur, dest, geometry, accurate=True)
        actual = _probe_duration(dest)
        if abs(actual - dur) > 0.15:
            raise RuntimeError(
                f"short {sid!r}: duration is still {actual:.2f}s after the "
                f"accurate fallback (wanted {dur:.2f}s)")

    size_kb = os.path.getsize(dest) / 1024
    say(f"{sid}: {actual:.2f}s -> {os.path.relpath(dest, pub.root)} ({size_kb:.0f} KB)")
    return dest


def wrap_hook(text, per_line=3):
    """Break a one-line cut title into the 2-3 short lines a hook wants.

    The story editor writes `title` as prose; the surround needs real
    newlines, balanced so no line is a lone orphan word.
    """
    words = text.split()
    if len(words) <= per_line:
        return " ".join(words)
    lines = max(2, min(3, round(len(words) / per_line)))
    per = len(words) / lines
    out, i = [], 0
    for n in range(lines):
        j = len(words) if n == lines - 1 else int(round(per * (n + 1)))
        out.append(" ".join(words[i:j]))
        i = j
    return "\n".join(ln for ln in out if ln)


#: `short1`, `short12` -- the cut directories the story editor writes.
SHORT_DIR = re.compile(r"^short(\d+)$")


def spec_from_cuts(pub, cta, dest=None, force=False):
    """Assemble `meta/shorts_spec.json` from the story editor's cut files.

    The `cut` stage writes one `short<N>/short.json` per short -- where the
    cut is and why. `shorts.py` renders from `meta/shorts_spec.json`. Nothing
    bridged the two, so every short had to be transcribed by hand and the
    `--short N` flag only worked as far as the decision.
    """
    found = []
    for path in glob.glob(os.path.join(pub.root, "short*", "short.json")):
        stem = os.path.basename(os.path.dirname(path))
        m = SHORT_DIR.match(stem)
        if not m:
            raise SystemExit(
                f"{stem!r} is not a cut directory; name it short1, short2, ...")
        found.append((int(m.group(1)), path))
    if not found:
        raise SystemExit(
            f"no short*/short.json under {pub.root} -- run the `cut` stage first")
    # Numeric order, so short10 does not sort before short2.
    found.sort()

    seen, shorts = {}, []
    for n, path in found:
        c = json.load(open(path))
        sid = f"s{n}"
        if sid in seen:
            raise SystemExit(f"{path} and {seen[sid]} both map to id {sid!r}")
        seen[sid] = path
        for key in ("start", "end"):
            if key not in c:
                raise SystemExit(f"{path}: missing {key!r}")
        title = c.get("title")
        # `why` is the editing rationale, written for whoever reviews the cut.
        # Promoting it to the hook would publish an internal note as the first
        # line a viewer reads, so a missing title is an error, not a fallback.
        if not isinstance(title, str) or not title.strip():
            raise SystemExit(
                f"{path}: needs a non-empty `title` -- it becomes the on-screen "
                "hook, and `why` is an editing note, not viewer-facing copy")
        entry = {"id": sid,
                 "start": round(float(c["start"]), 2),
                 "end": round(float(c["end"]), 2),
                 "hook": wrap_hook(title.strip().upper()),
                 "cta": cta}
        # Which film this cut came from. Without it every short renders from
        # whatever `publish.json` happens to name, so a cut taken from episode
        # two silently slices episode one at episode two's timestamps.
        src = c.get("source_video") or c.get("film")
        if src:
            entry["source"] = src
        shorts.append(entry)

    dest = dest or pub.p("meta", "shorts_spec.json")
    if os.path.exists(dest) and not force:
        raise SystemExit(
            f"{dest} exists -- pass --force to replace it "
            "(hand-tuned hooks and CTAs would be lost)")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"shorts": shorts}, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, dest)
    return dest, shorts


def main():
    ap = argparse.ArgumentParser(
        description="Render vertical YouTube Shorts from meta/shorts_spec.json")
    ap.add_argument("project", help="directory containing publish.json")
    ap.add_argument("--spec", default=None,
                     help="defaults to <project>/meta/shorts_spec.json")
    ap.add_argument("--only", default=None, help="render only this short id")
    ap.add_argument("--from-cuts", action="store_true",
                    help="build the spec from short*/short.json, then render")
    ap.add_argument("--cta", default="FULL FILM IN DESCRIPTION",
                    help="call to action baked under the window")
    ap.add_argument("--force", action="store_true",
                    help="let --from-cuts replace an existing spec")
    a = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _shared  # noqa: F401  (locates config.py in the publisher skill)
    from config import Publish, say

    pub = Publish(a.project)
    if a.from_cuts:
        spec_path, built = spec_from_cuts(
            pub, a.cta, dest=a.spec, force=a.force)
        say(f"{len(built)} cut(s) -> {os.path.relpath(spec_path, pub.root)}")
    else:
        spec_path = a.spec or pub.p("meta", "shorts_spec.json")
    if not os.path.exists(spec_path):
        raise SystemExit(f"missing {spec_path}")
    spec = json.load(open(spec_path))
    shorts = spec.get("shorts") or []
    if not shorts:
        raise SystemExit(f"{spec_path} has no shorts[]")

    if a.only:
        shorts = [s for s in shorts if s.get("id") == a.only]
        if not shorts:
            raise SystemExit(f"no short with id {a.only!r} in {spec_path}")

    # Every entry needs a readable source before any work starts.
    for sh in shorts:
        srel = sh.get("source")
        sp = os.path.join(pub.root, srel) if srel else pub.video
        if not os.path.exists(sp):
            raise SystemExit(
                f"{sh.get('id')}: missing source video: {sp}")

    # Fail the whole batch up front if any entry is oversized. A Short over
    # 60s silently uploads as an ordinary video -- discovering that after
    # rendering (and maybe uploading) is a much more expensive mistake than
    # refusing before any work starts.
    for s in shorts:
        dur = float(s["end"]) - float(s["start"])
        if dur <= 0:
            raise SystemExit(f"short {s.get('id')!r}: end must be after start")
        if dur >= MAX_SECONDS:
            raise SystemExit(
                f"short {s.get('id')!r} is {dur:.1f}s -- YouTube Shorts must "
                f"stay under {MAX_SECONDS}s or the upload is treated as an "
                f"ordinary video and the whole point is lost")

    os.makedirs(pub.p("out"), exist_ok=True)
    geometry = window_geometry()
    made = [render_short(pub, s, geometry, say) for s in shorts]
    say(f"rendered {len(made)} Short(s) into {pub.p('out')}")
    return made


if __name__ == "__main__":
    main()
