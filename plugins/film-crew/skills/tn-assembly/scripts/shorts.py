"""Render a planned moment as a vertical Short that routes back to the episode.

A Short is a trailer, not a highlight reel. Three things decide whether it
works:

1. **The frame.** Chamber footage is a wide 16:9 shot, so a centre crop throws
   away the speaker. The source is blurred and scaled to fill 1080x1920 with
   the real footage held full-width in the middle -- nothing is cropped away,
   and the padding reads as deliberate rather than as a letterbox.
2. **The first second.** Vertical feeds are swiped, not browsed. The hook card
   is burned over the opening frames rather than played before them, so the
   footage is already moving while the claim is being read.
3. **The exit.** Every Short names the episode it came from. A Short that ends
   without sending the viewer anywhere converts nothing.

Text is composited as CoreText-rendered PNG cards rather than ffmpeg's
`drawtext`. That is not a workaround: `drawtext` has no complex-script shaping,
so Tamil (and Devanagari, Arabic, ...) come out as broken glyph sequences. Many
ffmpeg builds also ship without the filter entirely.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, parse_approvals, require_overwrite_approval, say  # noqa: E402


def vertical_filter(w, h, mode="fill", focus=0.5):
    """Fit 16:9 chamber footage into a 1080x1920 frame.

    `fill` scales the source until it covers the frame and crops the sides, so
    the picture reaches every edge. This is the default because the
    alternative reads as a mistake: a blurred, mirrored copy of the same shot
    behind a strip of real footage looks like a horizontal video someone
    forgot to reframe, and it spends more than half the screen on something
    deliberately unwatchable, in a feed where the whole screen is the product.

    The cost is real -- cropping a wide shot does throw away the sides -- so
    `focus` moves the crop window horizontally (0 = left edge, 1 = right).
    A chamber camera frames whoever holds the floor near the middle, which is
    why 0.5 is a sane default rather than a lazy one, but a fixed-angle feed
    that sits the podium off-centre needs this set.

    `blur` keeps the earlier pillarboxed treatment for sources that genuinely
    cannot be cropped -- a wide two-shot where both faces matter, or slides
    and scoreboards where the edges carry the information.
    """
    if mode == "blur":
        return (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=28:2,eq=brightness=-0.12[bg];"
            f"[0:v]scale={w}:-2:flags=lanczos[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
        )
    focus = min(max(float(focus), 0.0), 1.0)
    return (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase:"
        f"flags=lanczos,crop={w}:{h}:(iw-{w})*{focus:.4f}:(ih-{h})/2[v]"
    )


def text_card(text, w, size, fg, bg, pad=30, font=None):
    """Rasterise one line of any script into an RGBA card via CoreText."""
    from PIL import Image
    import ct_text as ct

    font = font or (ct.TAMIL_BOLD if any(ord(c) > 0x0B00 for c in text)
                    else ct.LATIN_HEAVY)
    glyphs = ct.render_text(text, font, size, fg + (255,))
    cw = min(w - 40, glyphs.width + pad * 2)
    card = Image.new("RGBA", (cw, glyphs.height + pad * 2), bg + (235,))
    card.paste(glyphs, ((cw - glyphs.width) // 2, pad), glyphs)
    return card


def make_cards(pr, hook, cta, workdir):
    """Write the hook and CTA cards to disk, returning overlay jobs."""
    from config import publish_scripts
    publish_scripts()

    sh = pr["shorts"]
    w, h = sh["width"], sh["height"]
    ink = tuple(pr.get("brand", "ink", default=[10, 14, 26]))
    crimson = tuple(pr.get("brand", "crimson", default=[214, 34, 54]))
    os.makedirs(workdir, exist_ok=True)

    jobs = []
    if hook:
        p = os.path.join(workdir, "hook.png")
        text_card(hook, w, 66, (255, 255, 255), ink).save(p)
        jobs.append({"path": p, "y": int(h * 0.14), "enable": "lt(t,2.8)"})
    if cta:
        p = os.path.join(workdir, "cta.png")
        text_card(cta, w, 52, (255, 255, 255), crimson).save(p)
        jobs.append({"path": p, "y": int(h * 0.76), "tail": 3.0})
    return jobs


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def subject_focus(pr, short, default=0.5):
    """Where to aim a vertical crop, from where the speaker actually was.

    Filling a 9:16 frame from a 16:9 source keeps only about a third of the
    width, so a fixed centre crop removes the speaker outright whenever the
    chamber feed is not centred on them. The face sweep already recorded a
    horizontal position for every close-up it saw; averaging the ones inside
    this Short aims the crop at the subject instead of at the middle of the
    room.

    Averaging rather than tracking is deliberate: a crop that follows a face
    frame by frame looks like a handheld camera, and a Short is short enough
    that one well-chosen fixed position reads as intentional framing.
    """
    hits = (pr.load("vip_hits") or {}).get("hits", [])
    if not hits:
        return default
    a, b = short.get("start", 0.0), short.get("end", 0.0)
    xs = [h["cx"] for h in hits
          if "cx" in h and a <= h.get("t", -1) <= b]
    if not xs:
        return default
    return min(0.85, max(0.15, sum(xs) / len(xs)))


def render(pr, short, src, dest, hook="", cta=""):
    sh = pr["shorts"]
    w, h, fps = sh["width"], sh["height"], sh["fps"]

    jobs = make_cards(pr, hook, cta, os.path.join(
        os.path.dirname(dest), f"_cards_{short.get('id', 'x')}"))
    dur = duration(src)

    manual = sh.get("focus_x")
    manual = 0.5 if manual is None else float(manual)
    focus = (subject_focus(pr, short, default=manual)
             if sh.get("focus_auto", True) else manual)
    chain = vertical_filter(w, h, sh.get("framing", "fill"), focus)
    inputs = []
    for i, job in enumerate(jobs, 1):
        inputs += ["-i", job["path"]]
        enable = job.get("enable") or f"gt(t,{max(0, dur - job['tail']):.2f})"
        chain += (f";[v][{i}:v]overlay=(W-w)/2:{job['y']}:"
                  f"enable='{enable}'[v]")

    cmd = [
        "ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", src, *inputs,
        "-filter_complex", chain, "-map", "[v]", "-map", "0:a?",
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p",
        # loudnorm silently resamples to 96 kHz; force 48 kHz back or the
        # muxed audio drifts out of spec.
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", dest,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"render failed: {r.stderr[-500:]}")
    return dest


def main():
    ap = argparse.ArgumentParser(description="Render planned Shorts to 9:16")
    ap.add_argument("project")
    ap.add_argument("--only", default=None, help="short id, e.g. sh02")
    ap.add_argument("--approve-overwrite", action="append", default=[],
                    help="allow replacing an existing artifact as path:sha256")
    a = ap.parse_args()

    pr = Project(a.project)
    approvals = parse_approvals(a.approve_overwrite)
    plan = pr.load("plan")
    if not plan:
        raise SystemExit("no meta/plan.json -- run plan.py first")

    outdir = pr.p("out", "shorts")
    os.makedirs(outdir, exist_ok=True)
    made = 0
    missing = []

    for s in plan["shorts"]:
        if a.only and s["id"] != a.only:
            continue
        src = pr.p(s.get("file", "")) if s.get("file") else None
        if not src or not os.path.exists(src):
            missing.append(s["id"])
            say(f"! {s['id']}: no cut clip yet -- run cut.py first")
            continue
        dest = os.path.join(outdir, f"{s['id']}.mp4")
        hook = s.get("hook") or s.get("label") or ""
        cta = s.get("cta") or pr.get("shorts", "cta", default="")
        say(f"{s['id']}: {s['length']:.0f}s -> {os.path.basename(dest)}")
        require_overwrite_approval(dest, pr, approvals)
        render(pr, s, src, dest, hook, cta)
        s["render"] = os.path.relpath(dest, pr.root)
        made += 1

    pr.save("plan", plan)
    say(f"rendered {made} Short(s) into {outdir}")
    if missing:
        raise SystemExit(f"missing cut clips for: {', '.join(missing)}")


if __name__ == "__main__":
    main()
