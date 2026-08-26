#!/usr/bin/env python3
"""Render a resolved stock-footage storyboard into a film.

    python3 render.py storyboard.json --sheet          # LOOK AT THIS FIRST
    python3 render.py storyboard.json -o film.mp4
    python3 render.py storyboard.json --preview -j 8
    python3 render.py storyboard.json --frame 42.0 -o f.png

Every shot is cut, graded and moved into a **normalised segment** first, and
the segments are concatenated afterwards. That is more files and more passes
than building one enormous `filter_complex`, and it is worth it:

* Forty clips from forty videographers arrive at forty different resolutions,
  frame rates, pixel formats and aspect ratios, some with an audio track and
  some without. The concat demuxer will happily join them and produce a file
  that plays for four seconds and then falls apart. Normalising first is the
  only reliable fix, and it has to normalise *everything* — fps, SAR, pix_fmt
  and the audio's presence — not just the resolution.
* A forty-input filter graph fails as one unit. Forty small jobs fail
  individually, name the shot that broke, and re-run in parallel.

Text is drawn with Pillow and composited with `overlay`, never with `drawtext`.
`drawtext` needs ffmpeg to have been built against libfreetype, and the ffmpeg
this was developed against was not — the filter simply does not exist, and the
failure arrives as `Unknown filter` in the middle of a long render.
"""

import argparse
import concurrent.futures as futures
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("stock/render: Pillow is required", file=sys.stderr)
    raise SystemExit(1)

HERE = os.path.dirname(os.path.abspath(__file__))

#: The first font on this list that exists is used. A film whose captions are a
#: row of empty boxes is worse than one with no captions, so the chain ends in
#: a guaranteed-present face rather than in an exception.
FONT_STACK = [
    # Bebas Neue is the face ColdFusion uses for display type -- confirmed from
    # the CSS its own site loads, not inferred from looking at frames. It is
    # open-licence, so it is preferred when installed rather than bundled;
    # everything below is a fallback and the film still renders without it.
    "/Library/Fonts/BebasNeue-Regular.ttf",
    os.path.expanduser("~/Library/Fonts/BebasNeue-Regular.ttf"),
    "/usr/share/fonts/truetype/bebasneue/BebasNeue-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

#: How far a push-in travels over the whole shot, as a fraction. 6% is about
#: the largest move that still reads as "the camera leaned in" rather than as
#: "the picture is being resized", and on footage that is already moving it is
#: plenty.
PUSH = 0.06

#: Overscan for a drift. The picture is scaled this much larger than the frame
#: so there is somewhere to travel to.
DRIFT_OVERSCAN = 1.10


def log(msg):
    print("stock/render: %s" % msg, file=sys.stderr, flush=True)


def die(msg):
    log(msg)
    raise SystemExit(1)


def font(size):
    for p in FONT_STACK:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def run(cmd, what):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        tail = p.stderr.decode("utf-8", "replace").strip().splitlines()[-14:]
        raise RuntimeError("%s failed:\n  %s\n  %s"
                           % (what, " ".join(cmd[:9]) + " …",
                              "\n  ".join(tail)))
    return p.stdout


def probe(path):
    try:
        out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height,r_frame_rate",
                   "-show_entries", "format=duration",
                   "-of", "json", path], "ffprobe")
        d = json.loads(out)
        st = (d.get("streams") or [{}])[0]
        num, _, den = (st.get("r_frame_rate") or "30/1").partition("/")
        fps = float(num) / float(den or 1)
        return {"width": int(st.get("width") or 0),
                "height": int(st.get("height") or 0),
                "fps": fps,
                "duration": float((d.get("format") or {}).get("duration") or 0)}
    except (RuntimeError, ValueError, ZeroDivisionError):
        return None


#: How far auto-exposure is allowed to push a clip, and how much of the
#: computed correction is actually applied.
#:
#: Full correction is wrong, and it is wrong in a way that looks like a bug
#: report: dragging every clip to one target turns a deliberately dark
#: interior into flat grey and a bright exterior into mush, which is the "the
#: film went grey" note that every style in this plugin has had to answer at
#: least once. The job here is to *narrow the spread* between forty exposures,
#: not to erase it — a night shot should still read as night once it sits next
#: to a daylight shot, just not as a black rectangle.
GAMMA_MIN, GAMMA_MAX = 0.78, 1.30
EXPOSURE_STRENGTH = 0.5

YAVG_RE = __import__("re").compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")


def mean_luma(path, ss, dur):
    """The average brightness of the seconds this shot actually uses, 0..1.

    Forty clips shot by forty strangers arrive at forty exposures. A single
    grade applied blind to all of them is the defect that shows up as "half
    the film is black and half is blown out" — and it is invisible in any one
    frame, which is why it survives a spot check and dies on a contact sheet.

    Sampled at 3 fps over the used range rather than decoded in full: this
    runs once per shot and would otherwise dominate the render.
    """
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "info", "-ss", "%.3f" % max(0.0, ss),
             "-t", "%.3f" % max(0.3, min(dur, 6.0)), "-i", path,
             "-vf", "fps=3,scale=192:-2,signalstats,"
                    "metadata=print:key=lavfi.signalstats.YAVG",
             "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        vals = [float(m) for m in YAVG_RE.findall(
            out.stderr.decode("utf-8", "replace"))]
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None
    if not vals:
        return None
    vals.sort()
    # The median, not the mean: a single blown-out frame or a cut to black
    # inside the sampled range would otherwise drag the whole correction.
    return vals[len(vals) // 2] / 255.0


def exposure_filter(measured, target):
    """A gamma that moves `measured` toward `target`, clamped.

    Gamma rather than brightness because brightness is an offset — it lifts
    the blacks *and* the highlights together, so a dark clip corrected that way
    goes milky instead of exposed. Gamma leaves 0 and 1 pinned and moves the
    midtones, which is what an exposure difference actually is.
    """
    if not measured or measured <= 0.01 or measured >= 0.99:
        return None
    g = math.log(measured) / math.log(target)
    g = 1.0 + (g - 1.0) * EXPOSURE_STRENGTH
    g = max(GAMMA_MIN, min(GAMMA_MAX, g))
    if abs(g - 1.0) < 0.04:
        return None
    return "eq=gamma=%.4f" % g


# ------------------------------------------------------------------- plates --


def text_plate(W, H, spec, path):
    """Draw one transparent overlay and save it.

    Kept to two kinds deliberately. A stock film's picture is doing the work;
    every word laid over it is a word competing with the photograph, and a
    style that grows a seventh graphic stops looking like the thing it is.
    """
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    kind = spec.get("kind")

    if kind == "keyword":
        # A hard chip in the lower left. Full-strength white on a solid bar,
        # because a caption that inherits the grade is a caption that
        # disappears in the shot that needed it most.
        text = str(spec.get("text") or "").upper()
        f = font(max(28, int(H * 0.052)))
        box = d.textbbox((0, 0), text, font=f)
        tw, th = box[2] - box[0], box[3] - box[1]
        padx, pady = int(H * 0.026), int(H * 0.020)
        x0, y0 = int(W * 0.055), int(H * 0.80)
        d.rectangle([x0, y0, x0 + tw + padx * 2, y0 + th + pady * 2],
                    fill=(228, 30, 42, 235))
        d.text((x0 + padx - box[0], y0 + pady - box[1]), text,
               font=f, fill=(255, 255, 255, 255))

    elif kind == "title":
        title = str(spec.get("text") or "")
        sub = str(spec.get("sub") or "")
        # A scrim, so the title survives whatever the first clip happens to be.
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(scrim).rectangle([0, 0, W, H], fill=(6, 8, 12, 120))
        img = Image.alpha_composite(img, scrim)
        d = ImageDraw.Draw(img)

        f = font(max(52, int(H * 0.115)))
        box = d.textbbox((0, 0), title.upper(), font=f)
        tw, th = box[2] - box[0], box[3] - box[1]
        x = (W - tw) // 2 - box[0]
        y = (H - th) // 2 - box[1] - int(H * 0.03)
        d.text((x, y), title.upper(), font=f, fill=(255, 255, 255, 255))

        # The rule sits below the text's *ink*, not below its layout box. A
        # bounding box includes the font's descender space whether or not the
        # word has a descender in it, so measuring the box put the rule
        # through the middle of "NINETY SECONDS".
        ink_bottom = y + box[3]
        rule_y = ink_bottom + int(H * 0.042)
        d.rectangle([(W - tw) // 2, rule_y,
                     (W - tw) // 2 + tw, rule_y + max(3, int(H * 0.006))],
                    fill=(228, 30, 42, 255))
        if sub:
            fs = font(max(20, int(H * 0.030)))
            b2 = d.textbbox((0, 0), sub.upper(), font=fs)
            d.text(((W - (b2[2] - b2[0])) // 2 - b2[0],
                    rule_y + int(H * 0.028)), sub.upper(), font=fs,
                   fill=(205, 210, 220, 235))

    elif kind == "credits":
        scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(scrim).rectangle([0, 0, W, H], fill=(6, 8, 12, 190))
        img = Image.alpha_composite(img, scrim)
        d = ImageDraw.Draw(img)
        lines = list(spec.get("lines") or [])
        fh = font(max(18, int(H * 0.026)))
        ft = font(max(24, int(H * 0.036)))
        y = int(H * 0.20)
        head = str(spec.get("head") or "")
        b = d.textbbox((0, 0), head, font=ft)
        d.text(((W - (b[2] - b[0])) // 2 - b[0], y), head, font=ft,
               fill=(255, 255, 255, 255))
        y += int(H * 0.075)
        for ln in lines[:14]:
            b = d.textbbox((0, 0), ln, font=fh)
            d.text(((W - (b[2] - b[0])) // 2 - b[0], y), ln, font=fh,
                   fill=(198, 204, 214, 230))
            y += int(H * 0.038)

    elif kind == "placeholder":
        # Rule 2 of the style contract, made visible. A beat with no footage
        # gets a labelled slate saying so -- never the nearest lookalike.
        d.rectangle([0, 0, W, H], fill=(18, 18, 22, 255))
        f = font(max(24, int(H * 0.038)))
        fs = font(max(16, int(H * 0.024)))
        head = "NO FOOTAGE"
        b = d.textbbox((0, 0), head, font=f)
        d.text(((W - (b[2] - b[0])) // 2 - b[0], int(H * 0.42)), head,
               font=f, fill=(228, 30, 42, 255))
        sub = str(spec.get("text") or "")[:70]
        b = d.textbbox((0, 0), sub, font=fs)
        d.text(((W - (b[2] - b[0])) // 2 - b[0], int(H * 0.52)), sub,
               font=fs, fill=(190, 190, 200, 255))

    img.save(path)
    return path


# -------------------------------------------------------------------- shots --


def move_filter(shot, W, H):
    """The camera move, as a filter chain fragment.

    `scale` with `eval=frame` is used rather than `zoompan`. They look
    equivalent in a description and are not: `zoompan` computes an integer
    crop window per frame, so a slow push advances in whole pixels and judders
    on any hard edge, while `scale` re-samples and moves the picture
    sub-pixel. On footage that is already in motion the difference is the
    whole quality of the shot.
    """
    move = shot.get("move") or "hold"
    amt = float(shot.get("move_amount", 1.0))
    dur = max(0.2, float(shot.get("dur") or 1.0))

    if amt <= 0.0 or move == "hold":
        return ("scale=%d:%d:force_original_aspect_ratio=increase,"
                "crop=%d:%d" % (W, H, W, H))

    if move == "push-in":
        z = PUSH * amt
        # Grow from the covering size to (1+z) of it, centred.
        return (
            "scale=w='max(%d,ceil(%d*(1+%.5f*t/%.3f)/2)*2)':"
            "h='max(%d,ceil(%d*(1+%.5f*t/%.3f)/2)*2)':eval=frame,"
            "crop=%d:%d:'(iw-ow)/2':'(ih-oh)/2'"
            % (W, W, z, dur, H, H, z, dur, W, H)
        )

    # A drift: overscan, then travel across the slack. The picture is being
    # re-sampled every frame anyway, so integer crop steps are invisible here
    # in a way they would not be over a still.
    ow, oh = int(W * DRIFT_OVERSCAN) // 2 * 2, int(H * DRIFT_OVERSCAN) // 2 * 2
    slack_x, slack_y = ow - W, oh - H
    travel = min(1.0, amt)
    if move == "drift-left":
        x, y = "'(iw-ow)*(1-%.4f*t/%.3f)'" % (travel, dur), "'(ih-oh)/2'"
    elif move == "drift-right":
        x, y = "'(iw-ow)*(%.4f*t/%.3f)'" % (travel, dur), "'(ih-oh)/2'"
    elif move == "drift-up":
        x, y = "'(iw-ow)/2'", "'(ih-oh)*(1-%.4f*t/%.3f)'" % (travel, dur)
    else:
        x, y = "'(iw-ow)/2'", "'(ih-oh)*(%.4f*t/%.3f)'" % (travel, dur)
    if slack_x <= 0 or slack_y <= 0:
        return ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d"
                % (W, H, W, H))
    return ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
            "crop=%d:%d:%s:%s" % (ow, oh, ow, oh, W, H, x, y))


def in_point(shot, clip, need):
    """Where in the source clip this shot starts.

    Never at zero when there is room. Stock clips very often open on a fade, a
    slate or the first frame of a camera move that has not settled, and the
    last second is where a watermark or an end-fade lives. Taking from just
    inside both ends is free and removes most of both problems.
    """
    have = float((clip or {}).get("duration") or 0.0)
    if have <= need + 0.2:
        return 0.0
    head = min(0.6, (have - need) * 0.25)
    room = have - need - head
    if room <= 0:
        return round(max(0.0, head), 3)
    # Deterministic, but different per shot, so two shots that reuse one clip
    # do not show the same seconds of it.
    idx = int(str(shot.get("id") or "s0")[1:] or 0)
    return round(head + (room * ((idx * 0.37) % 1.0)), 3)


def build_segment(job):
    """Cut, grade, move and normalise one shot. Returns (id, path, error)."""
    (shot, sb, workdir, W, H, fps, crf, preset, no_auto_exposure) = job
    sid = shot["id"]
    out = os.path.join(workdir, "seg-%s.mp4" % sid)
    dur = max(0.10, float(shot.get("dur") or 1.0))
    clip = shot.get("clip")
    plate = shot.get("_plate")

    grade = sb.get("grade_filter") or ""
    speed = float(shot.get("speed") or 1.0)
    if not (0.25 <= speed <= 4.0):
        speed = 1.0

    try:
        if not clip or not clip.get("file"):
            # A placeholder is a real segment of the right length so the film's
            # clock never moves, and it is labelled so nobody mistakes it for a
            # deliberate black frame.
            png = os.path.join(workdir, "ph-%s.png" % sid)
            text_plate(W, H, {"kind": "placeholder",
                              "text": shot.get("subject") or shot.get("query")
                              or sid}, png)
            cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", "%.3f" % dur,
                   "-i", png, "-an", "-vf",
                   "fps=%d,format=yuv420p,setsar=1" % fps,
                   "-c:v", "libx264", "-preset", preset, "-crf", str(crf), out]
            run(cmd, "placeholder %s" % sid)
            return sid, out, None

        src = clip["file"]
        if not os.path.isabs(src):
            src = os.path.join(sb["_base"], src)
        if not os.path.isfile(src):
            return sid, None, "clip missing on disk: %s" % src

        info = probe(src) or {}
        have = float(info.get("duration") or clip.get("duration") or 0.0)
        need = dur * speed
        ss = in_point(shot, {"duration": have}, need)

        chain = []
        if speed != 1.0:
            chain.append("setpts=%.6f*PTS" % (1.0 / speed))
        chain.append("fps=%d" % fps)
        chain.append(move_filter(shot, W, H))
        # Exposure-match *before* the grade, never after. The grade is a look
        # and assumes a normally-exposed picture; correcting afterwards fights
        # the curve that was just applied.
        if not no_auto_exposure:
            m = mean_luma(src, ss, dur)
            ex = exposure_filter(m, float(sb.get("grade_target") or 0.47))
            if ex:
                chain.append(ex)
                shot["_luma"] = round(m, 4)
        if grade:
            chain.append(grade)
        chain.append("setsar=1")
        chain.append("format=yuv420p")

        cmd = ["ffmpeg", "-y", "-v", "error"]
        if have and have < need + 0.05:
            # Short clip: loop it rather than freeze on the last frame, which
            # is what a plain -t does and which reads as the video hanging.
            cmd += ["-stream_loop", "-1"]
        else:
            cmd += ["-ss", "%.3f" % ss]
        cmd += ["-i", src, "-t", "%.3f" % dur, "-an",
                "-vf", ",".join(chain),
                "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-r", str(fps), out]
        run(cmd, "segment %s" % sid)

        if plate:
            over = os.path.join(workdir, "seg-%s-t.mp4" % sid)
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", out, "-i", plate,
                   "-filter_complex",
                   "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p,setsar=1[v]",
                   "-map", "[v]", "-an",
                   "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                   "-r", str(fps), over]
            run(cmd, "overlay %s" % sid)
            os.replace(over, out)

        return sid, out, None
    except RuntimeError as e:
        return sid, None, str(e)


# -------------------------------------------------------------------- audio --


def build_audio(sb, workdir, duration, bed_path, no_music):
    """Narration laid on the film's clock, with the bed ducked underneath.

    Returns a path, or None when there is nothing to lay — a silent film is a
    legitimate intermediate (the picture is checkable without the voice), but
    it is reported rather than produced quietly.
    """
    base = sb["_base"]
    lines = []
    for n in sb.get("narration") or []:
        a = n.get("audio")
        if not a:
            continue
        p = a if os.path.isabs(a) else os.path.join(base, a)
        if os.path.isfile(p):
            lines.append((float(n.get("at") or 0.0), p))

    voice = None
    if lines:
        voice = os.path.join(workdir, "voice.wav")
        inputs, filt, labels = [], [], []
        for i, (at, p) in enumerate(lines):
            inputs += ["-i", p]
            filt.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,"
                        "adelay=%d|%d[a%d]" % (i, int(at * 1000), int(at * 1000), i))
            labels.append("[a%d]" % i)
        filt.append("%samix=inputs=%d:duration=longest:normalize=0,"
                    "apad,atrim=0:%.3f[out]"
                    % ("".join(labels), len(labels), duration))
        run(["ffmpeg", "-y", "-v", "error"] + inputs +
            ["-filter_complex", ";".join(filt), "-map", "[out]",
             "-c:a", "pcm_s16le", voice], "narration")

    music = None
    if not no_music and bed_path and os.path.isfile(bed_path):
        music = bed_path

    if not voice and not music:
        return None

    out = os.path.join(workdir, "mix.wav")
    if voice and music:
        # Duck by envelope, not by a fixed level -- the sound designer's first
        # non-negotiable. sidechaincompress keys the bed off the voice, so a
        # pause opens up and a sentence pushes the music down.
        run(["ffmpeg", "-y", "-v", "error", "-i", music, "-i", voice,
             "-filter_complex",
             "[0:a]aresample=48000,aformat=channel_layouts=stereo,"
             "atrim=0:%.3f,apad,atrim=0:%.3f,volume=0.62[bed];"
             "[1:a]aresample=48000,aformat=channel_layouts=stereo[vo];"
             "[vo]asplit=2[vo1][key];"
             "[bed][key]sidechaincompress=threshold=0.03:ratio=12:attack=8:"
             "release=420:makeup=1[duck];"
             "[duck][vo1]amix=inputs=2:duration=first:normalize=0,"
             "alimiter=limit=0.92,loudnorm=I=-14:TP=-1.0:LRA=11,"
             "aresample=48000[out]"
             % (duration, duration),
             "-map", "[out]", "-c:a", "pcm_s16le", out], "mix")
    elif voice:
        run(["ffmpeg", "-y", "-v", "error", "-i", voice, "-af",
             "alimiter=limit=0.92,loudnorm=I=-14:TP=-1.0:LRA=11,"
             "aresample=48000",
             "-c:a", "pcm_s16le", out], "voice-only mix")
    else:
        run(["ffmpeg", "-y", "-v", "error", "-i", music, "-af",
             "atrim=0:%.3f,apad,atrim=0:%.3f,volume=0.8,"
             "loudnorm=I=-16:TP=-1.0:LRA=11,aresample=48000"
             % (duration, duration),
             "-c:a", "pcm_s16le", out], "music-only mix")
    return out


# ------------------------------------------------------------------- sheet --


def contact_sheet(sb, segs, out, W, H, cols=6):
    """One frame from every shot, in order, labelled.

    Read this before committing to a render. The two failures that matter most
    in this style are invisible in a single frame and obvious across a grid:
    the same clip answering two different beats, and a run of shots that are
    all the same colour because the grade has flattened them.
    """
    tw = 320
    th = int(tw * H / float(W))
    rows = (len(segs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 26)), (12, 12, 16))
    d = ImageDraw.Draw(sheet)
    f = font(15)
    tmp = tempfile.mkdtemp(prefix="stock-sheet-")
    try:
        for i, (sid, path) in enumerate(segs):
            x, y = (i % cols) * tw, (i // cols) * (th + 26)
            png = os.path.join(tmp, "%s.png" % sid)
            try:
                run(["ffmpeg", "-y", "-v", "error", "-ss", "0.35", "-i", path,
                     "-frames:v", "1", "-vf", "scale=%d:%d" % (tw, th), png],
                    "sheet frame")
                sheet.paste(Image.open(png).convert("RGB"), (x, y))
            except (RuntimeError, OSError):
                d.rectangle([x, y, x + tw, y + th], fill=(60, 20, 20))
            shot = next((s for s in sb["shots"] if s["id"] == sid), {})
            label = "%s %s" % (sid, (shot.get("query") or "—")[:30])
            d.text((x + 5, y + th + 5), label, font=f, fill=(210, 210, 220))
        sheet.save(out, quality=88)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


# -------------------------------------------------------------------- main --


def main():
    ap = argparse.ArgumentParser(description="Render a stock-footage film.")
    ap.add_argument("storyboard")
    ap.add_argument("-o", "--out")
    ap.add_argument("--sheet", nargs="?", const=True,
                    help="write a contact sheet instead of a film")
    ap.add_argument("--frame", type=float, help="write one frame at this time")
    ap.add_argument("--preview", action="store_true", help="half resolution")
    ap.add_argument("-j", "--jobs", type=int, default=0)
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--no-auto-exposure", action="store_true",
                    help="skip per-clip exposure matching (faster; uneven)")
    ap.add_argument("--bed", help="use this music bed instead of synthesising")
    ap.add_argument("--keep", action="store_true", help="keep the work folder")
    a = ap.parse_args()

    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            die("%s is not on PATH" % exe)

    try:
        with open(a.storyboard, encoding="utf-8") as fh:
            sb = json.load(fh)
    except (OSError, ValueError) as e:
        die("cannot read %s: %s" % (a.storyboard, e))

    sb["_base"] = os.path.dirname(os.path.abspath(a.storyboard))
    shots = sb.get("shots") or []
    if not shots:
        die("storyboard has no shots")

    W, H = int(sb.get("width") or 1920), int(sb.get("height") or 1080)
    if a.preview:
        W, H = W // 2 // 2 * 2, H // 2 // 2 * 2
    fps = int(sb.get("fps") or 30)
    duration = float(sb.get("duration") or sum(s.get("dur") or 0 for s in shots))

    missing = [s["id"] for s in shots if not (s.get("clip") or {}).get("file")]
    if missing:
        log("%d shot(s) have no footage and will render as labelled "
            "placeholders: %s" % (len(missing), ", ".join(missing[:10])))
        log("run fetch.py first, or rewrite those beats — this style does not "
            "substitute the nearest available clip")

    workdir = tempfile.mkdtemp(prefix="stock-render-")
    try:
        # ---- plates. Built before the segment pass so the overlay is a plain
        # file input rather than a second graph inside every job.
        title_shots = [s for s in shots if s["at"] < 0.01]
        for s in shots:
            spec = None
            if s.get("keyword"):
                spec = {"kind": "keyword", "text": s["keyword"]}
            if s in title_shots and sb.get("title"):
                spec = {"kind": "title", "text": sb["title"],
                        "sub": (sb.get("acts") or [{}])[0].get("title") or ""}
            if spec:
                s["_plate"] = text_plate(
                    W, H, spec, os.path.join(workdir, "pl-%s.png" % s["id"]))

        jobs = [(s, sb, workdir, W, H, fps,
                 26 if a.preview else 20,
                 "veryfast" if a.preview else "medium",
                 a.no_auto_exposure) for s in shots]

        n = a.jobs or min(8, (os.cpu_count() or 4))
        log("cutting %d shots at %dx%d, %d at a time" % (len(shots), W, H, n))
        done, errs = {}, []
        with futures.ThreadPoolExecutor(max_workers=n) as pool:
            for sid, path, err in pool.map(build_segment, jobs):
                if err:
                    errs.append("%s: %s" % (sid, err))
                else:
                    done[sid] = path
        for e in errs:
            log("ERROR %s" % e)
        if not done:
            die("no segment rendered")

        segs = [(s["id"], done[s["id"]]) for s in shots if s["id"] in done]
        log("%d/%d segments" % (len(segs), len(shots)))

        if a.sheet:
            out = (a.sheet if isinstance(a.sheet, str)
                   else os.path.splitext(a.out or a.storyboard)[0] + "_sheet.jpg")
            contact_sheet(sb, segs, out, W, H)
            log("wrote %s — look at it before rendering" % out)
            return

        # ---- concat. The demuxer, not the filter: every segment was written
        # by the same encoder with the same parameters, so this is a stream
        # copy and costs nothing.
        listf = os.path.join(workdir, "segments.txt")
        with open(listf, "w", encoding="utf-8") as fh:
            for _, p in segs:
                fh.write("file '%s'\n" % p.replace("'", "'\\''"))
        silent = os.path.join(workdir, "picture.mp4")
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", listf, "-c", "copy", silent], "concat")

        picture = probe(silent) or {}
        log("picture: %.2fs (storyboard says %.2fs)"
            % (picture.get("duration") or 0, duration))

        if a.frame is not None:
            out = a.out or (os.path.splitext(a.storyboard)[0] + "_frame.png")
            run(["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % a.frame,
                 "-i", silent, "-frames:v", "1", out], "frame")
            log("wrote %s" % out)
            return

        # ---- score, then mix.
        bed = a.bed
        if not bed and not a.no_music:
            bed = os.path.join(workdir, "bed.wav")
            mood = (sb.get("music") or {}).get("mood") or "reflective"
            try:
                run([sys.executable, os.path.join(HERE, "score.py"),
                     "--mood", mood, "--duration",
                     "%.3f" % (picture.get("duration") or duration),
                     "--seed", str(int(sb.get("seed") or 7)), "-o", bed],
                    "score")
            except RuntimeError as e:
                log("could not synthesise a bed (%s); rendering without music" % e)
                bed = None

        audio = build_audio(sb, workdir, picture.get("duration") or duration,
                            bed, a.no_music)

        out = a.out or os.path.join(sb["_base"],
                                    (sb.get("title") or "film")
                                    .lower().replace(" ", "-") + ".mp4")
        if audio:
            run(["ffmpeg", "-y", "-v", "error", "-i", silent, "-i", audio,
                 "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                 "-movflags", "+faststart", out], "mux")
        else:
            log("no narration audio and no bed — rendering a silent picture")
            shutil.copy(silent, out)

        # ---- the sidecar the sound designer and subtitler read. Written from
        # the *rendered* segments, not from the storyboard, so it describes the
        # cut that exists rather than the one that was planned.
        t, timeline = 0.0, []
        for sid, p in segs:
            d = (probe(p) or {}).get("duration") or 0.0
            shot = next((s for s in shots if s["id"] == sid), {})
            timeline.append({"shot": sid, "beat": shot.get("beat"),
                             "at": round(t, 3), "dur": round(d, 3),
                             "query": shot.get("query"),
                             "clip": (shot.get("clip") or {}).get("id")})
            t += d
        side = os.path.splitext(out)[0] + ".timeline.json"
        with open(side, "w", encoding="utf-8") as fh:
            json.dump({"film": os.path.basename(out), "duration": round(t, 3),
                       "grade": sb.get("grade"),
                       "music": sb.get("music"), "shots": timeline,
                       "narration": sb.get("narration"),
                       "credits": sb.get("credits")}, fh, indent=1,
                      ensure_ascii=False)

        info = probe(out) or {}
        log("wrote %s — %.1fs, %dx%d, %.1f MB"
            % (out, info.get("duration") or 0, info.get("width") or 0,
               info.get("height") or 0, os.path.getsize(out) / 1048576.0))
        log("wrote %s" % os.path.basename(side))
        if errs:
            raise SystemExit(1)
    finally:
        if a.keep:
            log("work folder kept at %s" % workdir)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
