"""ffmpeg/ffprobe discovery + command builders."""
from __future__ import annotations
import json
import os
import shutil
import subprocess


def find_tools(ffmpeg_opt=None):
    cands = []
    if ffmpeg_opt:
        cands.append(ffmpeg_opt)
    if os.environ.get("FFMPEG"):
        cands.append(os.environ["FFMPEG"])
    w = shutil.which("ffmpeg")
    if w:
        cands.append(w)
    cands += ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]
    ffmpeg = next((c for c in cands if c and os.path.exists(os.path.expanduser(c))), None) or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found. Install it (see reference/cross-platform-setup.md) "
            "or pass --ffmpeg /path/to/ffmpeg.")
    ffmpeg = os.path.expanduser(ffmpeg)
    base = os.path.dirname(ffmpeg)
    probe = os.path.join(base, "ffprobe")
    if not os.path.exists(probe):
        probe = shutil.which("ffprobe") or probe
    return ffmpeg, probe


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(ffprobe, path):
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {r.stderr[:400]}")
    data = json.loads(r.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if not v:
        raise RuntimeError("No video stream found in input.")
    num, den = (v.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    dur = float(data["format"].get("duration") or v.get("duration") or 0)
    return {
        "duration": dur,
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": fps,
        "has_audio": a is not None,
    }


def scale_pad(fit, W, H, bg="0x101326"):
    fit = (fit or "height").lower()
    if fit == "contain":
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg}"
    if fit == "cover":
        return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    # 'height'/'width' => fill, top-aligned (preserves top-of-screen action)
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:(in_w-{W})/2:0"


def base_filter(segments, fit, W, H, fps, intro, outro, bg):
    parts = []
    sp = scale_pad(fit, W, H, bg)
    for i, (s, e) in enumerate(segments):
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,{sp}[v{i}]")
    cat_in = "".join(f"[v{i}]" for i in range(len(segments)))
    g = ";".join(parts) + f";{cat_in}concat=n={len(segments)}:v=1:a=0[cat]"
    tail = "[cat]"
    if intro > 0 or outro > 0:
        g += f";[cat]tpad=start_duration={intro:.3f}:stop_duration={outro:.3f}:start_mode=clone:stop_mode=clone[pad]"
        tail = "[pad]"
    g += f";{tail}fps={fps},format=yuv420p[outv]"
    return g
