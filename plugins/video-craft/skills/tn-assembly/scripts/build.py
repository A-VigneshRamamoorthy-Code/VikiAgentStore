"""Assemble a planned episode at full resolution.

  intro -> [clip + lower-third] x N -> outro

Each clip carries a lower-third naming what is being argued about, so a viewer
who joins mid-scroll knows the subject without waiting for context. Every
segment is normalised to the same resolution, frame rate, sample rate and
channel count *before* concatenation, because ffmpeg's concat demuxer copies
streams without re-encoding and silently produces a broken file if they differ.
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Project, publish_scripts, say  # noqa: E402

publish_scripts()  # the sibling skill supplies CoreText and the stings
import ct_text as ct  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

W, H, FPS = 1920, 1080, 30
CRIMSON = (214, 34, 54)
GOLD = (245, 194, 78)
INK = (10, 14, 26)
PAPER = (247, 245, 240)


def configure(pr):
    """Adopt the project's frame geometry and palette."""
    global W, H, FPS, CRIMSON, GOLD, INK, PAPER
    W = pr.get("video", "width", default=W)
    H = pr.get("video", "height", default=H)
    FPS = pr.get("video", "fps", default=FPS)
    CRIMSON = tuple(pr.get("brand", "crimson", default=list(CRIMSON)))
    GOLD = tuple(pr.get("brand", "gold", default=list(GOLD)))
    INK = tuple(pr.get("brand", "ink", default=list(INK)))
    PAPER = tuple(pr.get("brand", "paper", default=list(PAPER)))


def run(cmd):
    subprocess.run(cmd, check=True)


def lower_third(title_ta, sub_ta, out_png):
    """Translucent lower-third band with Tamil type and a crimson spine."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    title = ct.render_text(title_ta, ct.TAMIL_BOLD, 58, PAPER + (255,))
    sub = ct.render_text(sub_ta, ct.TAMIL_REG, 36, GOLD + (255,)) if sub_ta else None

    pad = 38
    bw = max(title.width, sub.width if sub else 0) + pad * 2 + 30
    bh = 146 if sub else 104
    x0, y0 = 88, H - bh - 108

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [x0 + 6, y0 + 10, x0 + bw + 6, y0 + bh + 10], radius=16, fill=(0, 0, 0, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    img = Image.alpha_composite(img, shadow)

    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=14, fill=INK + (234,))
    d.rounded_rectangle([x0, y0, x0 + 14, y0 + bh], radius=7, fill=CRIMSON)

    tx = x0 + pad + 16
    ty = y0 + (44 if sub else bh / 2)
    img.paste(title, (tx, int(ty - title.height / 2)), title)
    if sub:
        img.paste(sub, (tx, int(y0 + 102 - sub.height / 2)), sub)

    img.save(out_png)
    return out_png


def build_clip(pr, outdir, idx, spec):
    """Render one body clip from the accurate, boundary-snapped source cut.

    Sections are produced ahead of time by cut_clips.py, which uses
    --force-keyframes-at-cuts so audio and video start on the same frame.
    Durations therefore vary per clip and must be read from the plan rather
    than assumed.
    """
    raw = pr.p(spec["file"]) if spec.get("file") else None
    if not (raw and os.path.exists(raw) and os.path.getsize(raw) > 300_000):
        raise SystemExit(f"missing cut for clip {idx}; run cut.py first")

    png = os.path.join(outdir, f"lt_{idx:02d}.png")
    lower_third(spec.get("label", ""), spec.get("gloss", ""), png)

    dst = os.path.join(outdir, f"seg_{idx:02d}.mp4")
    dur = float(spec["duration"])
    lt_out = min(7.5, dur - 1.0)

    vf = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={FPS},setsar=1[base];"
        f"[1:v]format=rgba,fade=t=in:st=0.5:d=0.45:alpha=1,"
        f"fade=t=out:st={lt_out:.2f}:d=0.5:alpha=1[lt];"
        f"[base][lt]overlay=x='if(lt(t,0.95),-60+60*min(1,(t-0.5)/0.45),0)':y=0:"
        f"enable='between(t,0.5,{lt_out + 0.6:.2f})'[v1];"
        f"[v1]fade=t=in:st=0:d=0.3,fade=t=out:st={dur - 0.4:.2f}:d=0.4,"
        f"format=yuv420p[v]"
    )
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
         "-loop", "1", "-framerate", str(FPS), "-i", png,
         "-filter_complex", vf, "-map", "[v]", "-map", "0:a:0",
         "-af", f"afade=t=in:st=0:d=0.25,afade=t=out:st={dur - 0.4:.2f}:d=0.4",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-s", f"{W}x{H}",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-t", f"{dur:.2f}", dst])
    print(f"  [{idx}] built", flush=True)
    return dst


def normalise_sting(src, dst):
    """Conform a sting to the body's exact stream parameters."""
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
         "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-s", f"{W}x{H}",
         "-vf", "setsar=1",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", dst])
    return dst


def concat(parts, dst):
    lst = os.path.splitext(dst)[0] + "_concat.txt"
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.abspath(p)}'\n")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", dst])
    return dst


def main():
    ap = argparse.ArgumentParser(description="Assemble planned episodes")
    ap.add_argument("project")
    ap.add_argument("--only", default=None, help="episode id, e.g. ep02")
    a = ap.parse_args()

    pr = Project(a.project)
    configure(pr)
    plan = pr.load("plan")
    if not plan:
        raise SystemExit("no meta/plan.json -- run plan.py first")

    assets = pr.p("assets")
    intro_src = os.path.join(assets, "intro.mp4")
    outro_src = os.path.join(assets, "outro.mp4")
    for p in (intro_src, outro_src):
        if not os.path.exists(p):
            raise SystemExit(
                f"missing {p}. Render the channel stings first:\n"
                f"  python3 ../../youtube-publish/scripts/stings.py {pr.root}")

    for ep in plan["episodes"]:
        if a.only and ep["id"] != a.only:
            continue
        work = pr.p("work", ep["id"])
        outdir = pr.p("out", ep["id"])
        os.makedirs(work, exist_ok=True)
        os.makedirs(outdir, exist_ok=True)

        say(f"{ep['id']}: {len(ep['clips'])} clips")
        segs = [build_clip(pr, work, i + 1, c)
                for i, c in enumerate(ep["clips"])]

        intro = normalise_sting(intro_src, os.path.join(work, "intro_n.mp4"))
        outro = normalise_sting(outro_src, os.path.join(work, "outro_n.mp4"))

        stitched = os.path.join(work, "_stitched.mp4")
        concat([intro] + segs + [outro], stitched)

        final = os.path.join(outdir, "episode_1080p.mp4")
        say("  loudness pass")
        # loudnorm upsamples internally (96 kHz here), which YouTube would
        # then have to resample; force it back to 48 kHz in the same chain.
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", stitched,
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-ar", "48000", final])
        ep["render"] = os.path.relpath(final, pr.root)
        say(f"  -> {final}")

    pr.save("plan", plan)


if __name__ == "__main__":
    main()
